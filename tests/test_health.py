"""Tests for /health and / endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["cache"]["ok"] is True
    assert body["celery_eager"] is True
    assert "version" in body


def test_root_index(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"]
    assert body["health"] == "/health"
    assert body["docs"] == "/docs"


def test_openapi_schema_includes_endpoints(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/health" in paths
    assert "/api/v1/download" in paths
    assert "/api/v1/info" in paths
    assert "/api/v1/status/{task_id}" in paths
    assert "/api/v1/result/{task_id}" in paths


def test_docs_pages(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
