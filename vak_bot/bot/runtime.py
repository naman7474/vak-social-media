from __future__ import annotations

from aiogram import Bot, Dispatcher

from vak_bot.bot.handlers import register_handlers
from vak_bot.config import get_settings

settings = get_settings()

bot = Bot(token=settings.telegram_bot_token) if settings.telegram_bot_token else None
dispatcher = Dispatcher()
register_handlers(dispatcher)
