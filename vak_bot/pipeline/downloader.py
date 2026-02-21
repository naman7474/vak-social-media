from __future__ import annotations

from urllib.parse import urlparse

import httpx

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import DownloadError, PrivatePostError, UnsupportedMediaError
from vak_bot.pipeline.interfaces import DownloadedReference


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
            raise DownloadError("Missing DATABRIGHT_API_KEY")

        payload = {"url": source_url}
        headers = {"Authorization": f"Bearer {self.settings.databright_api_key}"}

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.settings.databright_base_url.rstrip('/')}/v1/social/download",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise DownloadError(str(exc)) from exc

        if data.get("status") in {"private", "deleted"}:
            raise PrivatePostError()

        media_type = (data.get("media_type") or "").lower()
        if media_type in {"reel", "video", "story"}:
            raise UnsupportedMediaError()

        images = data.get("images") or []
        if not images:
            raise DownloadError("No images returned")

        return DownloadedReference(
            source_url=source_url,
            image_urls=images,
            caption=data.get("caption"),
            hashtags=data.get("hashtags"),
            media_type="image",
        )
