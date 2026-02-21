from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import structlog
from aiogram import Dispatcher, F, Router
from aiogram.types import CallbackQuery, Message

from vak_bot.bot.callbacks import parse_callback
from vak_bot.bot.parser import is_supported_reference_url, parse_message_text
from vak_bot.bot.sender import send_text
from vak_bot.bot.texts import (
    HELP_MESSAGE,
    NEED_PHOTO_MESSAGE,
    PROCESSING_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    UNSUPPORTED_LINK_MESSAGE,
    V1_SCHEDULING_MESSAGE,
    WELCOME_MESSAGE,
)
from vak_bot.config import get_settings
from vak_bot.db.models import Post
from vak_bot.db.session import SessionLocal
from vak_bot.enums import CallbackAction, PostStatus, SessionState
from vak_bot.services.post_service import (
    create_draft_post,
    get_or_create_session,
    lookup_product_by_code,
    product_photo_urls,
    user_posts_today,
)
from vak_bot.workers.tasks import process_post_task, publish_post_task, rewrite_caption_task

logger = structlog.get_logger(__name__)
settings = get_settings()

ALBUM_CACHE: dict[str, dict] = {}
ALBUM_LOCK = asyncio.Lock()


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
        if user_posts_today(db, user_id) >= 10:
            await respond("Daily limit reached (10 posts). Try again tomorrow.")
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
            post.selected_variant_index = int(action_lower)
            db.commit()
            await message.answer(f"Selected option {action_lower}. Reply 'approve' when ready.")
            return True

        if action_lower == "edit caption":
            session.state = SessionState.AWAITING_CAPTION_EDIT.value
            db.commit()
            await message.answer(
                "What would you like to change? You can say: shorter, more festive, add price, or custom instructions."
            )
            return True

        if action_lower == "redo":
            post.status = PostStatus.PROCESSING.value
            db.commit()
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

        if parsed.command and parsed.command.startswith("/") and parsed.command not in {"/start", "/help"}:
            await message.answer("Unknown command. Use /help.")
            return

        if parsed.command in {"1", "2", "3", "approve", "redo", "cancel", "edit caption", "post now"} or (
            parsed.command and parsed.command.startswith("schedule")
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

        await callback.answer()

    dispatcher.include_router(router)
