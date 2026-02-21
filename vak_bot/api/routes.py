from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from aiogram.types import Update

from vak_bot.bot.runtime import bot, dispatcher
from vak_bot.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


@router.post("/webhooks/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=401, detail="invalid webhook secret")

    if bot is None:
        raise HTTPException(status_code=500, detail="telegram bot token is missing")

    payload = await request.json()
    update = Update.model_validate(payload)
    await dispatcher.feed_update(bot, update)
    return {"ok": True}
