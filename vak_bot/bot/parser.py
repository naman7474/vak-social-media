from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

PRODUCT_CODE_REGEX = re.compile(r"\bVAK-\d{3,}\b", re.IGNORECASE)
URL_REGEX = re.compile(r"https?://\S+")


@dataclass
class ParsedMessage:
    command: Optional[str]
    source_url: Optional[str]
    product_code: Optional[str]
    free_text: Optional[str]
    media_override: Optional[str] = None  # "reel" | "image" | None


SUPPORTED_HOSTS = {"instagram.com", "www.instagram.com", "pinterest.com", "www.pinterest.com", "pin.it"}


def extract_first_url(text: str) -> Optional[str]:
    match = URL_REGEX.search(text or "")
    if not match:
        return None
    return match.group(0).strip()


def extract_product_code(text: str) -> Optional[str]:
    match = PRODUCT_CODE_REGEX.search(text or "")
    if not match:
        return None
    return match.group(0).upper()


def is_supported_reference_url(url: str) -> bool:
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    return host in SUPPORTED_HOSTS or any(host.endswith(f".{h}") for h in SUPPORTED_HOSTS)


def parse_message_text(text: str | None) -> ParsedMessage:
    text = (text or "").strip()
    if not text:
        return ParsedMessage(command=None, source_url=None, product_code=None, free_text=None)

    lower = text.lower()
    if lower.startswith("/"):
        command = lower.split()[0]
        if command == "/reel":
            return ParsedMessage(
                command=command,
                source_url=extract_first_url(text),
                product_code=extract_product_code(text),
                free_text=text,
                media_override="reel",
            )
        if command == "/ad":
            return ParsedMessage(
                command=command,
                source_url=extract_first_url(text),
                product_code=extract_product_code(text),
                free_text=text,
                media_override="ad",
            )
        return ParsedMessage(command=command, source_url=None, product_code=None, free_text=text)

    if lower in {"1", "2", "3", "approve", "redo", "cancel", "edit caption", "post now", "reel this", "extend"}\
            or lower.startswith("schedule") or lower.startswith("extend ") or lower.startswith("redo "):
        return ParsedMessage(command=lower, source_url=None, product_code=None, free_text=text)

    # Detect media override keywords
    from vak_bot.pipeline.route_detector import detect_user_override
    media_override = detect_user_override(text)

    return ParsedMessage(
        command=None,
        source_url=extract_first_url(text),
        product_code=extract_product_code(text),
        free_text=text,
        media_override=media_override,
    )
