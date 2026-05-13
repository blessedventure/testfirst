"""
TP/SL price monitor — runs in background, checks open signals,
notifies channel + users when TP1/TP2/SL is hit.
"""
import asyncio
import logging
from datetime import datetime
from database import (
    get_open_signals, update_signal_result,
    get_users_for_signal, get_user
)
from config import (
    MONITOR_CHECK_INTERVAL_MINUTES,
    MONITOR_MAX_CANDLES_WATCH,
    SCAN_INTERVAL_MINUTES
)

logger = logging.getLogger(__name__)

MAX_WATCH_MINUTES = MONITOR_MAX_CANDLES_WATCH * SCAN_INTERVAL_MINUTES


def _fmt(v: float) -> str:
    if v >= 10000: return f"{v:,.1f}"
    if v >= 1000:  return f"{v:,.2f}"
    if v >= 1:     return f"{v:.4f}"
    if v >= 0.01:  return f"{v:.5f}"
    return f"{v:.8f}"


def _result_message(sig: dict, result: str, price: float) -> str:
    d_emoji = "🟢" if sig["direction"] == "LONG" else "🔴"
    if result == "TP1":
        emoji = "🎯"
        label = "TP1 HIT"
        note  = "Consider moving SL to breakeven"
    elif result == "TP2":
        emoji = "✅"
        label = "TP2 HIT — FULL TARGET"
        note  = "Trade closed in profit"
    else:
        emoji = "🛑"
        label = "STOP LOSS HIT"
        note  = "Loss contained. Stay disciplined."

    return (
        f"{emoji} <b>{label}</b>\n"
        f"{'─' * 30}\n"
        f"{d_emoji} <b>{sig['direction']} — {sig['symbol']}</b>\n"
        f"📊 Type: {sig['signal_type']}  |  Score: {sig['score']}\n"
        f"\n"
        f"💰 Entry:   <code>{_fmt(sig['entry'])}</code>\n"
        f"📍 Closed:  <code>{_fmt(price)}</code>\n"
        f"🛑 SL was:  <code>{_fmt(sig['stop_loss'])}</code>\n"
        f"🎯 TP1:     <code>{_fmt(sig['tp1'])}</code>\n"
        f"🎯 TP2:     <code>{_fmt(sig['tp2'])}</code>\n"
        f"\n"
        f"💬 <i>{note}</i>"
    )


class SignalMonitor:
    def __init__(self, binance_client, notifier):
        self.client   = binance_client
        self.notifier = notifier
        self._running = False

    async def _get_current_price(self, symbol: str) -> float | None:
        try:
            df = await self.client.get_klines(symbol, "1m", 2)
            if df.empty:
                return None
            return float(df["close"].iloc[-1])
        except Exception as e:
            logger.debug(f"Price fetch error {symbol}: {e}")
            return None

    async def _check_signal(self, sig: dict):
        symbol    = sig["symbol"]
        direction = sig["direction"]
        entry     = sig["entry"]
        sl        = sig["stop_loss"]
        tp1       = sig["tp1"]
        tp2       = sig["tp2"]
        sent_at   = datetime.fromisoformat(sig["sent_at"])

        # Stop watching after max watch window
        age_minutes = (datetime.utcnow() - sent_at).total_seconds() / 60
        if age_minutes > MAX_WATCH_MINUTES:
            update_signal_result(sig["id"], "EXPIRED", 0)
            logger.info(f"Signal expired: {symbol} [{sig['id']}]")
            return

        price = await self._get_current_price(symbol)
        if price is None:
            return

        result = None

        if direction == "LONG":
            if price >= tp2:
                result = "TP2"
            elif price >= tp1:
                result = "TP1"
            elif price <= sl:
                result = "SL"
        else:  # SHORT
            if price <= tp2:
                result = "TP2"
            elif price <= tp1:
                result = "TP1"
            elif price >= sl:
                result = "SL"

        if result:
            update_signal_result(sig["id"], result, price)
            logger.info(f"Signal result: {symbol} {direction} → {result} @ {price}")

            # Build result message
            msg = _result_message(sig, result, price)

            # Send to channel
            await self.notifier.send(msg)

            # Send to all users who received this signal
            user_ids = get_users_for_signal(sig["id"])
            for uid in user_ids:
                user = get_user(uid)
                if user and user["is_subscribed"]:
                    try:
                        await self.notifier.send_to_user(uid, msg)
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.debug(f"Result notify error {uid}: {e}")

    async def run(self):
        self._running = True
        interval = MONITOR_CHECK_INTERVAL_MINUTES * 60
        logger.info(
            f"Signal monitor started — checking every "
            f"{MONITOR_CHECK_INTERVAL_MINUTES} min"
        )
        while self._running:
            try:
                open_signals = get_open_signals()
                if open_signals:
                    logger.info(f"Monitor: checking {len(open_signals)} open signals")
                    for sig in open_signals:
                        await self._check_signal(sig)
                        await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False
