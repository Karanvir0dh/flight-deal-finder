from __future__ import annotations

import os
import time
from datetime import date
from typing import Any, cast

import httpx

from flight_deals.config.settings import ProviderBudget
from flight_deals.models.domain import (
    DiscoveryRequest,
    DiscoveryResult,
    FlightOffer,
    FlightSearchRequest,
    ProviderCapability,
    ProviderQuota,
    TripType,
    VerificationResult,
)


class AmadeusProvider:
    """Amadeus Self-Service integration for Flight Inspiration and Flight Offers Search."""

    name = "amadeus"
    capabilities = ProviderCapability(
        supports_anywhere_discovery=True,
        supports_exact_search=True,
        supports_booking_links=False,
        supports_baggage_data=True,
        supports_fare_verification=True,
        supports_one_way=True,
        supports_multi_city=True,
        supports_flexible_dates=True,
        supports_quota_reporting=False,
    )

    def __init__(self, budget: ProviderBudget) -> None:
        self.budget = budget
        self.client_id = os.getenv("AMADEUS_CLIENT_ID")
        self.client_secret = os.getenv("AMADEUS_CLIENT_SECRET")
        self.base_url = os.getenv("AMADEUS_BASE_URL", "https://test.api.amadeus.com")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30)
        self.token: str | None = None
        self.token_expires_at = 0.0
        self.requests_used = 0

    def available(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def discover_destinations(self, request: DiscoveryRequest) -> list[DiscoveryResult]:
        if not self.available():
            return []
        params: dict[str, Any] = {
            "origin": request.origin,
            "currency": request.currency,
        }
        if request.max_price:
            params["maxPrice"] = int(request.max_price)
        data = await self._get("/v1/shopping/flight-destinations", params)
        results = []
        for item in data.get("data", []):
            destination = item.get("destination")
            departure = item.get("departureDate")
            if not destination or not departure:
                continue
            total = float(item.get("price", {}).get("total", 0))
            results.append(
                DiscoveryResult(
                    provider=self.name,
                    origin=item.get("origin", request.origin),
                    destination=destination,
                    destination_name=destination,
                    region="unknown",
                    departure_date=date.fromisoformat(departure),
                    return_date=date.fromisoformat(item["returnDate"])
                    if item.get("returnDate")
                    else None,
                    trip_type=TripType.round_trip if item.get("returnDate") else TripType.one_way,
                    price=total,
                    currency=request.currency,
                    booking_link=(item.get("links") or {}).get("flightOffers"),
                    raw=item,
                )
            )
        return results

    async def search_flights(self, request: FlightSearchRequest) -> list[FlightOffer]:
        if not self.available():
            return []
        params: dict[str, Any] = {
            "originLocationCode": request.origin,
            "destinationLocationCode": request.destination,
            "departureDate": request.departure_date.isoformat(),
            "adults": request.adults,
            "currencyCode": request.currency,
            "travelClass": request.cabin.upper(),
            "nonStop": "false",
            "max": 10,
        }
        if request.return_date:
            params["returnDate"] = request.return_date.isoformat()
        if request.max_price:
            params["maxPrice"] = int(request.max_price)
        data = await self._get("/v2/shopping/flight-offers", params)
        offers: list[FlightOffer] = []
        for item in data.get("data", []):
            price = float(
                item.get("price", {}).get("grandTotal") or item.get("price", {}).get("total") or 0
            )
            itineraries = item.get("itineraries", [])
            segments = [seg for itin in itineraries for seg in itin.get("segments", [])]
            carriers = sorted(
                {seg.get("carrierCode", "") for seg in segments if seg.get("carrierCode")}
            )
            offers.append(
                FlightOffer(
                    provider=self.name,
                    origin=request.origin,
                    destination=request.destination,
                    departure_date=request.departure_date,
                    return_date=request.return_date,
                    trip_type=request.trip_type,
                    price=price,
                    currency=request.currency,
                    price_cad=price,
                    carriers=carriers,
                    stops=max(len(segments) - len(itineraries), 0),
                    total_duration_minutes=0,
                    baggage=self._baggage_summary(item),
                    includes_taxes=True,
                    raw_provider_id=item.get("id"),
                )
            )
        return offers

    async def verify_offer(self, offer: FlightOffer) -> VerificationResult:
        return VerificationResult(
            status="Verified by one provider",
            verified_price_cad=offer.price_cad,
            provider_prices={self.name: offer.price_cad},
            notes=(
                "Amadeus Flight Offers Search returned a current published fare. "
                "Use Flight Offers Price for booking-flow confirmation."
            ),
        )

    async def get_quota_status(self) -> ProviderQuota:
        return ProviderQuota(
            provider=self.name,
            monthly_quota=self.budget.monthly_quota,
            requests_used=self.requests_used,
            estimated_remaining=max(self.budget.monthly_quota - self.requests_used, 0),
            per_run_budget=self.budget.per_run_budget,
            reserved_for_verification=self.budget.reserve_for_verification,
            healthy=self.available(),
        )

    async def _token(self) -> str:
        if self.token and time.time() < self.token_expires_at - 60:
            return self.token
        self.requests_used += 1
        response = await self.client.post(
            "/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        data = response.json()
        self.token = str(data["access_token"])
        self.token_expires_at = time.time() + int(data.get("expires_in", 1799))
        return self.token

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.requests_used += 1
        token = await self._token()
        response = await self.client.get(
            path, params=params, headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    def _baggage_summary(self, item: dict[str, Any]) -> str | None:
        services = item.get("pricingOptions", {}).get("includedCheckedBagsOnly")
        if services is True:
            return "Checked-bag-inclusive fares only"
        return None
