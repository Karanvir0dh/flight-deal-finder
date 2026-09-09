from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def config_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONFIG_FILE", "config/default.yml")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
