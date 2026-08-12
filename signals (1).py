"""
APA-style Signal Generator
--------------------------
Combines structure + liquidity + multi-timeframe bias into clean signals.
"""

from __future__ import annotations
import pandas as pd
from dataclasses import dataclass
from typing import Optional, List
from .structure import (
    find_swings,
    classify_structure,
    detect_liquidity_sweeps,
    StructureEvent,
    LiquiditySweep,
)


@dataclass
class APASignal:
    direction: str              # "LONG" or "SHORT"
    strength: float             # 0.0 – 1.0 confluence score
    reason: str
    entry_hint: float
    stop_hint: float
    timestamp: Optional[pd.Timestamp]
    bias: str
    has_sweep: bool
    has_choch: bool
    has_bos: bool


def score_confluence(
    bias: str,
    latest_event: Optional[StructureEvent],
    latest_sweep: Optional[LiquiditySweep],
    htf_bias: str = "neutral"
) -> tuple[float, List[str]]:
    """
    Simple confluence scoring.
    Higher score = higher quality setup.
    """
    score = 0.0
    reasons = []

    # Higher timeframe alignment (most important filter)
    if htf_bias == bias and bias != "neutral":
        score += 0.40
        reasons.append(f"HTF bias aligned ({htf_bias})")
    elif htf_bias == "neutral":
        score += 0.10
        reasons.append("HTF neutral")

    # Structure event
    if latest_event:
        if latest_event.event_type == "CHOCH":
            score += 0.30
            reasons.append(f"CHOCH {latest_event.direction}")
        elif latest_event.event_type == "BOS":
            score += 0.20
            reasons.append(f"BOS {latest_event.direction}")

    # Liquidity sweep (very strong for APA-style entries)
    if latest_sweep:
        if latest_sweep.direction == bias or (bias == "bullish" and latest_sweep.direction == "bullish") or \
           (bias == "bearish" and latest_sweep.direction == "bearish"):
            score += 0.30
            reasons.append(f"Liquidity sweep ({latest_sweep.direction})")
        else:
            score += 0.10
            reasons.append("Sweep present but direction mismatch")

    return min(score, 1.0), reasons


def generate_signals(
    ltf_df: pd.DataFrame,
    htf_df: Optional[pd.DataFrame] = None,
    min_score: float = 0.55,
    swing_left: int = 3,
    swing_right: int = 3
) -> List[APASignal]:
    """
    Main signal generation function.

    ltf_df  : lower timeframe (entry timeframe)
    htf_df  : higher timeframe (bias timeframe). Optional but strongly recommended.
    min_score : minimum confluence required to emit a signal
    """
    # --- Lower timeframe analysis ---
    ltf_swings = find_swings(ltf_df, left=swing_left, right=swing_right)
    ltf_bias, ltf_events = classify_structure(ltf_swings)
    ltf_sweeps = detect_liquidity_sweeps(ltf_df, ltf_swings)

    latest_event = ltf_events[-1] if ltf_events else None
    latest_sweep = ltf_sweeps[-1] if ltf_sweeps else None

    # --- Higher timeframe bias ---
    htf_bias = "neutral"
    if htf_df is not None and len(htf_df) > 20:
        htf_swings = find_swings(htf_df, left=2, right=2)
        htf_bias, _ = classify_structure(htf_swings)

    score, reasons = score_confluence(ltf_bias, latest_event, latest_sweep, htf_bias)

    signals: List[APASignal] = []

    if score < min_score or ltf_bias == "neutral":
        return signals

    # Determine direction from bias + latest event
    direction = "LONG" if ltf_bias == "bullish" else "SHORT"

    # Simple entry / stop hints
    last_close = float(ltf_df["close"].iloc[-1])
    last_high = float(ltf_df["high"].iloc[-1])
    last_low = float(ltf_df["low"].iloc[-1])

    if direction == "LONG":
        entry_hint = last_close
        # Stop below recent swing low or the swept level
        stop_hint = latest_sweep.swept_level * 0.999 if latest_sweep and latest_sweep.direction == "bullish" else last_low * 0.998
    else:
        entry_hint = last_close
        stop_hint = latest_sweep.swept_level * 1.001 if latest_sweep and latest_sweep.direction == "bearish" else last_high * 1.002

    ts = ltf_df.index[-1] if isinstance(ltf_df.index, pd.DatetimeIndex) else None

    signals.append(APASignal(
        direction=direction,
        strength=score,
        reason=" | ".join(reasons),
        entry_hint=entry_hint,
        stop_hint=stop_hint,
        timestamp=ts,
        bias=ltf_bias,
        has_sweep=latest_sweep is not None,
        has_choch=latest_event is not None and latest_event.event_type == "CHOCH",
        has_bos=latest_event is not None and latest_event.event_type == "BOS",
    ))

    return signals
