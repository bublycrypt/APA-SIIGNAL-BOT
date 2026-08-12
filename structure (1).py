"""
APA / SMC Style Market Structure Detection
------------------------------------------
Core building blocks:
- Swing highs / lows
- Break of Structure (BOS)
- Change of Character (CHOCH)
- Liquidity sweeps
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class Swing:
    index: int
    price: float
    kind: str          # "high" or "low"
    timestamp: Optional[pd.Timestamp] = None


@dataclass
class StructureEvent:
    index: int
    timestamp: Optional[pd.Timestamp]
    event_type: str    # "BOS" or "CHOCH"
    direction: str     # "bullish" or "bearish"
    broken_level: float
    strength: float = 1.0


@dataclass
class LiquiditySweep:
    index: int
    timestamp: Optional[pd.Timestamp]
    direction: str     # "bullish" (swept low) or "bearish" (swept high)
    swept_level: float
    close: float


def find_swings(df: pd.DataFrame, left: int = 3, right: int = 3) -> List[Swing]:
    """
    Detect swing highs and lows using a simple fractal method.
    
    left / right = number of bars on each side that must be lower/higher.
    Higher values = fewer but more significant swings.
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    swings: List[Swing] = []

    for i in range(left, n - right):
        # Swing High
        if all(highs[i] > highs[i - j] for j in range(1, left + 1)) and \
           all(highs[i] > highs[i + j] for j in range(1, right + 1)):
            ts = df.index[i] if isinstance(df.index, pd.DatetimeIndex) else None
            swings.append(Swing(index=i, price=float(highs[i]), kind="high", timestamp=ts))

        # Swing Low
        if all(lows[i] < lows[i - j] for j in range(1, left + 1)) and \
           all(lows[i] < lows[i + j] for j in range(1, right + 1)):
            ts = df.index[i] if isinstance(df.index, pd.DatetimeIndex) else None
            swings.append(Swing(index=i, price=float(lows[i]), kind="low", timestamp=ts))

    return swings


def classify_structure(swings: List[Swing]) -> Tuple[str, List[StructureEvent]]:
    """
    Walk the swing sequence and detect BOS / CHOCH.
    
    Returns:
        current_bias: "bullish" | "bearish" | "neutral"
        events: list of StructureEvent
    """
    if len(swings) < 4:
        return "neutral", []

    events: List[StructureEvent] = []
    bias = "neutral"

    # Keep only the most recent meaningful swings in order
    ordered = sorted(swings, key=lambda s: s.index)

    for i in range(2, len(ordered)):
        prev = ordered[i - 2]
        curr = ordered[i]
        mid  = ordered[i - 1]

        # We need alternating high/low ideally, but we work with what we have
        if curr.kind == "high" and prev.kind == "high":
            # Two highs
            if curr.price > prev.price:
                # Higher High → potential bullish continuation
                if bias == "bearish":
                    # Breaking previous structure to the upside after bearish bias = CHOCH
                    events.append(StructureEvent(
                        index=curr.index,
                        timestamp=curr.timestamp,
                        event_type="CHOCH",
                        direction="bullish",
                        broken_level=prev.price
                    ))
                    bias = "bullish"
                else:
                    events.append(StructureEvent(
                        index=curr.index,
                        timestamp=curr.timestamp,
                        event_type="BOS",
                        direction="bullish",
                        broken_level=prev.price
                    ))
                    bias = "bullish"
            else:
                # Lower High
                if bias == "bullish":
                    events.append(StructureEvent(
                        index=curr.index,
                        timestamp=curr.timestamp,
                        event_type="CHOCH",
                        direction="bearish",
                        broken_level=prev.price
                    ))
                    bias = "bearish"

        elif curr.kind == "low" and prev.kind == "low":
            # Two lows
            if curr.price < prev.price:
                # Lower Low → bearish continuation
                if bias == "bullish":
                    events.append(StructureEvent(
                        index=curr.index,
                        timestamp=curr.timestamp,
                        event_type="CHOCH",
                        direction="bearish",
                        broken_level=prev.price
                    ))
                    bias = "bearish"
                else:
                    events.append(StructureEvent(
                        index=curr.index,
                        timestamp=curr.timestamp,
                        event_type="BOS",
                        direction="bearish",
                        broken_level=prev.price
                    ))
                    bias = "bearish"
            else:
                # Higher Low
                if bias == "bearish":
                    events.append(StructureEvent(
                        index=curr.index,
                        timestamp=curr.timestamp,
                        event_type="CHOCH",
                        direction="bullish",
                        broken_level=prev.price
                    ))
                    bias = "bullish"

    return bias, events


def detect_liquidity_sweeps(
    df: pd.DataFrame,
    swings: List[Swing],
    lookback: int = 20
) -> List[LiquiditySweep]:
    """
    Detect liquidity sweeps:
    - Price wicks beyond a recent swing high/low
    - Then closes back inside (false break)
    """
    sweeps: List[LiquiditySweep] = []
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    recent_swings = [s for s in swings if s.index >= len(df) - lookback - 50]

    for s in recent_swings:
        # Look a few bars after the swing for a sweep
        start = s.index + 1
        end = min(s.index + 15, len(df) - 1)

        for i in range(start, end + 1):
            if s.kind == "high":
                # Bearish sweep: wick above the high, close back below
                if highs[i] > s.price and closes[i] < s.price:
                    ts = df.index[i] if isinstance(df.index, pd.DatetimeIndex) else None
                    sweeps.append(LiquiditySweep(
                        index=i,
                        timestamp=ts,
                        direction="bearish",
                        swept_level=s.price,
                        close=float(closes[i])
                    ))
                    break
            else:
                # Bullish sweep: wick below the low, close back above
                if lows[i] < s.price and closes[i] > s.price:
                    ts = df.index[i] if isinstance(df.index, pd.DatetimeIndex) else None
                    sweeps.append(LiquiditySweep(
                        index=i,
                        timestamp=ts,
                        direction="bullish",
                        swept_level=s.price,
                        close=float(closes[i])
                    ))
                    break

    return sweeps


def get_latest_structure_summary(df: pd.DataFrame, swing_left: int = 3, swing_right: int = 3) -> dict:
    """
    Convenience function that returns a clean summary for the latest bars.
    """
    swings = find_swings(df, left=swing_left, right=swing_right)
    bias, events = classify_structure(swings)
    sweeps = detect_liquidity_sweeps(df, swings)

    latest_event = events[-1] if events else None
    latest_sweep = sweeps[-1] if sweeps else None

    return {
        "bias": bias,
        "latest_event": latest_event,
        "latest_sweep": latest_sweep,
        "swing_count": len(swings),
        "recent_events": events[-5:] if events else [],
        "recent_sweeps": sweeps[-3:] if sweeps else [],
    }
