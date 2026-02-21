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


class DataBrightClient(Protocol):
    def download_post(self, source_url: str) -> DownloadedReference: ...


class OpenAIAnalyzerClient(Protocol):
    def analyze_reference(self, reference_image_url: str, reference_caption: str | None) -> StyleBrief: ...


class GeminiStylerClient(Protocol):
    def generate_variants(
        self,
        saree_images: list[str],
        reference_image_url: str,
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

    def refresh_page_token(self) -> dict: ...


class StorageClient(Protocol):
    def upload_bytes(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str: ...

    def delete_by_url(self, url: str) -> None: ...
