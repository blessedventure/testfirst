# ============================================================
#  CONFIGURATION
#  All secrets loaded from environment variables.
#  Set these in Railway dashboard → Variables tab.
# ============================================================
import os

def _require(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise RuntimeError(
            f"❌ Missing required environment variable: {key}\n"
            f"   Set it in Railway → Variables tab."
        )
    return val

def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()

# ── Required secrets (set in Railway Variables) ──────────────
TELEGRAM_BOT_TOKEN  = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = _require("TELEGRAM_CHANNEL_ID")

# ── Admin IDs (comma-separated in Railway Variables) ─────────
# Example: ADMIN_IDS=123456789,987654321
_raw_admins = _optional("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _raw_admins.split(",") if x.strip().isdigit()]

# ── Scanning ─────────────────────────────────────────────────
SCAN_INTERVAL_MINUTES = 15
TIMEFRAMES = ["15m", "1h", "4h"]
ENTRY_TF   = "15m"
MID_TF     = "1h"
HTF        = "4h"

# ── Pair Filters ─────────────────────────────────────────────
MIN_VOLUME_USDT     = 10_000_000
MIN_SCORE_TO_TRADE  = 5
TOP_PAIRS_LIMIT     = 150

# ── Risk Management ──────────────────────────────────────────
RISK_REWARD_TREND   = 2.5
RISK_REWARD_RANGE   = 1.8
SL_ATR_MULTIPLIER   = 1.5
TP_ATR_MULTIPLIER   = SL_ATR_MULTIPLIER * RISK_REWARD_TREND

# ── Indicator Settings ───────────────────────────────────────
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

# ── Pattern Detection ────────────────────────────────────────
PATTERN_LOOKBACK    = 50
MIN_PATTERN_CANDLES = 8

# ── TP/SL Monitor ────────────────────────────────────────────
MONITOR_CHECK_INTERVAL_MINUTES = 5  # How often to check TP/SL (1-15 min)
MONITOR_MAX_CANDLES_WATCH      = 96 # Stop watching after N x 15m candles (96 = 24h)

# ── Channel Defaults (overridden live via /admin commands) ───
CHANNEL_DEFAULT_STRATEGY  = "ALL"   # ALL / TREND / RANGE / PATTERN
CHANNEL_DEFAULT_MIN_SCORE = 5.0
CHANNEL_DEFAULT_SESSIONS  = ["ALL"] # ALL / ASIA / LONDON / NEWYORK

# ── User Defaults ────────────────────────────────────────────
USER_DEFAULT_STRATEGY     = "ALL"
USER_DEFAULT_MIN_SCORE    = 5.0
USER_DEFAULT_SESSIONS     = ["ALL"]
USER_INACTIVE_DAYS        = 30      # Auto-pause after N days inactive
USER_INACTIVE_WARN_DAYS   = 25      # Warn user at N days

# ── Rate Limits ──────────────────────────────────────────────
FREE_MAX_SIGNALS_PER_HOUR = 3
PRO_MAX_SIGNALS_PER_HOUR  = 10

# ── Scanner Channel ──────────────────────────────────────────
MAX_SIGNALS_PER_SCAN      = 3       # Max signals sent to channel per scan

# ── Sessions (UTC hours) ─────────────────────────────────────
SESSIONS = {
    "ASIA"    : (0,  8),
    "LONDON"  : (7,  16),
    "NEWYORK" : (12, 21),
    "ALL"     : (0,  24),
}
