"""
SQLite database layer.
Tables: users, channel_settings, signal_log, user_signal_log
"""
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
from config import (
    USER_DEFAULT_STRATEGY, USER_DEFAULT_MIN_SCORE, USER_DEFAULT_SESSIONS,
    CHANNEL_DEFAULT_STRATEGY, CHANNEL_DEFAULT_MIN_SCORE, CHANNEL_DEFAULT_SESSIONS,
    FREE_MAX_SIGNALS_PER_HOUR, USER_INACTIVE_DAYS, USER_INACTIVE_WARN_DAYS
)

logger = logging.getLogger(__name__)

# Railway persistent volume mounts at /data — use it if available
# Otherwise fall back to local directory (for local dev)
import os
_data_dir = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "")
if _data_dir and os.path.isdir(_data_dir):
    DB_PATH = os.path.join(_data_dir, "cryptoscanner.db")
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryptoscanner.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id            INTEGER PRIMARY KEY,
            username           TEXT,
            first_name         TEXT,
            joined_at          TEXT    DEFAULT (datetime('now')),
            last_active        TEXT    DEFAULT (datetime('now')),
            is_subscribed      INTEGER DEFAULT 1,
            is_pro             INTEGER DEFAULT 0,
            strategy_filter    TEXT    DEFAULT '["ALL"]',
            confidence_filter  TEXT    DEFAULT '["ALL"]',
            volume_filter      TEXT    DEFAULT 'ANY',
            min_score          REAL    DEFAULT 5.0,
            sessions           TEXT    DEFAULT '["ALL"]',
            signals_received   INTEGER DEFAULT 0,
            signals_this_hour  INTEGER DEFAULT 0,
            hour_bucket        TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS channel_settings (
            id                INTEGER PRIMARY KEY DEFAULT 1,
            is_active         INTEGER DEFAULT 1,
            strategy_filter   TEXT    DEFAULT '["ALL"]',
            confidence_filter TEXT    DEFAULT '["ALL"]',
            volume_filter     TEXT    DEFAULT 'ANY',
            min_score         REAL    DEFAULT 5.0,
            sessions          TEXT    DEFAULT '["ALL"]'
        );

        CREATE TABLE IF NOT EXISTS signal_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol       TEXT,
            direction    TEXT,
            signal_type  TEXT,
            score        REAL,
            entry        REAL,
            stop_loss    REAL,
            tp1          REAL,
            tp2          REAL,
            pattern      TEXT,
            entry_reason TEXT,
            sent_at      TEXT DEFAULT (datetime('now')),
            result       TEXT DEFAULT 'OPEN',
            result_price REAL,
            result_at    TEXT,
            session      TEXT
        );

        CREATE TABLE IF NOT EXISTS user_signal_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER,
            signal_id INTEGER,
            sent_at   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id)   REFERENCES users(user_id),
            FOREIGN KEY(signal_id) REFERENCES signal_log(id)
        );
        """)

        # Ensure channel_settings row exists
        conn.execute("""
            INSERT OR IGNORE INTO channel_settings
              (id, strategy_filter, confidence_filter, volume_filter, min_score, sessions)
            VALUES (1, ?, ?, ?, ?, ?)
        """, (json.dumps([CHANNEL_DEFAULT_STRATEGY]),
              json.dumps(["ALL"]),
              "ANY",
              CHANNEL_DEFAULT_MIN_SCORE,
              json.dumps(CHANNEL_DEFAULT_SESSIONS)))

    logger.info("Database initialised")


# ── User Operations ──────────────────────────────────────────

def upsert_user(user_id: int, username: str, first_name: str):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing:
            conn.execute("""
                UPDATE users SET username=?, first_name=?, last_active=datetime('now')
                WHERE user_id=?
            """, (username, first_name, user_id))
        else:
            conn.execute("""
                INSERT INTO users
                  (user_id, username, first_name, strategy_filter,
                   confidence_filter, volume_filter, min_score, sessions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, username, first_name,
                  json.dumps([USER_DEFAULT_STRATEGY]),
                  json.dumps(["ALL"]),
                  "ANY",
                  USER_DEFAULT_MIN_SCORE,
                  json.dumps(USER_DEFAULT_SESSIONS)))
            logger.info(f"New user registered: {first_name} (@{username}) [{user_id}]")


def get_user(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if row:
            d = dict(row)
            d["sessions"]           = json.loads(d["sessions"])
            d["strategy_filter"]    = json.loads(d["strategy_filter"]) if d["strategy_filter"].startswith("[") else [d["strategy_filter"]]
            d["confidence_filter"]  = json.loads(d["confidence_filter"]) if d.get("confidence_filter") else ["ALL"]
            return d
    return None


def update_user_setting(user_id: int, field: str, value):
    allowed = {"strategy_filter", "confidence_filter", "volume_filter",
               "min_score", "sessions", "is_subscribed", "is_pro", "last_active"}
    if field not in allowed:
        raise ValueError(f"Invalid field: {field}")
    if field in ("sessions", "strategy_filter", "confidence_filter"):
        value = json.dumps(value) if isinstance(value, list) else value
    with get_conn() as conn:
        conn.execute(
            f"UPDATE users SET {field}=?, last_active=datetime('now') WHERE user_id=?",
            (value, user_id)
        )


def touch_user(user_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET last_active=datetime('now') WHERE user_id=?",
            (user_id,)
        )


def get_all_subscribed_users() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE is_subscribed=1"
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["sessions"]          = json.loads(d["sessions"])
            d["strategy_filter"]   = json.loads(d["strategy_filter"]) if d["strategy_filter"].startswith("[") else [d["strategy_filter"]]
            d["confidence_filter"] = json.loads(d.get("confidence_filter") or '["ALL"]')
            result.append(d)
        return result


def get_all_users() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY joined_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["sessions"]          = json.loads(d["sessions"])
            d["strategy_filter"]   = json.loads(d["strategy_filter"]) if d["strategy_filter"].startswith("[") else [d["strategy_filter"]]
            d["confidence_filter"] = json.loads(d.get("confidence_filter") or '["ALL"]')
            result.append(d)
        return result


def check_rate_limit(user_id: int, is_pro: bool) -> bool:
    """Returns True if user can receive signal, False if rate limited."""
    from config import FREE_MAX_SIGNALS_PER_HOUR, PRO_MAX_SIGNALS_PER_HOUR
    limit = PRO_MAX_SIGNALS_PER_HOUR if is_pro else FREE_MAX_SIGNALS_PER_HOUR
    current_hour = datetime.utcnow().strftime("%Y-%m-%d-%H")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT signals_this_hour, hour_bucket FROM users WHERE user_id=?",
            (user_id,)
        ).fetchone()
        if not row:
            return False
        count  = row["signals_this_hour"]
        bucket = row["hour_bucket"]
        if bucket != current_hour:
            conn.execute(
                "UPDATE users SET signals_this_hour=0, hour_bucket=? WHERE user_id=?",
                (current_hour, user_id)
            )
            count = 0
        if count >= limit:
            return False
        conn.execute(
            "UPDATE users SET signals_this_hour=signals_this_hour+1 WHERE user_id=?",
            (user_id,)
        )
        return True


def increment_signals_received(user_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET signals_received=signals_received+1 WHERE user_id=?",
            (user_id,)
        )


def auto_pause_inactive():
    """Pause users inactive for USER_INACTIVE_DAYS. Return list of warned users."""
    cutoff_pause = (datetime.utcnow() - timedelta(days=USER_INACTIVE_DAYS)).isoformat()
    cutoff_warn  = (datetime.utcnow() - timedelta(days=USER_INACTIVE_WARN_DAYS)).isoformat()
    warned = []
    with get_conn() as conn:
        conn.execute("""
            UPDATE users SET is_subscribed=0
            WHERE is_subscribed=1 AND last_active < ?
        """, (cutoff_pause,))
        rows = conn.execute("""
            SELECT user_id, first_name FROM users
            WHERE is_subscribed=1 AND last_active < ? AND last_active >= ?
        """, (cutoff_warn, cutoff_pause)).fetchall()
        warned = [dict(r) for r in rows]
    return warned


# ── Channel Settings ─────────────────────────────────────────

def get_channel_settings() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM channel_settings WHERE id=1").fetchone()
        d = dict(row)
        d["sessions"]          = json.loads(d["sessions"])
        d["strategy_filter"]   = json.loads(d["strategy_filter"]) if d["strategy_filter"].startswith("[") else [d["strategy_filter"]]
        d["confidence_filter"] = json.loads(d.get("confidence_filter") or '["ALL"]')
        return d


def update_channel_setting(field: str, value):
    allowed = {"is_active", "strategy_filter", "confidence_filter",
               "volume_filter", "min_score", "sessions"}
    if field not in allowed:
        raise ValueError(f"Invalid field: {field}")
    if field in ("sessions", "strategy_filter", "confidence_filter"):
        value = json.dumps(value) if isinstance(value, list) else value
    with get_conn() as conn:
        conn.execute(
            f"UPDATE channel_settings SET {field}=? WHERE id=1", (value,)
        )


# ── Signal Log ───────────────────────────────────────────────

def log_signal(signal) -> int:
    """Log a sent signal. Returns signal DB id."""
    from datetime import timezone
    now_utc = datetime.utcnow()
    hour = now_utc.hour
    if 0 <= hour < 8:    session = "ASIA"
    elif 7 <= hour < 16: session = "LONDON"
    elif 12 <= hour < 21: session = "NEWYORK"
    else:                session = "OTHER"

    pattern_name = signal.condition.pattern.name if signal.condition.pattern else None
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO signal_log
              (symbol, direction, signal_type, score, entry, stop_loss,
               tp1, tp2, pattern, entry_reason, session)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            signal.symbol, signal.direction, signal.signal_type,
            signal.condition.final_score,
            signal.entry, signal.stop_loss,
            signal.take_profit_1, signal.take_profit_2,
            pattern_name, signal.entry_reason, session
        ))
        return cur.lastrowid


def log_user_signal(user_id: int, signal_id: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO user_signal_log (user_id, signal_id) VALUES (?,?)",
            (user_id, signal_id)
        )


def get_open_signals() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM signal_log WHERE result='OPEN'
        """).fetchall()
        return [dict(r) for r in rows]


def update_signal_result(signal_id: int, result: str, result_price: float):
    with get_conn() as conn:
        conn.execute("""
            UPDATE signal_log
            SET result=?, result_price=?, result_at=datetime('now')
            WHERE id=?
        """, (result, result_price, signal_id))


def get_users_for_signal(signal_id: int) -> list[int]:
    """Get all user_ids who received a specific signal."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id FROM user_signal_log WHERE signal_id=?",
            (signal_id,)
        ).fetchall()
        return [r["user_id"] for r in rows]


def get_user_history(user_id: int, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.*, usl.sent_at as user_sent_at
            FROM signal_log s
            JOIN user_signal_log usl ON s.id = usl.signal_id
            WHERE usl.user_id = ?
            ORDER BY usl.sent_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def get_performance_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as c FROM signal_log WHERE result != 'OPEN'"
        ).fetchone()["c"]

        by_strategy = conn.execute("""
            SELECT signal_type,
                   COUNT(*) as total,
                   SUM(CASE WHEN result IN ('TP1','TP2') THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN result='SL' THEN 1 ELSE 0 END) as losses
            FROM signal_log WHERE result != 'OPEN'
            GROUP BY signal_type
        """).fetchall()

        by_session = conn.execute("""
            SELECT session,
                   COUNT(*) as total,
                   SUM(CASE WHEN result IN ('TP1','TP2') THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN result='SL' THEN 1 ELSE 0 END) as losses
            FROM signal_log WHERE result != 'OPEN'
            GROUP BY session
        """).fetchall()

        return {
            "total"      : total,
            "by_strategy": [dict(r) for r in by_strategy],
            "by_session" : [dict(r) for r in by_session],
        }
