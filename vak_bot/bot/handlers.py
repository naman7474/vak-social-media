from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import structlog
from aiogram import Dispatcher, F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func

from vak_bot.bot.callbacks import parse_callback
from vak_bot.bot.parser import is_supported_reference_url, parse_message_text
from vak_bot.bot.sender import send_text
from vak_bot.bot.texts import (
    HELP_MESSAGE,
    NEED_PHOTO_MESSAGE,
    PROCESSING_MESSAGE,
    REEL_DETECTED_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    UNSUPPORTED_LINK_MESSAGE,
    V1_SCHEDULING_MESSAGE,
    VIDEO_PROCESSING_MESSAGE,
    WELCOME_MESSAGE,
)
from vak_bot.config import get_settings
from vak_bot.db.models import Post, Product, VideoJob
from vak_bot.db.session import SessionLocal
from vak_bot.enums import CallbackAction, PostStatus, SessionState
from vak_bot.services.post_service import (
    create_draft_post,
    get_or_create_session,
    lookup_product_by_code,
    product_photo_urls,
    user_posts_today,
)
from vak_bot.workers.tasks import (
    extend_video_task,
    process_post_task,
    process_video_post_task,
    publish_post_task,
    reel_this_task,
    rewrite_caption_task,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

ALBUM_CACHE: dict[str, dict] = {}
ALBUM_LOCK = asyncio.Lock()
VALID_VIDEO_TYPES = {"fabric-flow", "close-up", "lifestyle", "reveal"}


def _is_allowed(user_id: int) -> bool:
    allowed = settings.allowed_user_id_set
    return not allowed or user_id in allowed


async def _file_id_to_download_url(message: Message, file_id: str) -> str:
    file_info = await message.bot.get_file(file_id)
    return f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_info.file_path}"


async def _extract_photo_file_ids(message: Message) -> list[str]:
    file_ids: list[str] = []
    if message.photo:
        file_ids.append(message.photo[-1].file_id)
    if message.document and (message.document.mime_type or "").startswith("image/"):
        file_ids.append(message.document.file_id)
    return file_ids


async def _extract_photo_urls(message: Message) -> tuple[list[str], list[str]]:
    file_ids = await _extract_photo_file_ids(message)
    urls: list[str] = []
    for file_id in file_ids:
        urls.append(await _file_id_to_download_url(message, file_id))
    return file_ids, urls


def _normalize_video_type(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.lower().strip()
    aliases = {
        "closeup": "close-up",
        "fabric flow": "fabric-flow",
    }
    normalized = aliases.get(cleaned, cleaned)
    if normalized in VALID_VIDEO_TYPES:
        return normalized
    return None


async def _process_ingestion(chat_id: int, user_id: int, text: str | None, photo_urls: list[str], photo_file_ids: list[str], send_via_message: Message | None = None) -> None:
    async def respond(message_text: str) -> None:
        if send_via_message:
            await send_via_message.answer(message_text)
        else:
            send_text(chat_id, message_text)

    parsed = parse_message_text(text)
    if not parsed.source_url or not is_supported_reference_url(parsed.source_url):
        await respond(UNSUPPORTED_LINK_MESSAGE)
        return

    with SessionLocal() as db:
        if user_posts_today(db, user_id) >= 50:
            await respond("Daily limit reached (50 posts). Try again tomorrow.")
            return

        product = None
        if parsed.product_code:
            product = lookup_product_by_code(db, parsed.product_code)
            if not product:
                await respond(f"Product {parsed.product_code} not found. Send photos or a valid code.")
                return
            if not photo_urls:
                photo_urls = product_photo_urls(product)

        if not photo_urls:
            # Save the reference URL in the session so photos can be sent separately
            session = get_or_create_session(db, user_id, chat_id)
            session.state = SessionState.AWAITING_PHOTOS.value
            session.context_json = {"pending_source_url": parsed.source_url, "product_code": parsed.product_code}
            db.commit()
            await respond(NEED_PHOTO_MESSAGE)
            return

        post = create_draft_post(
            db=db,
            telegram_user_id=user_id,
            source_url=parsed.source_url,
            product=product,
            input_photo_urls=photo_urls,
            telegram_photo_file_ids=photo_file_ids,
        )

        session = get_or_create_session(db, user_id, chat_id)
        session.post_id = post.id
        session.state = SessionState.AWAITING_APPROVAL.value
        session.context_json = {"selected_variant": None}
        db.commit()

    await respond(PROCESSING_MESSAGE)

    # Auto-detect media type and route to the right pipeline
    from vak_bot.pipeline.route_detector import resolve_pipeline_type
    pipeline_type = resolve_pipeline_type(parsed.source_url, text)
    if parsed.media_override:  # explicit user override takes priority
        pipeline_type = parsed.media_override

    # Store detected media type
    with SessionLocal() as db_update:
        p = db_update.get(Post, post.id)
        if p:
            p.detected_media_type = pipeline_type
            db_update.commit()

    if pipeline_type == "reel":
        await respond(REEL_DETECTED_MESSAGE)
        process_video_post_task.delay(post.id, chat_id)
    else:
        process_post_task.delay(post.id, chat_id)


async def _handle_action(message: Message, action: str) -> bool:
    user_id = message.from_user.id
    chat_id = message.chat.id

    with SessionLocal() as db:
        session = get_or_create_session(db, user_id, chat_id)
        if not session.post_id:
            return False

        post = db.get(Post, session.post_id)
        if not post:
            return False

        action_lower = action.lower().strip()

        if action_lower in {"1", "2", "3"}:
            selected = int(action_lower)
            post.selected_variant_index = selected
            if post.media_type == "reel":
                video_job = (
                    db.query(VideoJob)
                    .filter(VideoJob.post_id == post.id, VideoJob.variation_number == selected)
                    .first()
                )
                if not video_job or not video_job.video_url:
                    await message.answer("Video option not found. Choose 1 after preview is ready.")
                    return True
                post.video_url = video_job.video_url
            db.commit()
            await message.answer(f"Selected option {selected}. Reply 'approve' when ready.")
            return True

        if action_lower == "edit caption":
            session.state = SessionState.AWAITING_CAPTION_EDIT.value
            db.commit()
            await message.answer(
                "What would you like to change? You can say: shorter, more festive, add price, or custom instructions."
            )
            return True

        if action_lower == "redo" or action_lower.startswith("redo "):
            requested_video_type = None
            if action_lower.startswith("redo "):
                requested_video_type = _normalize_video_type(action_lower.split(" ", 1)[1])
                if not requested_video_type:
                    await message.answer("Unknown video style. Try: fabric-flow, close-up, lifestyle, or reveal.")
                    return True

            post.status = PostStatus.PROCESSING.value
            if requested_video_type:
                post.video_type = requested_video_type
            db.commit()

            if post.media_type == "reel" or requested_video_type:
                post.media_type = "reel"
                db.commit()
                if post.styled_image:
                    reel_this_task.delay(post.id, chat_id)
                else:
                    process_video_post_task.delay(post.id, chat_id)
                if requested_video_type:
                    await message.answer(f"Regenerating Reel options with {requested_video_type} style...")
                else:
                    await message.answer("Regenerating Reel options...")
            else:
                await message.answer("Regenerating options...")
                process_post_task.delay(post.id, chat_id)
            return True

        if action_lower == "cancel":
            post.status = PostStatus.CANCELLED.value
            session.state = SessionState.IDLE.value
            db.commit()
            await message.answer("Cancelled this post.")
            return True

        if action_lower == "approve":
            post.status = PostStatus.APPROVED.value
            session.state = SessionState.AWAITING_POST_CONFIRMATION.value
            db.commit()
            await message.answer("Ready to post. Reply 'post now'.")
            return True

        if action_lower.startswith("schedule"):
            await message.answer(V1_SCHEDULING_MESSAGE)
            return True

        if action_lower == "post now":
            publish_post_task.delay(post.id, chat_id, str(user_id))
            await message.answer("Posting now...")
            return True

        if session.state == SessionState.AWAITING_CAPTION_EDIT.value:
            rewrite_caption_task.delay(post.id, chat_id, action)
            session.state = SessionState.REVIEW_READY.value
            db.commit()
            await message.answer("Updating caption...")
            return True

        if action_lower == "reel this":
            reel_this_task.delay(post.id, chat_id)
            await message.answer("Converting to a Reel... This takes ~5 minutes.")
            return True

        if action_lower == "extend" or action_lower.startswith("extend "):
            parts = action_lower.split()
            variation = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else (post.selected_variant_index or 1)
            extend_video_task.delay(post.id, chat_id, variation)
            await message.answer("Extending video by 8 seconds...")
            return True

    return False


async def _finalize_album(media_group_id: str) -> None:
    await asyncio.sleep(2.0)
    async with ALBUM_LOCK:
        payload = ALBUM_CACHE.pop(media_group_id, None)

    if not payload:
        return

    text = payload.get("text")
    if not text:
        return

    await _process_ingestion(
        chat_id=payload["chat_id"],
        user_id=payload["user_id"],
        text=text,
        photo_urls=payload.get("photo_urls", []),
        photo_file_ids=payload.get("photo_file_ids", []),
    )


def register_handlers(dispatcher: Dispatcher) -> None:
    router = Router()

    @router.message(F.text == "/start")
    async def start_handler(message: Message) -> None:
        if not _is_allowed(message.from_user.id):
            await message.answer(UNAUTHORIZED_MESSAGE)
            return
        await message.answer(WELCOME_MESSAGE)

    @router.message(F.text == "/help")
    async def help_handler(message: Message) -> None:
        if not _is_allowed(message.from_user.id):
            await message.answer(UNAUTHORIZED_MESSAGE)
            return
        await message.answer(HELP_MESSAGE)

    @router.message(F.text)
    async def text_handler(message: Message) -> None:
        if not _is_allowed(message.from_user.id):
            await message.answer(UNAUTHORIZED_MESSAGE)
            return

        parsed = parse_message_text(message.text)

        if parsed.command == "/recent":
            with SessionLocal() as db:
                posts = (
                    db.query(Post)
                    .filter(Post.created_by == str(message.from_user.id))
                    .order_by(Post.created_at.desc())
                    .limit(5)
                    .all()
                )
            if not posts:
                await message.answer("No recent posts found.")
                return
            lines = ["Recent posts:"]
            for post in posts:
                icon = "🎬" if post.media_type == "reel" else "🖼"
                lines.append(f"{icon} #{post.id} • {post.status} • {post.media_type}")
            await message.answer("\n".join(lines))
            return

        if parsed.command == "/queue":
            with SessionLocal() as db:
                queued = (
                    db.query(Post)
                    .filter(
                        Post.created_by == str(message.from_user.id),
                        Post.status.in_(
                            [PostStatus.DRAFT.value, PostStatus.PROCESSING.value, PostStatus.APPROVED.value]
                        ),
                    )
                    .order_by(Post.created_at.desc())
                    .limit(10)
                    .all()
                )
            if not queued:
                await message.answer("Queue is empty.")
                return
            lines = ["Queue:"]
            for post in queued:
                lines.append(f"#{post.id} • {post.status} • {post.media_type}")
            await message.answer("\n".join(lines))
            return

        if parsed.command == "/reelqueue":
            with SessionLocal() as db:
                rows = (
                    db.query(VideoJob, Post)
                    .join(Post, VideoJob.post_id == Post.id)
                    .filter(Post.created_by == str(message.from_user.id), VideoJob.status.in_(["pending", "generating"]))
                    .order_by(VideoJob.created_at.desc())
                    .limit(10)
                    .all()
                )
            if not rows:
                await message.answer("No pending Reel jobs.")
                return
            lines = ["Reel queue:"]
            for job, post in rows:
                lines.append(f"post #{post.id} • variation {job.variation_number} • {job.status}")
            await message.answer("\n".join(lines))
            return

        if parsed.command == "/products":
            with SessionLocal() as db:
                products = (
                    db.query(Product)
                    .order_by(Product.product_code.asc())
                    .limit(20)
                    .all()
                )
            if not products:
                await message.answer("No products available.")
                return
            lines = ["Products:"]
            for product in products:
                name = product.product_name or "-"
                lines.append(f"{product.product_code} • {name}")
            await message.answer("\n".join(lines))
            return

        if parsed.command == "/stats":
            with SessionLocal() as db:
                total = db.query(func.count(Post.id)).filter(Post.created_by == str(message.from_user.id)).scalar() or 0
                reels = (
                    db.query(func.count(Post.id))
                    .filter(Post.created_by == str(message.from_user.id), Post.media_type == "reel")
                    .scalar()
                    or 0
                )
                posted = (
                    db.query(func.count(Post.id))
                    .filter(Post.created_by == str(message.from_user.id), Post.status == PostStatus.POSTED.value)
                    .scalar()
                    or 0
                )
            await message.answer(
                "Stats:\n"
                f"- Total posts: {total}\n"
                f"- Reels created: {reels}\n"
                f"- Posted successfully: {posted}\n"
                "- Reel views/reach tracking is not available in this build."
            )
            return

        if parsed.command == "/cancel":
            parts = (parsed.free_text or "").split()
            if len(parts) != 2 or not parts[1].isdigit():
                await message.answer("Usage: /cancel <post_id>")
                return
            post_id = int(parts[1])
            with SessionLocal() as db:
                post = db.get(Post, post_id)
                if not post or post.created_by != str(message.from_user.id):
                    await message.answer(f"Post #{post_id} not found.")
                    return
                post.status = PostStatus.CANCELLED.value
                session = get_or_create_session(db, message.from_user.id, message.chat.id)
                if session.post_id == post_id:
                    session.state = SessionState.IDLE.value
                db.commit()
            await message.answer(f"Cancelled post #{post_id}.")
            return

        if parsed.command == "/reel":
            if not parsed.source_url:
                await message.answer("Usage: /reel <instagram_or_pinterest_link> [VAK-XXX]")
                return
            photo_file_ids, photo_urls = await _extract_photo_urls(message)
            await _process_ingestion(
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                text=message.text,
                photo_urls=photo_urls,
                photo_file_ids=photo_file_ids,
                send_via_message=message,
            )
            return

        if parsed.command and parsed.command.startswith("/") and parsed.command not in {
            "/start",
            "/help",
            "/recent",
            "/queue",
            "/cancel",
            "/products",
            "/stats",
            "/reelqueue",
            "/reel",
        }:
            await message.answer("Unknown command. Use /help.")
            return

        if parsed.command in {"1", "2", "3", "approve", "redo", "cancel", "edit caption", "post now", "reel this", "extend"} or (
            parsed.command and (parsed.command.startswith("schedule") or parsed.command.startswith("extend ") or parsed.command.startswith("redo "))
        ):
            handled = await _handle_action(message, parsed.command)
            if not handled:
                await message.answer("No active post found. Send a new inspiration link to begin.")
            return

        photo_file_ids, photo_urls = await _extract_photo_urls(message)
        await _process_ingestion(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            text=message.text,
            photo_urls=photo_urls,
            photo_file_ids=photo_file_ids,
            send_via_message=message,
        )

    @router.message(F.photo, ~F.media_group_id)
    async def single_photo_handler(message: Message) -> None:
        """Handle a single photo (not part of an album)."""
        if not _is_allowed(message.from_user.id):
            await message.answer(UNAUTHORIZED_MESSAGE)
            return

        photo_file_ids, photo_urls = await _extract_photo_urls(message)
        caption_text = message.caption or ""

        # Check if there's a pending reference URL from a previous text message
        with SessionLocal() as db:
            session = get_or_create_session(db, message.from_user.id, message.chat.id)
            if session.state == SessionState.AWAITING_PHOTOS.value and session.context_json:
                pending_url = session.context_json.get("pending_source_url", "")
                if pending_url and not caption_text:
                    caption_text = pending_url
                session.state = SessionState.IDLE.value
                db.commit()

        if not caption_text:
            await message.answer("Please send a photo with an Instagram/Pinterest link as the caption, or send the link first.")
            return

        await _process_ingestion(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            text=caption_text,
            photo_urls=photo_urls,
            photo_file_ids=photo_file_ids,
            send_via_message=message,
        )

    @router.message(F.media_group_id)
    async def album_handler(message: Message) -> None:
        if not _is_allowed(message.from_user.id):
            await message.answer(UNAUTHORIZED_MESSAGE)
            return

        photo_file_ids, photo_urls = await _extract_photo_urls(message)

        async with ALBUM_LOCK:
            payload = ALBUM_CACHE.setdefault(
                message.media_group_id,
                {
                    "chat_id": message.chat.id,
                    "user_id": message.from_user.id,
                    "photo_file_ids": [],
                    "photo_urls": [],
                    "text": None,
                    "created_at": time.time(),
                },
            )
            payload["photo_file_ids"].extend(photo_file_ids)
            payload["photo_urls"].extend(photo_urls)
            if message.caption:
                payload["text"] = message.caption

            if not payload.get("scheduled"):
                payload["scheduled"] = True
                asyncio.create_task(_finalize_album(message.media_group_id))

    @router.callback_query()
    async def callback_handler(callback: CallbackQuery) -> None:
        if not callback.from_user or not _is_allowed(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return

        parsed = parse_callback(callback.data or "")
        if not parsed:
            await callback.answer("Invalid action")
            return

        with SessionLocal() as db:
            post = db.get(Post, parsed.post_id)
            if not post:
                await callback.answer("Post not found", show_alert=True)
                return

            if parsed.action == CallbackAction.SELECT:
                post.selected_variant_index = parsed.variant
                db.commit()
                await callback.message.answer(f"Selected option {parsed.variant}. Reply 'approve' when ready.")
            elif parsed.action == CallbackAction.EDIT_CAPTION:
                session = get_or_create_session(db, callback.from_user.id, callback.message.chat.id)
                session.state = SessionState.AWAITING_CAPTION_EDIT.value
                db.commit()
                await callback.message.answer("Tell me how you want to change the caption.")
            elif parsed.action == CallbackAction.REDO:
                post.status = PostStatus.PROCESSING.value
                db.commit()
                if post.media_type == "reel":
                    if post.styled_image:
                        reel_this_task.delay(post.id, callback.message.chat.id)
                    else:
                        process_video_post_task.delay(post.id, callback.message.chat.id)
                    await callback.message.answer("Regenerating Reel options...")
                else:
                    process_post_task.delay(post.id, callback.message.chat.id)
                    await callback.message.answer("Regenerating options...")
            elif parsed.action == CallbackAction.CANCEL:
                post.status = PostStatus.CANCELLED.value
                db.commit()
                await callback.message.answer("Cancelled this post.")
            elif parsed.action == CallbackAction.APPROVE:
                post.status = PostStatus.APPROVED.value
                db.commit()
                await callback.message.answer("Approved. Reply 'post now' to publish.")
            elif parsed.action == CallbackAction.SELECT_VIDEO:
                # Video variant selection
                from vak_bot.db.models import VideoJob
                video_job = (
                    db.query(VideoJob)
                    .filter(VideoJob.post_id == parsed.post_id, VideoJob.variation_number == parsed.variant)
                    .first()
                )
                if video_job and video_job.video_url:
                    post.video_url = video_job.video_url
                    post.selected_variant_index = parsed.variant
                    db.commit()
                    await callback.message.answer(f"Selected option {parsed.variant}. Reply 'approve' when ready.")
                else:
                    await callback.message.answer("Video option not found.")
            elif parsed.action == CallbackAction.EXTEND:
                extend_video_task.delay(post.id, callback.message.chat.id, post.selected_variant_index or 1)
                await callback.message.answer("Extending video by 8 seconds...")
            elif parsed.action == CallbackAction.REEL_THIS:
                reel_this_task.delay(post.id, callback.message.chat.id)
                await callback.message.answer("Converting to a Reel... This takes ~5 minutes.")

        await callback.answer()

    dispatcher.include_router(router)
