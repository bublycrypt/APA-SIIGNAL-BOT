"""
Bot runner for Railway deployment. Reads env and starts live monitoring loop.
"""

import os
import sys
import time
from dotenv import load_dotenv

from core.live_data import LiveDataFetcher
from core.signals import generate_signals
from core.telegram import send_telegram_message, format_signal_message

load_dotenv()


def main():
    exchange = os.getenv("EXCHANGE", "binance")
    symbol = os.getenv("SYMBOL", "BTC/USDT")
    timeframe = os.getenv("TIMEFRAME", "1h")
    min_score = float(os.getenv("MIN_SCORE", "0.55"))
    send = os.getenv("SEND_TELEGRAM", "false").lower() in ("1", "true", "yes")

    print(f"Starting bot_runner: {exchange} {symbol} {timeframe} (min_score={min_score})")

    fetcher = LiveDataFetcher(exchange)

    def on_new(latest_row):
        try:
            # Re-fetch short window for signal generation
            df = fetcher.fetch_ohlc(symbol, timeframe=timeframe, limit=200)
            signals = generate_signals(ltf_df=df, htf_df=None, min_score=min_score)
            if signals:
                sig = signals[0]
                print(f"Detected signal: {sig.direction} strength={sig.strength:.2f}")
                msg = format_signal_message(sig, symbol=symbol)
                if send:
                    send_telegram_message(msg)
        except Exception as e:
            print(f"Error handling new candle: {e}")

    try:
        fetcher.stream_latest(symbol, timeframe=timeframe, callback=on_new, interval_seconds=30)
    except KeyboardInterrupt:
        print("Stopping bot_runner")


if __name__ == "__main__":
    main()
