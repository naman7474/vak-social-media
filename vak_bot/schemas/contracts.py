from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from vak_bot.enums import MediaType


class Composition(BaseModel):
    product_placement: Literal["center", "left-third", "right-third", "diagonal", "scattered"]
    whitespace: Literal["minimal", "moderate", "generous"]
    text_area: Literal["top", "bottom", "left", "right", "overlay-center", "none"]
    aspect_ratio: Literal["1:1", "4:5", "9:16"]


class ColorMood(BaseModel):
    temperature: Literal["warm", "cool", "neutral"]
    dominant_colors: list[str] = Field(min_length=1, max_length=6)
    palette_name: Literal["earthy", "jewel-toned", "pastel", "monochrome", "vibrant", "muted"]


class BackgroundSpec(BaseModel):
    type: Literal["solid-color", "gradient", "textured", "lifestyle-scene", "props", "natural"]
    description: str
    suggested_bg_for_saree: str


class TextOverlaySpec(BaseModel):
    has_text: bool
    text_style: Literal["serif", "sans-serif", "handwritten", "none"]
    text_position: Literal["top-left", "center", "bottom", "none"]
    text_purpose: Literal["product-name", "price", "tagline", "quote", "none"]


class StyleBrief(BaseModel):
    layout_type: Literal["flat-lay", "draped", "on-model", "close-up", "grid", "lifestyle"]
    composition: Composition
    color_mood: ColorMood
    background: BackgroundSpec
    lighting: Literal["natural-soft", "natural-harsh", "studio", "golden-hour", "moody-dark", "backlit"]
    text_overlay: TextOverlaySpec
    content_format: Literal["single-image", "carousel", "before-after", "collage"]
    vibe_words: list[str] = Field(min_length=2, max_length=5)
    adaptation_notes: str


class CaptionPackage(BaseModel):
    caption: str
    hashtags: str
    alt_text: str
    overlay_text: Optional[str] = None


class StyledVariant(BaseModel):
    variant_index: int
    preview_url: str
    item_urls: list[str] = Field(default_factory=list)
    ssim_score: float
    is_valid: bool


class IngestionRequest(BaseModel):
    telegram_user_id: int
    chat_id: int
    source_url: str
    product_code: Optional[str] = None
    telegram_photo_file_ids: list[str] = Field(default_factory=list)
    media_type: MediaType = MediaType.SINGLE


class ApprovalPayload(BaseModel):
    post_id: int
    selected_variant: int
    caption: str
    hashtags: str
    alt_text: str


class PostResult(BaseModel):
    post_id: int
    instagram_post_id: str
    instagram_url: str
    published: bool
