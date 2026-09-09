from __future__ import annotations

from flight_deals.utilities.currency import CurrencyConverter


async def test_cad_conversion_is_identity() -> None:
    amount, rate = await CurrencyConverter().convert(123, "CAD", "CAD")
    assert amount == 123
    assert rate.rate == 1
