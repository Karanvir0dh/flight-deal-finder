from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from flight_deals.models.domain import TripType


class ProfileConfig(BaseModel):
    name: str = "Hamza"
    timezone: str = "America/Toronto"
    currency: str = "CAD"


class OriginConfig(BaseModel):
    primary: list[str] = Field(default_factory=lambda: ["YYZ", "YTZ", "YHM"])
    optional: list[str] = Field(default_factory=list)
    available_optional: list[str] = Field(default_factory=list)


class SearchConfig(BaseModel):
    origins: OriginConfig = Field(default_factory=OriginConfig)
    worldwide: bool = True
    earliest_departure_days: int = 7
    latest_departure_days: int = 365
    trip_lengths: list[tuple[int, int]] = Field(default_factory=lambda: [(6, 9)])
    trip_types: list[TripType] = Field(
        default_factory=lambda: [TripType.one_way, TripType.round_trip]
    )
    excluded_months: list[int] = Field(default_factory=list)
    preferred_months: list[int] = Field(default_factory=list)
    blackout_dates: list[str] = Field(default_factory=list)
    adults: int = 1
    cabin: str = "economy"
    maximum_stops: int = 2
    carry_on_preferred: bool = True
    personal_item_only_allowed: bool = True
    self_transfer_policy: str = "label"
    separate_ticket_policy: str = "label"
    mixed_airport_policy: str = "label"
    regional_searches_per_run: int = 6
    destination_catalogue: dict[str, list[str]] = Field(default_factory=dict)


class ThresholdConfig(BaseModel):
    one_way: dict[str, float]
    round_trip: dict[str, float]
    percent_below_median: dict[str, float]
    new_low: dict[str, float]


class ScoringConfig(BaseModel):
    weights: dict[str, float]
    penalties: dict[str, float]


class NotificationConfig(BaseModel):
    preferred_providers: list[str] = Field(default_factory=lambda: ["email"])
    immediate_minimum_level: str = "GREAT"
    digest_enabled: bool = True
    digest_time: str = "08:00"
    alert_email: str = "REPLACE_WITH_MY_EMAIL"
    duplicate_cooldown_hours: int = 48
    resend_price_drop_percent: float = 10
    resend_price_drop_cad: float = 40
    fare_disappeared_alerts: bool = False
    operational_empty_digest: bool = False


class ProviderBudget(BaseModel):
    enabled: bool = True
    monthly_quota: int = 0
    per_run_budget: int = 0
    reserve_for_verification: int = 0


class CurrencyConfig(BaseModel):
    provider: str = "exchangerate_host"
    cache_ttl_hours: int = 12
    stale_after_hours: int = 36


class AppConfig(BaseModel):
    profile: ProfileConfig
    search: SearchConfig
    regions: dict[str, Any]
    thresholds: ThresholdConfig
    scoring: ScoringConfig
    notifications: NotificationConfig
    providers: dict[str, ProviderBudget]
    currency: CurrencyConfig
    retention: dict[str, Any] = Field(default_factory=dict)
    schedule: dict[str, Any] = Field(default_factory=dict)
    logging: dict[str, Any] = Field(default_factory=dict)

    @field_validator("providers")
    @classmethod
    def require_mock_provider(cls, value: dict[str, ProviderBudget]) -> dict[str, ProviderBudget]:
        value.setdefault(
            "mock", ProviderBudget(enabled=True, monthly_quota=100000, per_run_budget=100)
        )
        return value


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> AppConfig:
    load_dotenv()
    selected_path: str | Path = (
        path if path is not None else os.getenv("CONFIG_FILE", "config/default.yml")
    )
    config_path = Path(selected_path)
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    personal = os.getenv("PERSONAL_CONFIG_FILE")
    personal_path = Path(personal) if personal else None
    if personal_path and personal_path.exists():
        with personal_path.open("r", encoding="utf-8") as handle:
            data = deep_merge(data, yaml.safe_load(handle) or {})
    alert_email = os.getenv("ALERT_EMAIL")
    if alert_email:
        data.setdefault("notifications", {})["alert_email"] = alert_email
    return AppConfig.model_validate(data)
