# TikTok Video Downloader REST API

Production-ready, fully-async TikTok Video Downloader REST API powered by
**FastAPI**, **yt-dlp**, **Celery + Redis**, and **Docker**. Returns
watermark-free MP4 / MP3 download URLs with per-IP rate limiting, API key
authentication, structured JSON logging, and graceful handling of private or
deleted videos.

> Built end-to-end as a single deployable service. Drop-in `Procfile` is
> included so you can ship the same image to Sevalla, Render, Railway,
> Fly.io, or any container host.

---

## Highlights

| Capability | Details |
|---|---|
| Framework | FastAPI (async), Python 3.11+ |
| Downloader | `yt-dlp` (latest), watermark-free TikTok extraction |
| Async queue | Celery + Redis (auto-fallback to in-process eager mode) |
| Caching | Redis with 1-hour TTL on results and metadata |
| Rate limiting | SlowAPI, 60 req/min per IP (configurable) |
| Auth | `X-API-Key` header (multi-key, comma-separated) |
| Validation | Pydantic v2 + strict schemas, structured 4xx errors |
| Logging | `structlog` JSON logs with per-request `request_id` |
| Docs | Swagger UI `/docs`, ReDoc `/redoc`, OpenAPI `/openapi.json` |
| Containers | `Dockerfile` + `docker-compose.yml` (API + worker + Redis) |
| Deploy targets | Sevalla (`Procfile`), Fly.io (`fly.toml`), or any Docker host |
| Testing | pytest + pytest-asyncio, 80%+ coverage with `--cov` |
| Code quality | black, ruff, mypy, pre-commit |

---

## Project Layout

```
tiktok-downloader-api/
├── app/
│   ├── api/
│   │   ├── deps.py                  # FastAPI DI providers
│   │   └── v1/
│   │       ├── download.py          # POST /api/v1/download
│   │       ├── status.py            # GET  /api/v1/status/{task_id}
│   │       ├── result.py            # GET  /api/v1/result/{task_id}
│   │       └── info.py              # GET  /api/v1/info?url=...
│   ├── core/
│   │   ├── config.py                # Pydantic BaseSettings
│   │   ├── logging.py               # structlog config
│   │   ├── exceptions.py            # APIError + JSON handlers
│   │   ├── security.py              # API key auth
│   │   ├── rate_limit.py            # SlowAPI integration
│   │   └── cache.py                 # Redis + in-memory cache backend
│   ├── schemas/
│   │   └── download.py              # Pydantic v2 request/response schemas
│   ├── services/
│   │   └── tiktok.py                # yt-dlp wrapper (watermark-free)
│   ├── workers/
│   │   └── celery_app.py            # Celery app + process_video_task
│   └── main.py                      # FastAPI factory + middleware
├── tests/                           # pytest suite (TestClient + mocked yt-dlp)
├── postman/
│   └── tiktok-downloader.postman_collection.json
├── Dockerfile
├── docker-compose.yml
├── Procfile                         # Sevalla / Heroku / Railway
├── fly.toml                         # Fly.io
├── .env.example
├── .pre-commit-config.yaml
├── pyproject.toml
└── README.md
```

---

## Endpoints

All `/api/v1/*` endpoints require the `X-API-Key` header (configure
`API_KEYS` in `.env`).

### `POST /api/v1/download`

Queue an async TikTok extraction task.

```bash
curl -X POST http://localhost:8000/api/v1/download \
  -H "Content-Type: application/json" \
  -H "X-API-Key: changeme-dev-key" \
  -d '{
    "url": "https://www.tiktok.com/@user/video/7000000000000000001",
    "quality": "high",
    "format": "mp4"
  }'
```

Response (HTTP 202):

```json
{
  "task_id": "f1d2c3...",
  "status": "queued",
  "cached": false,
  "poll_url": "http://localhost:8000/api/v1/status/f1d2c3...",
  "result_url": "http://localhost:8000/api/v1/result/f1d2c3..."
}
```

`quality` accepts `high | medium | low`. `format` accepts `mp4 | mp3`.

### `GET /api/v1/status/{task_id}`

Poll task status. Returns real-time progress.

```json
{
  "task_id": "f1d2c3...",
  "status": "completed",
  "progress": 100,
  "message": "Completed",
  "error": null,
  "updated_at": 1736615000.42,
  "result_url": "http://localhost:8000/api/v1/result/f1d2c3..."
}
```

### `GET /api/v1/result/{task_id}`

Returns the final, watermark-free download URL once the task is `completed`.

```json
{
  "task_id": "f1d2c3...",
  "status": "completed",
  "metadata": {
    "id": "7000000000000000001",
    "title": "Test TikTok Video",
    "author": "@user",
    "duration": 12.5,
    "thumbnail": "https://..."
  },
  "download_url": "https://cdn.tiktok.com/...mp4",
  "audio_url": "https://cdn.tiktok.com/...m4a",
  "format": "mp4",
  "quality": "high",
  "watermark_free": true
}
```

### `GET /api/v1/info?url=...`

Synchronous metadata lookup — title, author, duration, thumbnail,
available formats.

```bash
curl -G "http://localhost:8000/api/v1/info" \
  --data-urlencode "url=https://www.tiktok.com/@u/video/700..." \
  -H "X-API-Key: changeme-dev-key"
```

### `GET /health`

Liveness/readiness probe (no auth required).

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "production",
  "cache": {"backend": "redis", "ok": true},
  "celery_eager": false
}
```

### Error Schema

All errors follow a consistent structured JSON envelope:

```json
{
  "error": {
    "code": "video_unavailable",
    "message": "Failed to extract TikTok video: ...",
    "status_code": 404,
    "details": {}
  }
}
```

Common `code` values: `validation_error`, `unauthorized`, `rate_limited`,
`invalid_url`, `video_private`, `video_unavailable`, `extraction_failed`,
`task_not_found`, `task_not_ready`, `internal_error`.

---

## Local Setup

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env: set API_KEYS to a long random string
docker compose up --build
```

This starts:

- `redis` — broker + cache
- `api`   — FastAPI / Gunicorn on `:8000`
- `worker` — Celery worker

Open <http://localhost:8000/docs>.

### Option B — Python virtualenv

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# Terminal 1 — Redis
redis-server

# Terminal 2 — Celery worker
celery -A app.workers.celery_app.celery_app worker --loglevel=info

# Terminal 3 — API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

If `REDIS_URL` is empty, the app automatically falls back to in-memory
cache + Celery eager mode. Useful for quick local demos and CI.

---

## Testing

```bash
pip install -e ".[dev]"
pytest --cov=app --cov-report=term-missing
```

The test suite mocks `yt_dlp.YoutubeDL` so no network access is required.

---

## Code Quality

```bash
pre-commit install     # one-time
black .
ruff check . --fix
mypy app
```

---

## Deployment

### Sevalla / Render / Railway / Heroku (Procfile)

The included `Procfile` declares two process types:

```
web:    gunicorn app.main:app -k uvicorn.workers.UvicornWorker ...
worker: celery -A app.workers.celery_app.celery_app worker ...
```

1. Push the repo to your provider.
2. Provision a Redis add-on; expose it as `REDIS_URL`.
3. Set required env vars (see `.env.example`).
4. Scale: `web=1`, `worker=1`.

### Fly.io

```bash
fly launch --no-deploy            # accept the existing fly.toml
fly secrets set API_KEYS=$(openssl rand -hex 24)
fly secrets set REDIS_URL=redis://...   # Upstash, Redis Cloud, etc.
fly deploy
```

For low-traffic demos, leaving `REDIS_URL` unset and keeping
`CELERY_TASK_ALWAYS_EAGER=true` (the default in `fly.toml`) makes the API
work as a single self-contained machine.

### Any Docker host

```bash
docker build -t tiktok-downloader-api .
docker run --rm -p 8000:8000 \
  -e API_KEYS=changeme \
  -e REDIS_URL=redis://your-redis:6379/0 \
  tiktok-downloader-api
```

---

## Configuration Reference

| Variable | Default | Purpose |
|---|---|---|
| `API_KEYS` | *(empty)* | Comma-separated list. Empty disables auth. |
| `API_KEY_HEADER` | `X-API-Key` | Auth header name |
| `REDIS_URL` | *(empty)* | Redis URI; empty = in-memory + eager Celery |
| `CACHE_TTL_SECONDS` | `3600` | Result + metadata cache TTL |
| `RATE_LIMIT` | `60/minute` | Per-IP rate limit (SlowAPI syntax) |
| `RATE_LIMIT_ENABLED` | `true` | Disable for testing |
| `CELERY_TASK_ALWAYS_EAGER` | `false` | Force synchronous task execution |
| `LOG_LEVEL` | `INFO` | structlog/stdlib log level |
| `CORS_ORIGINS` | `*` | Comma-separated origins |
| `YTDLP_SOCKET_TIMEOUT` | `20` | yt-dlp socket timeout (sec) |
| `YTDLP_RETRIES` | `3` | yt-dlp retry count |

See `.env.example` for the full list.

---

## Postman Collection

A ready-to-import collection lives at
[`postman/tiktok-downloader.postman_collection.json`](postman/tiktok-downloader.postman_collection.json).
Set the `base_url` and `api_key` collection variables, then hit any
endpoint.

---

## License

MIT
