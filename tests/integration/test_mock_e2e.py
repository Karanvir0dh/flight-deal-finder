from __future__ import annotations

from flight_deals.config.settings import load_config
from flight_deals.database.session import init_db
from flight_deals.providers.factory import build_providers
from flight_deals.services.search_service import FlightDealService


async def test_mock_mode_end_to_end() -> None:
    init_db()
    config = load_config()
    service = FlightDealService(config, build_providers(config, force_mock=True))
    result = await service.run_once(dry_run=True)
    assert result.candidates
    assert any(candidate.offer.destination == "DUB" for candidate in result.candidates)
