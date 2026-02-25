from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import httpx
import structlog

from vak_bot.bot.sender import send_review_package, send_text, send_video_review_package
from vak_bot.db.models import JobRun, Post, PostVariant, PostVariantItem, VideoJob
from vak_bot.db.session import SessionLocal
from vak_bot.enums import JobStage, JobStatus, PostStatus
from vak_bot.pipeline.analyzer import OpenAIReferenceAnalyzer
from vak_bot.pipeline.caption_writer import ClaudeCaptionWriter
from vak_bot.pipeline.downloader import DataBrightDownloader
from vak_bot.pipeline.errors import PipelineError, VideoQualityError
from vak_bot.pipeline.gemini_styler import GeminiStyler
from vak_bot.pipeline.llm_utils import normalize_claude_model, normalize_gemini_image_model, normalize_openai_model
from vak_bot.pipeline.saree_validator import SareeValidator
from vak_bot.pipeline.veo_generator import VeoGenerator
from vak_bot.pipeline.video_stitcher import extract_first_frame, compress_video
from vak_bot.schemas import StyleBrief
from vak_bot.storage import R2StorageClient

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
    validator = SareeValidator(threshold=0.75)
    logger.info(
        "generation_models_configured",
        openai_model=normalize_openai_model(analyzer.settings.openai_model),
        gemini_model=normalize_gemini_image_model(styler.settings.gemini_image_model),
        claude_model=normalize_claude_model(captioner.settings.claude_model),
    )

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

                reference_urls = list(post.source_image_urls or [])
                if not reference_urls and post.reference_image:
                    reference_urls = [post.reference_image]

                if len(reference_urls) > 1:
                    post.media_type = "carousel"

                variants = styler.generate_variants(
                    saree_image_url=saree_sources[0],
                    reference_image_urls=reference_urls,
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
                low_ssim_variants: list[int] = []
                for variant in variants:
                    generated_bytes = _fetch_bytes(variant.preview_url)
                    is_valid, score, lpips_score = validator.verify_preserved(original_bytes, generated_bytes)
                    
                    if not is_valid or (lpips_score is not None and lpips_score > validator.lpips_threshold):
                        # Treat as warning only per user request
                        is_valid = True
                        low_ssim_variants.append(variant.variant_index)
                        logger.warning(
                            "low_ssim_or_lpips_score",
                            variant=variant.variant_index,
                            ssim_score=round(score, 4),
                            lpips_score=round(lpips_score, 4) if lpips_score is not None else None,
                            threshold=validator.threshold,
                        )
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
                    persisted_preview_urls.append(variant.preview_url)

                if low_ssim_variants:
                    logger.warning(
                        "saree_preservation_warning",
                        post_id=post_id,
                        low_ssim_variants=low_ssim_variants,
                        message="Some variants may have altered the saree. Human review recommended.",
                    )

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
                all_variants = (
                    session.query(PostVariant)
                    .filter(PostVariant.post_id == post_id)
                    .order_by(PostVariant.variant_index.asc())
                    .limit(3)
                    .all()
                )
                # Send all generated images (all carousel items) for review
                all_image_urls: list[str] = []
                for variant in all_variants:
                    items = (
                        session.query(PostVariantItem)
                        .filter(PostVariantItem.variant_id == variant.id)
                        .order_by(PostVariantItem.position.asc())
                        .all()
                    )
                    all_image_urls.extend(item.image_url for item in items)
                send_review_package(
                    chat_id=chat_id,
                    post_id=post.id,
                    image_urls=all_image_urls,
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
                    is_reel=(post.media_type == "reel"),
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

        post.status = PostStatus.APPROVED.value
        post.publish_idempotency_key = post.publish_idempotency_key or f"post:{post.id}:{uuid.uuid4().hex[:8]}"
        session.commit()

        try:
            with stage_run(session, post_id, JobStage.POST):
                if post.media_type == "reel":
                    if not post.video_url:
                        send_text(chat_id, "No video found for this post.")
                        return

                    publish_video_url = post.video_url
                    tmp_paths: list[str] = []
                    try:
                        import tempfile
                        from pathlib import Path

                        local_bytes = _fetch_bytes(post.video_url)
                        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
                            tf.write(local_bytes)
                            local_video_path = tf.name
                        tmp_paths.append(local_video_path)

                        compressed_path = compress_video(local_video_path, max_size_mb=950)
                        if compressed_path != local_video_path:
                            tmp_paths.append(compressed_path)
                            compressed_bytes = Path(compressed_path).read_bytes()
                            storage = R2StorageClient()
                            comp_key = f"reels/{post.id}/publish_compressed_{uuid.uuid4().hex[:6]}.mp4"
                            publish_video_url = storage.upload_bytes(comp_key, compressed_bytes, content_type="video/mp4")
                    finally:
                        for path in tmp_paths:
                            try:
                                from pathlib import Path

                                Path(path).unlink(missing_ok=True)
                            except Exception:
                                logger.warning("tmp_cleanup_failed", path=path)

                    result = poster_client.post_reel(
                        video_s3_url=publish_video_url,
                        caption=f"{post.caption}\n\n{post.hashtags}",
                        thumb_offset_ms=post.thumb_offset_ms or 0,
                        share_to_feed=True,
                    )
                else:
                    variant = (
                        session.query(PostVariant)
                        .filter(PostVariant.post_id == post_id, PostVariant.variant_index == (post.selected_variant_index or 1))
                        .first()
                    )
                    if not variant:
                        send_text(chat_id, "Please select a variant first (1, 2, or 3).")
                        return
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


# ══════════════════════════════════════════════════════════════════════════════
# VIDEO / REEL PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run_video_generation_pipeline(post_id: int, chat_id: int) -> None:
    """Full video generation pipeline — download → analyze → style start frame → Veo → caption → review."""
    downloader = DataBrightDownloader()
    analyzer = OpenAIReferenceAnalyzer()
    styler = GeminiStyler()
    veo = VeoGenerator()
    captioner = ClaudeCaptionWriter()
    validator = SareeValidator(threshold=0.75)
    video_validator = SareeValidator(threshold=0.8)
    storage = R2StorageClient()

    with SessionLocal() as session:
        post = session.get(Post, post_id)
        if not post:
            logger.error("post_not_found", post_id=post_id)
            return

        if post.status == PostStatus.CANCELLED.value:
            return

        post.status = PostStatus.PROCESSING.value
        post.media_type = "reel"
        post.error_code = None
        post.error_message = None
        session.commit()

        try:
            # ── Step 1: Download ──
            with stage_run(session, post_id, JobStage.DOWNLOAD):
                reference = downloader.download_post(post.reference_url or "")
                post.reference_image = reference.image_urls[0] if reference.image_urls else reference.thumbnail_url
                post.source_caption = reference.caption
                post.source_hashtags = reference.hashtags
                post.source_image_urls = reference.image_urls
                session.commit()

            # ── Step 2: Analyze (with video fields) ──
            with stage_run(session, post_id, JobStage.ANALYZE):
                style_brief = analyzer.analyze_reference(
                    post.reference_image or "",
                    post.source_caption,
                    is_video=True,
                )
                style_brief.composition.aspect_ratio = "9:16"
                post.style_brief = style_brief.model_dump()
                if style_brief.video_analysis:
                    post.video_style_brief = style_brief.video_analysis.model_dump()
                    post.video_type = style_brief.video_analysis.recommended_video_type
                session.commit()

            # ── Step 3: Style Start Frame (9:16) ──
            with stage_run(session, post_id, JobStage.STYLE):
                saree_sources = _resolve_saree_sources(post)
                if not saree_sources:
                    raise PipelineError("No saree photo found for this post")

                reference_urls = list(post.source_image_urls or [])
                if not reference_urls and post.reference_image:
                    reference_urls = [post.reference_image]

                variants = styler.generate_variants(
                    saree_image_url=saree_sources[0],
                    reference_image_urls=reference_urls,
                    style_brief=style_brief,
                    overlay_text=None,
                )

                if variants:
                    original_bytes = _fetch_bytes(saree_sources[0])
                    generated_bytes = _fetch_bytes(variants[0].preview_url)
                    is_valid, score, lpips_score = validator.verify_preserved(original_bytes, generated_bytes)
                    
                    if not is_valid or (lpips_score is not None and lpips_score > validator.lpips_threshold):
                        logger.warning(
                            "styled_frame_quality_warning",
                            ssim_score=round(score, 4),
                            lpips_score=round(lpips_score, 4) if lpips_score is not None else None,
                        )

                    post.styled_image = variants[0].preview_url
                    post.start_frame_url = variants[0].preview_url
                    session.commit()

            # ── Step 4: Generate Video (Veo 3.1) ──
            with stage_run(session, post_id, JobStage.VIDEO_GENERATE):
                # Download the styled frame to a temp file for Veo
                import tempfile
                from pathlib import Path

                styled_bytes = _fetch_bytes(post.styled_image or "")
                tmp_paths: list[str] = []
                try:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                        tf.write(styled_bytes)
                        styled_frame_path = tf.name
                    tmp_paths.append(styled_frame_path)

                    video_paths = veo.generate_reel_variations(
                        styled_frame_path=styled_frame_path,
                        style_brief=style_brief,
                        video_type=post.video_type,
                    )

                    tmp_paths.extend(video_paths)

                    # Upload videos to R2 and create VideoJob records
                    video_urls: list[str] = []
                    for idx, video_path in enumerate(video_paths, start=1):
                        try:
                            first_frame = extract_first_frame(video_path)
                            is_valid_video, video_ssim, video_lpips = video_validator.verify_preserved(styled_bytes, first_frame)
                            if not is_valid_video or (video_lpips is not None and video_lpips > video_validator.lpips_threshold):
                                logger.warning(
                                    "video_first_frame_warning",
                                    post_id=post_id,
                                    variation=idx,
                                    ssim_score=round(video_ssim, 4),
                                    lpips_score=round(video_lpips, 4) if video_lpips is not None else None,
                                    threshold=video_validator.threshold,
                                )
                        except Exception as exc:
                            logger.warning(
                                "video_first_frame_check_skipped",
                                post_id=post_id,
                                variation=idx,
                                error=str(exc),
                            )

                        video_bytes = Path(video_path).read_bytes()
                        video_key = f"reels/{post.id}/variation_{idx}_{uuid.uuid4().hex[:6]}.mp4"
                        video_s3_url = storage.upload_bytes(video_key, video_bytes, content_type="video/mp4")
                        video_urls.append(video_s3_url)

                        job = VideoJob(
                            post_id=post_id,
                            variation_number=idx,
                            video_url=video_s3_url,
                            status="done",
                        )
                        session.add(job)

                    if not video_urls:
                        raise VideoQualityError("No video variation was successfully generated or uploaded.")

                    post.video_url = video_urls[0]  # default to first
                    post.video_duration = 8
                    session.commit()
                finally:
                    for path in tmp_paths:
                        try:
                            Path(path).unlink(missing_ok=True)
                        except Exception:
                            logger.warning("tmp_cleanup_failed", path=path)

            # ── Step 5: Caption (Reel mode) ──
            with stage_run(session, post_id, JobStage.CAPTION):
                caption_package = captioner.generate_caption(
                    styled_image_url=post.styled_image or "",
                    style_brief=style_brief,
                    product_info=_build_product_info(post),
                    is_reel=True,
                )
                post.caption = caption_package.caption
                post.hashtags = caption_package.hashtags
                post.alt_text = caption_package.alt_text
                if hasattr(caption_package, "thumb_offset_ms"):
                    post.thumb_offset_ms = caption_package.thumb_offset_ms
                post.status = PostStatus.REVIEW_READY.value
                session.commit()

            # ── Step 6: Send for Review ──
            with stage_run(session, post_id, JobStage.REVIEW):
                video_jobs = (
                    session.query(VideoJob)
                    .filter(VideoJob.post_id == post_id, VideoJob.status == "done")
                    .order_by(VideoJob.variation_number.asc())
                    .all()
                )
                video_review_urls = [j.video_url for j in video_jobs if j.video_url]
                send_video_review_package(
                    chat_id=chat_id,
                    post_id=post.id,
                    video_urls=video_review_urls,
                    start_frame_url=post.start_frame_url or "",
                    caption=post.caption or "",
                    hashtags=post.hashtags or "",
                )

            logger.info("video_generation_pipeline_complete", post_id=post_id)
        except PipelineError as exc:
            post.status = PostStatus.FAILED.value
            post.error_code = exc.error_code
            post.error_message = str(exc)
            session.commit()
            send_text(chat_id, exc.user_message)
            logger.warning("video_pipeline_error", post_id=post_id, error_code=exc.error_code, error=str(exc))
        except Exception as exc:
            post.status = PostStatus.FAILED.value
            post.error_code = "internal_error"
            post.error_message = str(exc)
            session.commit()
            send_text(chat_id, "Something unexpected happened with video generation. Please retry.")
            logger.exception("video_pipeline_unhandled_error", post_id=post_id, error=str(exc))


def run_reel_this_conversion(post_id: int, chat_id: int) -> None:
    """Convert an already-styled image post into a Reel (skip Steps 1-3, start from Veo)."""
    veo = VeoGenerator()
    captioner = ClaudeCaptionWriter()
    video_validator = SareeValidator(threshold=0.7)
    storage = R2StorageClient()

    with SessionLocal() as session:
        post = session.get(Post, post_id)
        if not post or not post.styled_image:
            send_text(chat_id, "No styled image available to convert to a Reel.")
            return

        post.media_type = "reel"
        post.status = PostStatus.PROCESSING.value
        session.commit()

        try:
            style_brief = StyleBrief.model_validate(post.style_brief or {})
            style_brief.composition.aspect_ratio = "9:16"

            with stage_run(session, post_id, JobStage.VIDEO_GENERATE):
                import tempfile
                from pathlib import Path

                styled_bytes = _fetch_bytes(post.styled_image)
                tmp_paths: list[str] = []
                try:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                        tf.write(styled_bytes)
                        styled_frame_path = tf.name
                    tmp_paths.append(styled_frame_path)

                    post.start_frame_url = post.styled_image

                    video_paths = veo.generate_reel_variations(
                        styled_frame_path=styled_frame_path,
                        style_brief=style_brief,
                        video_type=post.video_type,
                    )
                    tmp_paths.extend(video_paths)

                    video_urls: list[str] = []
                    for idx, video_path in enumerate(video_paths, start=1):
                        try:
                            first_frame = extract_first_frame(video_path)
                            is_valid_video, video_ssim, video_lpips = video_validator.verify_preserved(styled_bytes, first_frame)
                            if not is_valid_video or (video_lpips is not None and video_lpips > video_validator.lpips_threshold):
                                logger.warning(
                                    "video_first_frame_warning",
                                    post_id=post_id,
                                    variation=idx,
                                    ssim_score=round(video_ssim, 4),
                                    lpips_score=round(video_lpips, 4) if video_lpips is not None else None,
                                    threshold=video_validator.threshold,
                                )
                        except Exception as exc:
                            logger.warning(
                                "video_first_frame_check_skipped",
                                post_id=post_id,
                                variation=idx,
                                error=str(exc),
                            )

                        video_bytes = Path(video_path).read_bytes()
                        video_key = f"reels/{post.id}/reelthis_{idx}_{uuid.uuid4().hex[:6]}.mp4"
                        video_s3_url = storage.upload_bytes(video_key, video_bytes, content_type="video/mp4")
                        video_urls.append(video_s3_url)
                        session.add(VideoJob(
                            post_id=post_id,
                            variation_number=idx,
                            video_url=video_s3_url,
                            status="done",
                        ))

                    if not video_urls:
                        raise VideoQualityError("No usable video variation passed the first-frame quality check.")

                    post.video_url = video_urls[0]
                    post.video_duration = 8
                    session.commit()
                finally:
                    for path in tmp_paths:
                        try:
                            Path(path).unlink(missing_ok=True)
                        except Exception:
                            logger.warning("tmp_cleanup_failed", path=path)

            with stage_run(session, post_id, JobStage.CAPTION):
                caption_package = captioner.generate_caption(
                    styled_image_url=post.styled_image,
                    style_brief=style_brief,
                    product_info=_build_product_info(post),
                    is_reel=True,
                )
                post.caption = caption_package.caption
                post.hashtags = caption_package.hashtags
                post.alt_text = caption_package.alt_text
                if hasattr(caption_package, "thumb_offset_ms"):
                    post.thumb_offset_ms = caption_package.thumb_offset_ms
                post.status = PostStatus.REVIEW_READY.value
                session.commit()

            video_jobs = (
                session.query(VideoJob)
                .filter(VideoJob.post_id == post_id, VideoJob.status == "done")
                .order_by(VideoJob.variation_number.asc())
                .all()
            )
            video_review_urls = [j.video_url for j in video_jobs if j.video_url]
            send_video_review_package(
                chat_id=chat_id,
                post_id=post.id,
                video_urls=video_review_urls,
                start_frame_url=post.start_frame_url or "",
                caption=post.caption or "",
                hashtags=post.hashtags or "",
            )

            send_text(chat_id, "Reel is ready for review!")
        except PipelineError as exc:
            post.status = PostStatus.FAILED.value
            session.commit()
            send_text(chat_id, exc.user_message)
        except Exception as exc:
            post.status = PostStatus.FAILED.value
            session.commit()
            send_text(chat_id, "Reel conversion failed. Please try again.")
            logger.exception("reel_this_error", post_id=post_id, error=str(exc))


def run_video_extension(post_id: int, chat_id: int, video_variation: int = 1) -> None:
    """Extend a selected video by 8 more seconds."""
    veo = VeoGenerator()
    storage = R2StorageClient()

    with SessionLocal() as session:
        post = session.get(Post, post_id)
        if not post:
            return

        video_job = (
            session.query(VideoJob)
            .filter(VideoJob.post_id == post_id, VideoJob.variation_number == video_variation)
            .first()
        )
        if not video_job or not video_job.video_url:
            send_text(chat_id, "No video found to extend.")
            return

        send_text(chat_id, "Extending video by 8 seconds. This will take ~3 minutes...")

        try:
            with stage_run(session, post_id, JobStage.VIDEO_EXTEND):
                import tempfile
                video_bytes = _fetch_bytes(video_job.video_url)
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
                    tf.write(video_bytes)
                    original_path = tf.name

                style_brief = StyleBrief.model_validate(post.style_brief or {})
                continuation_prompt = veo.build_video_prompt(style_brief, post.video_type)

                extended_path = veo.extend_reel(original_path, continuation_prompt)

                from pathlib import Path
                extended_bytes = Path(extended_path).read_bytes()
                ext_key = f"reels/{post.id}/extended_{video_variation}_{uuid.uuid4().hex[:6]}.mp4"
                ext_url = storage.upload_bytes(ext_key, extended_bytes, content_type="video/mp4")

                video_job.video_url = ext_url
                video_job.status = "extended"
                post.video_url = ext_url
                post.video_duration = (post.video_duration or 8) + 8
                session.commit()

            send_text(chat_id, f"Extended to {post.video_duration}s. Reply 'approve' to post, or 'extend' for more.")
        except PipelineError as exc:
            send_text(chat_id, exc.user_message)
        except Exception as exc:
            send_text(chat_id, "Video extension failed. You can still post the original clip.")


def run_multi_scene_ad_pipeline(post_id: int, chat_id: int, ad_structure: str = "30_second_reel") -> None:
    """Generate a multi-scene ad (30s or 15s) by creating discrete scenes and stitching."""
    veo = VeoGenerator()
    captioner = ClaudeCaptionWriter()
    video_validator = SareeValidator(threshold=0.75)
    storage = R2StorageClient()

    with SessionLocal() as session:
        post = session.get(Post, post_id)
        if not post or not post.styled_image:
            send_text(chat_id, "No styled image available for ad creation.")
            return

        post.status = PostStatus.PROCESSING.value
        post.media_type = "reel"
        session.commit()

        try:
            style_brief = StyleBrief.model_validate(post.style_brief or {})
            styled_bytes = _fetch_bytes(post.styled_image)

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                tf.write(styled_bytes)
                styled_frame_path = tf.name

            # Generate all scenes
            send_text(chat_id, f"🎬 Generating {ad_structure} ad — this will take 5-10 minutes...")
            scenes = veo.generate_multi_scene_ad(
                styled_frame_path=styled_frame_path,
                style_brief=style_brief,
                ad_structure=ad_structure,
            )

            if len(scenes) < 2:
                send_text(chat_id, "Could only generate 1 scene. Sending as a standard Reel instead.")
                # Fall back to single clip posting
                if scenes:
                    final_path = scenes[0]["path"]
                else:
                    return
            else:
                # Stitch scenes with FFmpeg
                from vak_bot.pipeline.video_stitcher import stitch_scenes
                final_path = stitch_scenes(
                    scene_paths=[s["path"] for s in scenes],
                    transition="dissolve",
                    transition_duration=1.5,
                )

            # Upload and send for review
            final_bytes = Path(final_path).read_bytes()
            key = f"videos/post-{post_id}/ad-{uuid.uuid4().hex[:8]}.mp4"
            video_url = storage.upload_bytes(key, final_bytes, content_type="video/mp4")

            post.video_url = video_url
            post.video_duration = sum(s["duration"] for s in scenes) if scenes else 8
            
            # Generate caption for ad
            with stage_run(session, post_id, JobStage.CAPTION):
                caption_package = captioner.generate_caption(
                    styled_image_url=post.styled_image,
                    style_brief=style_brief,
                    product_info=_build_product_info(post),
                    is_reel=True,
                )
                post.caption = caption_package.caption
                post.hashtags = caption_package.hashtags
                post.alt_text = caption_package.alt_text
                if hasattr(caption_package, "thumb_offset_ms"):
                    post.thumb_offset_ms = caption_package.thumb_offset_ms
                post.status = PostStatus.REVIEW_READY.value
            
            session.commit()

            send_text(chat_id, f"✅ {len(scenes)}-scene ad generated ({post.video_duration}s total)")
            
            send_video_review_package(
                chat_id=chat_id,
                post_id=post.id,
                video_urls=[video_url],
                start_frame_url=post.start_frame_url or post.styled_image or "",
                caption=post.caption or "",
                hashtags=post.hashtags or "",
            )

        except PipelineError as exc:
            post.status = PostStatus.FAILED.value
            post.error_message = str(exc)
            session.commit()
            send_text(chat_id, exc.user_message)
        except Exception as exc:
            post.status = PostStatus.FAILED.value
            post.error_message = str(exc)
            session.commit()
            send_text(chat_id, f"Ad generation failed: {str(exc)[:200]}")
            logger.exception("ad_generation_failed", post_id=post_id, error=str(exc))
            logger.exception("video_extension_error", post_id=post_id, error=str(exc))
