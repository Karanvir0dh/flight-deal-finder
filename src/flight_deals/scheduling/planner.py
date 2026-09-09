from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlannedSearch:
    origin: str
    region: str
    priority: float
    reason: str


def plan_coverage(origins: list[str], regions: list[str], limit: int = 12) -> list[PlannedSearch]:
    plans = [
        PlannedSearch(origin=origin, region=region, priority=1.0, reason="baseline exploration")
        for origin in origins
        for region in regions
    ]
    return sorted(plans, key=lambda p: (-p.priority, p.origin, p.region))[:limit]
