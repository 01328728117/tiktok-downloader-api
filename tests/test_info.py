"""Tests for /api/v1/info."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_info_returns_metadata(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get(
        "/api/v1/info",
        params={"url": "https://www.tiktok.com/@u/video/1"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["metadata"]["author"] == "@testuser"
    assert body["metadata"]["duration"] == 12.5
    assert body["available_formats"]
    assert body["cached"] is False


def test_info_cached_on_second_call(client: TestClient, auth_headers: dict[str, str]) -> None:
    url = "https://www.tiktok.com/@u/video/cached"
    first = client.get("/api/v1/info", params={"url": url}, headers=auth_headers).json()
    second = client.get("/api/v1/info", params={"url": url}, headers=auth_headers).json()
    assert first["cached"] is False
    assert second["cached"] is True


def test_info_rejects_non_tiktok_url(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get(
        "/api/v1/info",
        params={"url": "https://example.com/foo"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_url"
