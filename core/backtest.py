"""
Simple event-based backtester for APA-style signals.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from .signals import generate_signals, APASignal
from .structure import find_swings, classify_structure, detect_liquidity_sweeps


@dataclass
class Trade:
    direction: str
    entry_time: pd.Timestamp
    entry_price: float
    stop_price: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl_r: Optional[float] = None          # in R multiples
    outcome: Optional[str] = None          # "win" | "loss" | "open"
    reason: str = ""


@dataclass
class BacktestResult:
    trades: List[Trade] = field(default_factory=list)
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_r: float = 0.0
    avg_r: float = 0.0
    max_drawdown_r: float = 0.0
    equity_curve: List[float] = field(default_factory=list)


def run_backtest(
    ltf_df: pd.DataFrame,
    htf_df: Optional[pd.DataFrame] = None,
    min_score: float = 0.55,
    risk_reward: float = 2.0,
    swing_left: int = 3,
    swing_right: int = 3,
    lookforward_bars: int = 40,
) -> BacktestResult:
    """
    Simple sequential backtest.

    Logic:
    - Walk forward bar by bar on LTF
    - Every N bars (or on new structure) generate a signal using data up to current bar
    - If signal appears, enter at next bar open
    - Stop = signal.stop_hint
    - Target = entry ± (risk * risk_reward)
    - Exit on stop or target, whichever comes first within lookforward_bars
    """
    result = BacktestResult()
    equity = 0.0
    peak = 0.0
    max_dd = 0.0

    # We re-evaluate every 8 bars to keep it reasonably fast
    step = 8
    i = 80  # warm-up

    while i < len(ltf_df) - lookforward_bars - 2:
        window_ltf = ltf_df.iloc[: i + 1].copy()

        # HTF window (use data available up to now)
        window_htf = None
        if htf_df is not None:
            # Simple: take all HTF bars whose timestamp <= current LTF time
            current_time = window_ltf.index[-1]
            window_htf = htf_df[htf_df.index <= current_time].copy()

        signals = generate_signals(
            ltf_df=window_ltf,
            htf_df=window_htf,
            min_score=min_score,
            swing_left=swing_left,
            swing_right=swing_right,
        )

        if not signals:
            i += step
            continue

        sig = signals[0]

        # Enter on next bar open
        entry_idx = i + 1
        if entry_idx >= len(ltf_df):
            break

        entry_price = float(ltf_df["open"].iloc[entry_idx])
        entry_time = ltf_df.index[entry_idx]

        # Risk definition
        if sig.direction == "LONG":
            stop = min(sig.stop_hint, entry_price * 0.995)  # safety
            risk = entry_price - stop
            if risk <= 0:
                i += step
                continue
            target = entry_price + risk * risk_reward
        else:
            stop = max(sig.stop_hint, entry_price * 1.005)
            risk = stop - entry_price
            if risk <= 0:
                i += step
                continue
            target = entry_price - risk * risk_reward

        # Simulate forward
        trade = Trade(
            direction=sig.direction,
            entry_time=entry_time,
            entry_price=entry_price,
            stop_price=stop,
            reason=sig.reason,
        )

        exited = False
        for j in range(entry_idx + 1, min(entry_idx + lookforward_bars, len(ltf_df))):
            bar_high = float(ltf_df["high"].iloc[j])
            bar_low = float(ltf_df["low"].iloc[j])
            bar_time = ltf_df.index[j]

            if sig.direction == "LONG":
                if bar_low <= stop:
                    trade.exit_time = bar_time
                    trade.exit_price = stop
                    trade.pnl_r = -1.0
                    trade.outcome = "loss"
                    exited = True
                    break
                if bar_high >= target:
                    trade.exit_time = bar_time
                    trade.exit_price = target
                    trade.pnl_r = risk_reward
                    trade.outcome = "win"
                    exited = True
                    break
            else:  # SHORT
                if bar_high >= stop:
                    trade.exit_time = bar_time
                    trade.exit_price = stop
                    trade.pnl_r = -1.0
                    trade.outcome = "loss"
                    exited = True
                    break
                if bar_low <= target:
                    trade.exit_time = bar_time
                    trade.exit_price = target
                    trade.pnl_r = risk_reward
                    trade.outcome = "win"
                    exited = True
                    break

        if not exited:
            # Time exit at last bar close
            last_idx = min(entry_idx + lookforward_bars - 1, len(ltf_df) - 1)
            trade.exit_time = ltf_df.index[last_idx]
            trade.exit_price = float(ltf_df["close"].iloc[last_idx])
            if sig.direction == "LONG":
                trade.pnl_r = (trade.exit_price - entry_price) / risk
            else:
                trade.pnl_r = (entry_price - trade.exit_price) / risk
            trade.outcome = "time_exit"

        result.trades.append(trade)

        # Update equity stats
        equity += trade.pnl_r
        result.equity_curve.append(equity)
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)

        # Move forward past this trade to avoid overlapping entries
        i = entry_idx + 5

    # Summary stats
    closed = [t for t in result.trades if t.pnl_r is not None]
    result.total_trades = len(closed)
    if result.total_trades == 0:
        return result

    wins = [t for t in closed if t.pnl_r > 0]
    losses = [t for t in closed if t.pnl_r <= 0]
    result.wins = len(wins)
    result.losses = len(losses)
    result.win_rate = result.wins / result.total_trades
    result.total_r = sum(t.pnl_r for t in closed)
    result.avg_r = result.total_r / result.total_trades
    result.max_drawdown_r = max_dd

    gross_profit = sum(t.pnl_r for t in wins) if wins else 0.0
    gross_loss = abs(sum(t.pnl_r for t in losses)) if losses else 0.0
    result.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    return result


def print_backtest_report(result: BacktestResult):
    print("\n" + "=" * 55)
    print("           APA SIGNAL BOT – BACKTEST REPORT")
    print("=" * 55)
    print(f"Total Trades     : {result.total_trades}")
    print(f"Wins / Losses    : {result.wins} / {result.losses}")
    print(f"Win Rate         : {result.win_rate * 100:.1f}%")
    print(f"Profit Factor    : {result.profit_factor:.2f}")
    print(f"Total R          : {result.total_r:+.2f}R")
    print(f"Average R        : {result.avg_r:+.2f}R")
    print(f"Max Drawdown     : {result.max_drawdown_r:.2f}R")
    print("=" * 55)

    if result.trades:
        print("\nLast 8 trades:")
        for t in result.trades[-8:]:
            print(
                f"  {t.direction:5} | Entry {t.entry_price:.2f} → Exit {t.exit_price:.2f} | "
                f"{t.pnl_r:+.2f}R | {t.outcome}"
            )
