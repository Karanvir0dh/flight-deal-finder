from __future__ import annotations

from typing import Protocol

from flight_deals.models.domain import (
    DiscoveryRequest,
    DiscoveryResult,
    FlightOffer,
    FlightSearchRequest,
    ProviderCapability,
    ProviderQuota,
    VerificationResult,
)


class FlightProvider(Protocol):
    name: str
    capabilities: ProviderCapability

    async def discover_destinations(self, request: DiscoveryRequest) -> list[DiscoveryResult]:
        """Return broad destination/date candidates."""

    async def search_flights(self, request: FlightSearchRequest) -> list[FlightOffer]:
        """Return detailed fares for a specific route and date."""

    async def verify_offer(self, offer: FlightOffer) -> VerificationResult:
        """Re-check a candidate fare before alerting."""

    async def get_quota_status(self) -> ProviderQuota:
        """Return best-known quota and health state."""
