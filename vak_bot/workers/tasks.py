from __future__ import annotations

from datetime import datetime, timedelta

from celery.utils.log import get_task_logger
from dateutil.parser import parse as parse_dt

from vak_bot.config import get_settings
from vak_bot.pipeline.orchestrator import (
    notify_token_expiry,
    purge_old_reference_images,
    run_caption_rewrite,
    run_generation_pipeline,
    run_publish,
)
from vak_bot.pipeline.poster import MetaGraphPoster
from vak_bot.storage import R2StorageClient
from vak_bot.workers.celery_app import celery_app

logger = get_task_logger(__name__)
settings = get_settings()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def process_post_task(self, post_id: int, chat_id: int) -> None:
    logger.info("process_post_task_start post_id=%s", post_id)
    run_generation_pipeline(post_id=post_id, chat_id=chat_id)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def rewrite_caption_task(self, post_id: int, chat_id: int, instruction: str) -> None:
    logger.info("rewrite_caption_task_start post_id=%s", post_id)
    run_caption_rewrite(post_id=post_id, chat_id=chat_id, rewrite_instruction=instruction)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def publish_post_task(self, post_id: int, chat_id: int, posted_by: str) -> None:
    logger.info("publish_post_task_start post_id=%s", post_id)
    poster = MetaGraphPoster()
    run_publish(post_id=post_id, chat_id=chat_id, posted_by=posted_by, poster_client=poster)


@celery_app.task
def refresh_meta_token_task() -> None:
    poster = MetaGraphPoster()
    result = poster.refresh_page_token()
    logger.info("meta_token_refresh_result=%s", result)

    expiry = settings.meta_token_expires_at
    if not expiry or not settings.founder_telegram_chat_id:
        return

    expiry_dt = parse_dt(expiry)
    if expiry_dt - datetime.utcnow() <= timedelta(days=7):
        notify_token_expiry(settings.founder_telegram_chat_id, expiry_dt.isoformat())


@celery_app.task
def cleanup_reference_images_task() -> int:
    storage = R2StorageClient()
    deleted = purge_old_reference_images(days=30, storage_client=storage)
    logger.info("cleanup_reference_images deleted=%s", deleted)
    return deleted
