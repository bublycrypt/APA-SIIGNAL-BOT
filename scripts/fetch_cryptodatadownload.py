"""
Fetch OHLC CSVs from CryptoDataDownload.com (https://www.cryptodatadownload.com/)

Usage:
  python scripts/fetch_cryptodatadownload.py --exchange Binance --symbol BTC/USDT --timeframe 1h --out data/BTC_USDT_1h.csv

This is a best-effort downloader: CryptoDataDownload filenames vary by exchange and symbol naming.
"""

import requests
import argparse
import os
import pandas as pd
from urllib.parse import quote_plus

# Known exchange file prefixes on CryptoDataDownload (common)
EXCHANGE_MAP = {
    "binance": "Binance",
    "bitstamp": "Bitstamp",
    "coinbase": "Coinbase",  # may vary
    "poloniex": "Poloniex",
    "kraken": "Kraken",
}

TF_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

BASE_URL = "https://www.cryptodatadownload.com/cdd/"


def build_filename(exchange: str, symbol: str, timeframe: str) -> str:
    """Build a best-effort filename for CryptoDataDownload.

    Examples on the site include:
      - `Binance_BTCUSDT_1h.csv`
      - `Bitstamp_BTCUSD_1h.csv`

    We'll try common patterns.
    """
    exch = EXCHANGE_MAP.get(exchange.lower(), exchange)
    # Normalize symbol: remove slash and replace '-' with ''
    sym = symbol.replace("/", "").replace("-", "")
    # CryptoDataDownload sometimes uses USD vs USDT; keep as provided.
    tf = TF_MAP.get(timeframe, timeframe)
    filename = f"{exch}_{sym}_{tf}.csv"
    return filename


def download_file(filename: str, outpath: str) -> None:
    url = BASE_URL + quote_plus(filename)
    print(f"Downloading: {url}")
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to download {url} (status {resp.status_code})")
    os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
    with open(outpath, "wb") as f:
        f.write(resp.content)
    print(f"Saved to {outpath}")


def clean_csv(path: str) -> None:
    """CryptoDataDownload CSVs have header comments; clean to standard OHLC CSV.
    We read with pandas, skip initial comment lines and re-save with normalized columns.
    """
    # Read while skipping lines that start with '#'
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    data_lines = [ln for ln in lines if not ln.lstrip().startswith('#')]
    if not data_lines:
        raise RuntimeError("No CSV data found after stripping comments")
    from io import StringIO
    df = pd.read_csv(StringIO(''.join(data_lines)))
    # Try to standardize columns
    cols = [c.lower().strip() for c in df.columns]
    col_map = {}
    for c in cols:
        if 'date' in c or 'time' in c:
            col_map[c] = 'timestamp'
        elif 'open' == c:
            col_map[c] = 'open'
        elif 'high' == c:
            col_map[c] = 'high'
        elif 'low' == c:
            col_map[c] = 'low'
        elif 'close' == c:
            col_map[c] = 'close'
        elif 'volume' in c:
            col_map[c] = 'volume'
    df.columns = [col_map.get(c.lower().strip(), c) for c in df.columns]
    # Ensure timestamp column exists
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp')
    # Keep only OHLCV if present
    keep = [c for c in ['open','high','low','close','volume'] if c in df.columns]
    df = df[keep]
    df.to_csv(path, index=True)
    print(f"Cleaned CSV saved: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", required=True, help="Exchange name (Binance, Bitstamp)")
    parser.add_argument("--symbol", required=True, help="Symbol, e.g. BTC/USDT or BTCUSD")
    parser.add_argument("--timeframe", default="1h", help="Timeframe (1h, 1d, etc)")
    parser.add_argument("--out", default=None, help="Output path (default: data/<sym>_<tf>.csv)")
    args = parser.parse_args()

    filename = build_filename(args.exchange, args.symbol, args.timeframe)
    out = args.out or os.path.join("data", f"{args.symbol.replace('/','_')}_{args.timeframe}.csv")
    try:
        download_file(filename, out)
        clean_csv(out)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    main()
