from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from vak_bot.enums import MediaType, VideoType


class Composition(BaseModel):
    product_placement: str = "center"
    whitespace: Literal["minimal", "moderate", "generous"] = "moderate"
    text_area: str = "none"
    aspect_ratio: Literal["1:1", "4:5", "9:16"] = "4:5"
    grid_safe: Optional[bool] = None


class ColorMood(BaseModel):
    temperature: Literal["warm", "cool", "neutral"] = "warm"
    dominant_colors: list[str] = Field(min_length=1, max_length=6)
    accent_color: Optional[str] = None
    palette_name: str = "earthy"

    @field_validator("temperature", mode="before")
    @classmethod
    def normalize_temperature(cls, v: str) -> str:
        """Normalize LLM temperature responses to allowed values."""
        if not isinstance(v, str):
            return v
        v_lower = v.lower().strip()
        # Map common LLM variations to allowed values
        if v_lower in ("warm", "cool", "neutral"):
            return v_lower
        if "warm" in v_lower and "cool" not in v_lower:
            return "warm"
        if "cool" in v_lower and "warm" not in v_lower:
            return "cool"
        # Mixed or unknown → neutral
        return "neutral"


class BackgroundSpec(BaseModel):
    type: str = "textured"
    description: str = ""
    suggested_bg_for_saree: str = ""
    surface_texture: Optional[str] = None


class LightingSpec(BaseModel):
    type: str = "natural-soft"
    direction: str = "ambient"
    shadow_style: str = "soft-diffused"


class PropsSpec(BaseModel):
    has_props: bool = False
    suggested_props: list[str] = Field(default_factory=list)
    prop_placement: Optional[str] = None


class TextOverlaySpec(BaseModel):
    has_text: bool = False
    text_style: str = "none"
    text_position: str = "none"
    text_purpose: str = "none"
    suggested_text_color: Optional[str] = None


class VideoAnalysis(BaseModel):
    camera_motion: str = "slow-pan"  # slow-pan, zoom-in, zoom-out, orbit, tilt-up, tilt-down, static, tracking
    motion_type: str = "fabric-flow"  # fabric-flow, model-walk, reveal, product-rotate, parallax, morph
    motion_elements: str = ""  # What should be moving
    pacing: str = "slow-dreamy"  # slow-dreamy, medium-editorial, fast-energetic
    audio_mood: str = "ambient-nature"  # ambient-nature, soft-classical, modern-minimal, upbeat, silence
    transition_style: str = "none"  # none, fade, cut, zoom-through
    recommended_duration: int = 8  # 4, 6, or 8 seconds
    recommended_video_type: str = "fabric-flow"  # fabric-flow, close-up, lifestyle, reveal
    video_adaptation_notes: str = ""


class StyleBrief(BaseModel):
    layout_type: str = "flat-lay"
    composition: Composition = Field(default_factory=Composition)
    color_mood: ColorMood
    background: BackgroundSpec = Field(default_factory=BackgroundSpec)
    lighting: Union[LightingSpec, str] = Field(default="natural-soft")
    props: Optional[PropsSpec] = None
    text_overlay: TextOverlaySpec = Field(default_factory=TextOverlaySpec)
    content_format: str = "single-image"
    vibe_words: list[str] = Field(min_length=2, max_length=5)
    reference_has_model: Optional[bool] = None
    adaptation_notes: str = ""
    video_analysis: Optional[VideoAnalysis] = None

    @field_validator("lighting", mode="before")
    @classmethod
    def _coerce_lighting(cls, v):
        """Accept both a string and a dict for lighting."""
        if isinstance(v, str):
            return LightingSpec(type=v)
        if isinstance(v, dict):
            return LightingSpec(**v)
        return v

    @property
    def lighting_type(self) -> str:
        if isinstance(self.lighting, LightingSpec):
            return self.lighting.type
        return str(self.lighting)



class CaptionPackage(BaseModel):
    caption: str
    hashtags: str
    alt_text: str
    overlay_text: Optional[str] = None
    caption_mood: Optional[str] = None


class ReelCaptionPackage(CaptionPackage):
    cover_frame_description: Optional[str] = None
    thumb_offset_ms: int = 0


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
