# ============================================================
#  CONFIGURATION
#  Secrets loaded lazily from environment variables.
#  Set these in Railway dashboard → Variables tab.
# ============================================================
import os

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
MONITOR_CHECK_INTERVAL_MINUTES = 5
MONITOR_MAX_CANDLES_WATCH      = 96

# ── Channel Defaults ─────────────────────────────────────────
CHANNEL_DEFAULT_STRATEGY  = "ALL"
CHANNEL_DEFAULT_MIN_SCORE = 5.0
CHANNEL_DEFAULT_SESSIONS  = ["ALL"]

# ── User Defaults ────────────────────────────────────────────
USER_DEFAULT_STRATEGY     = "ALL"
USER_DEFAULT_MIN_SCORE    = 5.0
USER_DEFAULT_SESSIONS     = ["ALL"]
USER_INACTIVE_DAYS        = 30
USER_INACTIVE_WARN_DAYS   = 25

# ── Rate Limits ──────────────────────────────────────────────
FREE_MAX_SIGNALS_PER_HOUR = 3
PRO_MAX_SIGNALS_PER_HOUR  = 10

# ── Scanner ──────────────────────────────────────────────────
MAX_SIGNALS_PER_SCAN = 3

# ── Sessions (UTC hours) ─────────────────────────────────────
SESSIONS = {
    "ASIA"    : (0,  8),
    "LONDON"  : (7,  16),
    "NEWYORK" : (12, 21),
    "ALL"     : (0,  24),
}


# ── Lazy-loaded secrets ───────────────────────────────────────
# These are functions so they are only called at runtime,
# NOT at import time — this fixes Railway build errors.

def get_bot_token() -> str:
    val = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not val:
        raise RuntimeError(
            "❌ Missing environment variable: TELEGRAM_BOT_TOKEN\n"
            "   Set it in Railway → Variables tab."
        )
    return val


def get_channel_id() -> str:
    val = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not val:
        raise RuntimeError(
            "❌ Missing environment variable: TELEGRAM_CHANNEL_ID\n"
            "   Set it in Railway → Variables tab."
        )
    return val


def get_admin_ids() -> list[int]:
    raw = os.environ.get("ADMIN_IDS", "").strip()
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


# ── Convenience properties (read once at first use) ──────────
# Modules import these names — they resolve lazily on first call.

class _LazySecrets:
    """Reads env vars only when first accessed, not at import time."""
    _token   = None
    _channel = None
    _admins  = None

    @property
    def TELEGRAM_BOT_TOKEN(self) -> str:
        if self._token is None:
            self._token = get_bot_token()
        return self._token

    @property
    def TELEGRAM_CHANNEL_ID(self) -> str:
        if self._channel is None:
            self._channel = get_channel_id()
        return self._channel

    @property
    def ADMIN_IDS(self) -> list[int]:
        if self._admins is None:
            self._admins = get_admin_ids()
        return self._admins


_secrets = _LazySecrets()

# These names are what other modules import.
# They are descriptors — accessed only when used, not at import.
def __getattr__(name):
    if name == "TELEGRAM_BOT_TOKEN":
        return _secrets.TELEGRAM_BOT_TOKEN
    if name == "TELEGRAM_CHANNEL_ID":
        return _secrets.TELEGRAM_CHANNEL_ID
    if name == "ADMIN_IDS":
        return _secrets.ADMIN_IDS
    raise AttributeError(f"module 'config' has no attribute '{name}'")
