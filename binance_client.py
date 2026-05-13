"""
Binance Futures public REST client.
Uses httpx (async) which uses the system DNS resolver correctly on Windows,
unlike aiohttp which has a known async DNS bug on Windows event loops.
No API key required for market data.
"""
import asyncio
import httpx
import pandas as pd
from typing import Optional
import logging

logger = logging.getLogger(__name__)

BASE_FUTURES = "https://fapi.binance.com"
BASE_SPOT    = "https://api.binance.com"


class BinanceClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get(self, url: str, params: dict = None) -> dict | list:
        client = self._get_client()
        resp = await client.get(url, params=params or {})
        resp.raise_for_status()
        return resp.json()

    # ── Public Methods ──────────────────────────────────────

    async def get_usdt_perp_pairs(self) -> list[str]:
        """Return all active USDT perpetual symbols."""
        data = await self._get(f"{BASE_FUTURES}/fapi/v1/exchangeInfo")
        symbols = [
            s["symbol"]
            for s in data["symbols"]
            if s["quoteAsset"] == "USDT"
            and s["contractType"] == "PERPETUAL"
            and s["status"] == "TRADING"
        ]
        return sorted(symbols)

    async def get_24h_tickers(self) -> list[dict]:
        """Get 24h ticker data — futures first, spot fallback."""
        try:
            return await self._get(f"{BASE_FUTURES}/fapi/v1/ticker/24hr")
        except Exception:
            return await self._get(f"{BASE_SPOT}/api/v3/ticker/24hr")

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 210
    ) -> pd.DataFrame:
        """Fetch OHLCV candles — futures first, spot fallback."""
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        try:
            data = await self._get(f"{BASE_FUTURES}/fapi/v1/klines", params)
        except Exception:
            data = await self._get(f"{BASE_SPOT}/api/v3/klines", params)

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[col] = pd.to_numeric(df[col])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df.set_index("open_time", inplace=True)
        return df

    async def get_multi_tf_klines(
        self,
        symbol: str,
        timeframes: list[str],
        limit: int = 210
    ) -> dict[str, pd.DataFrame]:
        """Fetch multiple timeframes concurrently."""
        tasks = [self.get_klines(symbol, tf, limit) for tf in timeframes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            tf: r for tf, r in zip(timeframes, results)
            if isinstance(r, pd.DataFrame) and not r.empty
        }
