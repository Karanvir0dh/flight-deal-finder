from __future__ import annotations

from flight_deals.config.settings import AppConfig
from flight_deals.providers.amadeus import AmadeusProvider
from flight_deals.providers.base import FlightProvider
from flight_deals.providers.mock import MockFlightProvider
from flight_deals.providers.serpapi import SerpApiProvider


def build_providers(config: AppConfig, force_mock: bool = False) -> list[FlightProvider]:
    if force_mock:
        return [MockFlightProvider(config.providers["mock"])]
    providers: list[FlightProvider] = []
    serp_budget = config.providers.get("serpapi")
    if serp_budget and serp_budget.enabled:
        serp = SerpApiProvider(serp_budget)
        if serp.available():
            providers.append(serp)
    amadeus_budget = config.providers.get("amadeus")
    if amadeus_budget and amadeus_budget.enabled:
        amadeus = AmadeusProvider(amadeus_budget)
        if amadeus.available():
            providers.append(amadeus)
    if not providers:
        providers.append(MockFlightProvider(config.providers["mock"]))
    return providers
