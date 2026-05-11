"""Tests for /api/v1/download."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_download_queues_task(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/api/v1/download",
        json={"url": "https://www.tiktok.com/@testuser/video/7000000000000000001"},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["task_id"]
    # In eager mode, the task completes synchronously.
    assert body["status"] in {"queued", "completed"}
    assert body["poll_url"].endswith(f"/api/v1/status/{body['task_id']}")
    assert body["result_url"].endswith(f"/api/v1/result/{body['task_id']}")


def test_download_rejects_invalid_url(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/api/v1/download",
        json={"url": "https://example.com/not-tiktok"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"


def test_download_rejects_extra_fields(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/api/v1/download",
        json={"url": "https://www.tiktok.com/@u/video/1", "extra": "bad"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_download_quality_options(client: TestClient, auth_headers: dict[str, str]) -> None:
    for quality in ("high", "medium", "low"):
        resp = client.post(
            "/api/v1/download",
            json={
                "url": f"https://www.tiktok.com/@u/video/{quality}",
                "quality": quality,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 202


def test_download_cache_hit_on_repeat(client: TestClient, auth_headers: dict[str, str]) -> None:
    url = "https://www.tiktok.com/@cache/video/123"
    first = client.post("/api/v1/download", json={"url": url}, headers=auth_headers).json()
    second = client.post("/api/v1/download", json={"url": url}, headers=auth_headers).json()
    assert second["task_id"] == first["task_id"]
    assert second["cached"] is True


def test_download_mp3_format(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/api/v1/download",
        json={"url": "https://www.tiktok.com/@u/video/1", "format": "mp3"},
        headers=auth_headers,
    )
    assert resp.status_code == 202
