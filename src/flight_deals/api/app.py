from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import asc, desc, select
from starlette.requests import Request

from flight_deals.config.settings import load_config
from flight_deals.database.models import DealRecord, FareObservation, ProviderHealth, SearchRun
from flight_deals.database.session import SessionLocal, init_db
from flight_deals.discovery.regions import expand_region_filter, infer_destination_region
from flight_deals.providers.factory import build_providers
from flight_deals.services.search_service import FlightDealService

templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def require_token(x_api_token: str | None = Header(default=None)) -> None:
    expected = os.getenv("API_TOKEN", "change-me-for-dashboard-posts")
    if x_api_token != expected:
        raise HTTPException(status_code=401, detail="Invalid API token")


def create_app() -> FastAPI:
    app = FastAPI(title="Flight Deal Finder")

    @app.on_event("startup")
    def startup() -> None:
        init_db()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def dashboard(
        request: Request,
        sort: str = "score",
        direction: str = "desc",
        outside_na: bool = False,
    ) -> HTMLResponse:
        sort_columns = {
            "score": DealRecord.score,
            "price": FareObservation.price_cad,
            "newest": DealRecord.created_at,
            "departure": FareObservation.departure_date,
            "level": DealRecord.level,
        }
        sort_key = sort if sort in sort_columns else "score"
        sort_direction = "asc" if direction == "asc" else "desc"
        order_by = (
            asc(sort_columns[sort_key]) if sort_direction == "asc" else desc(sort_columns[sort_key])
        )
        with SessionLocal() as session:
            rows = session.execute(
                select(DealRecord, FareObservation)
                .join(FareObservation, DealRecord.observation_id == FareObservation.id)
                .order_by(order_by, DealRecord.created_at.desc())
                .limit(100)
            ).all()
            search_runs = list(
                session.execute(
                    select(SearchRun).order_by(SearchRun.started_at.desc()).limit(25)
                ).scalars()
            )
            deals = []
            outside_na_regions = expand_region_filter("outside_na")
            for deal, obs in rows:
                region = infer_destination_region(obs.destination)
                if outside_na and outside_na_regions and region not in outside_na_regions:
                    continue
                deals.append(
                    {
                        "id": deal.id,
                        "level": deal.level,
                        "score": deal.score,
                        "origin": obs.origin,
                        "destination": obs.destination,
                        "region": region,
                        "departure_date": obs.departure_date,
                        "return_date": obs.return_date,
                        "trip_type": obs.trip_type,
                        "price_cad": obs.price_cad,
                        "provider": obs.provider,
                        "observed_at": obs.observed_at,
                        "explanation": deal.explanation,
                    }
                )
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "deals": deals,
                "search_runs": search_runs,
                "sort": sort_key,
                "direction": sort_direction,
                "outside_na": outside_na,
            },
        )

    @app.get("/api/deals")
    def deals() -> list[dict[str, object]]:
        with SessionLocal() as session:
            rows = session.execute(
                select(DealRecord, FareObservation)
                .join(FareObservation, DealRecord.observation_id == FareObservation.id)
                .order_by(DealRecord.created_at.desc())
                .limit(50)
            ).all()
            return [
                {
                    "id": deal.id,
                    "level": deal.level,
                    "score": deal.score,
                    "origin": obs.origin,
                    "destination": obs.destination,
                    "price_cad": obs.price_cad,
                    "explanation": deal.explanation,
                }
                for deal, obs in rows
            ]

    @app.get("/api/deals/{deal_id}")
    def deal_detail(deal_id: int) -> dict[str, object]:
        with SessionLocal() as session:
            deal = session.get(DealRecord, deal_id)
            if not deal:
                raise HTTPException(status_code=404, detail="Deal not found")
            obs = session.get(FareObservation, deal.observation_id)
            return {"deal": deal.explanation, "price_cad": obs.price_cad if obs else None}

    @app.get("/api/routes/{origin}/{destination}/history")
    def route_history(origin: str, destination: str) -> list[dict[str, object]]:
        with SessionLocal() as session:
            rows = session.execute(
                select(FareObservation)
                .where(FareObservation.origin == origin.upper())
                .where(FareObservation.destination == destination.upper())
                .order_by(FareObservation.observed_at)
            ).scalars()
            return [{"observed_at": row.observed_at, "price_cad": row.price_cad} for row in rows]

    @app.get("/api/providers")
    def providers() -> list[dict[str, object]]:
        with SessionLocal() as session:
            rows = session.execute(select(ProviderHealth)).scalars()
            return [{"provider": row.provider, "healthy": bool(row.healthy)} for row in rows]

    @app.get("/api/coverage")
    def coverage() -> dict[str, str]:
        return {"status": "coverage planner available through CLI"}

    @app.post("/api/search/run", dependencies=[Depends(require_token)])
    async def run_search() -> dict[str, object]:
        config = load_config()
        service = FlightDealService(config, build_providers(config))
        result = await service.run_once()
        return {"correlation_id": result.correlation_id, "candidates": len(result.candidates)}

    @app.post("/api/deals/{deal_id}/verify", dependencies=[Depends(require_token)])
    def verify_deal(deal_id: int) -> dict[str, object]:
        return {"deal_id": deal_id, "status": "queued"}

    return app
