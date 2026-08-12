"""
Generate realistic synthetic OHLC data with clear structure,
swings, and occasional liquidity sweeps so we can properly test the bot.
"""

import numpy as np
import pandas as pd
from pathlib import Path


def generate_structured_ohlc(
    n_bars: int = 800,
    start_price: float = 1000.0,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Create synthetic price action that contains:
    - Clear trends (bullish / bearish phases)
    - Higher-highs / higher-lows and lower-highs / lower-lows
    - Occasional liquidity sweeps (wick beyond swing then reverse)
    """
    np.random.seed(seed)

    dates = pd.date_range("2026-01-01", periods=n_bars, freq="15min")
    price = start_price
    opens, highs, lows, closes = [], [], [], []

    # Regime changes every ~120-180 bars
    regime_length = 0
    direction = 1  # 1 = bullish, -1 = bearish
    volatility = 3.5

    for i in range(n_bars):
        if regime_length <= 0:
            direction = np.random.choice([1, -1])
            regime_length = np.random.randint(100, 180)
            volatility = np.random.uniform(2.5, 5.5)

        regime_length -= 1

        # Base move
        drift = direction * np.random.uniform(0.3, 1.8)
        noise = np.random.normal(0, volatility)

        open_p = price
        close_p = price + drift + noise

        # Occasional strong displacement or sweep
        is_sweep_bar = np.random.random() < 0.07
        if is_sweep_bar:
            # Create a wick that goes against the current move then closes back
            if direction == 1:
                # Bullish regime → occasional bearish sweep wick
                high_p = max(open_p, close_p) + abs(np.random.normal(0, 4))
                low_p = min(open_p, close_p) - abs(np.random.normal(6, 3))  # deep wick
            else:
                high_p = max(open_p, close_p) + abs(np.random.normal(6, 3))
                low_p = min(open_p, close_p) - abs(np.random.normal(0, 4))
        else:
            high_p = max(open_p, close_p) + abs(np.random.normal(0, 2.2))
            low_p = min(open_p, close_p) - abs(np.random.normal(0, 2.2))

        # Ensure high >= open/close and low <= open/close
        high_p = max(high_p, open_p, close_p)
        low_p = min(low_p, open_p, close_p)

        opens.append(open_p)
        highs.append(high_p)
        lows.append(low_p)
        closes.append(close_p)

        price = close_p

    df = pd.DataFrame({
        "timestamp": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
    })
    df.set_index("timestamp", inplace=True)
    return df


if __name__ == "__main__":
    out_dir = Path(__file__).parent

    # Lower timeframe (entry)
    ltf = generate_structured_ohlc(n_bars=1200, start_price=850.0, seed=42)
    ltf.to_csv(out_dir / "sample_ltf_m15.csv")
    print(f"Created sample_ltf_m15.csv  → {len(ltf)} bars")

    # Higher timeframe (bias) – resample to roughly H1
    htf = ltf.resample("1h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna()
    htf.to_csv(out_dir / "sample_htf_h1.csv")
    print(f"Created sample_htf_h1.csv   → {len(htf)} bars")

    print("\nSample data ready. You can now run the bot and backtester.")
