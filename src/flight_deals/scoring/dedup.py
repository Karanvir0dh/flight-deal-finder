from __future__ import annotations

from datetime import UTC, datetime, timedelta

from flight_deals.config.settings import NotificationConfig
from flight_deals.models.domain import FlightOffer


def should_send_alert(
    offer: FlightOffer,
    previous_alerted_at: datetime | None,
    previous_price_cad: float | None,
    config: NotificationConfig,
) -> bool:
    if previous_alerted_at is None or previous_price_cad is None:
        return True
    age = datetime.now(UTC) - previous_alerted_at
    price_drop = previous_price_cad - offer.price_cad
    percent_drop = price_drop / previous_price_cad * 100 if previous_price_cad else 0
    if price_drop >= config.resend_price_drop_cad:
        return True
    if percent_drop >= config.resend_price_drop_percent:
        return True
    return age >= timedelta(hours=config.duplicate_cooldown_hours)
