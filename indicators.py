"""
Pure-numpy/pandas indicator calculations — no TA-Lib dependency.
"""
import numpy as np
import pandas as pd
from config import (
    EMA_FAST, EMA_MID, EMA_SLOW, RSI_PERIOD,
    BB_PERIOD, BB_STD, ADX_PERIOD, VOLUME_MA_PERIOD
)


# ── Core Indicators ─────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def bollinger_bands(series: pd.Series, period: int = BB_PERIOD, std: float = BB_STD):
    mid = series.rolling(period).mean()
    dev = series.rolling(period).std()
    return mid - std * dev, mid, mid + std * dev


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm  = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    overlap  = (plus_dm > 0) & (minus_dm > 0)
    plus_dm[overlap & (minus_dm >= plus_dm)]  = 0
    minus_dm[overlap & (plus_dm  > minus_dm)] = 0

    tr_val = atr(df, 1)
    atr_s  = tr_val.ewm(span=period, adjust=False).mean()

    plus_di  = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr_s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(span=period, adjust=False).mean(), plus_di, minus_di


def volume_ma(df: pd.DataFrame, period: int = VOLUME_MA_PERIOD) -> pd.Series:
    return df["volume"].rolling(period).mean()


# ── Enriched DataFrame ──────────────────────────────────────

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicators to a candle DataFrame in-place."""
    if len(df) < VOLUME_MA_PERIOD + 5:
        return df

    c = df["close"]

    df["ema_fast"] = ema(c, EMA_FAST)
    df["ema_mid"]  = ema(c, EMA_MID)
    df["ema_slow"] = ema(c, EMA_SLOW)
    df["rsi"]      = rsi(c)
    df["atr"]      = atr(df)

    df["bb_lower"], df["bb_mid"], df["bb_upper"] = bollinger_bands(c)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    adx_val, plus_di, minus_di = adx(df)
    df["adx"]      = adx_val
    df["plus_di"]  = plus_di
    df["minus_di"] = minus_di

    df["vol_ma"]      = volume_ma(df)
    df["vol_ratio"]   = df["volume"] / df["vol_ma"]

    return df


# ── Market Structure Helpers ────────────────────────────────

def is_higher_highs_higher_lows(df: pd.DataFrame, lookback: int = 20) -> bool:
    """Check for bullish market structure (HH + HL)."""
    sub = df.tail(lookback)
    highs = sub["high"].values
    lows  = sub["low"].values
    pivots_h = [highs[i] for i in range(2, len(highs)-2)
                if highs[i] == max(highs[i-2:i+3])]
    pivots_l = [lows[i]  for i in range(2, len(lows)-2)
                if lows[i]  == min(lows[i-2:i+3])]
    if len(pivots_h) < 2 or len(pivots_l) < 2:
        return False
    return pivots_h[-1] > pivots_h[-2] and pivots_l[-1] > pivots_l[-2]


def is_lower_lows_lower_highs(df: pd.DataFrame, lookback: int = 20) -> bool:
    """Check for bearish market structure (LL + LH)."""
    sub = df.tail(lookback)
    highs = sub["high"].values
    lows  = sub["low"].values
    pivots_h = [highs[i] for i in range(2, len(highs)-2)
                if highs[i] == max(highs[i-2:i+3])]
    pivots_l = [lows[i]  for i in range(2, len(lows)-2)
                if lows[i]  == min(lows[i-2:i+3])]
    if len(pivots_h) < 2 or len(pivots_l) < 2:
        return False
    return pivots_l[-1] < pivots_l[-2] and pivots_h[-1] < pivots_h[-2]


def find_support_resistance(df: pd.DataFrame, lookback: int = 50) -> tuple[float, float]:
    """Simple swing-based S/R levels."""
    sub = df.tail(lookback)
    highs = sub["high"].values
    lows  = sub["low"].values
    resistance = max(highs[i] for i in range(2, len(highs)-2)
                     if highs[i] == max(highs[i-2:i+3])) if len(highs) > 5 else sub["high"].max()
    support    = min(lows[i]  for i in range(2, len(lows)-2)
                     if lows[i]  == min(lows[i-2:i+3]))  if len(lows)  > 5 else sub["low"].min()
    return support, resistance
