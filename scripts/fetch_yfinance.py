"""
Fetch OHLC via yfinance (Yahoo Finance) for backtests.
Usage:
  python scripts/fetch_yfinance.py --symbol BTC-USD --interval 15m --period 60d --out data/BTC_USD_15m.csv
"""

import argparse
import pandas as pd


def fetch_yfinance(symbol: str, interval: str = "15m", period: str = "60d") -> pd.DataFrame:
    try:
        import yfinance as yf
    except Exception as e:
        raise RuntimeError("yfinance is required. Install with: pip install yfinance") from e

    ticker = yf.Ticker(symbol)
    # yfinance uses intervals like '15m', '1h', and periods like '60d'
    df = ticker.history(period=period, interval=interval, auto_adjust=False, progress=False)
    if df.empty:
        raise RuntimeError(f"No data returned for {symbol} {interval} {period}")

    # Standardize columns
    df = df.rename(columns={
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume'
    })

    # Keep only OHLCV
    keep = [c for c in ['open','high','low','close','volume'] if c in df.columns]
    df = df[keep]
    df.index.name = 'timestamp'
    return df


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', required=True, help='Ticker symbol, e.g. BTC-USD')
    parser.add_argument('--interval', default='15m', help='Interval like 15m,1h,1d')
    parser.add_argument('--period', default='60d', help='Period like 60d,1y')
    parser.add_argument('--out', default=None, help='Output CSV path')
    args = parser.parse_args()

    df = fetch_yfinance(args.symbol, interval=args.interval, period=args.period)
    out = args.out or f"data/{args.symbol.replace('/','_')}_{args.interval}.csv"
    df.to_csv(out, index=True)
    print(f"Saved to {out}")
