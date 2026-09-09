from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx


@dataclass
class ExchangeRate:
    source_currency: str
    target_currency: str
    rate: float
    checked_at: datetime


class CurrencyConverter:
    def __init__(self, ttl_hours: int = 12) -> None:
        self.ttl = timedelta(hours=ttl_hours)
        self.cache: dict[tuple[str, str], ExchangeRate] = {}

    async def convert(
        self, amount: float, source: str, target: str = "CAD"
    ) -> tuple[float, ExchangeRate]:
        if source == target:
            rate = ExchangeRate(source, target, 1.0, datetime.now(UTC))
            return amount, rate
        rate = await self.get_rate(source, target)
        return round(amount * rate.rate, 2), rate

    async def get_rate(self, source: str, target: str) -> ExchangeRate:
        key = (source, target)
        cached = self.cache.get(key)
        if cached and datetime.now(UTC) - cached.checked_at < self.ttl:
            return cached
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"https://api.exchangerate.host/convert?from={source}&to={target}"
            )
            response.raise_for_status()
            data = response.json()
        rate_value = float(data.get("info", {}).get("rate") or data.get("result", 0) or 0)
        if rate_value <= 0:
            raise RuntimeError(f"No exchange rate available for {source}->{target}")
        rate = ExchangeRate(source, target, rate_value, datetime.now(UTC))
        self.cache[key] = rate
        return rate
