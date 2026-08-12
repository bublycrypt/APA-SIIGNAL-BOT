"""
APA Signal Bot – Main entry point (enhanced) with yfinance support
"""

import argparse
import pandas as pd
from pathlib import Path
import sys

from core.signals import generate_signals
from core.backtest_enhanced import run_backtest, print_backtest_report, export_trades_csv
from core.live_data import LiveDataFetcher
from core.telegram import send_telegram_message, format_signal_message


def load_ohlc(path: str) -> pd.DataFrame:
    """Load OHLC from CSV."""
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]

    required = {"open", "high", "low", "close"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"CSV must contain columns: {required}")

    # Auto-detect datetime column
    for col in ["timestamp", "time", "date", "datetime"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
            df = df.set_index(col)
            break

    return df[["open", "high", "low", "close"]].astype(float)


def fetch_yfinance(symbol: str, interval: str = "15m", period: str = "60d") -> pd.DataFrame:
    try:
        import yfinance as yf
    except Exception:
        raise RuntimeError("yfinance is required — add it to requirements or install locally: pip install yfinance")

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, auto_adjust=False, progress=False)
    if df.empty:
        raise RuntimeError(f"yfinance returned no data for {symbol} {interval} {period}")

    df = df.rename(columns={
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume'
    })
    keep = [c for c in ['open','high','low','close','volume'] if c in df.columns]
    df = df[keep]
    df.index.name = 'timestamp'
    return df


def main():
    parser = argparse.ArgumentParser(
        description="APA Signal Bot – Structure + Liquidity Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # --- SIGNAL MODE ---
    signal_parser = subparsers.add_parser("signal", help="Generate signals from data")
    signal_parser.add_argument("--ltf", required=True, help="Lower timeframe CSV")
    signal_parser.add_argument("--htf", help="Higher timeframe CSV")
    signal_parser.add_argument("--symbol", default="SAMPLE", help="Symbol name")
    signal_parser.add_argument("--min-score", type=float, default=0.55)
    signal_parser.add_argument("--swing-left", type=int, default=3)
    signal_parser.add_argument("--swing-right", type=int, default=3)
    signal_parser.add_argument("--send", action="store_true", help="Send signal to Telegram")
    
    # --- BACKTEST MODE ---
    backtest_parser = subparsers.add_parser("backtest", help="Run historical backtest")
    
    # Data source (local, exchange, or yfinance)
    data_group = backtest_parser.add_mutually_exclusive_group(required=True)
    data_group.add_argument("--ltf", help="Local LTF CSV file")
    data_group.add_argument("--exchange", help="Crypto exchange (binance, kraken, etc)")
    data_group.add_argument("--yfinance", action="store_true", help="Use yfinance to fetch historical OHLC via Yahoo")
    
    backtest_parser.add_argument("--htf", help="Local HTF CSV file")
    backtest_parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair (for exchange)")
    backtest_parser.add_argument("--ltf-tf", default="1h", help="LTF timeframe (for exchange)")
    backtest_parser.add_argument("--htf-tf", default="4h", help="HTF timeframe (for exchange)")
    
    backtest_parser.add_argument("--min-score", type=float, default=0.55)
    backtest_parser.add_argument("--rr", type=float, default=2.0, help="Risk:Reward ratio")
    backtest_parser.add_argument("--risk-per-trade", type=float, default=0.02, help="% of capital at risk")
    backtest_parser.add_argument("--initial-capital", type=float, default=10000.0)
    backtest_parser.add_argument("--swing-left", type=int, default=3)
    backtest_parser.add_argument("--swing-right", type=int, default=3)
    backtest_parser.add_argument("--lookforward", type=int, default=40, help="Max bars to hold trade")
    backtest_parser.add_argument("--export", action="store_true", help="Export trades to CSV")
    # yfinance specific
    backtest_parser.add_argument("--yf-symbol", help="Ticker for yfinance, e.g. BTC-USD")
    backtest_parser.add_argument("--yf-interval", default="15m", help="Interval for yfinance (15m,1h)")
    backtest_parser.add_argument("--yf-period", default="60d", help="Period for yfinance (60d,1y)")
    
    # --- LIVE MODE ---
    live_parser = subparsers.add_parser("live", help="Monitor live signals")
    live_parser.add_argument("--exchange", required=True, help="Exchange (binance, kraken, etc)")
    live_parser.add_argument("--symbol", required=True, help="Trading pair (BTC/USDT)")
    live_parser.add_argument("--timeframe", default="1h", help="Monitoring timeframe")
    live_parser.add_argument("--min-score", type=float, default=0.55)
    live_parser.add_argument("--send", action="store_true", help="Send alerts to Telegram")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # ========== SIGNAL ==========
    if args.command == "signal":
        print(f"Loading LTF: {args.ltf}")
        ltf_df = load_ohlc(args.ltf)
        print(f"  → {len(ltf_df)} bars")
        
        htf_df = None
        if args.htf:
            print(f"Loading HTF: {args.htf}")
            htf_df = load_ohlc(args.htf)
            print(f"  → {len(htf_df)} bars")
        
        signals = generate_signals(
            ltf_df=ltf_df,
            htf_df=htf_df,
            min_score=args.min_score,
            swing_left=args.swing_left,
            swing_right=args.swing_right,
        )
        
        if not signals:
            print("\n✗ No signal meeting the minimum confluence score.")
            return
        
        for sig in signals:
            print("\n" + "=" * 60)
            print(f"SIGNAL: {sig.direction:5} | Strength: {sig.strength:.2f}")
            print(f"Reason   : {sig.reason}")
            print(f"Entry    : {sig.entry_hint:.5f}")
            print(f"Stop     : {sig.stop_hint:.5f}")
            print("=" * 60)
            
            msg = format_signal_message(sig, symbol=args.symbol)
            if args.send:
                ok = send_telegram_message(msg)
                print("✓ Telegram sent." if ok else "✗ Telegram failed.")
            else:
                print("\n[Preview] Telegram message:")
                print(msg)
    
    # ========== BACKTEST ==========
    elif args.command == "backtest":
        # Load data
        if args.ltf:
            print(f"Loading LTF from CSV: {args.ltf}")
            ltf_df = load_ohlc(args.ltf)
        elif args.exchange:
            print(f"Fetching {args.symbol} {args.ltf_tf} from {args.exchange.upper()}...")
            fetcher = LiveDataFetcher(args.exchange)
            ltf_df = fetcher.fetch_ohlc(args.symbol, timeframe=args.ltf_tf, limit=500)
        elif args.yfinance:
            if not args.yf_symbol:
                raise ValueError("--yf-symbol is required when --yfinance is used")
            print(f"Fetching {args.yf_symbol} via yfinance {args.yf_interval}/{args.yf_period}...")
            ltf_df = fetch_yfinance(args.yf_symbol, interval=args.yf_interval, period=args.yf_period)
        else:
            raise ValueError("No data source provided")
        
        print(f"  → {len(ltf_df)} bars")
        
        htf_df = None
        if args.htf:
            print(f"Loading HTF from CSV: {args.htf}")
            htf_df = load_ohlc(args.htf)
        elif args.exchange:
            print(f"Fetching {args.symbol} {args.htf_tf} from {args.exchange.upper()}...")
            fetcher = LiveDataFetcher(args.exchange)
            htf_df = fetcher.fetch_ohlc(args.symbol, timeframe=args.htf_tf, limit=500)
        
        if htf_df is not None:
            print(f"  → {len(htf_df)} bars")
        
        # Run backtest
        print("\n[BACKTEST] Running...\n")
        result = run_backtest(
            ltf_df=ltf_df,
            htf_df=htf_df,
            min_score=args.min_score,
            risk_reward=args.rr,
            swing_left=args.swing_left,
            swing_right=args.swing_right,
            lookforward_bars=args.lookforward,
            initial_capital=args.initial_capital,
            risk_per_trade=args.risk_per_trade,
        )
        
        print_backtest_report(result, detailed=True)
        
        if args.export and result.trades:
            export_trades_csv(result, "backtest_trades.csv")
    
    # ========== LIVE ==========
    elif args.command == "live":
        print(f"Starting live monitoring: {args.symbol} {args.timeframe}")
        print(f"Exchange: {args.exchange.upper()}")
        print(f"Min score: {args.min_score}\n")
        
        try:
            fetcher = LiveDataFetcher(args.exchange)
            
            # Fetch initial data
            df = fetcher.fetch_ohlc(args.symbol, timeframe=args.timeframe, limit=100)
            
            def on_new_candle(latest_row):
                """Called when a new candle completes."""
                try:
                    # Re-fetch to get full window
                    df = fetcher.fetch_ohlc(args.symbol, timeframe=args.timeframe, limit=50)
                    
                    signals = generate_signals(
                        ltf_df=df,
                        htf_df=None,
                        min_score=args.min_score,
                    )
                    
                    if signals:
                        sig = signals[0]
                        print(f"\n{'='*60}")
                        print(f"🚨 SIGNAL: {sig.direction} | Strength: {sig.strength:.2f}")
                        print(f"   Entry: {sig.entry_hint:.5f}")
                        print(f"   Stop: {sig.stop_hint:.5f}")
                        print(f"{'='*60}\n")
                        
                        if args.send:
                            msg = format_signal_message(sig, symbol=args.symbol)
                            send_telegram_message(msg)
                
                except Exception as e:
                    print(f"Error processing candle: {e}")
            
            # Start streaming
            fetcher.stream_latest(
                args.symbol,
                timeframe=args.timeframe,
                callback=on_new_candle,
                interval_seconds=30,
            )
        
        except Exception as e:
            print(f"✗ Error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
