"""
Chart pattern detector: falling wedge, rising wedge, bull/bear flag,
ascending/descending/symmetrical triangle, cup and handle.
Returns pattern name + direction or None.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from config import PATTERN_LOOKBACK, MIN_PATTERN_CANDLES


@dataclass
class PatternResult:
    name: str           # e.g. "Falling Wedge"
    direction: str      # "LONG" or "SHORT"
    breakout: bool      # True if price already broke out
    strength: float     # 0-1 confidence score


def _linear_slope(values: np.ndarray) -> float:
    x = np.arange(len(values), dtype=float)
    if x.std() == 0:
        return 0.0
    return float(np.polyfit(x, values, 1)[0])


def _pivot_highs(arr: np.ndarray, wing: int = 2) -> list[tuple[int, float]]:
    out = []
    for i in range(wing, len(arr) - wing):
        if arr[i] == arr[i-wing:i+wing+1].max():
            out.append((i, arr[i]))
    return out


def _pivot_lows(arr: np.ndarray, wing: int = 2) -> list[tuple[int, float]]:
    out = []
    for i in range(wing, len(arr) - wing):
        if arr[i] == arr[i-wing:i+wing+1].min():
            out.append((i, arr[i]))
    return out


def detect_patterns(df: pd.DataFrame) -> Optional[PatternResult]:
    """
    Run all pattern detectors and return the strongest match or None.
    Priority: wedges > flags > triangles > cup
    """
    sub = df.tail(PATTERN_LOOKBACK).copy()
    if len(sub) < MIN_PATTERN_CANDLES:
        return None

    highs  = sub["high"].values
    lows   = sub["low"].values
    closes = sub["close"].values
    last   = closes[-1]

    ph = _pivot_highs(highs)
    pl = _pivot_lows(lows)

    results: list[PatternResult] = []

    # ── 1. WEDGES ───────────────────────────────────────────
    if len(ph) >= 2 and len(pl) >= 2:
        slope_h = _linear_slope(np.array([v for _, v in ph]))
        slope_l = _linear_slope(np.array([v for _, v in pl]))

        # Falling Wedge → LONG (both slopes negative, lower slope less steep)
        if slope_h < -0.0001 and slope_l < -0.0001 and slope_l > slope_h:
            breakout = last > max(v for _, v in ph[-2:])
            results.append(PatternResult("Falling Wedge", "LONG", breakout, 0.85))

        # Rising Wedge → SHORT (both slopes positive, upper slope less steep)
        elif slope_h > 0.0001 and slope_l > 0.0001 and slope_h < slope_l:
            breakout = last < min(v for _, v in pl[-2:])
            results.append(PatternResult("Rising Wedge", "SHORT", breakout, 0.85))

    # ── 2. FLAGS ────────────────────────────────────────────
    if len(sub) >= 20:
        # Bull Flag: strong up move then tight downward consolidation
        first_half  = closes[:len(closes)//2]
        second_half = closes[len(closes)//2:]
        fh_move = (first_half[-1] - first_half[0]) / (first_half[0] + 1e-9)
        sh_move = (second_half[-1] - second_half[0]) / (second_half[0] + 1e-9)

        if fh_move > 0.04 and -0.06 < sh_move < 0.0:
            results.append(PatternResult("Bull Flag", "LONG", False, 0.80))

        elif fh_move < -0.04 and 0.0 < sh_move < 0.06:
            results.append(PatternResult("Bear Flag", "SHORT", False, 0.80))

    # ── 3. TRIANGLES ────────────────────────────────────────
    if len(ph) >= 2 and len(pl) >= 2:
        slope_h = _linear_slope(np.array([v for _, v in ph]))
        slope_l = _linear_slope(np.array([v for _, v in pl]))

        # Ascending Triangle: flat top, rising lows → LONG
        if abs(slope_h) < 0.0001 and slope_l > 0.0001:
            breakout = last > np.mean([v for _, v in ph])
            results.append(PatternResult("Ascending Triangle", "LONG", breakout, 0.78))

        # Descending Triangle: flat bottom, falling highs → SHORT
        elif abs(slope_l) < 0.0001 and slope_h < -0.0001:
            breakout = last < np.mean([v for _, v in pl])
            results.append(PatternResult("Descending Triangle", "SHORT", breakout, 0.78))

        # Symmetrical Triangle: converging slopes
        elif slope_h < -0.0001 and slope_l > 0.0001:
            # Direction determined by trend (caller decides)
            results.append(PatternResult("Symmetrical Triangle", "NEUTRAL", False, 0.65))

    # ── 4. CUP AND HANDLE ───────────────────────────────────
    if len(sub) >= 30:
        mid_idx = len(closes) // 2
        cup_left  = closes[0]
        cup_right = closes[-1]
        cup_bottom = closes[mid_idx - 5: mid_idx + 5].min()

        depth = (min(cup_left, cup_right) - cup_bottom) / (min(cup_left, cup_right) + 1e-9)
        if 0.05 < depth < 0.35 and abs(cup_left - cup_right) / (cup_left + 1e-9) < 0.05:
            results.append(PatternResult("Cup and Handle", "LONG", False, 0.75))

    if not results:
        return None

    # Return highest strength pattern
    return max(results, key=lambda r: r.strength)
