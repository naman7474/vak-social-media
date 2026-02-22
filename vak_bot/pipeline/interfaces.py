from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vak_bot.schemas import CaptionPackage, StyleBrief, StyledVariant


@dataclass
class DownloadedReference:
    source_url: str
    image_urls: list[str]
    caption: str | None
    hashtags: str | None
    media_type: str
    video_url: str | None = None
    thumbnail_url: str | None = None


class DataBrightClient(Protocol):
    def download_post(self, source_url: str) -> DownloadedReference: ...


class OpenAIAnalyzerClient(Protocol):
    def analyze_reference(self, reference_image_url: str, reference_caption: str | None) -> StyleBrief: ...


class GeminiStylerClient(Protocol):
    def generate_variants(
        self,
        saree_image_url: str,
        reference_image_urls: list[str],
        style_brief: StyleBrief,
        overlay_text: str | None,
    ) -> list[StyledVariant]: ...


class ClaudeCaptionClient(Protocol):
    def generate_caption(
        self,
        styled_image_url: str,
        style_brief: StyleBrief,
        product_info: dict,
    ) -> CaptionPackage: ...


class MetaGraphPosterClient(Protocol):
    def post_single_image(self, image_url: str, caption: str, alt_text: str, idempotency_key: str) -> dict: ...

    def post_carousel(self, image_urls: list[str], caption: str, alt_text: str, idempotency_key: str) -> dict: ...

    def post_reel(self, video_s3_url: str, caption: str, thumb_offset_ms: int, share_to_feed: bool) -> dict: ...

    def refresh_page_token(self) -> dict: ...


class VeoGeneratorClient(Protocol):
    def generate_reel_variations(
        self,
        styled_frame_path: str,
        style_brief: StyleBrief,
        video_type: str | None,
        reference_image_path: str | None,
    ) -> list[str]: ...

    def extend_reel(self, original_video_path: str, continuation_prompt: str) -> str: ...


class StorageClient(Protocol):
    def upload_bytes(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str: ...

    def delete_by_url(self, url: str) -> None: ...
