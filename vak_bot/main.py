from __future__ import annotations

from fastapi import FastAPI

from vak_bot.api import router as api_router
from vak_bot.config import get_settings
from vak_bot.config.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title=settings.app_name)
app.include_router(api_router)
