"""shared/fixtures/{catalog,expanded-outputs}.json are generated for the web tests (plan1.txt T7)."""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import export_web_fixtures  # noqa: E402


@pytest.mark.parametrize("name", list(export_web_fixtures.OUTPUTS))
def test_committed_fixture_matches_export(name):
    path = export_web_fixtures.FIXTURES / name
    assert path.read_text() == export_web_fixtures.OUTPUTS[name](), (
        f"{name} is stale: run scripts/export_web_fixtures.py"
    )


def test_catalog_fixture_matches_endpoint():
    client = TestClient(app)
    fixture = json.loads((export_web_fixtures.FIXTURES / "catalog.json").read_text())
    assert client.get("/api/catalog").json() == fixture
