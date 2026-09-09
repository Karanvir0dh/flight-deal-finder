from __future__ import annotations

from flight_deals.config.settings import load_config


def test_config_loads_personal_defaults() -> None:
    config = load_config()
    assert config.profile.currency == "CAD"
    assert "YYZ" in config.search.origins.primary
    assert config.notifications.alert_email == "REPLACE_WITH_MY_EMAIL"
