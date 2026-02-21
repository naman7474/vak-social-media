from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

from vak_bot.bot.callbacks import make_callback
from vak_bot.config import get_settings
from vak_bot.enums import CallbackAction


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        return asyncio.create_task(coro)
    return asyncio.run(coro)


def _bot() -> Bot:
    settings = get_settings()
    return Bot(token=settings.telegram_bot_token)


def build_review_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1", callback_data=make_callback(post_id, 1, CallbackAction.SELECT)),
                InlineKeyboardButton(text="2", callback_data=make_callback(post_id, 2, CallbackAction.SELECT)),
                InlineKeyboardButton(text="3", callback_data=make_callback(post_id, 3, CallbackAction.SELECT)),
            ],
            [
                InlineKeyboardButton(
                    text="Edit Caption",
                    callback_data=make_callback(post_id, 0, CallbackAction.EDIT_CAPTION),
                ),
                InlineKeyboardButton(text="Redo", callback_data=make_callback(post_id, 0, CallbackAction.REDO)),
            ],
            [
                InlineKeyboardButton(text="Approve", callback_data=make_callback(post_id, 0, CallbackAction.APPROVE)),
                InlineKeyboardButton(text="Cancel", callback_data=make_callback(post_id, 0, CallbackAction.CANCEL)),
            ],
        ]
    )


async def _send_text_async(chat_id: int, text: str) -> None:
    bot = _bot()
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    finally:
        await bot.session.close()


def send_text(chat_id: int, text: str) -> None:
    _run(_send_text_async(chat_id, text))


async def _send_review_async(chat_id: int, post_id: int, image_urls: list[str], caption: str, hashtags: str) -> None:
    bot = _bot()
    try:
        media = [InputMediaPhoto(media=url) for url in image_urls[:3] if url]
        if media:
            await bot.send_media_group(chat_id=chat_id, media=media)

        message = (
            "Here are your options for this post:\n\n"
            f"Caption:\n\"{caption}\"\n\n"
            f"Hashtags:\n{hashtags}\n\n"
            "Reply with 1, 2, or 3; or use the buttons below."
        )
        await bot.send_message(chat_id=chat_id, text=message, reply_markup=build_review_keyboard(post_id))
    finally:
        await bot.session.close()


def send_review_package(chat_id: int, post_id: int, image_urls: list[str], caption: str, hashtags: str) -> None:
    _run(_send_review_async(chat_id, post_id, image_urls, caption, hashtags))
