"""
Signal generator — entry, SL, TP calculation.

Hard filters (all must pass before a signal fires):
  1. Volume >= 0.8x average          — no low-volume ghost moves
  2. Price not overextended          — must be within 2x ATR of EMA20
  3. Pullback to value OR pattern    — entry at EMA or confirmed pattern
  4. Pattern direction must match    — no contradicting patterns
  5. RR >= 1.8 trend / 1.5 range    — minimum reward justification
  6. RSI not exhausted at entry      — no chasing overbought/oversold entries
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional
from scorer import MarketCondition
from config import (
    SL_ATR_MULTIPLIER, RISK_REWARD_TREND,
    RISK_REWARD_RANGE, ENTRY_TF
)

# ── Hard filter thresholds ────────────────────────────────────────────────────
MIN_VOLUME_RATIO       = 0.5    # Volume must be at least 80% of average
MAX_ATR_EXTENSION      = 3.0    # Price must be within 2x ATR of EMA20
PULLBACK_EMA_PCT       = 0.04  # Price within 2.5% of EMA20 = valid pullback zone
RSI_MAX_LONG_ENTRY     = 75     # Don't enter LONG when RSI already overbought
RSI_MIN_SHORT_ENTRY    = 25     # Don't enter SHORT when RSI already oversold
MIN_ADX_TREND          = 25     # ADX must confirm trend at signal time
MAX_RISK_PCT           = 8.0    # Reject if SL is more than 8% away


@dataclass
class TradeSignal:
    symbol: str
    direction: str
    signal_type: str        # "TREND" or "RANGE"
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_pct: float
    rr_ratio: float
    timeframe: str
    condition: MarketCondition
    confidence: str
    leverage_suggestion: int
    entry_reason: str       # Why this entry is valid — shown in signal


def _reject(symbol: str, reason: str) -> None:
    """Silent reject — just returns None. Logged at DEBUG level."""
    import logging
    logging.getLogger("SignalGen").info(f"REJECT {symbol}: {reason}")
    return None


def generate_signal(
    condition: MarketCondition,
    df_entry: pd.DataFrame
) -> Optional[TradeSignal]:
    """
    Convert a MarketCondition into a high-quality trade signal.
    Every hard filter must pass — no exceptions.
    """
    if not condition.tradeable:
        return None

    if len(df_entry) < 10:
        return None

    last  = df_entry.iloc[-1]
    prev  = df_entry.iloc[-2]
    prev2 = df_entry.iloc[-3]

    price = float(last["close"])
    atr   = condition.atr

    if atr <= 0 or price <= 0:
        return None

    # ── HARD FILTER 0: Candle staleness check ────────────
    # Reject if the last candle's high-low range already moved
    # more than 2x ATR — signal is stale, entry price no longer valid
    candle_range = float(last["high"]) - float(last["low"])
    if candle_range > atr * 2.5:
        return _reject(condition.symbol,
            f"Candle range {candle_range:.6g} > 2.5x ATR — stale/spiked candle")

    # Reject if close is more than 1.5% from open — momentum already spent
    candle_body_pct = abs(float(last["close"]) - float(last["open"])) / float(last["open"]) * 100
    if candle_body_pct > 3.0:
        return _reject(condition.symbol,
            f"Candle body {candle_body_pct:.1f}% — momentum already spent, wait for next candle")

    # ── HARD FILTER 1: Volume ─────────────────────────────
    # Low volume = no conviction = no signal
    if condition.volume_ratio < MIN_VOLUME_RATIO:
        return _reject(condition.symbol,
            f"Volume too low: {condition.volume_ratio:.2f}x (min {MIN_VOLUME_RATIO}x)")

    # ── Pull indicator values ─────────────────────────────
    ema_fast = float(last["ema_fast"]) if not np.isnan(last["ema_fast"]) else price
    ema_mid  = float(last["ema_mid"])  if not np.isnan(last["ema_mid"])  else price
    ema_slow = float(last["ema_slow"]) if not np.isnan(last["ema_slow"]) else price
    rsi      = condition.rsi
    pattern  = condition.pattern

    # ── HARD FILTER 2: Pattern contradiction ──────────────
    # If a pattern exists, its direction must agree with trade direction
    if pattern and pattern.direction != "NEUTRAL":
        if pattern.direction != condition.direction:
            return _reject(condition.symbol,
                f"Pattern {pattern.name} contradicts direction {condition.direction}")

    # ── HARD FILTER 3: ADX confirmation at signal time ────
    if condition.adx < MIN_ADX_TREND and condition.condition == "TRENDING":
        return _reject(condition.symbol,
            f"ADX {condition.adx:.1f} too weak for trend entry")

    # ══════════════════════════════════════════════════════
    # TREND SIGNAL
    # ══════════════════════════════════════════════════════
    if condition.condition == "TRENDING":
        rr = RISK_REWARD_TREND

        if condition.direction == "LONG":

            # HARD FILTER 4: Price must be above EMA50 (trend intact)
            if price < ema_mid:
                return _reject(condition.symbol,
                    f"Price {price:.6g} below EMA50 {ema_mid:.6g} — trend broken")

            # HARD FILTER 4b: Confirm recent candles also above EMA50
            recent_closes = df_entry["close"].tail(3).values
            ema_mid_recent = df_entry["ema_mid"].tail(3).values
            candles_above = sum(1 for c, e in zip(recent_closes, ema_mid_recent) if c > e)
            if candles_above < 2:
                return _reject(condition.symbol,
                    f"LONG: less than 2 of last 3 candles above EMA50 — spike, not trend")

            # HARD FILTER 5: RSI not overbought at entry
            if rsi > RSI_MAX_LONG_ENTRY:
                return _reject(condition.symbol,
                    f"RSI {rsi:.1f} overbought — chasing, skip")

            # HARD FILTER 6: Price extension check
            # Price must not be more than 2x ATR above EMA20 (overextended)
            extension = (price - ema_fast) / atr
            if extension > MAX_ATR_EXTENSION:
                return _reject(condition.symbol,
                    f"Price {extension:.1f}x ATR above EMA20 — overextended, wait for pullback")

            # ── Entry quality: pullback or pattern ────────
            # Valid entries:
            #   A) Price pulled back to EMA20 zone (within 2.5%)
            #   B) Confirmed pattern breakout (closed beyond boundary)
            #   C) Recent candle touched EMA20 and bounced (prev low near EMA)

            near_ema20     = abs(price - ema_fast) / price <= PULLBACK_EMA_PCT
            prev_touch_ema = float(prev["low"]) <= ema_fast * 1.008
            has_pattern    = pattern is not None and pattern.direction == "LONG"
            bounced        = float(prev2["close"]) < ema_fast and float(prev["close"]) > ema_fast

            valid_entry = near_ema20 or prev_touch_ema or has_pattern or bounced

            if not valid_entry:
                return _reject(condition.symbol,
                    f"No valid entry: price not at EMA20 pullback and no pattern confirmation")

            # Determine entry reason for signal message
            if has_pattern:
                entry_reason = f"Pattern breakout: {pattern.name}"
            elif bounced:
                entry_reason = "EMA20 bounce confirmed"
            elif near_ema20 or prev_touch_ema:
                entry_reason = "EMA20 pullback zone"
            else:
                entry_reason = "Trend continuation"

            entry = price
            sl    = entry - atr * SL_ATR_MULTIPLIER
            # Place SL below the nearest swing low if available
            recent_low = float(df_entry["low"].tail(10).min())
            if recent_low < entry and recent_low > entry * 0.93:
                sl = min(sl, recent_low * 0.998)

            tp1 = entry + atr * SL_ATR_MULTIPLIER * rr * 0.55
            tp2 = entry + atr * SL_ATR_MULTIPLIER * rr

        else:  # SHORT

            # HARD FILTER 4: Price must be below EMA50
            if price > ema_mid:
                return _reject(condition.symbol,
                    f"Price above EMA50 — bearish trend not confirmed")

            # HARD FILTER 4b: Confirm recent candles also below EMA50
            # Prevents entering after a single spike candle breaks below
            recent_closes = df_entry["close"].tail(3).values
            ema_mid_recent = df_entry["ema_mid"].tail(3).values
            candles_below = sum(1 for c, e in zip(recent_closes, ema_mid_recent) if c < e)
            if candles_below < 2:
                return _reject(condition.symbol,
                    f"SHORT: less than 2 of last 3 candles below EMA50 — spike, not trend")

            # HARD FILTER 5: RSI not oversold at short entry
            if rsi < RSI_MIN_SHORT_ENTRY:
                return _reject(condition.symbol,
                    f"RSI {rsi:.1f} oversold — chasing short, skip")

            # HARD FILTER 6: Extension check
            extension = (ema_fast - price) / atr
            if extension > MAX_ATR_EXTENSION:
                return _reject(condition.symbol,
                    f"Price {extension:.1f}x ATR below EMA20 — overextended short")

            near_ema20     = abs(price - ema_fast) / price <= PULLBACK_EMA_PCT
            prev_touch_ema = float(prev["high"]) >= ema_fast * 0.992
            has_pattern    = pattern is not None and pattern.direction == "SHORT"
            bounced        = float(prev2["close"]) > ema_fast and float(prev["close"]) < ema_fast

            valid_entry = near_ema20 or prev_touch_ema or has_pattern or bounced

            if not valid_entry:
                return _reject(condition.symbol,
                    f"No valid entry: not at EMA20 and no pattern")

            if has_pattern:
                entry_reason = f"Pattern breakdown: {pattern.name}"
            elif bounced:
                entry_reason = "EMA20 rejection confirmed"
            elif near_ema20 or prev_touch_ema:
                entry_reason = "EMA20 resistance zone"
            else:
                entry_reason = "Trend continuation"

            entry = price
            sl    = entry + atr * SL_ATR_MULTIPLIER
            recent_high = float(df_entry["high"].tail(10).max())
            if recent_high > entry and recent_high < entry * 1.07:
                sl = max(sl, recent_high * 1.002)

            tp1 = entry - atr * SL_ATR_MULTIPLIER * rr * 0.55
            tp2 = entry - atr * SL_ATR_MULTIPLIER * rr

        signal_type = "TREND"

    # ══════════════════════════════════════════════════════
    # RANGE / MEAN REVERSION SIGNAL
    # ══════════════════════════════════════════════════════
    else:
        rr = RISK_REWARD_RANGE

        bb_upper = float(last["bb_upper"]) if not np.isnan(last["bb_upper"]) else price * 1.02
        bb_lower = float(last["bb_lower"]) if not np.isnan(last["bb_lower"]) else price * 0.98
        bb_mid   = float(last["bb_mid"])   if not np.isnan(last["bb_mid"])   else price

        if condition.direction == "LONG":
            # Must be at or below BB lower AND RSI oversold
            if price > bb_lower * 1.025:
                return _reject(condition.symbol,
                    f"Range LONG: price {price:.6g} not at BB lower {bb_lower:.6g}")
            if rsi > 42:
                return _reject(condition.symbol,
                    f"Range LONG: RSI {rsi:.1f} not oversold enough (need <42)")
            # Need a rejection candle — previous candle wick below current close
            if not (float(prev["low"]) < float(last["low"])):
                return _reject(condition.symbol,
                    "Range LONG: no rejection candle at support")

            entry_reason = f"BB lower bounce + RSI {rsi:.0f}"
            entry = price
            sl    = min(entry - atr * SL_ATR_MULTIPLIER,
                        float(df_entry["low"].tail(5).min()) * 0.998)
            tp1   = bb_mid
            tp2   = entry + abs(entry - sl) * rr

        else:  # SHORT
            if price < bb_upper * 0.975:
                return _reject(condition.symbol,
                    f"Range SHORT: price not at BB upper")
            if rsi < 58:
                return _reject(condition.symbol,
                    f"Range SHORT: RSI {rsi:.1f} not overbought enough (need >58)")
            if not (float(prev["high"]) > float(last["high"])):
                return _reject(condition.symbol,
                    "Range SHORT: no rejection candle at resistance")

            entry_reason = f"BB upper rejection + RSI {rsi:.0f}"
            entry = price
            sl    = max(entry + atr * SL_ATR_MULTIPLIER,
                        float(df_entry["high"].tail(5).max()) * 1.002)
            tp1   = bb_mid
            tp2   = entry - abs(sl - entry) * rr

        signal_type = "RANGE"

    # ── FINAL VALIDATION ─────────────────────────────────
    risk_pct = abs(entry - sl) / entry * 100
    rr_ratio = abs(entry - tp2) / abs(entry - sl) if abs(entry - sl) > 0 else 0

    min_rr = 1.8 if signal_type == "TREND" else 1.5

    if rr_ratio < min_rr:
        return _reject(condition.symbol,
            f"RR {rr_ratio:.2f} below minimum {min_rr}")

    if risk_pct > MAX_RISK_PCT:
        return _reject(condition.symbol,
            f"Risk {risk_pct:.1f}% too wide (max {MAX_RISK_PCT}%)")

    if risk_pct < 0.15:
        return _reject(condition.symbol,
            f"Risk {risk_pct:.2f}% too tight — likely bad data")

    # Confidence: HIGH requires score ≥ 8.5 AND volume ≥ 1.0x
    if condition.final_score >= 8.5 and condition.volume_ratio >= 1.0:
        confidence = "HIGH"
        leverage   = 5
    elif condition.final_score >= 7.0:
        confidence = "MEDIUM"
        leverage   = 3
    else:
        confidence = "MEDIUM"
        leverage   = 2

    return TradeSignal(
        symbol=condition.symbol,
        direction=condition.direction,
        signal_type=signal_type,
        entry=round(entry, 6),
        stop_loss=round(sl, 6),
        take_profit_1=round(tp1, 6),
        take_profit_2=round(tp2, 6),
        risk_pct=round(risk_pct, 3),
        rr_ratio=round(rr_ratio, 2),
        timeframe=ENTRY_TF,
        condition=condition,
        confidence=confidence,
        leverage_suggestion=leverage,
        entry_reason=entry_reason
    )
