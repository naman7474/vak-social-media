from __future__ import annotations

from celery import Celery

from vak_bot.config import get_settings

settings = get_settings()

celery_app = Celery("vak_bot", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.default_posting_timezone,
    enable_utc=True,
    task_track_started=True,
    task_routes={
        "vak_bot.workers.tasks.process_post_task": {"queue": "pipeline"},
        "vak_bot.workers.tasks.process_video_post_task": {"queue": "pipeline"},
        "vak_bot.workers.tasks.extend_video_task": {"queue": "pipeline"},
        "vak_bot.workers.tasks.reel_this_task": {"queue": "pipeline"},
        "vak_bot.workers.tasks.publish_post_task": {"queue": "pipeline"},
        "vak_bot.workers.tasks.rewrite_caption_task": {"queue": "pipeline"},
        "vak_bot.workers.tasks.refresh_meta_token_task": {"queue": "maintenance"},
        "vak_bot.workers.tasks.cleanup_reference_images_task": {"queue": "maintenance"},
    },
    beat_schedule={
        "refresh-meta-token-daily": {
            "task": "vak_bot.workers.tasks.refresh_meta_token_task",
            "schedule": 86400,
        },
        "cleanup-reference-images-daily": {
            "task": "vak_bot.workers.tasks.cleanup_reference_images_task",
            "schedule": 86400,
        },
    },
)

celery_app.autodiscover_tasks(["vak_bot.workers"])
