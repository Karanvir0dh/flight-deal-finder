from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TripType(StrEnum):
    one_way = "one_way"
    round_trip = "round_trip"


class DealLevel(StrEnum):
    WATCH = "WATCH"
    GOOD = "GOOD"
    GREAT = "GREAT"
    EXCEPTIONAL = "EXCEPTIONAL"
    POSSIBLE_MISTAKE_FARE = "POSSIBLE MISTAKE FARE"


class BookingConfidenceLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ProviderCapability(BaseModel):
    supports_anywhere_discovery: bool = False
    supports_exact_search: bool = False
    supports_booking_links: bool = False
    supports_baggage_data: bool = False
    supports_fare_verification: bool = False
    supports_one_way: bool = True
    supports_multi_city: bool = False
    supports_flexible_dates: bool = False
    supports_quota_reporting: bool = False


class ProviderQuota(BaseModel):
    provider: str
    monthly_quota: int
    requests_used: int
    estimated_remaining: int
    reset_date: date | None = None
    per_run_budget: int
    reserved_for_verification: int
    consecutive_errors: int = 0
    rate_limited: bool = False
    healthy: bool = True


class DiscoveryRequest(BaseModel):
    origin: str
    earliest_departure: date
    latest_departure: date
    return_date: date | None = None
    trip_lengths: list[tuple[int, int]]
    trip_types: list[TripType]
    currency: str = "CAD"
    max_price: float | None = None
    region: str | None = None
    arrival_id: str | None = None
    arrival_area_id: str | None = None


class DiscoveryResult(BaseModel):
    provider: str
    origin: str
    destination: str
    destination_name: str
    region: str
    departure_date: date
    return_date: date | None = None
    trip_type: TripType
    price: float
    currency: str
    stops: int = 0
    airline: str | None = None
    booking_link: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class FlightSearchRequest(BaseModel):
    origin: str
    destination: str
    departure_date: date
    return_date: date | None = None
    trip_type: TripType = TripType.round_trip
    adults: int = 1
    cabin: str = "economy"
    currency: str = "CAD"
    maximum_stops: int = 2
    max_price: float | None = None


class Segment(BaseModel):
    origin: str
    destination: str
    departure_at: datetime
    arrival_at: datetime
    carrier: str
    flight_number: str | None = None
    duration_minutes: int


class FlightOffer(BaseModel):
    provider: str
    origin: str
    destination: str
    departure_date: date
    return_date: date | None = None
    trip_type: TripType
    price: float
    currency: str
    price_cad: float
    exchange_rate: float = 1.0
    exchange_rate_checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    segments: list[Segment] = Field(default_factory=list)
    carriers: list[str] = Field(default_factory=list)
    stops: int = 0
    total_duration_minutes: int = 0
    layovers: list[str] = Field(default_factory=list)
    baggage: str | None = None
    cabin: str = "economy"
    fare_class: str | None = None
    basic_economy: bool = False
    self_transfer: bool = False
    separate_tickets: bool = False
    mixed_airports: bool = False
    includes_taxes: bool | None = None
    booking_link: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_provider_id: str | None = None

    @property
    def fingerprint_key(self) -> str:
        bucket = int(self.price_cad // 10) * 10
        carrier = ",".join(sorted(self.carriers)) or "unknown"
        return (
            f"{self.origin}:{self.destination}:{self.departure_date}:{self.return_date}:"
            f"{self.trip_type}:{carrier}:{bucket}"
        )


class HistoricalStats(BaseModel):
    median_price: float | None = None
    mean_price: float | None = None
    min_price: float | None = None
    p10_price: float | None = None
    p25_price: float | None = None
    seven_day_median: float | None = None
    thirty_day_median: float | None = None
    ninety_day_median: float | None = None
    percent_below_route_median: float | None = None
    percent_below_recent_lowest: float | None = None
    price_change_since_last_observation: float | None = None
    price_change_since_last_alert: float | None = None
    robust_anomaly_score: float | None = None
    observation_count: int = 0


class VerificationResult(BaseModel):
    status: str
    verified_price_cad: float | None = None
    provider_prices: dict[str, float] = Field(default_factory=dict)
    booking_link: str | None = None
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str = ""


class DealCandidate(BaseModel):
    offer: FlightOffer
    score: int
    level: DealLevel
    explanation: str
    booking_confidence_score: int
    booking_confidence_level: BookingConfidenceLevel
    historical_stats: HistoricalStats
    verification: VerificationResult | None = None
