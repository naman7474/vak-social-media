from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import httpx
import structlog

from vak_bot.bot.sender import send_review_package, send_text
from vak_bot.db.models import JobRun, Post, PostVariant, PostVariantItem
from vak_bot.db.session import SessionLocal
from vak_bot.enums import JobStage, JobStatus, PostStatus
from vak_bot.pipeline.analyzer import OpenAIReferenceAnalyzer
from vak_bot.pipeline.caption_writer import ClaudeCaptionWriter
from vak_bot.pipeline.downloader import DataBrightDownloader
from vak_bot.pipeline.errors import PipelineError
from vak_bot.pipeline.gemini_styler import GeminiStyler
from vak_bot.pipeline.saree_validator import SareeValidator
from vak_bot.schemas import StyleBrief

logger = structlog.get_logger(__name__)


@contextmanager
def stage_run(session, post_id: int, stage: JobStage):
    run = JobRun(
        post_id=post_id,
        stage=stage.value,
        status=JobStatus.STARTED.value,
    )
    session.add(run)
    session.commit()
    try:
        yield
        run.status = JobStatus.SUCCEEDED.value
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as exc:
        run.status = JobStatus.FAILED.value
        run.error_code = getattr(exc, "error_code", "internal_error")
        run.error_message = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        raise


def _fetch_bytes(url: str) -> bytes:
    with httpx.Client(timeout=40.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def _build_product_info(post: Post) -> dict:
    if not post.product:
        return {}
    return {
        "product_code": post.product.product_code,
        "product_name": post.product.product_name,
        "product_type": post.product.product_type,
        "fabric": post.product.fabric,
        "colors": post.product.colors,
        "motif": post.product.motif,
        "artisan_name": post.product.artisan_name,
        "days_to_make": post.product.days_to_make,
        "technique": post.product.technique,
        "price": str(post.product.price) if post.product.price is not None else None,
        "shopify_url": post.product.shopify_url,
    }


def _resolve_saree_sources(post: Post) -> list[str]:
    if post.input_photo_urls:
        return list(post.input_photo_urls)
    if post.product_id and post.product and post.product.photos:
        ordered = sorted(post.product.photos, key=lambda p: (not p.is_primary, p.id))
        return [photo.photo_url for photo in ordered]
    return []


def run_generation_pipeline(post_id: int, chat_id: int) -> None:
    downloader = DataBrightDownloader()
    analyzer = OpenAIReferenceAnalyzer()
    styler = GeminiStyler()
    captioner = ClaudeCaptionWriter()
    validator = SareeValidator(threshold=0.6)

    with SessionLocal() as session:
        post = session.get(Post, post_id)
        if not post:
            logger.error("post_not_found", post_id=post_id)
            return

        if post.status == PostStatus.CANCELLED.value:
            return

        post.status = PostStatus.PROCESSING.value
        post.error_code = None
        post.error_message = None
        session.commit()

        try:
            with stage_run(session, post_id, JobStage.DOWNLOAD):
                reference = downloader.download_post(post.reference_url or "")
                post.reference_image = reference.image_urls[0]
                post.source_caption = reference.caption
                post.source_hashtags = reference.hashtags
                post.source_image_urls = reference.image_urls
                session.commit()

            with stage_run(session, post_id, JobStage.ANALYZE):
                style_brief = analyzer.analyze_reference(post.reference_image or "", post.source_caption)
                post.style_brief = style_brief.model_dump()
                session.commit()

            with stage_run(session, post_id, JobStage.STYLE):
                saree_sources = _resolve_saree_sources(post)
                if not saree_sources:
                    raise PipelineError("No saree photo found for this post")

                variants = styler.generate_variants(
                    saree_images=saree_sources,
                    reference_image_url=post.reference_image or "",
                    style_brief=style_brief,
                    overlay_text=None,
                )

                existing = session.query(PostVariant).filter(PostVariant.post_id == post_id).all()
                for old_variant in existing:
                    for old_item in old_variant.items:
                        session.delete(old_item)
                    session.delete(old_variant)
                session.commit()

                original_bytes = _fetch_bytes(saree_sources[0])

                persisted_preview_urls: list[str] = []
                for variant in variants:
                    generated_bytes = _fetch_bytes(variant.preview_url)
                    is_valid, score = validator.verify_preserved(original_bytes, generated_bytes)
                    record = PostVariant(
                        post_id=post_id,
                        variant_index=variant.variant_index,
                        preview_url=variant.preview_url,
                        ssim_score=score,
                        is_valid=is_valid,
                    )
                    session.add(record)
                    session.flush()
                    for idx, image_url in enumerate(variant.item_urls, start=1):
                        session.add(
                            PostVariantItem(variant_id=record.id, position=idx, image_url=image_url)
                        )
                    if is_valid:
                        persisted_preview_urls.append(variant.preview_url)

                if not persisted_preview_urls:
                    raise PipelineError("No valid variants passed saree preservation check")

                post.styled_image = persisted_preview_urls[0]
                session.commit()

            with stage_run(session, post_id, JobStage.CAPTION):
                caption_package = captioner.generate_caption(
                    styled_image_url=post.styled_image or "",
                    style_brief=style_brief,
                    product_info=_build_product_info(post),
                )
                post.caption = caption_package.caption
                post.hashtags = caption_package.hashtags
                post.alt_text = caption_package.alt_text
                post.status = PostStatus.REVIEW_READY.value
                session.commit()

            with stage_run(session, post_id, JobStage.REVIEW):
                valid_variants = (
                    session.query(PostVariant)
                    .filter(PostVariant.post_id == post_id, PostVariant.is_valid.is_(True))
                    .order_by(PostVariant.variant_index.asc())
                    .limit(3)
                    .all()
                )
                send_review_package(
                    chat_id=chat_id,
                    post_id=post.id,
                    image_urls=[variant.preview_url for variant in valid_variants],
                    caption=post.caption or "",
                    hashtags=post.hashtags or "",
                )

            logger.info("generation_pipeline_complete", post_id=post_id)
        except PipelineError as exc:
            post.status = PostStatus.FAILED.value
            post.error_code = exc.error_code
            post.error_message = str(exc)
            session.commit()
            send_text(chat_id, exc.user_message)
            logger.warning("pipeline_error", post_id=post_id, error_code=exc.error_code, error=str(exc))
        except Exception as exc:
            post.status = PostStatus.FAILED.value
            post.error_code = "internal_error"
            post.error_message = str(exc)
            session.commit()
            send_text(chat_id, "Something unexpected happened. Please retry.")
            logger.exception("pipeline_unhandled_error", post_id=post_id, error=str(exc))


def run_caption_rewrite(post_id: int, chat_id: int, rewrite_instruction: str) -> None:
    captioner = ClaudeCaptionWriter()

    with SessionLocal() as session:
        post = session.get(Post, post_id)
        if not post or not post.style_brief or not post.styled_image:
            return

        brief = dict(post.style_brief)
        brief["adaptation_notes"] = f"Rewrite instruction from user: {rewrite_instruction}"
        style_brief = StyleBrief.model_validate(brief)

        try:
            with stage_run(session, post_id, JobStage.CAPTION):
                package = captioner.generate_caption(
                    styled_image_url=post.styled_image,
                    style_brief=style_brief,
                    product_info=_build_product_info(post),
                )
                post.caption = package.caption
                post.hashtags = package.hashtags
                post.alt_text = package.alt_text
                post.status = PostStatus.REVIEW_READY.value
                session.commit()

            send_text(chat_id, "Updated caption is ready. Reply 'approve' or 'post now'.")
        except PipelineError as exc:
            send_text(chat_id, exc.user_message)
        except Exception:
            send_text(chat_id, "Caption rewrite failed. Please try again.")


def run_publish(post_id: int, chat_id: int, posted_by: str, poster_client) -> None:
    with SessionLocal() as session:
        post = session.get(Post, post_id)
        if not post:
            return
        if post.status == PostStatus.POSTED.value:
            send_text(chat_id, f"Already posted: {post.instagram_url}")
            return

        variant = (
            session.query(PostVariant)
            .filter(PostVariant.post_id == post_id, PostVariant.variant_index == (post.selected_variant_index or 1))
            .first()
        )
        if not variant:
            send_text(chat_id, "Please select a variant first (1, 2, or 3).")
            return

        post.status = PostStatus.APPROVED.value
        post.publish_idempotency_key = post.publish_idempotency_key or f"post:{post.id}:variant:{variant.variant_index}:{uuid.uuid4().hex[:8]}"
        session.commit()

        try:
            with stage_run(session, post_id, JobStage.POST):
                if post.media_type == "carousel":
                    items = (
                        session.query(PostVariantItem)
                        .filter(PostVariantItem.variant_id == variant.id)
                        .order_by(PostVariantItem.position.asc())
                        .all()
                    )
                    result = poster_client.post_carousel(
                        image_urls=[item.image_url for item in items],
                        caption=f"{post.caption}\n\n{post.hashtags}",
                        alt_text=post.alt_text or "",
                        idempotency_key=post.publish_idempotency_key,
                    )
                else:
                    result = poster_client.post_single_image(
                        image_url=variant.preview_url,
                        caption=f"{post.caption}\n\n{post.hashtags}",
                        alt_text=post.alt_text or "",
                        idempotency_key=post.publish_idempotency_key,
                    )

                post.instagram_post_id = result.get("id")
                post.instagram_url = result.get("permalink")
                post.posted_at = datetime.now(timezone.utc)
                post.posted_by = posted_by
                post.status = PostStatus.POSTED.value
                session.commit()

            send_text(chat_id, f"Posted successfully: {post.instagram_url}")
        except PipelineError as exc:
            post.status = PostStatus.FAILED.value
            post.error_code = exc.error_code
            post.error_message = str(exc)
            session.commit()
            send_text(chat_id, exc.user_message)
        except Exception as exc:
            post.status = PostStatus.FAILED.value
            post.error_code = "publish_error"
            post.error_message = str(exc)
            session.commit()
            send_text(chat_id, "Posting failed. You can retry with 'post now'.")


def purge_old_reference_images(days: int, storage_client) -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 24 * 3600)
    deleted = 0
    with SessionLocal() as session:
        posts = session.query(Post).filter(Post.reference_image.is_not(None)).all()
        for post in posts:
            if post.created_at.timestamp() <= cutoff and post.reference_image:
                storage_client.delete_by_url(post.reference_image)
                post.reference_image = None
                deleted += 1
        session.commit()
    return deleted


def notify_token_expiry(chat_id: int, expiry_text: str) -> None:
    send_text(chat_id, f"Meta page token is nearing expiry ({expiry_text}). Refresh it this week.")
