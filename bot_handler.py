"""
Bot handler — full button UI for admin and users.
All settings via inline keyboards. Admin panel hidden from users.
"""
import asyncio
import json
import logging
import httpx
import config
import database as db
from telegram_bot import (
    TelegramNotifier, format_signal,
    format_admin_status, format_user_list,
    format_performance, format_user_status, format_user_history,
)

logger = logging.getLogger(__name__)
# API URL built lazily in BotHandler methods

# ── Keyboard builders ────────────────────────────────────────

def _check(selected: list, value: str) -> str:
    return "✅ " if value in selected else ""


def kb_main_menu(is_admin: bool) -> dict:
    rows = [
        [{"text": "⚙️ My Settings", "callback_data": "menu_settings"}],
        [
            {"text": "▶️ Resume Signals", "callback_data": "user_resume"},
            {"text": "⏸ Pause Signals",  "callback_data": "user_pause"},
        ],
        [
            {"text": "📋 My History",  "callback_data": "menu_history"},
            {"text": "👑 Upgrade Pro", "callback_data": "menu_upgrade"},
        ],
    ]
    if is_admin:
        rows.insert(0, [{"text": "🔧 ADMIN PANEL", "callback_data": "menu_admin"}])
    return {"inline_keyboard": rows}


def kb_settings_menu() -> dict:
    return {"inline_keyboard": [
        [{"text": "📈 Strategy Filter",   "callback_data": "set_strategy"}],
        [{"text": "🔥 Confidence Filter", "callback_data": "set_confidence"}],
        [{"text": "📦 Volume Filter",     "callback_data": "set_volume"}],
        [{"text": "🎯 Minimum Score",     "callback_data": "set_score"}],
        [{"text": "🕐 Session Filter",    "callback_data": "set_session"}],
        [{"text": "◀️ Back",             "callback_data": "menu_main"}],
    ]}


def kb_strategy(selected: list) -> dict:
    return {"inline_keyboard": [
        [
            {"text": f"{_check(selected,'TREND')}📈 TREND",   "callback_data": "strat_TREND"},
            {"text": f"{_check(selected,'RANGE')}↔️ RANGE",   "callback_data": "strat_RANGE"},
            {"text": f"{_check(selected,'PATTERN')}🔷 PATTERN","callback_data": "strat_PATTERN"},
        ],
        [{"text": "🌐 ALL (reset)", "callback_data": "strat_ALL"}],
        [{"text": "✔️ Done", "callback_data": "set_strategy_done"}],
        [{"text": "◀️ Back", "callback_data": "menu_settings"}],
    ]}


def kb_confidence(selected: list) -> dict:
    return {"inline_keyboard": [
        [
            {"text": f"{_check(selected,'HIGH')}🔥 HIGH",     "callback_data": "conf_HIGH"},
            {"text": f"{_check(selected,'MEDIUM')}✅ MEDIUM", "callback_data": "conf_MEDIUM"},
        ],
        [{"text": "🌐 ALL (reset)", "callback_data": "conf_ALL"}],
        [{"text": "✔️ Done", "callback_data": "set_conf_done"}],
        [{"text": "◀️ Back", "callback_data": "menu_settings"}],
    ]}


def kb_volume() -> dict:
    return {"inline_keyboard": [
        [{"text": "🔥 Strong only (≥1.5x)",        "callback_data": "vol_STRONG"}],
        [{"text": "✅ Normal + Strong (≥1.0x)",     "callback_data": "vol_NORMAL"}],
        [{"text": "🌐 Any volume",                  "callback_data": "vol_ANY"}],
        [{"text": "◀️ Back", "callback_data": "menu_settings"}],
    ]}


def kb_score(current: float) -> dict:
    scores = [5.0, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0]
    rows = []
    row = []
    for s in scores:
        mark = "✅ " if s == current else ""
        row.append({"text": f"{mark}{s}", "callback_data": f"score_{s}"})
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "◀️ Back", "callback_data": "menu_settings"}])
    return {"inline_keyboard": rows}


def kb_session(selected: list) -> dict:
    return {"inline_keyboard": [
        [
            {"text": f"{_check(selected,'ASIA')}🌏 Asia",       "callback_data": "sess_ASIA"},
            {"text": f"{_check(selected,'LONDON')}🇬🇧 London",  "callback_data": "sess_LONDON"},
        ],
        [
            {"text": f"{_check(selected,'NEWYORK')}🇺🇸 New York", "callback_data": "sess_NEWYORK"},
        ],
        [{"text": "🌐 ALL (reset)", "callback_data": "sess_ALL"}],
        [{"text": "✔️ Done", "callback_data": "set_sess_done"}],
        [{"text": "◀️ Back", "callback_data": "menu_settings"}],
    ]}


# ── Admin keyboards ──────────────────────────────────────────

def kb_admin_panel() -> dict:
    return {"inline_keyboard": [
        [{"text": "📡 Channel Settings",    "callback_data": "adm_channel_menu"}],
        [
            {"text": "▶️ Resume Channel", "callback_data": "adm_resume"},
            {"text": "⏸ Pause Channel",  "callback_data": "adm_pause"},
        ],
        [
            {"text": "👥 Users",           "callback_data": "adm_users"},
            {"text": "📊 Performance",     "callback_data": "adm_perf"},
        ],
        [{"text": "📢 Broadcast",          "callback_data": "adm_broadcast_prompt"}],
        [{"text": "◀️ Back",              "callback_data": "menu_main"}],
    ]}


def kb_admin_channel_menu() -> dict:
    return {"inline_keyboard": [
        [{"text": "📈 Strategy Filter",    "callback_data": "adm_set_strategy"}],
        [{"text": "🔥 Confidence Filter",  "callback_data": "adm_set_confidence"}],
        [{"text": "📦 Volume Filter",      "callback_data": "adm_set_volume"}],
        [{"text": "🎯 Minimum Score",      "callback_data": "adm_set_score"}],
        [{"text": "🕐 Session Filter",     "callback_data": "adm_set_session"}],
        [{"text": "◀️ Back",             "callback_data": "menu_admin"}],
    ]}


def kb_adm_strategy(selected: list) -> dict:
    return {"inline_keyboard": [
        [
            {"text": f"{_check(selected,'TREND')}📈 TREND",    "callback_data": "adm_strat_TREND"},
            {"text": f"{_check(selected,'RANGE')}↔️ RANGE",    "callback_data": "adm_strat_RANGE"},
            {"text": f"{_check(selected,'PATTERN')}🔷 PATTERN","callback_data": "adm_strat_PATTERN"},
        ],
        [{"text": "🌐 ALL (reset)", "callback_data": "adm_strat_ALL"}],
        [{"text": "✔️ Done", "callback_data": "adm_strat_done"}],
        [{"text": "◀️ Back", "callback_data": "adm_channel_menu"}],
    ]}


def kb_adm_confidence(selected: list) -> dict:
    return {"inline_keyboard": [
        [
            {"text": f"{_check(selected,'HIGH')}🔥 HIGH",     "callback_data": "adm_conf_HIGH"},
            {"text": f"{_check(selected,'MEDIUM')}✅ MEDIUM", "callback_data": "adm_conf_MEDIUM"},
        ],
        [{"text": "🌐 ALL (reset)", "callback_data": "adm_conf_ALL"}],
        [{"text": "✔️ Done", "callback_data": "adm_conf_done"}],
        [{"text": "◀️ Back", "callback_data": "adm_channel_menu"}],
    ]}


def kb_adm_volume() -> dict:
    return {"inline_keyboard": [
        [{"text": "🔥 Strong only (≥1.5x)",    "callback_data": "adm_vol_STRONG"}],
        [{"text": "✅ Normal + Strong (≥1.0x)", "callback_data": "adm_vol_NORMAL"}],
        [{"text": "🌐 Any volume",              "callback_data": "adm_vol_ANY"}],
        [{"text": "◀️ Back", "callback_data": "adm_channel_menu"}],
    ]}


def kb_adm_score(current: float) -> dict:
    scores = [5.0, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0]
    rows = []
    row = []
    for s in scores:
        mark = "✅ " if s == current else ""
        row.append({"text": f"{mark}{s}", "callback_data": f"adm_score_{s}"})
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "◀️ Back", "callback_data": "adm_channel_menu"}])
    return {"inline_keyboard": rows}


def kb_adm_session(selected: list) -> dict:
    return {"inline_keyboard": [
        [
            {"text": f"{_check(selected,'ASIA')}🌏 Asia",        "callback_data": "adm_sess_ASIA"},
            {"text": f"{_check(selected,'LONDON')}🇬🇧 London",   "callback_data": "adm_sess_LONDON"},
        ],
        [
            {"text": f"{_check(selected,'NEWYORK')}🇺🇸 New York","callback_data": "adm_sess_NEWYORK"},
        ],
        [{"text": "🌐 ALL (reset)", "callback_data": "adm_sess_ALL"}],
        [{"text": "✔️ Done", "callback_data": "adm_sess_done"}],
        [{"text": "◀️ Back", "callback_data": "adm_channel_menu"}],
    ]}


# ── Helpers ──────────────────────────────────────────────────

def _toggle_list(current: list, value: str, reset_val: str = "ALL") -> list:
    """Toggle a value in a multi-select list."""
    if value == reset_val:
        return [reset_val]
    new = [v for v in current if v != reset_val]
    if value in new:
        new.remove(value)
    else:
        new.append(value)
    return new if new else [reset_val]


# ── Handler class ────────────────────────────────────────────

class BotHandler:
    def __init__(self, notifier: TelegramNotifier):
        self.notifier  = notifier
        self._client   = notifier._client
        self._offset   = 0
        self._running  = False
        # Track users waiting for broadcast text
        self._broadcast_pending: set = set()

    async def _get_updates(self) -> list[dict]:
        try:
            resp = await self._client.get(
                f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"offset": self._offset, "timeout": 20, "limit": 50},
                timeout=httpx.Timeout(25.0)
            )
            data = resp.json()
            return data.get("result", []) if data.get("ok") else []
        except Exception as e:
            logger.debug(f"getUpdates error: {e}")
            return []

    async def run(self):
        self._running = True
        logger.info("Bot handler polling started")
        while self._running:
            updates = await self._get_updates()
            for upd in updates:
                self._offset = upd["update_id"] + 1
                try:
                    if "message" in upd:
                        await self._handle_message(upd["message"])
                    elif "callback_query" in upd:
                        await self._handle_callback(upd["callback_query"])
                except Exception as e:
                    logger.error(f"Handler error: {e}")
            if not updates:
                await asyncio.sleep(1)

    def stop(self):
        self._running = False

    # ── Message router ───────────────────────────────────────

    async def _handle_message(self, msg: dict):
        user_id    = msg["from"]["id"]
        username   = msg["from"].get("username", "")
        first_name = msg["from"].get("first_name", "Unknown")
        text       = msg.get("text", "").strip()
        if not text:
            return

        is_admin = user_id in config.ADMIN_IDS
        db.upsert_user(user_id, username, first_name)

        # Broadcast text collection
        if user_id in self._broadcast_pending:
            self._broadcast_pending.discard(user_id)
            users    = db.get_all_subscribed_users()
            user_ids = [u["user_id"] for u in users]
            sent     = await self.notifier.broadcast(
                f"📢 <b>Announcement</b>\n{'─'*28}\n{text}", user_ids
            )
            await self.notifier.send_to_user(
                user_id, f"📢 Broadcast sent to <b>{sent}</b> users."
            )
            return

        cmd = text.split()[0].lower().split("@")[0]

        if cmd in ("/start", "/menu"):
            await self._show_main_menu(user_id, first_name, is_admin)
        elif cmd == "/admin" and is_admin:
            await self._show_admin_panel(user_id)
        elif cmd == "/broadcast" and is_admin:
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                users    = db.get_all_subscribed_users()
                user_ids = [u["user_id"] for u in users]
                sent     = await self.notifier.broadcast(
                    f"📢 <b>Announcement</b>\n{'─'*28}\n{parts[1]}", user_ids
                )
                await self.notifier.send_to_user(
                    user_id, f"📢 Broadcast sent to <b>{sent}</b> users."
                )
            else:
                await self.notifier.send_to_user(
                    user_id,
                    "Send your broadcast message now.\n"
                    "(next message you type will be sent to all users)"
                )
                self._broadcast_pending.add(user_id)
        elif cmd == "/setpro" and is_admin:
            parts = text.split()
            if len(parts) >= 2:
                await self._admin_set_pro(user_id, parts[1].lstrip("@"))
        else:
            # Default: show menu
            await self._show_main_menu(user_id, first_name, is_admin)

    # ── Callback router ──────────────────────────────────────

    async def _handle_callback(self, cb: dict):
        user_id  = cb["from"]["id"]
        data     = cb.get("data", "")
        cb_id    = cb["id"]
        is_admin = user_id in config.ADMIN_IDS
        first_name = cb["from"].get("first_name", "")

        db.touch_user(user_id)
        await self.notifier.answer_callback(cb_id)

        # ── Main menu ────────────────────────────────────────
        if data == "menu_main":
            await self._show_main_menu(user_id, first_name, is_admin)

        elif data == "menu_admin" and is_admin:
            await self._show_admin_panel(user_id)

        elif data == "menu_settings":
            await self.notifier.send_to_user(
                user_id, "⚙️ <b>My Settings</b>\nChoose what to configure:",
                reply_markup=kb_settings_menu()
            )

        elif data == "menu_history":
            history = db.get_user_history(user_id, 10)
            await self.notifier.send_to_user(user_id, format_user_history(history))

        elif data == "menu_upgrade":
            await self.notifier.send_to_user(
                user_id,
                "👑 <b>Pro Upgrade</b>\n{'─'*28}\n"
                "Free: max 3 signals/hour\n"
                "Pro:  max 10 signals/hour\n\n"
                "Contact the admin to upgrade your account."
            )

        # ── User pause/resume ────────────────────────────────
        elif data == "user_pause":
            db.update_user_setting(user_id, "is_subscribed", 0)
            await self.notifier.send_to_user(
                user_id,
                "⏸ <b>Signals paused.</b>\nTap Resume when you're ready.",
                reply_markup=kb_main_menu(is_admin)
            )

        elif data == "user_resume":
            db.update_user_setting(user_id, "is_subscribed", 1)
            await self.notifier.send_to_user(
                user_id,
                "▶️ <b>Signals active!</b>\nYou'll receive signals matching your settings.",
                reply_markup=kb_main_menu(is_admin)
            )

        # ── User strategy (multi-select) ─────────────────────
        elif data == "set_strategy":
            user = db.get_user(user_id)
            sel  = user["strategy_filter"]
            await self.notifier.send_to_user(
                user_id,
                "📈 <b>Strategy Filter</b>\nTap to toggle on/off. Tap ✔️ Done when finished.",
                reply_markup=kb_strategy(sel)
            )

        elif data.startswith("strat_") and not data.startswith("strat_") == False:
            val  = data.replace("strat_", "")
            user = db.get_user(user_id)
            sel  = user["strategy_filter"]
            new_sel = _toggle_list(sel, val)
            db.update_user_setting(user_id, "strategy_filter", new_sel)
            await self.notifier.send_to_user(
                user_id,
                f"📈 <b>Strategy Filter</b>\nSelected: <b>{', '.join(new_sel)}</b>\nTap more or ✔️ Done.",
                reply_markup=kb_strategy(new_sel)
            )

        elif data == "set_strategy_done":
            user = db.get_user(user_id)
            await self.notifier.send_to_user(
                user_id,
                f"✅ Strategy set to: <b>{', '.join(user['strategy_filter'])}</b>",
                reply_markup=kb_settings_menu()
            )

        # ── User confidence (multi-select) ───────────────────
        elif data == "set_confidence":
            user = db.get_user(user_id)
            sel  = user.get("confidence_filter", ["ALL"])
            await self.notifier.send_to_user(
                user_id,
                "🔥 <b>Confidence Filter</b>\nTap to toggle. ✔️ Done when finished.",
                reply_markup=kb_confidence(sel)
            )

        elif data.startswith("conf_"):
            val  = data.replace("conf_", "")
            user = db.get_user(user_id)
            sel  = user.get("confidence_filter", ["ALL"])
            new_sel = _toggle_list(sel, val)
            db.update_user_setting(user_id, "confidence_filter", new_sel)
            await self.notifier.send_to_user(
                user_id,
                f"🔥 <b>Confidence Filter</b>\nSelected: <b>{', '.join(new_sel)}</b>",
                reply_markup=kb_confidence(new_sel)
            )

        elif data == "set_conf_done":
            user = db.get_user(user_id)
            sel  = user.get("confidence_filter", ["ALL"])
            await self.notifier.send_to_user(
                user_id,
                f"✅ Confidence set to: <b>{', '.join(sel)}</b>",
                reply_markup=kb_settings_menu()
            )

        # ── User volume ──────────────────────────────────────
        elif data == "set_volume":
            await self.notifier.send_to_user(
                user_id,
                "📦 <b>Volume Filter</b>\nChoose minimum volume requirement:",
                reply_markup=kb_volume()
            )

        elif data.startswith("vol_"):
            val = data.replace("vol_", "")
            db.update_user_setting(user_id, "volume_filter", val)
            labels = {"STRONG": "🔥 Strong only", "NORMAL": "✅ Normal+", "ANY": "🌐 Any"}
            await self.notifier.send_to_user(
                user_id,
                f"✅ Volume filter set to: <b>{labels.get(val, val)}</b>",
                reply_markup=kb_settings_menu()
            )

        # ── User score ───────────────────────────────────────
        elif data == "set_score":
            user = db.get_user(user_id)
            await self.notifier.send_to_user(
                user_id,
                "🎯 <b>Minimum Score</b>\nOnly signals at or above this score will be sent to you.",
                reply_markup=kb_score(user["min_score"])
            )

        elif data.startswith("score_") and not data.startswith("adm_"):
            score = float(data.replace("score_", ""))
            db.update_user_setting(user_id, "min_score", score)
            await self.notifier.send_to_user(
                user_id,
                f"✅ Minimum score set to: <b>{score}/10</b>",
                reply_markup=kb_settings_menu()
            )

        # ── User session (multi-select) ──────────────────────
        elif data == "set_session":
            user = db.get_user(user_id)
            sel  = user["sessions"]
            await self.notifier.send_to_user(
                user_id,
                "🕐 <b>Session Filter</b>\nTap to toggle sessions. ✔️ Done when finished.",
                reply_markup=kb_session(sel)
            )

        elif data.startswith("sess_") and not data.startswith("adm_"):
            val  = data.replace("sess_", "")
            user = db.get_user(user_id)
            sel  = user["sessions"]
            new_sel = _toggle_list(sel, val)
            db.update_user_setting(user_id, "sessions", new_sel)
            await self.notifier.send_to_user(
                user_id,
                f"🕐 <b>Session Filter</b>\nSelected: <b>{', '.join(new_sel)}</b>",
                reply_markup=kb_session(new_sel)
            )

        elif data == "set_sess_done":
            user = db.get_user(user_id)
            await self.notifier.send_to_user(
                user_id,
                f"✅ Sessions set to: <b>{', '.join(user['sessions'])}</b>",
                reply_markup=kb_settings_menu()
            )

        # ── Admin panel ──────────────────────────────────────
        elif data == "adm_channel_menu" and is_admin:
            await self.notifier.send_to_user(
                user_id,
                "📡 <b>Channel Settings</b>\nConfigure what signals go to the channel:",
                reply_markup=kb_admin_channel_menu()
            )

        elif data in ("adm_pause", "adm_resume") and is_admin:
            active = 1 if data == "adm_resume" else 0
            db.update_channel_setting("is_active", active)
            label = "▶️ Channel RESUMED" if active else "⏸ Channel PAUSED"
            await self.notifier.send_to_user(user_id, f"<b>{label}</b>",
                reply_markup=kb_admin_panel())

        elif data == "adm_users" and is_admin:
            all_users    = db.get_all_users()
            active_count = sum(1 for u in all_users if u["is_subscribed"])
            pro_count    = sum(1 for u in all_users if u["is_pro"])
            await self.notifier.send_to_user(
                user_id,
                f"👥 <b>User Summary</b>\n{'─'*28}\n"
                f"Total users: <b>{len(all_users)}</b>\n"
                f"Active subs: <b>{active_count}</b>\n"
                f"Pro users:   <b>{pro_count}</b>\n"
                f"Inactive:    <b>{len(all_users)-active_count}</b>\n\n"
                + format_user_list(all_users),
                reply_markup=kb_admin_panel()
            )

        elif data == "adm_perf" and is_admin:
            stats = db.get_performance_stats()
            await self.notifier.send_to_user(
                user_id, format_performance(stats),
                reply_markup=kb_admin_panel()
            )

        elif data == "adm_broadcast_prompt" and is_admin:
            self._broadcast_pending.add(user_id)
            await self.notifier.send_to_user(
                user_id,
                "📢 <b>Broadcast</b>\nType your message now — it will be sent to all subscribers."
            )

        # ── Admin strategy ───────────────────────────────────
        elif data == "adm_set_strategy" and is_admin:
            s = db.get_channel_settings()
            await self.notifier.send_to_user(
                user_id,
                "📈 <b>Channel Strategy Filter</b>\nToggle strategies for the channel:",
                reply_markup=kb_adm_strategy(s["strategy_filter"])
            )

        elif data.startswith("adm_strat_") and is_admin:
            val = data.replace("adm_strat_", "")
            s   = db.get_channel_settings()
            sel = s["strategy_filter"]
            new_sel = _toggle_list(sel, val)
            db.update_channel_setting("strategy_filter", new_sel)
            await self.notifier.send_to_user(
                user_id,
                f"📈 Channel strategy: <b>{', '.join(new_sel)}</b>",
                reply_markup=kb_adm_strategy(new_sel)
            )

        elif data == "adm_strat_done" and is_admin:
            s = db.get_channel_settings()
            await self.notifier.send_to_user(
                user_id,
                f"✅ Channel strategy: <b>{', '.join(s['strategy_filter'])}</b>",
                reply_markup=kb_admin_channel_menu()
            )

        # ── Admin confidence ─────────────────────────────────
        elif data == "adm_set_confidence" and is_admin:
            s = db.get_channel_settings()
            await self.notifier.send_to_user(
                user_id,
                "🔥 <b>Channel Confidence Filter</b>:",
                reply_markup=kb_adm_confidence(s["confidence_filter"])
            )

        elif data.startswith("adm_conf_") and is_admin:
            val = data.replace("adm_conf_", "")
            s   = db.get_channel_settings()
            sel = s["confidence_filter"]
            new_sel = _toggle_list(sel, val)
            db.update_channel_setting("confidence_filter", new_sel)
            await self.notifier.send_to_user(
                user_id,
                f"🔥 Channel confidence: <b>{', '.join(new_sel)}</b>",
                reply_markup=kb_adm_confidence(new_sel)
            )

        elif data == "adm_conf_done" and is_admin:
            s = db.get_channel_settings()
            await self.notifier.send_to_user(
                user_id,
                f"✅ Channel confidence: <b>{', '.join(s['confidence_filter'])}</b>",
                reply_markup=kb_admin_channel_menu()
            )

        # ── Admin volume ─────────────────────────────────────
        elif data == "adm_set_volume" and is_admin:
            await self.notifier.send_to_user(
                user_id,
                "📦 <b>Channel Volume Filter</b>:",
                reply_markup=kb_adm_volume()
            )

        elif data.startswith("adm_vol_") and is_admin:
            val = data.replace("adm_vol_", "")
            db.update_channel_setting("volume_filter", val)
            labels = {"STRONG": "🔥 Strong only", "NORMAL": "✅ Normal+", "ANY": "🌐 Any"}
            await self.notifier.send_to_user(
                user_id,
                f"✅ Channel volume filter: <b>{labels.get(val, val)}</b>",
                reply_markup=kb_admin_channel_menu()
            )

        # ── Admin score ──────────────────────────────────────
        elif data == "adm_set_score" and is_admin:
            s = db.get_channel_settings()
            await self.notifier.send_to_user(
                user_id,
                "🎯 <b>Channel Minimum Score</b>:",
                reply_markup=kb_adm_score(s["min_score"])
            )

        elif data.startswith("adm_score_") and is_admin:
            score = float(data.replace("adm_score_", ""))
            db.update_channel_setting("min_score", score)
            await self.notifier.send_to_user(
                user_id,
                f"✅ Channel min score: <b>{score}/10</b>",
                reply_markup=kb_admin_channel_menu()
            )

        # ── Admin session ────────────────────────────────────
        elif data == "adm_set_session" and is_admin:
            s = db.get_channel_settings()
            await self.notifier.send_to_user(
                user_id,
                "🕐 <b>Channel Session Filter</b>:",
                reply_markup=kb_adm_session(s["sessions"])
            )

        elif data.startswith("adm_sess_") and is_admin:
            val = data.replace("adm_sess_", "")
            s   = db.get_channel_settings()
            sel = s["sessions"]
            new_sel = _toggle_list(sel, val)
            db.update_channel_setting("sessions", new_sel)
            await self.notifier.send_to_user(
                user_id,
                f"🕐 Channel sessions: <b>{', '.join(new_sel)}</b>",
                reply_markup=kb_adm_session(new_sel)
            )

        elif data == "adm_sess_done" and is_admin:
            s = db.get_channel_settings()
            await self.notifier.send_to_user(
                user_id,
                f"✅ Channel sessions: <b>{', '.join(s['sessions'])}</b>",
                reply_markup=kb_admin_channel_menu()
            )

    # ── Helpers ──────────────────────────────────────────────

    async def _show_main_menu(self, user_id: int, first_name: str, is_admin: bool):
        user = db.get_user(user_id)
        sub  = "✅ Active" if user and user["is_subscribed"] else "⏸ Paused"
        pro  = " 👑 PRO" if user and user["is_pro"] else ""
        strat = ", ".join(user["strategy_filter"]) if user else "ALL"
        conf  = ", ".join(user.get("confidence_filter", ["ALL"])) if user else "ALL"
        vol   = user.get("volume_filter", "ANY") if user else "ANY"
        score = user["min_score"] if user else 5.0
        sess  = ", ".join(user["sessions"]) if user else "ALL"

        await self.notifier.send_to_user(
            user_id,
            f"👋 <b>Welcome, {first_name}!</b>{pro}\n"
            f"{'─'*32}\n"
            f"Status: <b>{sub}</b>\n\n"
            f"<b>Current Filters:</b>\n"
            f"  📈 Strategy:   <b>{strat}</b>\n"
            f"  🔥 Confidence: <b>{conf}</b>\n"
            f"  📦 Volume:     <b>{vol}</b>\n"
            f"  🎯 Min Score:  <b>{score}/10</b>\n"
            f"  🕐 Sessions:   <b>{sess}</b>\n\n"
            f"Use the buttons below to manage your signals:",
            reply_markup=kb_main_menu(is_admin)
        )

    async def _show_admin_panel(self, user_id: int):
        s            = db.get_channel_settings()
        all_users    = db.get_all_users()
        active_count = sum(1 for u in all_users if u["is_subscribed"])
        status       = "✅ ACTIVE" if s["is_active"] else "⏸ PAUSED"
        strat        = ", ".join(s["strategy_filter"])
        conf         = ", ".join(s["confidence_filter"])
        vol          = s.get("volume_filter", "ANY")
        sess         = ", ".join(s["sessions"])

        await self.notifier.send_to_user(
            user_id,
            f"🔧 <b>Admin Panel</b>\n"
            f"{'─'*32}\n"
            f"📡 Channel: <b>{status}</b>\n\n"
            f"<b>Channel Filters:</b>\n"
            f"  📈 Strategy:   <b>{strat}</b>\n"
            f"  🔥 Confidence: <b>{conf}</b>\n"
            f"  📦 Volume:     <b>{vol}</b>\n"
            f"  🎯 Min Score:  <b>{s['min_score']}/10</b>\n"
            f"  🕐 Sessions:   <b>{sess}</b>\n\n"
            f"👥 Users: <b>{len(all_users)}</b> total, <b>{active_count}</b> active",
            reply_markup=kb_admin_panel()
        )

    async def _admin_set_pro(self, admin_id: int, username: str):
        all_users = db.get_all_users()
        found = next((u for u in all_users if u.get("username") == username), None)
        if found:
            db.update_user_setting(found["user_id"], "is_pro", 1)
            await self.notifier.send_to_user(admin_id, f"👑 @{username} upgraded to PRO.")
            await self.notifier.send_to_user(
                found["user_id"],
                "👑 <b>You've been upgraded to PRO!</b>\n"
                "You can now receive up to 10 signals per hour."
            )
        else:
            await self.notifier.send_to_user(admin_id, f"❌ User @{username} not found.")
