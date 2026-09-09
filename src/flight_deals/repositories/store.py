from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from flight_deals.database.models import Airport, DealRecord, FareObservation, NotificationRecord
from flight_deals.models.domain import DealCandidate, FlightOffer

AIRPORT_SEED = [
    ("YYZ", "Toronto Pearson", "Toronto", "Canada", "canada_nearby_us"),
    ("YTZ", "Billy Bishop Toronto City", "Toronto", "Canada", "canada_nearby_us"),
    ("YHM", "Hamilton International", "Hamilton", "Canada", "canada_nearby_us"),
    ("BUF", "Buffalo Niagara International", "Buffalo", "United States", "canada_nearby_us"),
    ("YKF", "Region of Waterloo International", "Waterloo", "Canada", "canada_nearby_us"),
    ("YOW", "Ottawa International", "Ottawa", "Canada", "canada_nearby_us"),
    ("DTW", "Detroit Metropolitan", "Detroit", "United States", "canada_nearby_us"),
    ("YUL", "Montreal Trudeau", "Montreal", "Canada", "canada_nearby_us"),
    ("DUB", "Dublin", "Dublin", "Ireland", "europe"),
    ("LIS", "Lisbon", "Lisbon", "Portugal", "europe"),
    ("SAN", "San Diego", "San Diego", "United States", "united_states"),
    ("MEX", "Mexico City", "Mexico City", "Mexico", "mexico_caribbean_central_america"),
    ("BOG", "El Dorado", "Bogota", "Colombia", "south_america"),
    ("NRT", "Narita", "Tokyo", "Japan", "asia"),
    ("SYD", "Sydney", "Sydney", "Australia", "oceania"),
]


def seed_airports(session: Session) -> int:
    count = 0
    for code, name, city, country, region in AIRPORT_SEED:
        if session.get(Airport, code) is None:
            session.add(Airport(code=code, name=name, city=city, country=country, region=region))
            count += 1
    return count


def store_observation(session: Session, offer: FlightOffer) -> FareObservation:
    observation = FareObservation(
        provider=offer.provider,
        origin=offer.origin,
        destination=offer.destination,
        departure_date=offer.departure_date,
        return_date=offer.return_date,
        trip_type=offer.trip_type.value,
        price=offer.price,
        currency=offer.currency,
        price_cad=offer.price_cad,
        fingerprint=offer.fingerprint_key,
    )
    session.add(observation)
    session.flush()
    return observation


def route_prices(session: Session, offer: FlightOffer) -> list[float]:
    rows = session.execute(
        select(FareObservation.price_cad)
        .where(FareObservation.origin == offer.origin)
        .where(FareObservation.destination == offer.destination)
        .where(FareObservation.trip_type == offer.trip_type.value)
        .order_by(FareObservation.observed_at)
    ).all()
    return [float(row[0]) for row in rows]


def store_deal(
    session: Session, candidate: DealCandidate, observation: FareObservation
) -> DealRecord:
    deal = DealRecord(
        observation_id=observation.id,
        fingerprint=candidate.offer.fingerprint_key,
        level=candidate.level.value,
        score=candidate.score,
        explanation=candidate.explanation,
        booking_confidence=candidate.booking_confidence_level.value,
    )
    session.add(deal)
    session.flush()
    return deal


def latest_notification(session: Session, fingerprint: str) -> tuple[datetime | None, float | None]:
    row = session.execute(
        select(NotificationRecord.sent_at, FareObservation.price_cad)
        .join(DealRecord, NotificationRecord.deal_id == DealRecord.id)
        .join(FareObservation, DealRecord.observation_id == FareObservation.id)
        .where(NotificationRecord.fingerprint == fingerprint)
        .where(NotificationRecord.status == "sent")
        .order_by(NotificationRecord.sent_at.desc())
    ).first()
    if row is None:
        return None, None
    return row[0], float(row[1])


def mark_notification(
    session: Session,
    deal_id: int,
    fingerprint: str,
    channel: str,
    status: str,
    error: str | None = None,
) -> NotificationRecord:
    record = NotificationRecord(
        deal_id=deal_id,
        fingerprint=fingerprint,
        channel=channel,
        status=status,
        sent_at=datetime.now(UTC) if status == "sent" else None,
        error=error,
        idempotency_key=f"{deal_id}:{channel}:{fingerprint}",
    )
    session.add(record)
    session.flush()
    return record
