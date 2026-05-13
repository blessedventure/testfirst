# 🤖 CryptoScanner — Binance Futures Signal Bot

Professional-grade crypto futures signal bot using multi-timeframe analysis,
chart pattern detection, trend/range scoring, and Telegram delivery via Aiogram.

---

## ⚡ Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure your settings
Open `config.py` and set:
```python
TELEGRAM_BOT_TOKEN  = "YOUR_BOT_TOKEN"       # From @BotFather on Telegram
TELEGRAM_CHANNEL_ID = "@your_channel"         # Your channel username or numeric ID
```

### 3. Run the bot
```bash
python scanner.py
```

---

## 🔧 Getting Your Telegram Bot Token

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow the steps
3. Copy the token it gives you → paste into `config.py`

## 📢 Setting Up Your Channel

1. Create a Telegram channel (public or private)
2. Add your bot as **Administrator** with "Post Messages" permission
3. Use the channel username (`@mychannel`) or copy the numeric ID

---

## 📊 How The System Works

```
Every 15 minutes:
│
├─ 1. SCAN — Pull all USDT perp pairs from Binance (200+)
│
├─ 2. FILTER — Keep only pairs with $10M+ daily volume
│
├─ 3. SCORE each pair (0-10):
│   ├─ Trending Score: ADX + EMA alignment + Market Structure + Volume
│   └─ Range Score:    ADX + Bollinger Bands + RSI + S/R proximity
│
├─ 4. DETECT patterns (falling wedge, bull flag, triangle, etc.)
│
├─ 5. GENERATE signals only if:
│   ├─ Score ≥ 6/10
│   ├─ Multi-timeframe confirmation (15m + 1h + 4h)
│   └─ Pattern aligns with trend direction
│
├─ 6. FILTER: Max 3 signals per scan (no spam)
│   └─ 4-hour cooldown per symbol+direction (no duplicates)
│
└─ 7. SEND to Telegram with entry, SL, TP1, TP2, RR ratio
```

---

## 📈 Signal Types

### TREND Signals
- Triggered when ADX > 25, EMAs aligned, market structure confirmed
- Entry near EMA20 pullback for best risk/reward
- Patterns: Falling Wedge, Bull/Bear Flag, Ascending/Descending Triangle

### RANGE Signals  
- Triggered when ADX < 20, price at BB boundary, RSI extreme
- Entry at support/resistance with RSI confirmation
- TP1 at BB midline, TP2 at full RR target

---

## ⚙️ Key Config Settings

| Setting | Default | Description |
|---|---|---|
| `SCAN_INTERVAL_MINUTES` | 15 | How often to scan |
| `MIN_VOLUME_USDT` | 10,000,000 | Minimum 24h volume filter |
| `MIN_SCORE_TO_TRADE` | 6 | Min score (0-10) to generate signal |
| `TOP_PAIRS_LIMIT` | 30 | Max pairs deep-analysed per scan |
| `RISK_REWARD_TREND` | 2.5 | RR ratio for trend trades |
| `RISK_REWARD_RANGE` | 1.8 | RR ratio for range trades |
| `SL_ATR_MULTIPLIER` | 1.5 | Stop loss distance (1.5x ATR) |

---

## 🛡️ Risk Management Built In

- **Max 3 signals per scan** — quality over quantity
- **4-hour cooldown** per pair+direction — no duplicate spam
- **Leverage capped** at 3x-5x suggestions — protects capital
- **ATR-based stops** — dynamic SL respects current volatility
- **RR filter** — signals with < 1.5 RR are automatically rejected
- **Score threshold** — only high-conviction setups are sent

---

## 📁 File Structure

```
crypto_scanner/
├── scanner.py          ← Main bot (run this)
├── config.py           ← All settings
├── binance_client.py   ← Binance Futures API
├── indicators.py       ← EMA, RSI, BB, ATR, ADX
├── patterns.py         ← Chart pattern detection
├── scorer.py           ← Market condition + scoring
├── signal_generator.py ← Entry/SL/TP calculation
├── telegram_bot.py     ← Aiogram message formatting
└── requirements.txt
```

---

## ⚠️ Disclaimer

This tool is for **educational and informational purposes only**.
It is not financial advice. Always do your own research (DYOR).
Never risk more than 1-2% of your account per trade.
Past performance does not guarantee future results.
