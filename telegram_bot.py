"""
Telegram bot — pure httpx.
Handles channel delivery, user DM delivery, admin commands, user commands.
"""
import httpx
import logging
import asyncio
from signal_generator import TradeSignal
import config

logger = logging.getLogger(__name__)
# TELEGRAM_API built lazily in TelegramNotifier.__init__

DIR_EMOJI  = {"LONG": "🟢", "SHORT": "🔴"}
TYPE_EMOJI = {"TREND": "📈", "RANGE": "↔️"}
CONF_EMOJI = {"HIGH": "🔥", "MEDIUM": "✅"}


def _fmt(v: float) -> str:
    if v >= 10000: return f"{v:,.1f}"
    if v >= 1000:  return f"{v:,.2f}"
    if v >= 1:     return f"{v:.4f}"
    if v >= 0.01:  return f"{v:.5f}"
    return f"{v:.8f}"


def format_signal(signal: TradeSignal) -> str:
    c       = signal.condition
    d_emoji = DIR_EMOJI.get(signal.direction, "⚪")
    t_emoji = TYPE_EMOJI.get(signal.signal_type, "📊")
    conf_e  = CONF_EMOJI.get(signal.confidence, "✅")
    vr      = c.volume_ratio
    vol_label = "🔥 Strong" if vr>=1.5 else "✅ Normal" if vr>=1.0 else "⚠️ Weak" if vr>=0.8 else "❌ Low"
    pattern_line = f"🔷 <b>Pattern:</b> {c.pattern.name} ✓\n" if c.pattern and c.pattern.direction == signal.direction else ""
    reasons_text = "\n".join(f"  • {r}" for r in c.reasons[:3])

    return (
        f"{d_emoji} <b>{signal.direction} — {signal.symbol}</b> {d_emoji}\n"
        f"{'─'*32}\n"
        f"{t_emoji} <b>Type:</b> {signal.signal_type}  {conf_e} <b>Conf:</b> {signal.confidence}\n"
        f"📊 <b>Score:</b> {c.final_score}/10  |  <b>ADX:</b> {c.adx}  |  <b>RSI:</b> {c.rsi}\n"
        f"📦 <b>Volume:</b> {vr}x avg — {vol_label}\n"
        f"⏱ <b>TF:</b> {signal.timeframe}\n"
        f"{pattern_line}"
        f"🎯 <b>Entry reason:</b> {signal.entry_reason}\n\n"
        f"{'─'*32}\n"
        f"💰 <b>ENTRY</b>      <code>{_fmt(signal.entry)}</code>\n"
        f"🛑 <b>STOP LOSS</b>  <code>{_fmt(signal.stop_loss)}</code>  <i>({signal.risk_pct}%)</i>\n"
        f"🎯 <b>TP1</b>        <code>{_fmt(signal.take_profit_1)}</code>\n"
        f"🎯 <b>TP2</b>        <code>{_fmt(signal.take_profit_2)}</code>\n"
        f"{'─'*32}\n"
        f"⚖️ <b>RR:</b> 1:{signal.rr_ratio}   🔧 <b>Leverage:</b> {signal.leverage_suggestion}x max\n\n"
        f"📝 <b>Why this trade:</b>\n{reasons_text}\n\n"
        f"<i>⚠️ DYOR. Max 1-2% account risk per trade.</i>"
    )


def format_startup() -> str:
    return (
        "🤖 <b>CryptoScanner Bot Started</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Binance Futures Scanner: Online\n"
        "✅ Pattern Detection: Active\n"
        "✅ Multi-Timeframe Analysis: Active\n"
        "✅ TP/SL Monitor: Active\n"
        "✅ User System: Online\n\n"
        "📡 First scan starting now...\n"
        "🎯 Quality signals only — no spam.\n\n"
        "<i>Users: send /start to the bot to subscribe</i>"
    )


def format_scan_summary(total, trending, ranging, signals, top_pairs) -> str:
    pairs_text = ", ".join(top_pairs[:8]) if top_pairs else "None"
    return (
        f"🔍 <b>Scan Complete</b>\n{'─'*32}\n"
        f"📊 Scanned: <b>{total}</b> pairs\n"
        f"📈 Trending: <b>{trending}</b>   ↔️ Ranging: <b>{ranging}</b>\n"
        f"⚡ Signals sent: <b>{signals}</b>\n\n"
        f"🏆 <b>Top setups:</b>\n<code>{pairs_text}</code>"
    )


# ── Admin message builders ───────────────────────────────────

def format_admin_status(settings: dict, user_count: int, active_count: int) -> str:
    sessions = ", ".join(settings["sessions"])
    status   = "✅ ACTIVE" if settings["is_active"] else "⏸ PAUSED"
    return (
        f"⚙️ <b>Admin Status</b>\n{'─'*30}\n"
        f"📡 Channel: <b>{status}</b>\n"
        f"📈 Strategy: <b>{settings['strategy_filter']}</b>\n"
        f"🎯 Min Score: <b>{settings['min_score']}</b>\n"
        f"🕐 Sessions: <b>{sessions}</b>\n\n"
        f"👥 Total users: <b>{user_count}</b>\n"
        f"✅ Active subs: <b>{active_count}</b>"
    )


def format_user_list(users: list[dict]) -> str:
    if not users:
        return "No users yet."
    lines = ["👥 <b>All Users</b>\n" + "─"*30]
    for u in users[:30]:
        sub  = "✅" if u["is_subscribed"] else "⏸"
        pro  = " 👑" if u["is_pro"] else ""
        name = u["first_name"] or "Unknown"
        uname= f"@{u['username']}" if u["username"] else f"ID:{u['user_id']}"
        lines.append(
            f"{sub}{pro} <b>{name}</b> ({uname})\n"
            f"   Strategy: {u['strategy_filter']} | Score: {u['min_score']} | "
            f"Signals: {u['signals_received']}"
        )
    if len(users) > 30:
        lines.append(f"\n<i>...and {len(users)-30} more</i>")
    return "\n".join(lines)


def format_performance(stats: dict) -> str:
    lines = ["📊 <b>Performance Report</b>\n" + "─"*30]
    lines.append(f"Total closed signals: <b>{stats['total']}</b>\n")

    lines.append("<b>By Strategy:</b>")
    for r in stats["by_strategy"]:
        total = r["total"] or 1
        wr = round(r["wins"] / total * 100, 1)
        lines.append(
            f"  {r['signal_type']}: {r['wins']}W / {r['losses']}L "
            f"— Win rate: <b>{wr}%</b>"
        )

    lines.append("\n<b>By Session:</b>")
    for r in stats["by_session"]:
        total = r["total"] or 1
        wr = round(r["wins"] / total * 100, 1)
        lines.append(
            f"  {r['session']}: {r['wins']}W / {r['losses']}L "
            f"— Win rate: <b>{wr}%</b>"
        )
    return "\n".join(lines)


def format_user_status(user: dict) -> str:
    sub      = "✅ Active" if user["is_subscribed"] else "⏸ Paused"
    pro      = " 👑 PRO" if user["is_pro"] else " (Free)"
    sessions = ", ".join(user["sessions"])
    return (
        f"👤 <b>Your Settings</b>\n{'─'*30}\n"
        f"Status: <b>{sub}</b>{pro}\n"
        f"📈 Strategy: <b>{user['strategy_filter']}</b>\n"
        f"🎯 Min Score: <b>{user['min_score']}</b>\n"
        f"🕐 Sessions: <b>{sessions}</b>\n"
        f"📨 Signals received: <b>{user['signals_received']}</b>\n\n"
        f"Use the commands below to change your settings:\n"
        f"/strategy  /minscore  /session  /pause  /resume"
    )


def format_user_history(history: list[dict]) -> str:
    if not history:
        return "No signal history yet."
    lines = ["📋 <b>Your Last Signals</b>\n" + "─"*30]
    for h in history:
        d_emoji = "🟢" if h["direction"] == "LONG" else "🔴"
        result  = h["result"]
        if result == "TP2":   r_label = "✅ TP2"
        elif result == "TP1": r_label = "🎯 TP1"
        elif result == "SL":  r_label = "🛑 SL"
        elif result == "OPEN":r_label = "⏳ Open"
        else:                 r_label = "⌛ Expired"
        lines.append(
            f"{d_emoji} <b>{h['symbol']}</b> {h['direction']} "
            f"[{h['signal_type']}] Score:{h['score']} → {r_label}"
        )
    return "\n".join(lines)


# ── Keyboard builders ────────────────────────────────────────

def kb_strategy():
    return {"inline_keyboard": [[
        {"text": "📈 TREND",   "callback_data": "strat_TREND"},
        {"text": "↔️ RANGE",   "callback_data": "strat_RANGE"},
        {"text": "🔷 PATTERN", "callback_data": "strat_PATTERN"},
        {"text": "🌐 ALL",     "callback_data": "strat_ALL"},
    ]]}


def kb_minscore():
    return {"inline_keyboard": [[
        {"text": f"{s}", "callback_data": f"score_{s}"}
        for s in [5, 6, 7, 8, 9, 10]
    ]]}


def kb_sessions():
    return {"inline_keyboard": [
        [
            {"text": "🌏 Asia",    "callback_data": "sess_ASIA"},
            {"text": "🇬🇧 London", "callback_data": "sess_LONDON"},
        ],
        [
            {"text": "🇺🇸 New York",   "callback_data": "sess_NEWYORK"},
            {"text": "🌐 All Sessions", "callback_data": "sess_ALL"},
        ],
    ]}


def kb_admin_strategy():
    return {"inline_keyboard": [[
        {"text": "📈 TREND",   "callback_data": "adm_strat_TREND"},
        {"text": "↔️ RANGE",   "callback_data": "adm_strat_RANGE"},
        {"text": "🔷 PATTERN", "callback_data": "adm_strat_PATTERN"},
        {"text": "🌐 ALL",     "callback_data": "adm_strat_ALL"},
    ]]}


def kb_admin_minscore():
    return {"inline_keyboard": [[
        {"text": f"{s}", "callback_data": f"adm_score_{s}"}
        for s in [5, 6, 7, 8, 9, 10]
    ]]}


def kb_admin_sessions():
    return {"inline_keyboard": [
        [
            {"text": "🌏 Asia",    "callback_data": "adm_sess_ASIA"},
            {"text": "🇬🇧 London", "callback_data": "adm_sess_LONDON"},
        ],
        [
            {"text": "🇺🇸 New York",   "callback_data": "adm_sess_NEWYORK"},
            {"text": "🌐 All Sessions", "callback_data": "adm_sess_ALL"},
        ],
    ]}


# ── Notifier ─────────────────────────────────────────────────

class TelegramNotifier:
    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
        )
        self.channel = TELEGRAM_CHANNEL_ID

    async def _post(self, method: str, payload: dict) -> dict:
        resp = await self._client.post(
            f"{TELEGRAM_API}/{method}", json=payload
        )
        return resp.json()

    async def send(self, text: str, reply_markup=None) -> bool:
        payload = {
            "chat_id": self.channel,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = await self._post("sendMessage", payload)
            if not r.get("ok"):
                logger.error(f"Channel send error: {r}")
                return False
            return True
        except Exception as e:
            logger.error(f"Channel send exception: {e}")
            return False

    async def send_to_user(self, user_id: int, text: str, reply_markup=None) -> bool:
        payload = {
            "chat_id": user_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = await self._post("sendMessage", payload)
            if not r.get("ok"):
                logger.debug(f"User {user_id} send error: {r.get('description')}")
                return False
            return True
        except Exception as e:
            logger.debug(f"User {user_id} send exception: {e}")
            return False

    async def answer_callback(self, callback_id: str, text: str = ""):
        await self._post("answerCallbackQuery", {
            "callback_query_id": callback_id,
            "text": text
        })

    async def send_signal(self, signal: TradeSignal):
        await self.send(format_signal(signal))

    async def send_startup(self) -> bool:
        return await self.send(format_startup())

    async def send_summary(self, total, trending, ranging, signals, top_pairs):
        await self.send(format_scan_summary(total, trending, ranging, signals, top_pairs))

    async def broadcast(self, text: str, user_ids: list[int]):
        sent = 0
        for uid in user_ids:
            ok = await self.send_to_user(uid, text)
            if ok:
                sent += 1
            await asyncio.sleep(0.05)
        return sent

    async def close(self):
        await self._client.aclose()
