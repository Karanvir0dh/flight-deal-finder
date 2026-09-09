from __future__ import annotations

from flight_deals.scheduling.planner import plan_coverage


def test_planner_rotates_origins_and_regions() -> None:
    plans = plan_coverage(["YYZ", "YTZ"], ["europe", "asia"], limit=3)
    assert len(plans) == 3
    assert {p.origin for p in plans}
