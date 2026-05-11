"""End-to-end tests for status + result endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _queue(
    client: TestClient, headers: dict[str, str], url: str = "https://www.tiktok.com/@u/video/1"
) -> str:
    resp = client.post("/api/v1/download", json={"url": url}, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()["task_id"]


def test_status_returns_completed_in_eager_mode(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    task_id = _queue(client, auth_headers)
    resp = client.get(f"/api/v1/status/{task_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == task_id
    assert body["status"] == "completed"
    assert body["progress"] == 100
    assert body["result_url"]


def test_status_unknown_task(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/api/v1/status/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "task_not_found"


def test_result_returns_watermark_free_download_url(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    task_id = _queue(client, auth_headers)
    resp = client.get(f"/api/v1/result/{task_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == task_id
    assert body["watermark_free"] is True
    assert "watermark=1" not in body["download_url"]
    assert body["metadata"]["id"]
    assert body["metadata"]["author"] == "@testuser"
    assert body["quality"] == "high"
    assert body["audio_url"]


def test_result_mp3_format(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/api/v1/download",
        json={"url": "https://www.tiktok.com/@u/video/mp3", "format": "mp3"},
        headers=auth_headers,
    )
    task_id = resp.json()["task_id"]
    result = client.get(f"/api/v1/result/{task_id}", headers=auth_headers).json()
    assert result["format"] == "mp3"
    assert result["download_url"].endswith(".m4a")


def test_result_unavailable_video_failure(client: TestClient, auth_headers: dict[str, str]) -> None:
    # The patched ytdlp raises a DownloadError for URLs containing "404".
    resp = client.post(
        "/api/v1/download",
        json={"url": "https://www.tiktok.com/@u/video/404-gone"},
        headers=auth_headers,
    )
    task_id = resp.json()["task_id"]
    status = client.get(f"/api/v1/status/{task_id}", headers=auth_headers).json()
    assert status["status"] == "failed"
    assert status["error"]["code"] in {"video_unavailable", "extraction_failed"}

    result = client.get(f"/api/v1/result/{task_id}", headers=auth_headers)
    assert result.status_code in {404, 502}
    assert result.json()["error"]["code"] in {"video_unavailable", "extraction_failed"}


def test_result_private_video_failure(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/api/v1/download",
        json={"url": "https://www.tiktok.com/@u/video/private-clip"},
        headers=auth_headers,
    )
    task_id = resp.json()["task_id"]
    status = client.get(f"/api/v1/status/{task_id}", headers=auth_headers).json()
    assert status["status"] == "failed"
    assert status["error"]["code"] == "video_private"
