"""
Scores each pair on TREND strength and RANGE quality.

Scoring is strict — volume is a hard gate, not just a bonus.
A pair with low volume cannot score above 5 regardless of other factors.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Literal
from indicators import (
    add_indicators, is_higher_highs_higher_lows,
    is_lower_lows_lower_highs, find_support_resistance
)
from patterns import detect_patterns, PatternResult
from config import (
    ADX_TREND_THRESHOLD, ADX_RANGE_THRESHOLD,
    RSI_OB, RSI_OS, MIN_SCORE_TO_TRADE,
    EMA_FAST, EMA_MID, EMA_SLOW
)

# Volume gates — pairs below these thresholds are capped in score
VOL_MINIMUM     = 0.5   # Below this → force CHOPPY, no trade
VOL_WEAK        = 0.8   # Below this → score capped at 5.0
VOL_GOOD        = 1.0   # Above this → full scoring applies
VOL_STRONG      = 1.5   # Above this → volume bonus


@dataclass
class MarketCondition:
    symbol: str
    condition: Literal["TRENDING", "RANGING", "CHOPPY"]
    direction: Literal["LONG", "SHORT", "NEUTRAL"]
    trend_score: float
    range_score: float
    final_score: float
    adx: float
    rsi: float
    atr: float
    atr_pct: float
    volume_ratio: float
    support: float
    resistance: float
    pattern: Optional[PatternResult] = None
    reasons: list[str] = field(default_factory=list)
    tradeable: bool = False


def score_pair(
    symbol: str,
    tf_data: dict[str, pd.DataFrame],
    entry_tf: str,
    mid_tf: str,
    htf: str
) -> Optional[MarketCondition]:

    if entry_tf not in tf_data or htf not in tf_data:
        return None

    df_entry = add_indicators(tf_data[entry_tf].copy())
    df_htf   = add_indicators(tf_data[htf].copy())
    df_mid   = add_indicators(tf_data[mid_tf].copy()) if mid_tf in tf_data else None

    if len(df_entry) < 50 or len(df_htf) < 50:
        return None

    last_e = df_entry.iloc[-1]
    last_h = df_htf.iloc[-1]
    price  = float(last_e["close"])

    adx_val  = float(last_h["adx"])       if not np.isnan(last_h["adx"])       else 0
    rsi_val  = float(last_e["rsi"])       if not np.isnan(last_e["rsi"])       else 50
    atr_val  = float(last_e["atr"])       if not np.isnan(last_e["atr"])       else 0
    atr_pct  = atr_val / price * 100      if price > 0 else 0
    vol_rat  = float(last_e["vol_ratio"]) if not np.isnan(last_e["vol_ratio"]) else 1.0

    # ── HARD VOLUME GATE ──────────────────────────────────
    # Pairs with critically low volume are skipped entirely
    if vol_rat < VOL_MINIMUM:
        return MarketCondition(
            symbol=symbol, condition="CHOPPY", direction="NEUTRAL",
            trend_score=0, range_score=0, final_score=0,
            adx=round(adx_val,2), rsi=round(rsi_val,2),
            atr=round(atr_val,6), atr_pct=round(atr_pct,3),
            volume_ratio=round(vol_rat,2),
            support=0, resistance=0,
            reasons=[f"Volume critically low: {vol_rat:.2f}x — skipped"],
            tradeable=False
        )

    support, resistance = find_support_resistance(df_htf)

    # ── TREND SCORING ─────────────────────────────────────
    trend_score   = 0.0
    trend_reasons = []
    direction     = "NEUTRAL"

    # 1. ADX (0-2.5 pts) — must be genuinely strong
    if adx_val >= 35:
        trend_score += 2.5
        trend_reasons.append(f"Strong ADX {adx_val:.1f}")
    elif adx_val >= ADX_TREND_THRESHOLD:
        trend_score += 1.5
        trend_reasons.append(f"ADX trending {adx_val:.1f}")
    else:
        trend_reasons.append(f"ADX weak {adx_val:.1f}")

    # 2. HTF EMA alignment (0-2.5 pts)
    ema_f_h  = float(last_h["ema_fast"]) if not np.isnan(last_h["ema_fast"]) else price
    ema_m_h  = float(last_h["ema_mid"])  if not np.isnan(last_h["ema_mid"])  else price
    ema_s_h  = float(last_h["ema_slow"]) if not np.isnan(last_h["ema_slow"]) else price
    price_h  = float(last_h["close"])

    bull_ema = price_h > ema_f_h > ema_m_h > ema_s_h
    bear_ema = price_h < ema_f_h < ema_m_h < ema_s_h

    if bull_ema:
        trend_score += 2.5
        direction = "LONG"
        trend_reasons.append("HTF EMA fully bullish — LONG bias")
    elif bear_ema:
        trend_score += 2.5
        direction = "SHORT"
        trend_reasons.append("HTF EMA fully bearish — SHORT bias")
    elif price_h > ema_m_h and ema_f_h > ema_m_h:
        trend_score += 1.2
        direction = "LONG"
        trend_reasons.append("HTF partial bullish EMA alignment")
    elif price_h < ema_m_h and ema_f_h < ema_m_h:
        trend_score += 1.2
        direction = "SHORT"
        trend_reasons.append("HTF partial bearish EMA alignment")

    # 3. Market structure on HTF (0-2 pts)
    # Only award structure points when structure CONFIRMS direction
    if direction == "LONG" and is_higher_highs_higher_lows(df_htf):
        trend_score += 2.0
        trend_reasons.append("HH+HL bullish structure confirmed")
    elif direction == "SHORT" and is_lower_lows_lower_highs(df_htf):
        trend_score += 2.0
        trend_reasons.append("LL+LH bearish structure confirmed")
    elif direction == "SHORT" and is_higher_highs_higher_lows(df_htf):
        # HTF bullish but entry-TF bearish — this is a counter-trend short
        # Penalise: structure works AGAINST the short
        trend_score -= 1.5
        trend_reasons.append("⚠️ Counter-trend SHORT (HTF bullish)")
    elif direction == "LONG" and is_lower_lows_lower_highs(df_htf):
        trend_score -= 1.5
        trend_reasons.append("⚠️ Counter-trend LONG (HTF bearish)")

    # 4. Volume — gated scoring (0-1.5 pts only if volume is decent)
    if vol_rat >= VOL_STRONG:
        trend_score += 1.5
        trend_reasons.append(f"Strong volume {vol_rat:.1f}x")
    elif vol_rat >= VOL_GOOD:
        trend_score += 0.75
        trend_reasons.append(f"Volume OK {vol_rat:.1f}x")
    elif vol_rat >= VOL_WEAK:
        trend_score += 0.25
        trend_reasons.append(f"Volume below avg {vol_rat:.1f}x")
    else:
        # Weak volume → penalise score
        trend_score -= 1.0
        trend_reasons.append(f"Low volume {vol_rat:.1f}x ⚠️")

    # 5. Mid-TF alignment bonus (0-1.5 pts)
    if df_mid is not None:
        last_m  = df_mid.iloc[-1]
        price_m = float(last_m["close"])
        ema_f_m = float(last_m["ema_fast"]) if not np.isnan(last_m["ema_fast"]) else price_m
        ema_m_m = float(last_m["ema_mid"])  if not np.isnan(last_m["ema_mid"])  else price_m
        if direction == "LONG" and price_m > ema_f_m > ema_m_m:
            trend_score += 1.5
            trend_reasons.append("Mid-TF trend aligned")
        elif direction == "SHORT" and price_m < ema_f_m < ema_m_m:
            trend_score += 1.5
            trend_reasons.append("Mid-TF trend aligned")

    # ── RANGE SCORING ─────────────────────────────────────
    range_score   = 0.0
    range_reasons = []

    # 1. Low ADX (0-2.5 pts)
    if adx_val < ADX_RANGE_THRESHOLD:
        range_score += 2.5
        range_reasons.append(f"Low ADX {adx_val:.1f} (ranging)")
    elif adx_val < 23:
        range_score += 1.5

    # 2. Price at BB boundary (0-2.5 pts)
    bb_upper = float(last_e["bb_upper"]) if not np.isnan(last_e["bb_upper"]) else price * 1.02
    bb_lower = float(last_e["bb_lower"]) if not np.isnan(last_e["bb_lower"]) else price * 0.98
    bb_width = float(last_e["bb_width"]) if not np.isnan(last_e["bb_width"]) else 0.05

    if price >= bb_upper * 0.99:
        range_score += 2.5
        range_reasons.append("Price at BB upper → SHORT reversion")
        direction = "SHORT"
    elif price <= bb_lower * 1.01:
        range_score += 2.5
        range_reasons.append("Price at BB lower → LONG reversion")
        direction = "LONG"

    # 3. RSI extremes (0-2 pts) — must be genuinely extreme
    if rsi_val >= RSI_OB:
        range_score += 2.0
        range_reasons.append(f"RSI overbought {rsi_val:.1f}")
        direction = "SHORT"
    elif rsi_val <= RSI_OS:
        range_score += 2.0
        range_reasons.append(f"RSI oversold {rsi_val:.1f}")
        direction = "LONG"
    elif rsi_val >= 68:
        range_score += 0.8
    elif rsi_val <= 32:
        range_score += 0.8

    # 4. Near S/R level (0-2 pts)
    sr_buffer = atr_val * 1.5
    if abs(price - resistance) <= sr_buffer:
        range_score += 2.0
        range_reasons.append(f"Near resistance {resistance:.4g}")
    elif abs(price - support) <= sr_buffer:
        range_score += 2.0
        range_reasons.append(f"Near support {support:.4g}")

    # 5. BB squeeze (0-1 pt)
    if bb_width < 0.04:
        range_score += 1.0
        range_reasons.append("BB squeeze")

    # Volume penalty also applies to range score
    if vol_rat < VOL_WEAK:
        range_score -= 1.0

    # ── PATTERN DETECTION ─────────────────────────────────
    pattern = detect_patterns(df_entry)

    if pattern and pattern.direction != "NEUTRAL":
        # Only award bonus if pattern aligns with current direction
        if pattern.direction == direction or direction == "NEUTRAL":
            direction = pattern.direction
            if trend_score >= range_score:
                trend_score = min(10, trend_score + 0.75)
                trend_reasons.append(f"Pattern: {pattern.name}")
            else:
                range_score = min(10, range_score + 0.75)
                range_reasons.append(f"Pattern: {pattern.name}")

    trend_score = max(0.0, round(trend_score, 2))
    range_score = max(0.0, round(range_score, 2))

    # ── DETERMINE CONDITION ───────────────────────────────
    if trend_score >= range_score and trend_score >= MIN_SCORE_TO_TRADE:
        condition   = "TRENDING"
        final_score = trend_score
        reasons     = trend_reasons
    elif range_score > trend_score and range_score >= MIN_SCORE_TO_TRADE:
        condition   = "RANGING"
        final_score = range_score
        reasons     = range_reasons
    else:
        condition   = "CHOPPY"
        final_score = max(trend_score, range_score)
        reasons     = ["Score below threshold — skipping"]
        direction   = "NEUTRAL"

    # Volume weak cap — cannot be HIGH confidence if volume is poor
    if vol_rat < VOL_WEAK and condition != "CHOPPY":
        condition = "CHOPPY"
        reasons   = [f"Volume {vol_rat:.2f}x below minimum — skipping"] + reasons[:2]
        direction = "NEUTRAL"

    tradeable = condition != "CHOPPY" and direction != "NEUTRAL"

    return MarketCondition(
        symbol=symbol,
        condition=condition,
        direction=direction,
        trend_score=trend_score,
        range_score=range_score,
        final_score=round(final_score, 2),
        adx=round(adx_val, 2),
        rsi=round(rsi_val, 2),
        atr=round(atr_val, 6),
        atr_pct=round(atr_pct, 3),
        volume_ratio=round(vol_rat, 2),
        support=round(support, 6),
        resistance=round(resistance, 6),
        pattern=pattern,
        reasons=reasons,
        tradeable=tradeable
    )
