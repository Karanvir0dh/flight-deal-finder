from __future__ import annotations

import os
from datetime import date
from typing import Any, cast

import httpx

from flight_deals.config.settings import ProviderBudget
from flight_deals.discovery.regions import infer_destination_region, infer_region_from_text
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


class SerpApiProvider:
    """SerpApi integration using documented Google Travel Explore and Google Flights engines."""

    name = "serpapi"
    capabilities = ProviderCapability(
        supports_anywhere_discovery=True,
        supports_exact_search=True,
        supports_booking_links=True,
        supports_baggage_data=False,
        supports_fare_verification=True,
        supports_one_way=True,
        supports_flexible_dates=True,
        supports_quota_reporting=False,
    )

    def __init__(self, budget: ProviderBudget, api_key: str | None = None) -> None:
        self.budget = budget
        self.api_key = api_key or os.getenv("SERPAPI_API_KEY")
        self.requests_used = 0
        self.client = httpx.AsyncClient(base_url="https://serpapi.com", timeout=30)

    def available(self) -> bool:
        return bool(self.api_key)

    async def discover_destinations(self, request: DiscoveryRequest) -> list[DiscoveryResult]:
        if not self.api_key:
            return []
        params: dict[str, Any] = {
            "engine": "google_travel_explore",
            "departure_id": request.origin,
            "currency": request.currency,
            "gl": "ca",
            "hl": "en",
            "api_key": self.api_key,
        }
        if request.arrival_area_id:
            params["arrival_area_id"] = request.arrival_area_id
        if request.arrival_id:
            params["arrival_id"] = request.arrival_id
        if request.return_date:
            params["outbound_date"] = request.earliest_departure.isoformat()
            params["type"] = "1"
            params["return_date"] = request.return_date.isoformat()
        elif request.trip_types == [TripType.one_way]:
            params["outbound_date"] = request.earliest_departure.isoformat()
            params["type"] = "2"
        if request.max_price:
            params["max_price"] = int(request.max_price)
        data = await self._get_json("/search.json", params)
        results: list[DiscoveryResult] = []
        results.extend(self._parse_top_level_flights(data, request))
        for item in data.get("destinations", []):
            first_flight = (item.get("flights") or [{}])[0]
            airport = (
                item.get("destination_airport")
                or item.get("arrival_airport")
                or first_flight.get("arrival_airport")
                or {}
            )
            code = airport.get("code") or airport.get("id") or item.get("airport_code")
            start = item.get("start_date") or item.get("outbound_date")
            price = item.get("flight_price") or item.get("price") or first_flight.get("price")
            if not code or not price:
                continue
            end = item.get("end_date")
            departure_date = date.fromisoformat(start) if start else request.earliest_departure
            region = infer_destination_region(
                code,
                infer_region_from_text(
                    item.get("country"),
                    item.get("name"),
                    item.get("description"),
                    fallback="unknown",
                ),
            )
            results.append(
                DiscoveryResult(
                    provider=self.name,
                    origin=request.origin,
                    destination=code,
                    destination_name=item.get("name", code),
                    region=region,
                    departure_date=departure_date,
                    return_date=date.fromisoformat(end) if end else None,
                    trip_type=TripType.round_trip if end else TripType.one_way,
                    price=float(price),
                    currency=request.currency,
                    stops=int(
                        item.get("number_of_stops") or first_flight.get("number_of_stops") or 0
                    ),
                    airline=item.get("airline") or first_flight.get("airline"),
                    booking_link=item.get("link") or item.get("serpapi_link"),
                    raw=item,
                )
            )
        return results

    def _parse_top_level_flights(
        self, data: dict[str, Any], request: DiscoveryRequest
    ) -> list[DiscoveryResult]:
        results: list[DiscoveryResult] = []
        destination = request.arrival_id
        start = data.get("start_date") or request.earliest_departure.isoformat()
        end = data.get("end_date")
        for item in data.get("flights", []):
            arrival_airport = item.get("arrival_airport") or {}
            code = arrival_airport.get("id") or arrival_airport.get("code") or destination
            price = item.get("price") or item.get("flight_price")
            if not code or not price:
                continue
            region = infer_destination_region(code, request.region or "unknown")
            results.append(
                DiscoveryResult(
                    provider=self.name,
                    origin=request.origin,
                    destination=code,
                    destination_name=arrival_airport.get("name") or code,
                    region=region,
                    departure_date=date.fromisoformat(start),
                    return_date=date.fromisoformat(end) if end else None,
                    trip_type=TripType.round_trip if end else TripType.one_way,
                    price=float(price),
                    currency=request.currency,
                    stops=int(item.get("number_of_stops") or 0),
                    airline=item.get("airline"),
                    booking_link=data.get("link") or data.get("serpapi_link"),
                    raw=item,
                )
            )
        return results

    async def search_flights(self, request: FlightSearchRequest) -> list[FlightOffer]:
        if not self.api_key:
            return []
        params: dict[str, Any] = {
            "engine": "google_flights",
            "departure_id": request.origin,
            "arrival_id": request.destination,
            "outbound_date": request.departure_date.isoformat(),
            "currency": request.currency,
            "gl": "ca",
            "hl": "en",
            "travel_class": "1",
            "type": "2" if request.trip_type == TripType.one_way else "1",
            "api_key": self.api_key,
        }
        if request.return_date:
            params["return_date"] = request.return_date.isoformat()
        data = await self._get_json("/search.json", params)
        offers: list[FlightOffer] = []
        for item in data.get("best_flights", []) + data.get("other_flights", []):
            price = item.get("price")
            if price is None:
                continue
            flights = item.get("flights", [])
            carriers = sorted({f.get("airline", "") for f in flights if f.get("airline")})
            offers.append(
                FlightOffer(
                    provider=self.name,
                    origin=request.origin,
                    destination=request.destination,
                    departure_date=request.departure_date,
                    return_date=request.return_date,
                    trip_type=request.trip_type,
                    price=float(price),
                    currency=request.currency,
                    price_cad=float(price),
                    carriers=carriers,
                    stops=max(len(flights) - 1, 0),
                    total_duration_minutes=int(item.get("total_duration") or 0),
                    layovers=[str(layover.get("name")) for layover in item.get("layovers", [])],
                    booking_link=item.get("booking_token"),
                    raw_provider_id=item.get("departure_token") or item.get("booking_token"),
                    segments=[],
                )
            )
        return offers

    async def verify_offer(self, offer: FlightOffer) -> VerificationResult:
        return VerificationResult(
            status="Verified by one provider" if offer.booking_link else "Unverified",
            verified_price_cad=offer.price_cad,
            provider_prices={self.name: offer.price_cad},
            booking_link=offer.booking_link,
            notes="SerpApi detailed result was used for verification.",
        )

    async def get_quota_status(self) -> ProviderQuota:
        return ProviderQuota(
            provider=self.name,
            monthly_quota=self.budget.monthly_quota,
            requests_used=self.requests_used,
            estimated_remaining=max(self.budget.monthly_quota - self.requests_used, 0),
            per_run_budget=self.budget.per_run_budget,
            reserved_for_verification=self.budget.reserve_for_verification,
            healthy=bool(self.api_key),
        )

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.requests_used += 1
        try:
            response = await self.client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"SerpApi transport error: {exc.__class__.__name__}") from exc
        try:
            data = cast(dict[str, Any], response.json())
        except ValueError:
            data = {}
        if response.status_code >= 400:
            provider_error = data.get("error") or data.get("message") or response.reason_phrase
            raise RuntimeError(f"SerpApi request failed ({response.status_code}): {provider_error}")
        if data.get("error"):
            raise RuntimeError(f"SerpApi error: {data['error']}")
        return data
