"""
Enhanced backtester with realistic metrics and trade validation.
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
    """Represents a single closed trade."""
    direction: str
    entry_time: pd.Timestamp
    entry_price: float
    stop_price: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl_r: Optional[float] = None          # in R multiples (risk units)
    pnl_percent: Optional[float] = None    # % return on entry
    pnl_usd: Optional[float] = None        # absolute P&L
    outcome: Optional[str] = None          # "win" | "loss" | "time_exit"
    reason: str = ""
    bars_held: int = 0
    risk: float = 0.0


@dataclass
class BacktestResult:
    """Complete backtest performance summary."""
    trades: List[Trade] = field(default_factory=list)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    break_even_trades: int = 0
    
    win_rate: float = 0.0                   # % of wins
    profit_factor: float = 0.0              # gross_profit / gross_loss
    
    total_r: float = 0.0                    # total R units
    avg_r: float = 0.0                      # avg R per trade
    expectancy: float = 0.0                 # (win_rate * avg_win) - (loss_rate * avg_loss)
    
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    
    max_drawdown_r: float = 0.0             # peak-to-trough in R
    max_drawdown_pct: float = 0.0           # as percentage
    
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    largest_win_r: float = 0.0
    largest_loss_r: float = 0.0
    
    sharpe_ratio: float = 0.0               # Sharpe ratio (daily returns)
    sortino_ratio: float = 0.0              # Sortino ratio (downside deviation)
    
    avg_bars_held: float = 0.0
    equity_curve: List[float] = field(default_factory=list)
    
    # Meta
    start_date: Optional[pd.Timestamp] = None
    end_date: Optional[pd.Timestamp] = None


def run_backtest(
    ltf_df: pd.DataFrame,
    htf_df: Optional[pd.DataFrame] = None,
    min_score: float = 0.55,
    risk_reward: float = 2.0,
    swing_left: int = 3,
    swing_right: int = 3,
    lookforward_bars: int = 40,
    initial_capital: float = 10000.0,
    risk_per_trade: float = 0.02,  # 2% risk per trade
) -> BacktestResult:
    """
    Enhanced sequential backtest with realistic P&L tracking.
    
    Args:
        ltf_df: Lower timeframe OHLC
        htf_df: Higher timeframe OHLC (optional)
        min_score: Minimum confluence score for entry
        risk_reward: Risk:Reward ratio target
        swing_left/right: Swing detection parameters
        lookforward_bars: Max bars to hold a trade
        initial_capital: Starting account size
        risk_per_trade: % of capital at risk per trade
    
    Returns:
        BacktestResult with full metrics
    """
    result = BacktestResult()
    
    if len(ltf_df) < 100:
        print("[!] Not enough data for backtest (need >= 100 bars)")
        return result
    
    result.start_date = ltf_df.index[0] if isinstance(ltf_df.index, pd.DatetimeIndex) else None
    result.end_date = ltf_df.index[-1] if isinstance(ltf_df.index, pd.DatetimeIndex) else None
    
    equity = initial_capital
    peak_equity = equity
    max_dd = 0.0
    
    # Track P&L for Sharpe/Sortino
    daily_returns = []
    
    step = 8  # Re-evaluate every N bars
    i = 80    # Warm-up period
    
    while i < len(ltf_df) - lookforward_bars - 2:
        window_ltf = ltf_df.iloc[: i + 1].copy()
        
        window_htf = None
        if htf_df is not None:
            current_time = window_ltf.index[-1]
            window_htf = htf_df[htf_df.index <= current_time].copy()
        
        # Generate signals
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
        
        # Entry on next bar open
        entry_idx = i + 1
        if entry_idx >= len(ltf_df):
            break
        
        entry_price = float(ltf_df["open"].iloc[entry_idx])
        entry_time = ltf_df.index[entry_idx]
        
        # Calculate risk & position size
        if sig.direction == "LONG":
            stop = min(sig.stop_hint, entry_price * 0.995)
            risk = entry_price - stop
            if risk <= 0:
                i += step
                continue
            target = entry_price + risk * risk_reward
            position_size = (equity * risk_per_trade) / risk
        else:  # SHORT
            stop = max(sig.stop_hint, entry_price * 1.005)
            risk = stop - entry_price
            if risk <= 0:
                i += step
                continue
            target = entry_price - risk * risk_reward
            position_size = (equity * risk_per_trade) / risk
        
        # Simulate forward
        trade = Trade(
            direction=sig.direction,
            entry_time=entry_time,
            entry_price=entry_price,
            stop_price=stop,
            risk=risk,
            reason=sig.reason,
        )
        
        exit_price = None
        exit_time = None
        exit_reason = "time_exit"
        bars_held = 0
        
        for j in range(entry_idx + 1, min(entry_idx + lookforward_bars, len(ltf_df))):
            bar_high = float(ltf_df["high"].iloc[j])
            bar_low = float(ltf_df["low"].iloc[j])
            bar_time = ltf_df.index[j]
            bars_held = j - entry_idx
            
            if sig.direction == "LONG":
                if bar_low <= stop:
                    exit_price = stop
                    exit_time = bar_time
                    exit_reason = "stop_hit"
                    break
                if bar_high >= target:
                    exit_price = target
                    exit_time = bar_time
                    exit_reason = "target_hit"
                    break
            else:  # SHORT
                if bar_high >= stop:
                    exit_price = stop
                    exit_time = bar_time
                    exit_reason = "stop_hit"
                    break
                if bar_low <= target:
                    exit_price = target
                    exit_time = bar_time
                    exit_reason = "target_hit"
                    break
        
        # Time exit (no stop/target hit)
        if exit_price is None:
            last_idx = min(entry_idx + lookforward_bars - 1, len(ltf_df) - 1)
            exit_time = ltf_df.index[last_idx]
            exit_price = float(ltf_df["close"].iloc[last_idx])
            exit_reason = "time_exit"
            bars_held = last_idx - entry_idx
        
        # Calculate P&L
        if sig.direction == "LONG":
            pnl_usd = (exit_price - entry_price) * position_size
            pnl_percent = (exit_price - entry_price) / entry_price * 100
            pnl_r = (exit_price - entry_price) / risk
        else:
            pnl_usd = (entry_price - exit_price) * position_size
            pnl_percent = (entry_price - exit_price) / entry_price * 100
            pnl_r = (entry_price - exit_price) / risk
        
        trade.exit_time = exit_time
        trade.exit_price = exit_price
        trade.pnl_usd = pnl_usd
        trade.pnl_percent = pnl_percent
        trade.pnl_r = pnl_r
        trade.bars_held = bars_held
        
        # Outcome classification
        if pnl_r > 0:
            trade.outcome = "win"
        elif pnl_r < 0:
            trade.outcome = "loss"
        else:
            trade.outcome = "break_even"
        
        result.trades.append(trade)
        
        # Update equity
        equity += pnl_usd
        result.equity_curve.append(equity)
        daily_returns.append(pnl_percent)
        
        # Drawdown tracking
        peak_equity = max(peak_equity, equity)
        dd = peak_equity - equity
        max_dd = max(max_dd, dd)
        
        # Move forward to avoid overlapping trades
        i = entry_idx + 5
    
    # === Calculate summary stats ===
    if not result.trades:
        print("[!] No trades generated.")
        return result
    
    result.total_trades = len(result.trades)
    wins = [t for t in result.trades if t.outcome == "win"]
    losses = [t for t in result.trades if t.outcome == "loss"]
    break_even = [t for t in result.trades if t.outcome == "break_even"]
    
    result.winning_trades = len(wins)
    result.losing_trades = len(losses)
    result.break_even_trades = len(break_even)
    
    # Win rate
    result.win_rate = (result.winning_trades / result.total_trades) if result.total_trades > 0 else 0.0
    
    # R stats
    result.total_r = sum(t.pnl_r for t in result.trades)
    result.avg_r = result.total_r / result.total_trades if result.total_trades > 0 else 0.0
    
    # Profit factor
    gross_profit = sum(t.pnl_usd for t in wins) if wins else 0.0
    gross_loss = abs(sum(t.pnl_usd for t in losses)) if losses else 0.0
    result.gross_profit = gross_profit
    result.gross_loss = gross_loss
    result.net_profit = equity - initial_capital
    result.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    
    # Win/Loss stats
    if wins:
        result.avg_win_r = sum(t.pnl_r for t in wins) / len(wins)
        result.largest_win_r = max(t.pnl_r for t in wins)
    
    if losses:
        result.avg_loss_r = sum(t.pnl_r for t in losses) / len(losses)
        result.largest_loss_r = min(t.pnl_r for t in losses)
    
    # Expectancy
    if result.winning_trades > 0 and result.losing_trades > 0:
        win_rate = result.win_rate
        loss_rate = 1 - win_rate
        result.expectancy = (win_rate * result.avg_win_r) - (loss_rate * abs(result.avg_loss_r))
    
    # Drawdown
    result.max_drawdown_r = max_dd / (equity - initial_capital) if (equity - initial_capital) != 0 else 0.0
    result.max_drawdown_pct = (max_dd / peak_equity * 100) if peak_equity > 0 else 0.0
    
    # Consecutive wins/losses
    streak = 0
    max_streak = 0
    for t in result.trades:
        if t.outcome == "win":
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    result.max_consecutive_wins = max_streak
    
    streak = 0
    max_streak = 0
    for t in result.trades:
        if t.outcome == "loss":
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    result.max_consecutive_losses = max_streak
    
    # Avg bars held
    result.avg_bars_held = np.mean([t.bars_held for t in result.trades]) if result.trades else 0.0
    
    # Sharpe & Sortino
    if daily_returns:
        returns_arr = np.array(daily_returns) / 100.0  # Convert to decimal
        daily_std = np.std(returns_arr) if len(returns_arr) > 1 else 0.0
        
        # Annualize (assuming ~250 trading days)
        if daily_std > 0:
            result.sharpe_ratio = (np.mean(returns_arr) / daily_std) * np.sqrt(250)
        
        # Sortino: only downside deviation
        downside_returns = np.array([r for r in returns_arr if r < 0])
        downside_std = np.std(downside_returns) if len(downside_returns) > 1 else 0.0
        
        if downside_std > 0:
            result.sortino_ratio = (np.mean(returns_arr) / downside_std) * np.sqrt(250)
    
    return result


def print_backtest_report(result: BacktestResult, detailed: bool = True):
    """Pretty-print backtest results."""
    print("\n" + "=" * 70)
    print("                    APA SIGNAL BOT – BACKTEST REPORT")
    print("=" * 70)
    
    if result.start_date and result.end_date:
        print(f"Period       : {result.start_date} → {result.end_date}")
    
    print(f"\nTRADE SUMMARY:")
    print(f"  Total Trades     : {result.total_trades}")
    print(f"  Wins / Losses    : {result.winning_trades} / {result.losing_trades} ({result.break_even_trades} break-even)")
    print(f"  Win Rate         : {result.win_rate * 100:.1f}%")
    
    print(f"\nPROFITABILITY:")
    print(f"  Gross Profit     : ${result.gross_profit:,.2f}")
    print(f"  Gross Loss       : ${result.gross_loss:,.2f}")
    print(f"  Net Profit       : ${result.net_profit:,.2f}")
    print(f"  Profit Factor    : {result.profit_factor:.2f}x")
    
    print(f"\nR-MULTIPLE STATS:")
    print(f"  Total R          : {result.total_r:+.2f}R")
    print(f"  Avg R / Trade    : {result.avg_r:+.2f}R")
    print(f"  Expectancy       : {result.expectancy:+.2f}R")
    print(f"  Best Win         : {result.largest_win_r:+.2f}R")
    print(f"  Worst Loss       : {result.largest_loss_r:+.2f}R")
    
    print(f"\nRISK METRICS:")
    print(f"  Max Drawdown     : {result.max_drawdown_pct:.1f}% ({result.max_drawdown_r:.2f}R)")
    print(f"  Sharpe Ratio     : {result.sharpe_ratio:.2f}")
    print(f"  Sortino Ratio    : {result.sortino_ratio:.2f}")
    
    print(f"\nCONSECUTIVE STATS:")
    print(f"  Max Consecutive W: {result.max_consecutive_wins}")
    print(f"  Max Consecutive L: {result.max_consecutive_losses}")
    print(f"  Avg Bars Held    : {result.avg_bars_held:.1f}")
    
    print("=" * 70)
    
    if detailed and result.trades:
        print("\nLast 10 Trades:")
        print("-" * 70)
        for t in result.trades[-10:]:
            bar_str = f" ({t.bars_held}bars)"
            print(f"  {t.direction:5} | Entry ${t.entry_price:>8.2f} → Exit ${t.exit_price:>8.2f} | "
                  f"{t.pnl_r:+6.2f}R | {t.pnl_percent:+7.2f}% | {t.outcome:10}{bar_str}")
        print("-" * 70)


def export_trades_csv(result: BacktestResult, filepath: str = "backtest_trades.csv"):
    """Export trades to CSV for further analysis."""
    trades_data = []
    for t in result.trades:
        trades_data.append({
            "direction": t.direction,
            "entry_time": t.entry_time,
            "entry_price": t.entry_price,
            "stop_price": t.stop_price,
            "exit_time": t.exit_time,
            "exit_price": t.exit_price,
            "pnl_r": t.pnl_r,
            "pnl_pct": t.pnl_percent,
            "pnl_usd": t.pnl_usd,
            "outcome": t.outcome,
            "bars_held": t.bars_held,
            "reason": t.reason,
        })
    
    df = pd.DataFrame(trades_data)
    df.to_csv(filepath, index=False)
    print(f"\n✓ Trades exported to {filepath}")