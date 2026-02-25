from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import httpx
import structlog

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import DownloadError, PrivatePostError
from vak_bot.pipeline.interfaces import DownloadedReference

logger = structlog.get_logger(__name__)

BRIGHTDATA_SCRAPE_URL = "https://api.brightdata.com/datasets/v3/scrape"
BRIGHTDATA_DATASET_ID = "gd_lk5ns7kz21pck8jpis"  # Instagram Posts dataset


def _parse_duration_seconds(raw: object) -> int | None:
    if raw is None:
        return None

    if isinstance(raw, (int, float)):
        value = float(raw)
        if value <= 0:
            return None
        # Some providers return milliseconds.
        if value >= 1000:
            value = value / 1000.0
        return max(1, int(round(value)))

    if isinstance(raw, str):
        text = raw.strip().lower()
        if not text:
            return None

        # "00:30" or "01:02:03"
        if ":" in text:
            parts = text.split(":")
            if all(p.isdigit() for p in parts):
                if len(parts) == 2:
                    return int(parts[0]) * 60 + int(parts[1])
                if len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

        # "30s", "30 sec", "30.5 seconds", "30"
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if match:
            value = float(match.group(1))
            if "ms" in text:
                value = value / 1000.0
            if value > 0:
                return max(1, int(round(value)))

    return None


def _extract_video_duration_seconds(post_data: dict) -> int | None:
    candidate_keys = [
        "video_duration_seconds",
        "video_duration",
        "duration_seconds",
        "duration_sec",
        "duration",
        "video_length",
        "length",
    ]
    for key in candidate_keys:
        parsed = _parse_duration_seconds(post_data.get(key))
        if parsed is not None:
            return parsed

    # Fallback for nested payloads occasionally returned by providers.
    video_meta = post_data.get("video_metadata")
    if isinstance(video_meta, dict):
        for key in candidate_keys:
            parsed = _parse_duration_seconds(video_meta.get(key))
            if parsed is not None:
                return parsed
    return None


class DataBrightDownloader:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _validate_source(self, source_url: str) -> None:
        host = (urlparse(source_url).hostname or "").lower()
        if "instagram.com" not in host and "pinterest.com" not in host and "pin.it" not in host:
            raise DownloadError("Unsupported source")

    def download_post(self, source_url: str) -> DownloadedReference:
        self._validate_source(source_url)

        if self.settings.dry_run:
            return DownloadedReference(
                source_url=source_url,
                image_urls=["https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=1080"],
                caption="Hand-painted saree inspiration",
                hashtags="#handpaintedsaree #artisanmade",
                media_type="image",
            )

        if not self.settings.databright_api_key:
            raise DownloadError("Missing DATABRIGHT_API_KEY (Bright Data API token)")

        headers = {
            "Authorization": f"Bearer {self.settings.databright_api_key}",
            "Content-Type": "application/json",
        }

        payload = json.dumps({
            "input": [{"url": source_url}],
        })

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{BRIGHTDATA_SCRAPE_URL}?dataset_id={BRIGHTDATA_DATASET_ID}&notify=false&include_errors=true&format=json",
                    headers=headers,
                    content=payload,
                )
                response.raise_for_status()
                raw_text = response.text
                logger.info("bright_data_raw_response", status=response.status_code, body=raw_text[:500])
                results = response.json()
        except Exception as exc:
            logger.error("bright_data_request_failed", error=str(exc))
            raise DownloadError(str(exc)) from exc

        # Handle different response formats
        if isinstance(results, dict):
            # Might be a snapshot_id response or a single post object
            if "snapshot_id" in results:
                raise DownloadError(f"Bright Data returned async snapshot_id: {results['snapshot_id']}. Sync mode may not be supported.")
            # Single post object — wrap in a list
            results = [results]

        if not isinstance(results, list) or len(results) == 0:
            raise DownloadError(f"Unexpected response from Bright Data: {raw_text[:200]}")

        post_data = results[0]

        # Check for errors in the response
        if "error" in post_data:
            error_msg = post_data.get("error", "Unknown error")
            if "private" in str(error_msg).lower():
                raise PrivatePostError()
            raise DownloadError(f"Bright Data error: {error_msg}")

        # Determine content type
        content_type = (post_data.get("content_type") or "").lower()
        is_video = content_type in {"reel", "video", "igtv"}

        # Extract video URL if it's a Reel/video
        video_url: str | None = None
        thumbnail_url: str | None = None
        if is_video:
            video_url = post_data.get("video_url") or post_data.get("video")
            thumbnail_url = post_data.get("thumbnail") or post_data.get("display_url")
        video_duration_seconds = _extract_video_duration_seconds(post_data) if is_video else None

        # Extract image URLs from photos or post_content
        image_urls: list[str] = []

        # Primary: use 'photos' array (direct CDN URLs)
        photos = post_data.get("photos") or []
        if photos:
            image_urls = photos
        else:
            # Fallback: use 'post_content' for individual media items
            post_content = post_data.get("post_content") or []
            for item in post_content:
                if item.get("type", "").lower() == "photo" and item.get("url"):
                    image_urls.append(item["url"])

        if not image_urls and thumbnail_url:
            image_urls = [thumbnail_url]

        if not image_urls:
            if is_video:
                raise DownloadError("No thumbnail found for Reel/video post")
            raise DownloadError("No images found in post")

        # Extract caption and hashtags
        caption = post_data.get("description")
        hashtags_list = post_data.get("hashtags") or []
        hashtags = " ".join(hashtags_list) if hashtags_list else None

        # Determine final media type
        if is_video:
            final_media_type = "reel"
        elif content_type == "carousel":
            final_media_type = "carousel"
        else:
            final_media_type = "image"

        logger.info(
            "bright_data_download_success",
            source_url=source_url,
            image_count=len(image_urls),
            content_type=content_type,
            is_video=is_video,
            video_duration_seconds=video_duration_seconds,
        )

        return DownloadedReference(
            source_url=source_url,
            image_urls=image_urls,
            caption=caption,
            hashtags=hashtags,
            media_type=final_media_type,
            video_url=video_url,
            thumbnail_url=thumbnail_url,
            video_duration_seconds=video_duration_seconds,
        )
