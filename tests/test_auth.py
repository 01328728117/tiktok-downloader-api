"""API key authentication tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_missing_api_key_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/download",
        json={"url": "https://www.tiktok.com/@user/video/123"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "unauthorized"


def test_wrong_api_key_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/download",
        json={"url": "https://www.tiktok.com/@user/video/123"},
        headers={"X-API-Key": "nope"},
    )
    assert resp.status_code == 401


def test_correct_api_key_accepted(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/api/v1/download",
        json={"url": "https://www.tiktok.com/@user/video/123"},
        headers=auth_headers,
    )
    assert resp.status_code == 202


def test_info_requires_api_key(client: TestClient, auth_headers: dict[str, str]) -> None:
    no_auth = client.get("/api/v1/info", params={"url": "https://www.tiktok.com/@u/video/1"})
    assert no_auth.status_code == 401
    ok = client.get(
        "/api/v1/info",
        params={"url": "https://www.tiktok.com/@u/video/1"},
        headers=auth_headers,
    )
    assert ok.status_code == 200


def test_health_no_auth_required(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
