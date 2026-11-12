"""Smoke tests for the API. FastAPI's TestClient needs no server and no network."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from serve.app import app

client = TestClient(app)


@pytest.fixture(scope="module")
def health():
    r = client.get("/health")
    if r.status_code == 503:
        pytest.skip("artefacts not built")
    return r


def test_health_reports_the_layer(health):
    body = health.json()
    assert body["status"] == "ok"
    assert body["cells"] > 500
    assert 2025 in body["years"]


def test_water_returns_ranked_cells(health):
    year = max(health.json()["years"])
    r = client.get(f"/water/{year}", params={"limit": 5})
    assert r.status_code == 200
    cells = r.json()["cells"]
    assert len(cells) == 5
    values = [c["accessibility_af"] for c in cells]
    assert values == sorted(values, reverse=True), "cells are not ranked"
    assert all(v >= 0 for v in values)


def test_water_rejects_unknown_year(health):
    r = client.get("/water/1901")
    assert r.status_code == 404


def test_county_returns_a_series(health):
    r = client.get("/county/colusa")
    assert r.status_code == 200
    body = r.json()
    assert body["county"] == "COLUSA"
    assert len(body["years"]) > 10
    assert all(y["acres"] > 0 for y in body["years"])


def test_county_404(health):
    assert client.get("/county/atlantis").status_code == 404


def test_reservoirs_report_validation(health):
    body = client.get("/reservoirs").json()
    names = {r["reservoir"] for r in body["validated"]}
    assert {"Shasta", "Oroville"} <= names
    for r in body["validated"]:
        assert -1 <= r["spearman"] <= 1
