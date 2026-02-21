from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx
import structlog

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import DownloadError, PrivatePostError, UnsupportedMediaError
from vak_bot.pipeline.interfaces import DownloadedReference

logger = structlog.get_logger(__name__)

BRIGHTDATA_SCRAPE_URL = "https://api.brightdata.com/datasets/v3/scrape"
BRIGHTDATA_DATASET_ID = "gd_lk5ns7kz21pck8jpis"  # Instagram Posts dataset


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
        if content_type in {"reel", "video", "igtv"}:
            raise UnsupportedMediaError()

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

        if not image_urls:
            raise DownloadError("No images found in post")

        # Extract caption and hashtags
        caption = post_data.get("description")
        hashtags_list = post_data.get("hashtags") or []
        hashtags = " ".join(hashtags_list) if hashtags_list else None

        logger.info(
            "bright_data_download_success",
            source_url=source_url,
            image_count=len(image_urls),
            content_type=content_type,
        )

        return DownloadedReference(
            source_url=source_url,
            image_urls=image_urls,
            caption=caption,
            hashtags=hashtags,
            media_type="image" if content_type != "carousel" else "carousel",
        )
