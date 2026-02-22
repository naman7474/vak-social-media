"""Detect whether a URL points to an image post or a Reel/video and handle user overrides."""

from __future__ import annotations

import mimetypes
import re
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)

# ── Keywords that override auto-detection ──────────────────────────────────

_REEL_OVERRIDE_KEYWORDS = [
    "make it a reel",
    "reel this",
    "make a reel",
    "reel instead",
    "want a video",
    "video",
]

_IMAGE_OVERRIDE_KEYWORDS = [
    "just the photo",
    "image only",
    "no video",
    "photo post",
    "static",
]


def detect_media_type(url: str) -> str:
    """
    Detect whether a URL points to an image post or a Reel/video.

    Returns: "reel" | "image" | "unknown"
    """
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Instagram
    if "instagram.com" in (parsed.netloc or ""):
        if "/reel/" in path or "/reels/" in path:
            return "reel"
        elif "/p/" in path:
            return "image"
        elif "/tv/" in path:  # IGTV (legacy, treat as video)
            return "reel"

    # Pinterest — can't tell from URL alone, need to check after download
    if "pinterest.com" in (parsed.netloc or "") or "pin.it" in (parsed.netloc or ""):
        return "unknown"  # Resolve after DataBright download

    return "unknown"


def detect_user_override(text: str | None) -> str | None:
    """
    Check if user message text contains an explicit media-type override.

    Returns: "reel" | "image" | None
    """
    if not text:
        return None
    lower = text.lower().strip()

    # Check image overrides FIRST — negation patterns like "no video"
    # must take priority over the bare "video" reel keyword.
    for keyword in _IMAGE_OVERRIDE_KEYWORDS:
        if keyword in lower:
            return "image"

    for keyword in _REEL_OVERRIDE_KEYWORDS:
        if keyword in lower:
            return "reel"

    return None


def confirm_media_type_from_mime(file_path: str, url_hint: str) -> str:
    """
    Confirm media type from the downloaded file's MIME type.
    Falls back to URL hint if MIME is ambiguous.
    """
    mime, _ = mimetypes.guess_type(file_path)

    if mime and mime.startswith("video/"):
        return "reel"
    elif mime and mime.startswith("image/"):
        return "image"

    # Fallback to URL detection
    return detect_media_type(url_hint)


def resolve_pipeline_type(url: str, user_text: str | None = None) -> str:
    """
    Decide the final pipeline type by combining URL detection and user overrides.
    User overrides always win.

    Returns: "reel" | "image"
    """
    # User override has highest priority
    user_override = detect_user_override(user_text)
    if user_override:
        logger.info("pipeline_type_user_override", override=user_override)
        return user_override

    # Otherwise detect from URL pattern
    detected = detect_media_type(url)
    if detected != "unknown":
        logger.info("pipeline_type_url_detected", detected=detected, url=url)
        return detected

    # Ambiguous — default to image (will confirm after download via MIME)
    logger.info("pipeline_type_defaulting_to_image", url=url)
    return "image"
