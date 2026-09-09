from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from flight_deals.config.settings import AppConfig
from flight_deals.database.models import SchedulerState, SearchRun
from flight_deals.database.session import SessionLocal
from flight_deals.discovery.regions import (
    OUTSIDE_NORTH_AMERICA_REGIONS,
    SERPAPI_AREA_BY_REGION,
    expand_region_filter,
    infer_destination_region,
)
from flight_deals.models.domain import (
    DealCandidate,
    DiscoveryRequest,
    FlightSearchRequest,
    TripType,
)
from flight_deals.notifications.adapters import build_notification_adapters
from flight_deals.providers.base import FlightProvider
from flight_deals.repositories.store import (
    latest_notification,
    mark_notification,
    route_prices,
    store_deal,
    store_observation,
)
from flight_deals.scoring.dedup import should_send_alert
from flight_deals.scoring.engine import DealScorer

logger = logging.getLogger(__name__)


class SearchCycleResult:
    def __init__(
        self,
        correlation_id: str,
        candidates: list[DealCandidate],
        alerts_sent: int,
        raw_discoveries: int = 0,
        filtered_discoveries: int = 0,
        offers_seen: int = 0,
    ) -> None:
        self.correlation_id = correlation_id
        self.candidates = candidates
        self.alerts_sent = alerts_sent
        self.raw_discoveries = raw_discoveries
        self.filtered_discoveries = filtered_discoveries
        self.offers_seen = offers_seen


class FlightDealService:
    def __init__(self, config: AppConfig, providers: list[FlightProvider]) -> None:
        self.config = config
        self.providers = providers
        self.scorer = DealScorer(config)

    async def run_once(
        self,
        dry_run: bool = False,
        origins: list[str] | None = None,
        region: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        max_price: float | None = None,
        one_way: bool = False,
        round_trip: bool = False,
        debug: bool = False,
        searches: int | None = None,
    ) -> SearchCycleResult:
        correlation_id = uuid.uuid4().hex
        today = date.today()
        selected_origins = origins or [self.config.search.origins.primary[0]]
        earliest = start_date or today + timedelta(days=self.config.search.earliest_departure_days)
        latest = end_date or today + timedelta(days=self.config.search.latest_departure_days)
        trip_types: list[TripType] = self.config.search.trip_types
        if one_way and not round_trip:
            trip_types = [TripType.one_way]
        elif round_trip and not one_way:
            trip_types = [TripType.round_trip]
        allowed_regions = expand_region_filter(region)
        search_limit = searches or self.config.search.regional_searches_per_run
        candidates: list[DealCandidate] = []
        alerts_sent = 0
        raw_discoveries_count = 0
        filtered_discoveries_count = 0
        offers_seen = 0
        discovery_request_count = 0
        adapters = build_notification_adapters()
        with SessionLocal() as session:
            rotation_seed = self._next_rotation_seed(session, region or "all")
            search_run = SearchRun(
                correlation_id=correlation_id,
                status="running",
                summary=(
                    f"origins={','.join(selected_origins)}; "
                    f"region={region or 'all'}; "
                    f"start={earliest}; "
                    f"end={latest}; "
                    f"trip_types={','.join(str(trip_type) for trip_type in trip_types)}; "
                    f"dry_run={dry_run}"
                ),
            )
            session.add(search_run)
            session.flush()
            for provider in self.providers:
                for origin in selected_origins:
                    discovery_requests = self._build_discovery_requests(
                        origin=origin,
                        earliest=earliest,
                        latest=latest,
                        return_date=end_date if round_trip else None,
                        trip_types=trip_types,
                        region=region,
                        max_price=max_price,
                        limit=search_limit,
                        rotation_seed=rotation_seed,
                    )
                    provider_budget = self.config.providers.get(
                        provider.name, self.config.providers["mock"]
                    ).per_run_budget
                    accepted_for_detail = 0
                    seen_discoveries: set[tuple[str, date, date | None]] = set()
                    for request in discovery_requests:
                        discovery_request_count += 1
                        try:
                            discoveries = await provider.discover_destinations(request)
                        except RuntimeError as exc:
                            logger.warning(
                                "Provider discovery failed",
                                extra={"provider": provider.name, "error": str(exc)},
                            )
                            continue
                        raw_discoveries_count += len(discoveries)
                        for discovery in discoveries:
                            discovery_key = (
                                discovery.destination,
                                discovery.departure_date,
                                discovery.return_date,
                            )
                            if discovery_key in seen_discoveries:
                                continue
                            seen_discoveries.add(discovery_key)
                            discovery.region = infer_destination_region(
                                discovery.destination,
                                discovery.region,
                            )
                            if allowed_regions and discovery.region not in allowed_regions:
                                if debug:
                                    logger.info(
                                        "Filtered destination by region",
                                        extra={
                                            "destination": discovery.destination,
                                            "destination_name": discovery.destination_name,
                                            "region": discovery.region,
                                        },
                                    )
                                continue
                            if not earliest <= discovery.departure_date <= latest:
                                continue
                            if accepted_for_detail >= provider_budget:
                                continue
                            accepted_for_detail += 1
                            filtered_discoveries_count += 1
                            if debug:
                                logger.info(
                                    "Accepted destination for detailed search",
                                    extra={
                                        "destination": discovery.destination,
                                        "destination_name": discovery.destination_name,
                                        "region": discovery.region,
                                    },
                                )
                            try:
                                offers = await provider.search_flights(
                                    FlightSearchRequest(
                                        origin=discovery.origin,
                                        destination=discovery.destination,
                                        departure_date=discovery.departure_date,
                                        return_date=discovery.return_date,
                                        trip_type=discovery.trip_type,
                                        adults=self.config.search.adults,
                                        cabin=self.config.search.cabin,
                                        currency=self.config.profile.currency,
                                        maximum_stops=self.config.search.maximum_stops,
                                        max_price=max_price,
                                    )
                                )
                            except RuntimeError as exc:
                                logger.warning(
                                    "Provider flight search failed",
                                    extra={
                                        "provider": provider.name,
                                        "origin": discovery.origin,
                                        "destination": discovery.destination,
                                        "error": str(exc),
                                    },
                                )
                                continue
                            offers_seen += len(offers)
                            for offer in offers:
                                observation = store_observation(session, offer)
                                prices = route_prices(session, offer)
                                candidate = self.scorer.score(offer, prices)
                                if candidate.level.value in {
                                    "GREAT",
                                    "EXCEPTIONAL",
                                    "POSSIBLE MISTAKE FARE",
                                }:
                                    verification = await provider.verify_offer(offer)
                                    candidate = self.scorer.score(offer, prices, verification)
                                deal = store_deal(session, candidate, observation)
                                candidates.append(candidate)
                                previous_at, previous_price = latest_notification(
                                    session, offer.fingerprint_key
                                )
                                if (
                                    not dry_run
                                    and candidate.level.value
                                    in {"GREAT", "EXCEPTIONAL", "POSSIBLE MISTAKE FARE"}
                                    and should_send_alert(
                                        offer,
                                        previous_at,
                                        previous_price,
                                        self.config.notifications,
                                    )
                                ):
                                    for adapter in adapters:
                                        try:
                                            await adapter.send_deal_alert(candidate)
                                            mark_notification(
                                                session,
                                                deal.id,
                                                offer.fingerprint_key,
                                                adapter.name,
                                                "sent",
                                            )
                                            alerts_sent += 1
                                        except Exception as exc:
                                            mark_notification(
                                                session,
                                                deal.id,
                                                offer.fingerprint_key,
                                                adapter.name,
                                                "failed",
                                                str(exc),
                                            )
            search_run.finished_at = datetime.now(UTC)
            search_run.status = "completed"
            search_run.summary = (
                f"{search_run.summary}; raw_discoveries={raw_discoveries_count}; "
                f"filtered_discoveries={filtered_discoveries_count}; offers={offers_seen}; "
                f"discovery_requests={discovery_request_count}; "
                f"candidates={len(candidates)}"
            )
            session.commit()
        return SearchCycleResult(
            correlation_id,
            candidates,
            alerts_sent,
            raw_discoveries_count,
            filtered_discoveries_count,
            offers_seen,
        )

    def _build_discovery_requests(
        self,
        origin: str,
        earliest: date,
        latest: date,
        return_date: date | None,
        trip_types: list[TripType],
        region: str | None,
        max_price: float | None,
        limit: int,
        rotation_seed: int,
    ) -> list[DiscoveryRequest]:
        base = DiscoveryRequest(
            origin=origin,
            earliest_departure=earliest,
            latest_departure=latest,
            return_date=return_date,
            trip_lengths=self.config.search.trip_lengths,
            trip_types=trip_types,
            currency=self.config.profile.currency,
            max_price=max_price,
            region=region,
        )
        requests = [base]
        requested_regions = expand_region_filter(region)
        if requested_regions == OUTSIDE_NORTH_AMERICA_REGIONS:
            region_names = self._rotate(sorted(OUTSIDE_NORTH_AMERICA_REGIONS), rotation_seed)
            for region_name in region_names:
                area_id = SERPAPI_AREA_BY_REGION.get(region_name)
                if area_id:
                    requests.append(base.model_copy(update={"arrival_area_id": area_id}))
                destinations = self._rotate(
                    self.config.search.destination_catalogue.get(region_name, []),
                    rotation_seed,
                )
                for destination in destinations:
                    requests.append(
                        base.model_copy(
                            update={
                                "arrival_id": destination,
                                "region": region_name,
                            }
                        )
                    )
        return requests[: max(limit, 1)]

    def _next_rotation_seed(self, session: Session, region: str) -> int:
        key = f"rotation:{region}"
        state = session.get(SchedulerState, key)
        current = int(state.value) if state and state.value.isdigit() else 0
        next_value = current + 1
        if state is None:
            session.add(SchedulerState(key=key, value=str(next_value)))
        else:
            state.value = str(next_value)
            state.updated_at = datetime.now(UTC)
        session.flush()
        return current

    def _rotate(self, values: list[str], seed: int) -> list[str]:
        if not values:
            return values
        offset = seed % len(values)
        return values[offset:] + values[:offset]

    async def quota_status(self) -> list[str]:
        statuses = []
        for provider in self.providers:
            quota = await provider.get_quota_status()
            statuses.append(
                f"{quota.provider}: used {quota.requests_used}/{quota.monthly_quota}, "
                f"remaining {quota.estimated_remaining}, healthy={quota.healthy}"
            )
        return statuses
