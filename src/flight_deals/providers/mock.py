from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from flight_deals.config.settings import ProviderBudget
from flight_deals.models.domain import (
    DiscoveryRequest,
    DiscoveryResult,
    FlightOffer,
    FlightSearchRequest,
    ProviderCapability,
    ProviderQuota,
    Segment,
    TripType,
    VerificationResult,
)


class MockFlightProvider:
    name = "mock"
    capabilities = ProviderCapability(
        supports_anywhere_discovery=True,
        supports_exact_search=True,
        supports_booking_links=True,
        supports_baggage_data=True,
        supports_fare_verification=True,
        supports_one_way=True,
        supports_flexible_dates=True,
        supports_quota_reporting=True,
    )

    def __init__(self, budget: ProviderBudget) -> None:
        self.budget = budget
        self.requests_used = 0

    async def discover_destinations(self, request: DiscoveryRequest) -> list[DiscoveryResult]:
        self.requests_used += 1
        base = request.earliest_departure + timedelta(days=28)
        return [
            DiscoveryResult(
                provider=self.name,
                origin=request.origin,
                destination="DUB",
                destination_name="Dublin",
                region="europe",
                departure_date=base,
                return_date=None,
                trip_type=TripType.one_way,
                price=104,
                currency="CAD",
                stops=1,
                airline="WestJet",
                booking_link="https://example.invalid/book/yyz-dub-104",
            ),
            DiscoveryResult(
                provider=self.name,
                origin=request.origin,
                destination="LIS",
                destination_name="Lisbon",
                region="europe",
                departure_date=base + timedelta(days=14),
                return_date=base + timedelta(days=23),
                trip_type=TripType.round_trip,
                price=438,
                currency="CAD",
                stops=1,
                airline="Air Transat",
                booking_link="https://example.invalid/book/yyz-lis-438",
            ),
            DiscoveryResult(
                provider=self.name,
                origin=request.origin,
                destination="SAN",
                destination_name="San Diego",
                region="united_states",
                departure_date=base + timedelta(days=42),
                return_date=base + timedelta(days=49),
                trip_type=TripType.round_trip,
                price=319,
                currency="CAD",
                stops=1,
                airline="United",
            ),
        ]

    async def search_flights(self, request: FlightSearchRequest) -> list[FlightOffer]:
        self.requests_used += 1
        price = (
            104.0
            if request.destination == "DUB" and request.trip_type == TripType.one_way
            else 438.0
        )
        dep = datetime.combine(request.departure_date, time(20, 15), tzinfo=UTC)
        arr = dep + timedelta(hours=8, minutes=30)
        segments = [
            Segment(
                origin=request.origin,
                destination=request.destination,
                departure_at=dep,
                arrival_at=arr,
                carrier="WS",
                flight_number="WS42",
                duration_minutes=510,
            )
        ]
        return [
            FlightOffer(
                provider=self.name,
                origin=request.origin,
                destination=request.destination,
                departure_date=request.departure_date,
                return_date=request.return_date,
                trip_type=request.trip_type,
                price=price,
                currency="CAD",
                price_cad=price,
                segments=segments,
                carriers=["WS"],
                stops=0 if request.destination == "DUB" else 1,
                total_duration_minutes=510,
                layovers=[],
                baggage="Personal item included; carry-on may cost extra",
                basic_economy=True,
                includes_taxes=True,
                booking_link=f"https://example.invalid/book/{request.origin.lower()}-{request.destination.lower()}",
                raw_provider_id=f"mock-{request.origin}-{request.destination}-{request.departure_date}",
            )
        ]

    async def verify_offer(self, offer: FlightOffer) -> VerificationResult:
        self.requests_used += 1
        return VerificationResult(
            status="Verified by one provider",
            verified_price_cad=offer.price_cad,
            provider_prices={self.name: offer.price_cad},
            booking_link=offer.booking_link,
            notes="Mock provider rechecked the same deterministic fare.",
        )

    async def get_quota_status(self) -> ProviderQuota:
        return ProviderQuota(
            provider=self.name,
            monthly_quota=self.budget.monthly_quota,
            requests_used=self.requests_used,
            estimated_remaining=max(self.budget.monthly_quota - self.requests_used, 0),
            reset_date=date.today().replace(day=1),
            per_run_budget=self.budget.per_run_budget,
            reserved_for_verification=self.budget.reserve_for_verification,
        )
