# Vâk Telegram -> Instagram Bot

Production-oriented v1 implementation of the PRD in `PRD.md`.

## Stack

- FastAPI (webhook API)
- aiogram (Telegram bot interactions)
- Celery + Redis (background jobs + beat)
- PostgreSQL + SQLAlchemy + Alembic
- Cloudflare R2 / S3 compatible storage

## Implemented v1 Scope

- `/start`, `/help`
- Intake: Instagram/Pinterest link + photo(s), or link + product code
- Product code lookup from DB
- Carousel support when multiple source photos are provided
- Pipeline: DataBright -> OpenAI style brief -> Gemini variants (3) -> SSIM check -> Claude caption
- Approval actions: `1|2|3`, `edit caption`, `redo`, `approve`, `cancel`, `post now`
- Immediate Instagram publish via Meta Graph API
- Security: allowlist, daily post cap (10 per user)
- Reliability: retries, user-friendly errors, token refresh + expiry alert, ref image cleanup

## Deferred from v1

- Scheduling and queue commands (`schedule`, `/queue`, `/recent`, `/stats`, `/cancel [id]`)
- Facebook cross-post

## Quick Start

1. Copy envs:

```bash
cp .env.example .env
```

2. Bring up local services:

```bash
docker compose up --build
```

3. Run migrations:

```bash
alembic upgrade head
```

4. Set Telegram webhook to:

```text
https://<your-domain>/webhooks/telegram
```

5. Start worker + beat (if not using compose):

```bash
celery -A vak_bot.workers.celery_app.celery_app worker -Q pipeline,maintenance --loglevel=info
celery -A vak_bot.workers.celery_app.celery_app beat --loglevel=info
```

## Railway Deployment

Create three Railway services from this repo:

1. `web` service start command:

```bash
uvicorn vak_bot.main:app --host 0.0.0.0 --port $PORT
```

2. `worker` service start command:

```bash
celery -A vak_bot.workers.celery_app.celery_app worker -Q pipeline,maintenance --loglevel=info
```

3. `beat` service start command:

```bash
celery -A vak_bot.workers.celery_app.celery_app beat --loglevel=info
```

Attach the same env vars to all services.

## Notes

- `DRY_RUN=true` lets you test full orchestration without live third-party API calls.
- Reference images are cleaned up after 30 days by a scheduled beat task.
- If both product code and uploaded photos are sent, uploaded photos are preferred.
