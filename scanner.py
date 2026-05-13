"""
Main scanner — orchestrates scanning, scoring, signal delivery,
user management, TP/SL monitoring, and bot command handling.
"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

from binance_client import BinanceClient
from scorer import score_pair, MarketCondition
from signal_generator import generate_signal, TradeSignal
from indicators import add_indicators
from telegram_bot import TelegramNotifier
from bot_handler import BotHandler
from monitor import SignalMonitor
from filters import signal_passes_for_channel, signal_passes_for_user
import database as db
import os
from config import (
    SCAN_INTERVAL_MINUTES, TIMEFRAMES, ENTRY_TF, MID_TF, HTF,
    MIN_VOLUME_USDT, TOP_PAIRS_LIMIT, MIN_SCORE_TO_TRADE,
    MAX_SIGNALS_PER_SCAN, ADMIN_IDS
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scanner.log", encoding="utf-8"),
    ]
)
# Suppress noisy httpx request logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger    = logging.getLogger("Scanner")
sig_log   = logging.getLogger("SignalGen")


class CryptoScanner:
    def __init__(self):
        self.client   = BinanceClient()
        self.notifier = TelegramNotifier()
        self.handler  = BotHandler(self.notifier)
        self.monitor  = SignalMonitor(self.client, self.notifier)

        self._sent_signals: dict[str, datetime] = {}
        self._signal_cooldown_hours = 4
        self._running = False

    # ── Dedup ────────────────────────────────────────────────

    def _is_duplicate(self, signal: TradeSignal) -> bool:
        key = f"{signal.symbol}_{signal.direction}"
        if key in self._sent_signals:
            age = datetime.utcnow() - self._sent_signals[key]
            if age < timedelta(hours=self._signal_cooldown_hours):
                return True
        return False

    def _mark_sent(self, signal: TradeSignal):
        key = f"{signal.symbol}_{signal.direction}"
        self._sent_signals[key] = datetime.utcnow()

    def _cleanup_old_signals(self):
        cutoff = datetime.utcnow() - timedelta(hours=self._signal_cooldown_hours + 1)
        self._sent_signals = {k: v for k, v in self._sent_signals.items() if v > cutoff}

    # ── Volume filter ────────────────────────────────────────

    async def _get_top_volume_pairs(self) -> list[str]:
        try:
            tickers = await self.client.get_24h_tickers()
            usdt_pairs = [
                t for t in tickers
                if t["symbol"].endswith("USDT")
                and float(t.get("quoteVolume", 0)) >= MIN_VOLUME_USDT
            ]
            usdt_pairs.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
            symbols = [t["symbol"] for t in usdt_pairs[:TOP_PAIRS_LIMIT]]
            logger.info(f"Volume filter: {len(symbols)} pairs qualify (min ${MIN_VOLUME_USDT:,})")
            return symbols
        except Exception as e:
            logger.error(f"Volume filter error: {e}")
            return []

    # ── Single pair analysis ─────────────────────────────────

    async def _analyse_pair(self, symbol: str) -> Optional[TradeSignal]:
        try:
            tf_data = await self.client.get_multi_tf_klines(symbol, TIMEFRAMES)
            if len(tf_data) < 2:
                return None

            condition = score_pair(symbol, tf_data, ENTRY_TF, MID_TF, HTF)
            if condition is None:
                return None

            logger.info(
                f"{symbol:<16} {condition.condition:<9} {condition.direction:<7}"
                f" T={condition.trend_score:<5} R={condition.range_score:<5}"
                f" ADX={condition.adx:<6} RSI={condition.rsi:<6}"
                f" Vol={condition.volume_ratio:.2f}x  Trade={condition.tradeable}"
            )

            if not condition.tradeable:
                return None

            df_entry = add_indicators(tf_data[ENTRY_TF].copy())
            signal   = generate_signal(condition, df_entry)
            return signal

        except Exception as e:
            logger.info(f"{symbol} error: {e}")
            return None

    # ── Deliver to users ─────────────────────────────────────

    async def _deliver_to_users(self, signal: TradeSignal, signal_db_id: int):
        users = db.get_all_subscribed_users()
        delivered = 0
        for user in users:
            try:
                if not signal_passes_for_user(signal, user):
                    continue
                if not db.check_rate_limit(user["user_id"], user["is_pro"]):
                    logger.info(f"Rate limit: {user['user_id']}")
                    continue
                ok = await self.notifier.send_to_user(
                    user["user_id"],
                    f"📡 <b>Personal Signal</b>\n\n" +
                    __import__("telegram_bot").format_signal(signal)
                )
                if ok:
                    db.log_user_signal(user["user_id"], signal_db_id)
                    db.increment_signals_received(user["user_id"])
                    delivered += 1
                    await asyncio.sleep(0.05)
            except Exception as e:
                logger.debug(f"User delivery error {user['user_id']}: {e}")
        if delivered:
            logger.info(f"Delivered to {delivered} users")

    # ── Inactive user check ──────────────────────────────────

    async def _check_inactive_users(self):
        warned = db.auto_pause_inactive()
        for user in warned:
            await self.notifier.send_to_user(
                user["user_id"],
                "⚠️ <b>Inactivity Warning</b>\n"
                "Your signals will be paused in 5 days due to inactivity.\n"
                "Send /resume to stay subscribed."
            )

    # ── Full scan cycle ──────────────────────────────────────

    async def _run_scan(self):
        logger.info("━━━━━━ Starting scan cycle ━━━━━━")
        self._cleanup_old_signals()

        symbols = await self._get_top_volume_pairs()
        if not symbols:
            logger.warning("No pairs passed volume filter")
            return

        channel_settings = db.get_channel_settings()

        BATCH = 10
        all_signals: list[TradeSignal] = []
        trending_count = 0
        ranging_count  = 0

        for i in range(0, len(symbols), BATCH):
            batch   = symbols[i:i + BATCH]
            tasks   = [self._analyse_pair(sym) for sym in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, TradeSignal):
                    if r.condition.condition == "TRENDING":
                        trending_count += 1
                    else:
                        ranging_count += 1
                    all_signals.append(r)
            await asyncio.sleep(0.3)

        # Sort by score descending
        all_signals.sort(key=lambda s: s.condition.final_score, reverse=True)

        sent_count = 0
        for signal in all_signals:
            if sent_count >= MAX_SIGNALS_PER_SCAN:
                break
            if self._is_duplicate(signal):
                continue

            # ── Channel delivery ─────────────────────────────
            channel_sent = False
            if signal_passes_for_channel(signal, channel_settings):
                ok = await self.notifier.send_signal(signal)
                if ok:
                    channel_sent = True
                    self._mark_sent(signal)
                    sent_count += 1
                    logger.info(
                        f"✅ Channel: {signal.symbol} {signal.direction} "
                        f"[{signal.signal_type}] Score={signal.condition.final_score} "
                        f"RR=1:{signal.rr_ratio}"
                    )

            # ── Log to DB ────────────────────────────────────
            signal_db_id = db.log_signal(signal)

            # ── User delivery (always, regardless of channel) ─
            await self._deliver_to_users(signal, signal_db_id)

            if channel_sent:
                await asyncio.sleep(1.5)

        # Summary
        if sent_count > 0:
            top_pairs = [s.symbol for s in all_signals[:8]]
            await self.notifier.send_summary(
                total=len(symbols),
                trending=trending_count,
                ranging=ranging_count,
                signals=sent_count,
                top_pairs=top_pairs
            )

        logger.info(
            f"Scan done — {len(symbols)} pairs | "
            f"T:{trending_count} R:{ranging_count} | "
            f"Channel: {sent_count}"
        )

    # ── Main loop ────────────────────────────────────────────

    async def run(self):
        self._running = True
        db.init_db()
        logger.info("CryptoScanner starting up...")

        # Small delay so Windows SelectorEventLoop DNS resolves cleanly
        await asyncio.sleep(2)

        # Retry startup message up to 5 times
        for attempt in range(5):
            ok = await self.notifier.send_startup()
            if ok:
                break
            logger.warning(f"Startup message failed (attempt {attempt+1}/5), retrying in 3s...")
            await asyncio.sleep(3)

        # Run scanner + bot handler + monitor concurrently
        await asyncio.gather(
            self._scanner_loop(),
            self.handler.run(),
            self.monitor.run(),
            self._maintenance_loop(),
        )

    async def _scanner_loop(self):
        try:
            while self._running:
                try:
                    await self._run_scan()
                except Exception as e:
                    logger.error(f"Scan error: {e}")
                logger.info(f"Next scan in {SCAN_INTERVAL_MINUTES} minutes")
                await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)
        except asyncio.CancelledError:
            pass

    async def _maintenance_loop(self):
        """Daily maintenance — inactive user check."""
        try:
            while self._running:
                await asyncio.sleep(24 * 3600)
                await self._check_inactive_users()
        except asyncio.CancelledError:
            pass

    def stop(self):
        self._running = False
        self.handler.stop()
        self.monitor.stop()


async def main():
    scanner = CryptoScanner()
    try:
        await scanner.run()
    except KeyboardInterrupt:
        scanner.stop()
        logger.info("Shutting down gracefully...")
    finally:
        await scanner.client.close()
        await scanner.notifier.close()


if __name__ == "__main__":
    # Windows local dev: use SelectorEventLoop for DNS compatibility
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Railway/Linux: default event loop works perfectly
    asyncio.run(main())
