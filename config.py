import os

# ── All non-secret constants ─────────────────────────────────
SCAN_INTERVAL_MINUTES = 15
TIMEFRAMES = ["15m", "1h", "4h"]
ENTRY_TF   = "15m"
MID_TF     = "1h"
HTF        = "4h"

MIN_VOLUME_USDT     = 10_000_000
MIN_SCORE_TO_TRADE  = 5
TOP_PAIRS_LIMIT     = 150

RISK_REWARD_TREND   = 2.5
RISK_REWARD_RANGE   = 1.8
SL_ATR_MULTIPLIER   = 1.5
TP_ATR_MULTIPLIER   = SL_ATR_MULTIPLIER * RISK_REWARD_TREND

EMA_FAST   = 20
EMA_MID    = 50
EMA_SLOW   = 200
RSI_PERIOD = 14
RSI_OB     = 70
RSI_OS     = 30
BB_PERIOD  = 20
BB_STD     = 2.0
ADX_PERIOD = 14
ADX_TREND_THRESHOLD  = 25
ADX_RANGE_THRESHOLD  = 20
VOLUME_MA_PERIOD     = 20

PATTERN_LOOKBACK    = 50
MIN_PATTERN_CANDLES = 8

MONITOR_CHECK_INTERVAL_MINUTES = 5
MONITOR_MAX_CANDLES_WATCH      = 96

CHANNEL_DEFAULT_STRATEGY  = "ALL"
CHANNEL_DEFAULT_MIN_SCORE = 5.0
CHANNEL_DEFAULT_SESSIONS  = ["ALL"]

USER_DEFAULT_STRATEGY     = "ALL"
USER_DEFAULT_MIN_SCORE    = 5.0
USER_DEFAULT_SESSIONS     = ["ALL"]
USER_INACTIVE_DAYS        = 30
USER_INACTIVE_WARN_DAYS   = 25

FREE_MAX_SIGNALS_PER_HOUR = 3
PRO_MAX_SIGNALS_PER_HOUR  = 10
MAX_SIGNALS_PER_SCAN      = 3

SESSIONS = {
    "ASIA"    : (0,  8),
    "LONDON"  : (7,  16),
    "NEWYORK" : (12, 21),
    "ALL"     : (0,  24),
}

# ── Secrets — lazy loaded at runtime only ────────────────────
# These are NOT read at import time.
# They are only accessed when the bot actually starts.
# This prevents Railway build failures.

def __getattr__(name):
    if name == "TELEGRAM_BOT_TOKEN":
        val = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not val:
            raise RuntimeError("Missing env var: TELEGRAM_BOT_TOKEN")
        return val
    if name == "TELEGRAM_CHANNEL_ID":
        val = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
        if not val:
            raise RuntimeError("Missing env var: TELEGRAM_CHANNEL_ID")
        return val
    if name == "ADMIN_IDS":
        raw = os.environ.get("ADMIN_IDS", "").strip()
        return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
    raise AttributeError(f"module 'config' has no attribute '{name}'")
