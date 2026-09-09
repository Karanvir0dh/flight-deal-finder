from __future__ import annotations

from datetime import date

from flight_deals.config.settings import load_config
from flight_deals.models.domain import FlightOffer, TripType, VerificationResult
from flight_deals.notifications.render import render_alert
from flight_deals.scoring.engine import DealScorer


def test_notification_render_contains_booking_warning() -> None:
    offer = FlightOffer(
        provider="mock",
        origin="YYZ",
        destination="DUB",
        departure_date=date(2026, 9, 1),
        trip_type=TripType.one_way,
        price=104,
        currency="CAD",
        price_cad=104,
        booking_link="https://example.invalid",
    )
    candidate = DealScorer(load_config()).score(
        offer, [400, 350, 300], VerificationResult(status="Verified by one provider")
    )
    subject, html, text = render_alert(candidate)
    assert "YYZ to DUB" in subject
    assert "Verify the final fare" in html
    assert "Booking confidence" in text
