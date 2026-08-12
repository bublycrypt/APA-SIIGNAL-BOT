# APA Signal Bot

A clean, practical **Advanced Price Action (APA) / Smart Money Concepts** signal engine focused on the highest-probability mechanical parts of the strategy:

- Market structure (Swing → BOS / CHOCH)
- Liquidity sweeps
- Multi-timeframe bias filter
- Confluence scoring
- Telegram alerts

This is **not** a full discretionary APA mentor system.  
It is a solid foundation that captures the core technical qualifications the strategy needs, so you can generate consistent, rule-based signals.

---

## Project Structure

```
apa-signal-bot/
├── core/
│   ├── structure.py      # Swings, BOS, CHOCH, Liquidity sweeps
│   └── signals.py        # Confluence scoring + signal generation
├── utils/
│   └── telegram.py       # Telegram alert helper
├── data/                 # Put your OHLC CSVs here
├── config/
├── main.py               # Entry point
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Install dependencies

```bash
cd apa-signal-bot
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 2. Prepare data

You need OHLC CSVs with at least these columns (case-insensitive):

- `open`, `high`, `low`, `close`
- Optional: `timestamp` / `time` / `date` (will be used as index)

Place them in the `data/` folder, for example:

- `data/v75_m15.csv`  → lower timeframe
- `data/v75_h1.csv`   → higher timeframe

### 3. Run

```bash
python main.py --ltf data/v75_m15.csv --htf data/v75_h1.csv --symbol V75 --min-score 0.55
```

Add `--send` to actually push the signal to Telegram (requires `.env` setup).

### 4. Telegram setup (optional)

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

---

## How signals are generated

1. Detect swings on the lower timeframe
2. Classify structure → current bias + latest BOS / CHOCH
3. Detect recent liquidity sweeps
4. (Optional) Get higher-timeframe bias
5. Score confluence:
   - HTF alignment (highest weight)
   - CHOCH > BOS
   - Liquidity sweep in the direction of the bias
6. Emit signal only if score ≥ `min-score`

You can raise `min-score` (e.g. 0.70) for fewer but higher-quality signals.

---

## Next improvements (easy to add)

- Live data feed (ccxt for crypto, MetaTrader5 for Deriv/synthetics, or TradingView webhooks)
- Fair Value Gaps + Order Blocks
- Session filters
- Automatic risk calculation (position size from stop distance)
- Simple backtester
- Web dashboard

---

## Philosophy

This bot prioritizes **clarity and reliability** over trying to clone every discretionary nuance of the original APA strategy.  
Start here, validate the signals visually, then tighten or expand the rules based on your own results.

---

**Disclaimer**: This is an educational / research tool. Trading involves substantial risk of loss. Past structure patterns do not guarantee future results. Always test thoroughly on demo before risking real capital.
