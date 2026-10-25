from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest

os.environ["HUB_OFFLINE"] = "1"

from governance_hub.db import connect  # noqa: E402
from governance_hub.intake import Intake  # noqa: E402
from governance_hub.seed import build  # noqa: E402


@pytest.fixture(scope="session")
def seeded_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    p = tmp_path_factory.mktemp("seed") / "hub.db"
    build(p).close()
    return p


@pytest.fixture()
def db(seeded_path: Path, tmp_path: Path) -> sqlite3.Connection:
    """A fresh copy of the seeded demo database for each test."""
    p = tmp_path / "hub.db"
    shutil.copy(seeded_path, p)
    return connect(p)


def make(**kw: Any) -> Intake:
    base: dict[str, Any] = {"title": "Test case", "purpose": "A test use case", "team": "Customer Service"}
    base.update(kw)
    return Intake(**base)


def by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
    assert row is not None
    return row
