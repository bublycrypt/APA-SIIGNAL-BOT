"""
Simple main entry (normalized copy)
"""

import argparse
import pandas as pd
from pathlib import Path

from core.signals import generate_signals
from core.backtest import run_backtest, print_backtest_report
from core.telegram import send_telegram_message, format_signal_message


def load_ohlc(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]

    required = {"open", "high", "low", "close"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"CSV must contain columns: {required}")

    for col in ["timestamp", "time", "date", "datetime"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
            df = df.set_index(col)
            break

    return df[["open", "high", "low", "close"]].astype(float)


def main():
    parser = argparse.ArgumentParser(description="APA-style Structure + Liquidity Signal Bot")
    parser.add_argument("--mode", choices=["signal", "backtest"], default="signal")
    parser.add_argument("--ltf", required=True, help="Path to lower timeframe CSV")
    parser.add_argument("--htf", default=None, help="Path to higher timeframe CSV")
    parser.add_argument("--symbol", default="SAMPLE", help="Symbol name")
    parser.add_argument("--min-score", type=float, default=0.55)
    parser.add_argument("--rr", type=float, default=2.0, help="Risk:Reward target")
    parser.add_argument("--swing-left", type=int, default=3)
    parser.add_argument("--swing-right", type=int, default=3)
    parser.add_argument("--send", action="store_true")

    args = parser.parse_args()

    print(f"Loading LTF: {args.ltf}")
    ltf_df = load_ohlc(args.ltf)
    print(f"  → {len(ltf_df)} bars")

    htf_df = None
    if args.htf:
        print(f"Loading HTF: {args.htf}")
        htf_df = load_ohlc(args.htf)
        print(f"  → {len(htf_df)} bars")

    if args.mode == "signal":
        signals = generate_signals(
            ltf_df=ltf_df,
            htf_df=htf_df,
            min_score=args.min_score,
            swing_left=args.swing_left,
            swing_right=args.swing_right,
        )

        if not signals:
            print("\nNo signal meeting the minimum confluence score.")
            return

        for sig in signals:
            print("\n" + "=" * 50)
            print(f"SIGNAL: {sig.direction}  |  Strength: {sig.strength:.2f}")
            print(f"Reason: {sig.reason}")
            print(f"Entry hint: {sig.entry_hint:.5f}")
            print(f"Stop hint : {sig.stop_hint:.5f}")
            print("=" * 50)

            msg = format_signal_message(sig, symbol=args.symbol)
            if args.send:
                ok = send_telegram_message(msg)
                print("Telegram sent." if ok else "Telegram failed / not configured.")
            else:
                print("\n[Preview] Telegram message:")
                print(msg)

    elif args.mode == "backtest":
        print("\nRunning backtest...")
        result = run_backtest(
            ltf_df=ltf_df,
            htf_df=htf_df,
            min_score=args.min_score,
            risk_reward=args.rr,
            swing_left=args.swing_left,
            swing_right=args.swing_right,
        )
        print_backtest_report(result)


if __name__ == "__main__":
    main()
