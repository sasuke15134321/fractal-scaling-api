"""Fractal Scaling API wrapper tests — runs with TEST_MODE=true (no payment required)."""
import os
os.environ["TEST_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "Fractal Scaling API"
    assert data["version"] == "0.1.0"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
    assert r.json()["test_mode"] is True


def test_x402_discovery():
    r = client.get("/.well-known/x402.json")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == 1
    assert any(e["path"] == "/scale" for e in data["endpoints"])


def test_ai_agent_policy():
    r = client.get("/ai-agent-policy.json")
    assert r.status_code == 200
    data = r.json()
    assert data["agent_name"] == "Fractal Scaling API"


def test_scale_basic():
    r = client.post("/scale", json={
        "points": [[0.0, 0.0], [1.0, 0.0], [0.5, 0.866], [0.5, 0.289]],
        "value": 0.5,
    })
    assert r.status_code == 200
    data = r.json()
    assert "selected_indices" in data
    assert "stats" in data
    assert isinstance(data["selected_indices"], list)
    assert len(data["selected_indices"]) == 2  # 0.5 * 4 = 2


def test_scale_value_zero():
    r = client.post("/scale", json={
        "points": [[0.0, 0.0], [1.0, 0.0], [0.5, 0.866]],
        "value": 0.0,
    })
    assert r.status_code == 200
    assert r.json()["selected_indices"] == []
    assert r.json()["stats"]["selected"] == 0


def test_scale_value_one():
    r = client.post("/scale", json={
        "points": [[0.0, 0.0], [1.0, 0.0], [0.5, 0.866]],
        "value": 1.0,
    })
    assert r.status_code == 200
    assert len(r.json()["selected_indices"]) == 3
    assert r.json()["stats"]["selected"] == 3


def test_scale_with_weights():
    r = client.post("/scale", json={
        "points": [[0.0, 0.0], [1.0, 0.0], [0.5, 0.866]],
        "value": 0.34,
        "weights": [1.0, 0.5, 0.1],
    })
    assert r.status_code == 200
    assert len(r.json()["selected_indices"]) == 1


def test_scale_deterministic():
    body = {
        "points": [[0.0, 0.0], [1.0, 0.0], [0.5, 0.866], [0.5, 0.289]],
        "value": 0.75,
    }
    r1 = client.post("/scale", json=body)
    r2 = client.post("/scale", json=body)
    assert r1.json()["selected_indices"] == r2.json()["selected_indices"]


def test_scale_progressive():
    pts = [[float(i), float(i)] for i in range(10)]
    r_half = client.post("/scale", json={"points": pts, "value": 0.5})
    r_full = client.post("/scale", json={"points": pts, "value": 1.0})
    half = set(r_half.json()["selected_indices"])
    full = set(r_full.json()["selected_indices"])
    assert half.issubset(full)


def test_scale_invalid_points_1d():
    r = client.post("/scale", json={
        "points": [1.0, 2.0, 3.0],
        "value": 0.5,
    })
    assert r.status_code in (422, 500)


def test_scale_invalid_value_out_of_range():
    r = client.post("/scale", json={
        "points": [[0.0, 0.0], [1.0, 1.0]],
        "value": 1.5,
    })
    assert r.status_code == 422


def test_scale_stats_fields():
    r = client.post("/scale", json={
        "points": [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
        "value": 0.67,
    })
    stats = r.json()["stats"]
    for key in ["scale", "selected", "total", "reuse_from_previous",
                "mean_coverage_distance", "weighted_mean_coverage_distance",
                "max_coverage_distance"]:
        assert key in stats, f"Missing stats key: {key}"


def test_scale_requires_payment_without_test_mode(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "false")
    import importlib, main as m
    m.TEST_MODE = False
    r = client.post("/scale", json={
        "points": [[0.0, 0.0], [1.0, 0.0]],
        "value": 0.5,
    })
    assert r.status_code == 402
    data = r.json()
    assert data.get("x402Version") == 2
    assert "accepts" in data
    m.TEST_MODE = True
