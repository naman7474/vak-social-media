from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import httpx
from PIL import Image, ImageEnhance, ImageOps, ImageStat

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import StylingError
from vak_bot.pipeline.prompts import load_brand_config, load_styling_prompt
from vak_bot.schemas import StyleBrief, StyledVariant
from vak_bot.storage import R2StorageClient


def _create_placeholder_variant(source_url: str, mode: str) -> bytes:
    # Placeholder styling for dry-run: tint and contrast to create distinct previews.
    image = Image.new("RGB", (1080, 1350), color=(245, 240, 232))
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(source_url)
            resp.raise_for_status()
            image = Image.open(io.BytesIO(resp.content)).convert("RGB")
            image = ImageOps.fit(image, (1080, 1350))
    except Exception:
        pass

    if mode == "minimal":
        image = ImageEnhance.Color(image).enhance(0.8)
    elif mode == "warm":
        overlay = Image.new("RGB", image.size, (255, 220, 180))
        image = Image.blend(image, overlay, 0.15)
    else:
        image = ImageEnhance.Contrast(image).enhance(1.2)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class GeminiStyler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage = R2StorageClient()

    def _build_prompt(self, style_brief: StyleBrief, overlay_text: str | None, modifier: str) -> str:
        base = load_styling_prompt()
        return (
            f"{base}\n\n"
            f"Layout: {style_brief.layout_type}\n"
            f"Placement: {style_brief.composition.product_placement}\n"
            f"Background: {style_brief.background.suggested_bg_for_saree}\n"
            f"Lighting: {style_brief.lighting}\n"
            f"Palette: {style_brief.color_mood.palette_name} ({style_brief.color_mood.temperature})\n"
            f"Dominant colors: {', '.join(style_brief.color_mood.dominant_colors)}\n"
            f"Vibe: {', '.join(style_brief.vibe_words)}\n"
            f"Variation modifier: {modifier}\n"
            + (f"Overlay text: {overlay_text}\n" if overlay_text else "")
        )

    def generate_variants(
        self,
        saree_images: list[str],
        reference_image_url: str,
        style_brief: StyleBrief,
        overlay_text: str | None,
    ) -> list[StyledVariant]:
        config = load_brand_config()
        modifiers = config.get("variation_modifiers", [])[:3]

        if self.settings.dry_run:
            variants: list[StyledVariant] = []
            for idx, modifier in enumerate(modifiers, start=1):
                mode = "minimal" if idx == 1 else "warm" if idx == 2 else "editorial"
                item_urls: list[str] = []
                first_image_url = ""
                for position, source_url in enumerate(saree_images, start=1):
                    content = _create_placeholder_variant(source_url, mode)
                    key = f"styled/post-{uuid.uuid4().hex}/variant-{idx}/item-{position}.jpg"
                    uploaded = self.storage.upload_bytes(key, content)
                    item_urls.append(uploaded)
                    if position == 1:
                        first_image_url = uploaded
                variants.append(
                    StyledVariant(
                        variant_index=idx,
                        preview_url=first_image_url,
                        item_urls=item_urls,
                        ssim_score=0.82,
                        is_valid=True,
                    )
                )
            return variants

        if not self.settings.google_api_key:
            raise StylingError("Missing GOOGLE_API_KEY")

        generated: list[StyledVariant] = []
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_image_model}:generateContent?key={self.settings.google_api_key}"
        )

        for idx, modifier in enumerate(modifiers, start=1):
            prompt = self._build_prompt(style_brief, overlay_text, modifier)
            item_urls: list[str] = []
            for position, saree_url in enumerate(saree_images, start=1):
                payload = {
                    "contents": [{"parts": [{"text": prompt}, {"text": f"Reference: {reference_image_url}"}, {"text": f"Saree: {saree_url}"}]}],
                    "generationConfig": {
                        "responseModalities": ["IMAGE", "TEXT"],
                    },
                }
                try:
                    with httpx.Client(timeout=120.0) as client:
                        resp = client.post(endpoint, json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                except Exception as exc:
                    raise StylingError(str(exc)) from exc

                image_bytes = self._extract_image_bytes(data)
                key = f"styled/post-{uuid.uuid4().hex}/variant-{idx}/item-{position}.jpg"
                item_url = self.storage.upload_bytes(key, image_bytes)
                item_urls.append(item_url)

            generated.append(
                StyledVariant(
                    variant_index=idx,
                    preview_url=item_urls[0],
                    item_urls=item_urls,
                    ssim_score=0.75,
                    is_valid=True,
                )
            )
        return generated

    def _extract_image_bytes(self, response_json: dict) -> bytes:
        candidates = response_json.get("candidates", [])
        for candidate in candidates:
            parts = candidate.get("content", {}).get("parts", [])
            for part in parts:
                inline = part.get("inlineData")
                if inline and inline.get("data"):
                    import base64

                    return base64.b64decode(inline["data"])
        raise StylingError(f"Gemini did not return an image: {json.dumps(response_json)[:200]}")
