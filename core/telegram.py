"""
Simple Telegram alert helper.
"""

import os
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def send_telegram_message(text: str, parse_mode: str = "HTML") -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env")
        print("Message that would have been sent:")
        print(text)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False


def format_signal_message(signal, symbol: str = "SYMBOL") -> str:
    emoji = "🟢" if signal.direction == "LONG" else "🔴"
    conf = f"{signal.strength * 100:.0f}%"

    msg = (
        f"{emoji} <b>APA Signal – {symbol}</b>\n\n"
        f"<b>Direction:</b> {signal.direction}\n"
        f"<b>Confluence:</b> {conf}\n"
        f"<b>Bias:</b> {signal.bias}\n"
        f"<b>Reason:</b> {signal.reason}\n\n"
        f"<b>Entry hint:</b> {signal.entry_hint:.5f}\n"
        f"<b>Stop hint:</b> {signal.stop_hint:.5f}\n"
    )

    if signal.timestamp:
        msg += f"\n<i>{signal.timestamp}</i>"

    return msg
