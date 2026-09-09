from __future__ import annotations

from datetime import date

from flight_deals.config.settings import load_config
from flight_deals.models.domain import FlightOffer, TripType, VerificationResult
from flight_deals.scoring.engine import DealScorer


def test_exceptional_mock_dublin_fare_scores_high() -> None:
    offer = FlightOffer(
        provider="mock",
        origin="YYZ",
        destination="DUB",
        departure_date=date(2026, 9, 1),
        trip_type=TripType.one_way,
        price=104,
        currency="CAD",
        price_cad=104,
        carriers=["WS"],
        stops=0,
        total_duration_minutes=510,
        baggage="personal item",
        booking_link="https://example.invalid",
        includes_taxes=True,
    )
    candidate = DealScorer(load_config()).score(
        offer,
        route_prices=[450, 420, 390, 360, 340, 300, 280],
        verification=VerificationResult(status="Verified by one provider", verified_price_cad=104),
    )
    assert candidate.score >= 80
    assert candidate.level.value in {"EXCEPTIONAL", "POSSIBLE MISTAKE FARE"}
    assert "below route median" in candidate.explanation
