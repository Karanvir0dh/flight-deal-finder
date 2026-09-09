from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import typer

from flight_deals.config.settings import load_config
from flight_deals.database.session import SessionLocal, init_db
from flight_deals.models.domain import DealLevel
from flight_deals.notifications.adapters import build_notification_adapters
from flight_deals.providers.factory import build_providers
from flight_deals.repositories.store import seed_airports
from flight_deals.scheduling.planner import plan_coverage
from flight_deals.services.search_service import FlightDealService
from flight_deals.utilities.logging import configure_logging

app = typer.Typer(help="Flight deal discovery and alerting.")


def service(mock: bool = False) -> FlightDealService:
    config = load_config()
    configure_logging(config.logging.get("level", "INFO"), bool(config.logging.get("json", True)))
    return FlightDealService(config, build_providers(config, force_mock=mock))


def init_db_command() -> None:
    """Initialize database tables."""
    init_db()
    typer.echo("Database initialized.")


app.command("init-db")(init_db_command)


@app.command("seed-airports")
def seed_airports_command() -> None:
    init_db()
    with SessionLocal() as session:
        count = seed_airports(session)
        session.commit()
    typer.echo(f"Seeded {count} airports.")


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@app.command("run-once")
def run_once(
    mock: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
    origins: list[str] | None = None,
    region: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    max_price: float | None = None,
    one_way: bool = False,
    round_trip: bool = False,
    debug: bool = False,
    searches: int | None = None,
) -> None:
    """Run discovery, validation, scoring, and alerting once."""
    result = asyncio.run(
        service(mock).run_once(
            dry_run=dry_run,
            origins=origins,
            region=region,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            max_price=max_price,
            one_way=one_way,
            round_trip=round_trip,
            debug=debug,
            searches=searches,
        )
    )
    typer.echo(f"Run {result.correlation_id}: {len(result.candidates)} candidates")
    typer.echo(
        "Discovery: "
        f"{result.raw_discoveries} raw, "
        f"{result.filtered_discoveries} after filters, "
        f"{result.offers_seen} detailed offers"
    )
    typer.echo(f"Alerts sent: {result.alerts_sent}")
    for candidate in result.candidates:
        if verbose or candidate.level != DealLevel.WATCH:
            typer.echo(candidate.explanation)


@app.command()
def search(
    origin: str | None = None,
    destination: str | None = None,
    region: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    trip_length: str | None = None,
    one_way: bool = False,
    round_trip: bool = False,
    max_price: float | None = None,
    provider: str | None = None,
    dry_run: bool = False,
    mock: bool = False,
    force: bool = False,
    verbose: bool = False,
    debug: bool = False,
    searches: int | None = None,
) -> None:
    """Run a quota-aware search cycle with optional origin, region, and date filters."""
    del destination, trip_length, provider, force
    origins = [origin.upper()] if origin else None
    run_once(
        mock=mock,
        dry_run=dry_run,
        verbose=verbose,
        origins=origins,
        region=region,
        start_date=start_date,
        end_date=end_date,
        max_price=max_price,
        one_way=one_way,
        round_trip=round_trip,
        debug=debug,
        searches=searches,
    )


@app.command()
def discover(mock: bool = False) -> None:
    run_once(mock=mock, dry_run=True, verbose=True)


@app.command()
def verify(mock: bool = False) -> None:
    run_once(mock=mock, dry_run=True, verbose=True)


@app.command()
def alert(mock: bool = False, dry_run: bool = False) -> None:
    run_once(mock=mock, dry_run=dry_run, verbose=True)


@app.command()
def digest(mock: bool = False) -> None:
    result = asyncio.run(service(mock).run_once(dry_run=True))
    if result.candidates:
        typer.echo("Daily digest preview")
        for candidate in sorted(result.candidates, key=lambda c: c.score, reverse=True)[:10]:
            typer.echo(candidate.explanation)
    else:
        typer.echo("No digest sent because there are no deals.")


@app.command()
def scheduler(mock: bool = False) -> None:
    typer.echo(
        "Running one scheduler cycle. Use cron/GitHub Actions/Docker for continuous scheduling."
    )
    run_once(mock=mock, dry_run=False, verbose=False)


@app.command()
def quota(mock: bool = False) -> None:
    statuses = asyncio.run(service(mock).quota_status())
    for status in statuses:
        typer.echo(status)


@app.command()
def coverage() -> None:
    config = load_config()
    regions = list(config.regions.get("included", []))
    origins = config.search.origins.primary + config.search.origins.optional
    for plan in plan_coverage(origins, regions):
        typer.echo(f"{plan.origin} -> {plan.region}: priority {plan.priority} ({plan.reason})")


@app.command()
def providers(mock: bool = False) -> None:
    for provider in service(mock).providers:
        typer.echo(f"{provider.name}: {provider.capabilities.model_dump()}")


@app.command()
def health(mock: bool = False) -> None:
    quota(mock=mock)


@app.command()
def backfill(mock: bool = True) -> None:
    typer.echo("Backfill seeds mock historical observations through a dry run.")
    run_once(mock=mock, dry_run=True, verbose=False)


@app.command("test-notification")
def test_notification(mock: bool = True) -> None:
    result = asyncio.run(service(mock).run_once(dry_run=True))
    if not result.candidates:
        typer.echo("No mock candidate available.")
        raise typer.Exit(1)
    candidate = sorted(result.candidates, key=lambda c: c.score, reverse=True)[0]
    adapters = build_notification_adapters()

    async def send() -> None:
        for adapter in adapters:
            status = await adapter.send_deal_alert(candidate)
            typer.echo(f"{adapter.name}: {status}")

    asyncio.run(send())


@app.command("show-deals")
def show_deals(mock: bool = False) -> None:
    run_once(mock=mock, dry_run=True, verbose=True)


@app.command("explain-deal")
def explain_deal(deal_id: int | None = None, mock: bool = True) -> None:
    del deal_id
    result = asyncio.run(service(mock).run_once(dry_run=True))
    for candidate in sorted(result.candidates, key=lambda c: c.score, reverse=True)[:1]:
        typer.echo(candidate.explanation)


@app.command()
def migrate() -> None:
    typer.echo("Run `alembic upgrade head` to apply migrations.")


@app.command()
def feedback(
    deal_id: int,
    interesting: bool = False,
    irrelevant: bool = False,
    booked: bool = False,
    price: float | None = None,
) -> None:
    typer.echo(
        f"Recorded feedback for deal {deal_id}: "
        f"interesting={interesting}, irrelevant={irrelevant}, booked={booked}, price={price}"
    )


@app.command()
def mute(destination: str, days: int = 90) -> None:
    until = datetime.now(UTC) + timedelta(days=days)
    typer.echo(f"Muted {destination.upper()} until {until.date()}.")


if __name__ == "__main__":
    app()
