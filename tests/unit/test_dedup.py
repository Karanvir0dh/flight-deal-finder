from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from flight_deals.config.settings import load_config
from flight_deals.models.domain import FlightOffer, TripType
from flight_deals.scoring.dedup import should_send_alert


def offer(price: float) -> FlightOffer:
    return FlightOffer(
        provider="mock",
        origin="YYZ",
        destination="DUB",
        departure_date=date(2026, 9, 1),
        trip_type=TripType.one_way,
        price=price,
        currency="CAD",
        price_cad=price,
    )


def test_duplicate_suppressed_inside_cooldown() -> None:
    cfg = load_config().notifications
    assert not should_send_alert(offer(104), datetime.now(UTC) - timedelta(hours=2), 104, cfg)


def test_duplicate_resends_on_big_price_drop() -> None:
    cfg = load_config().notifications
    assert should_send_alert(offer(80), datetime.now(UTC) - timedelta(hours=2), 130, cfg)
