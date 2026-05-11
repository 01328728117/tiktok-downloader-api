# Deploy to Sevalla

This guide walks you through deploying the TikTok Downloader API to
[Sevalla](https://sevalla.com) end to end — web service, Redis broker, and the
Celery background worker.

## Prerequisites

- A Sevalla account with billing or trial credit attached.
- The `01328728117/tiktok-downloader-api` repository connected to Sevalla
  (Sevalla → Settings → Connect Git provider → GitHub → grant access).
- At least one API key generated for `X-API-Key` auth
  (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).

## 1. Add the application

1. Sevalla dashboard → **Applications** → **Add application**.
2. Select GitHub → `01328728117/tiktok-downloader-api`.
3. Branch: `develop` (or your default after merging Sevalla PR).
4. Build strategy: **Nixpacks** (default). The repo includes a
   [`nixpacks.toml`](../nixpacks.toml) that pins Python 3.11, installs
   `ffmpeg`, and sets the gunicorn start command.
5. Instance size: start with the smallest tier (~0.5 GB RAM / 0.5 CPU) — bump
   later if you hit memory limits when extracting long videos.
6. Location: pick a region close to your users; the Redis database (next step)
   must live in the same region so internal networking can connect them.

## 2. Provision Redis

1. Sevalla dashboard → **Databases** → **Add database** → **Redis** → pick the
   same region as the application.
2. Once provisioned, the Redis instance has both an **internal** and
   **external** connection string. Use the internal one.

## 3. Wire Redis to the application

1. Open your application → **Networking** → **Add internal connection**.
2. Pick the Redis database created in step 2.
3. Click **Add environment variables to the application**. Sevalla will
   inject a `DB_URL` (or similar). **Rename it to `REDIS_URL`** before
   clicking **Add internal connection**.

## 4. Configure environment variables

Application → **Environment variables**, paste:

```
ENVIRONMENT=production
LOG_LEVEL=INFO
API_KEYS=<your-generated-key-1>,<your-generated-key-2>
RATE_LIMIT=60/minute
RATE_LIMIT_ENABLED=true
CACHE_TTL_SECONDS=3600
CELERY_TASK_ALWAYS_EAGER=false
WEB_CONCURRENCY=2
WORKER_CONCURRENCY=2
CORS_ORIGINS=*
```

`REDIS_URL` was injected automatically in step 3 — don't duplicate it.

## 5. Add the background worker

The Celery worker is a separate Sevalla process.

1. Application → **Processes** → **Create process** → **Background worker**.
2. Start command:
   ```
   /opt/venv/bin/celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=${WORKER_CONCURRENCY:-2}
   ```
3. Instance size: smallest tier is usually enough — the worker is mostly
   network-bound (yt-dlp calling TikTok).

The worker process inherits the application's environment variables, so it
will pick up `REDIS_URL`, `API_KEYS`, etc. automatically.

## 6. Deploy

Push the application — Sevalla detects the Nixpacks config, builds, and
exposes the service on a `<your-app>.sevalla.app` hostname. The
`/health` endpoint should return `200` once the container starts.

```sh
curl https://<your-app>.sevalla.app/health
```

Then verify a real extraction (replace API key):

```sh
curl -X POST "https://<your-app>.sevalla.app/api/v1/download" \
  -H "X-API-Key: <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.tiktok.com/@scout2015/video/6718335390845095173","quality":"high","format":"mp4"}'
```

## 7. Custom domain (optional)

Application → **Domains** → **Add domain** → follow the DNS instructions
(Sevalla will print the exact CNAME / A records). TLS is provisioned
automatically.

## 8. Logs & observability

Application → **Logs** streams structlog JSON output. Search by `code=`,
`task_id=`, or `status_code=`. The worker's logs are under
**Processes → background worker → Logs**.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `cache.backend=memory` on `/health` after deploy | `REDIS_URL` isn't injected — re-check step 3. |
| Worker logs show `[ERROR] Connection refused` | Redis is in a different region or down — re-create in the same region. |
| TikTok extraction fails with `Your IP address is blocked from accessing this post` | TikTok blocks Sevalla's datacenter IPs. Route via a residential proxy with `HTTPS_PROXY`. |
| `429 rate_limited` for legitimate users | Bump `RATE_LIMIT` (e.g. `120/minute`) or scale to multiple web instances. |
| Builds fail with `ffmpeg not found` | Confirm `nixpacks.toml` is committed at the repo root. |

## Switching to Dockerfile builds

If you prefer the project Dockerfile over Nixpacks:

1. Application → **Settings** → **Build strategy** → **Dockerfile**.
2. Re-deploy. The repo's [`Dockerfile`](../Dockerfile) already includes
   ffmpeg, gunicorn, and the same start command — no other changes needed.
