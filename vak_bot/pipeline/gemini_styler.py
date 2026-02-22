from __future__ import annotations

import base64
import io
import json
import uuid
from typing import Any

import httpx
import structlog
from PIL import Image, ImageEnhance, ImageOps

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # pragma: no cover - optional dependency
    genai = None
    genai_types = None

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import StylingError
from vak_bot.pipeline.llm_utils import normalize_gemini_image_model
from vak_bot.pipeline.prompts import load_brand_config, load_styling_prompt
from vak_bot.schemas import StyleBrief, StyledVariant
from vak_bot.storage import R2StorageClient

logger = structlog.get_logger(__name__)

_SUPPORTED_INPUT_MIMES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
_PIL_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "HEIC": "image/heic",
    "HEIF": "image/heif",
}


def _normalize_mime(mime: str) -> str:
    cleaned = (mime or "").split(";")[0].strip().lower()
    if cleaned == "image/jpg":
        return "image/jpeg"
    return cleaned


def _detect_image_mime(data: bytes) -> str | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            return _PIL_TO_MIME.get((image.format or "").upper())
    except Exception:
        return None


def _convert_to_jpeg(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            rgb = image.convert("RGB")
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=95)
            return out.getvalue()
    except Exception:
        return data


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


def _download_image_as_base64(url: str) -> tuple[str, str]:
    """Download an image URL and return (base64_data, mime_type)."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.content
        header_mime = _normalize_mime(resp.headers.get("content-type", ""))
        detected_mime = _detect_image_mime(data)
        mime = header_mime if header_mime in _SUPPORTED_INPUT_MIMES else (detected_mime or "")
        if mime not in _SUPPORTED_INPUT_MIMES:
            data = _convert_to_jpeg(data)
            mime = "image/jpeg"
        return base64.b64encode(data).decode("utf-8"), mime


class GeminiStyler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage = R2StorageClient()
        self.api_key = self.settings.google_api_key or self.settings.gemini_api_key
        self.image_model = normalize_gemini_image_model(self.settings.gemini_image_model)
        self._sdk_client = None
        self._runtime_model: str | None = None
        self._runtime_part_style: str | None = None
        if self.image_model != self.settings.gemini_image_model:
            logger.info("gemini_model_normalized", configured=self.settings.gemini_image_model, normalized=self.image_model)
        if genai is not None and self.api_key:
            try:
                self._sdk_client = genai.Client(api_key=self.api_key)
                logger.info("gemini_sdk_available")
            except Exception as exc:
                logger.warning("gemini_sdk_init_failed", error=str(exc))

    def _model_candidates(self) -> list[str]:
        if self._runtime_model:
            return [self._runtime_model]
        if self.image_model == "gemini-3-pro-image-preview":
            return [self.image_model, "gemini-2.5-flash-image"]
        return [self.image_model]

    def _part_style_candidates(self) -> list[str]:
        if self._runtime_part_style:
            return [self._runtime_part_style]
        return ["snake", "camel"]

    def _build_image_parts(
        self,
        prompt: str,
        ref_mime: str,
        ref_b64: str,
        saree_mime: str,
        saree_b64: str,
        part_style: str,
    ) -> list[dict[str, Any]]:
        if part_style == "camel":
            ref_image_part = {"inlineData": {"mimeType": ref_mime, "data": ref_b64}}
            saree_image_part = {"inlineData": {"mimeType": saree_mime, "data": saree_b64}}
        else:
            ref_image_part = {"inline_data": {"mime_type": ref_mime, "data": ref_b64}}
            saree_image_part = {"inline_data": {"mime_type": saree_mime, "data": saree_b64}}
        return [
            {"text": prompt},
            {"text": "Reference image (style inspiration):"},
            ref_image_part,
            {"text": "Saree image (keep product accurate):"},
            saree_image_part,
        ]

    def _build_generation_config(self, model: str, style_brief: StyleBrief) -> dict[str, Any]:
        image_config: dict[str, Any] = {
            "aspectRatio": style_brief.composition.aspect_ratio,
        }
        if model == "gemini-3-pro-image-preview":
            image_config["imageSize"] = "1K"
        return {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": image_config,
        }

    def _extract_image_bytes_from_sdk_response(self, response: Any) -> bytes:
        # SDK may expose parts directly or via candidates.
        parts = getattr(response, "parts", None)
        if isinstance(parts, list):
            for part in parts:
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline is not None else None
                if isinstance(data, (bytes, bytearray)) and data:
                    return bytes(data)
                if isinstance(data, str) and data:
                    return base64.b64decode(data)

        candidates = getattr(response, "candidates", None)
        if isinstance(candidates, list):
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None) if content is not None else None
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    inline = getattr(part, "inline_data", None)
                    data = getattr(inline, "data", None) if inline is not None else None
                    if isinstance(data, (bytes, bytearray)) and data:
                        return bytes(data)
                    if isinstance(data, str) and data:
                        return base64.b64decode(data)
        raise StylingError("Gemini SDK did not return image bytes")

    def _request_generation_sdk(
        self,
        prompt: str,
        ref_bytes: bytes,
        ref_mime: str,
        saree_bytes: bytes,
        saree_mime: str,
        style_brief: StyleBrief,
        variant: int,
        position: int,
    ) -> bytes | None:
        if self._sdk_client is None or genai_types is None:
            return None

        model_candidates = self._model_candidates()
        last_error: Exception | None = None
        for idx, model in enumerate(model_candidates):
            is_last = idx == (len(model_candidates) - 1)
            image_cfg_kwargs: dict[str, Any] = {"aspect_ratio": style_brief.composition.aspect_ratio}
            if model == "gemini-3-pro-image-preview":
                image_cfg_kwargs["image_size"] = "1K"
            try:
                config = genai_types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=genai_types.ImageConfig(**image_cfg_kwargs),
                )
                contents = [
                    genai_types.Content(
                        role="user",
                        parts=[
                            genai_types.Part.from_text(text=prompt),
                            genai_types.Part.from_bytes(data=ref_bytes, mime_type=ref_mime),
                            genai_types.Part.from_bytes(data=saree_bytes, mime_type=saree_mime),
                        ],
                    )
                ]
                response = self._sdk_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                self._runtime_model = model
                self._runtime_part_style = "sdk"
                return self._extract_image_bytes_from_sdk_response(response)
            except Exception as exc:
                logger.error(
                    "gemini_sdk_generation_failed",
                    error=str(exc),
                    model=model,
                    variant=variant,
                    position=position,
                )
                last_error = exc
                if not is_last:
                    logger.warning("gemini_model_fallback", from_model=model, to_model=model_candidates[idx + 1])
                    continue
                break
        logger.warning("gemini_sdk_fallback_to_rest", error=str(last_error) if last_error else "unknown")
        return None

    def _request_generation(
        self,
        parts_by_style: dict[str, list[dict[str, Any]]],
        style_brief: StyleBrief,
        headers: dict[str, str],
        variant: int,
        position: int,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        model_candidates = self._model_candidates()
        part_style_candidates = [style for style in self._part_style_candidates() if style in parts_by_style]
        attempts = [(model, part_style) for model in model_candidates for part_style in part_style_candidates]

        for idx, (model, part_style) in enumerate(attempts):
            is_last_attempt = idx == (len(attempts) - 1)
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            payload = {
                "contents": [{"parts": parts_by_style[part_style]}],
                "generationConfig": self._build_generation_config(model, style_brief),
            }
            try:
                with httpx.Client(timeout=180.0) as client:
                    resp = client.post(endpoint, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    self._runtime_model = model
                    self._runtime_part_style = part_style
                    return data
            except httpx.HTTPStatusError as exc:
                body_preview = exc.response.text[:600] if exc.response is not None else ""
                logger.error(
                    "gemini_styling_http_error",
                    error=str(exc),
                    model=model,
                    part_style=part_style,
                    status_code=exc.response.status_code if exc.response is not None else None,
                    body_preview=body_preview,
                    variant=variant,
                    position=position,
                )
                error_message = str(exc)
                if body_preview:
                    error_message = f"{exc} | response={body_preview}"
                last_error = StylingError(error_message)
                should_fallback = (
                    exc.response is not None
                    and exc.response.status_code in {400, 404}
                    and not is_last_attempt
                )
                if should_fallback:
                    next_model, next_part_style = attempts[idx + 1]
                    logger.warning(
                        "gemini_request_fallback",
                        from_model=model,
                        from_part_style=part_style,
                        to_model=next_model,
                        to_part_style=next_part_style,
                    )
                    continue
                raise StylingError(error_message) from exc
            except Exception as exc:
                logger.error(
                    "gemini_styling_failed",
                    error=str(exc),
                    model=model,
                    part_style=part_style,
                    variant=variant,
                    position=position,
                )
                last_error = exc
                if not is_last_attempt:
                    next_model, next_part_style = attempts[idx + 1]
                    logger.warning(
                        "gemini_request_fallback",
                        from_model=model,
                        from_part_style=part_style,
                        to_model=next_model,
                        to_part_style=next_part_style,
                    )
                    continue
                raise StylingError(str(exc)) from exc
        raise StylingError(str(last_error) if last_error is not None else "Gemini request failed")

    def _build_prompt(self, style_brief: StyleBrief, overlay_text: str | None, modifier: str) -> str:
        base = load_styling_prompt()
        config = load_brand_config()

        # Build props instructions from brand config based on vibe
        vibe_lower = " ".join(style_brief.vibe_words).lower()
        props_lib = config.get("props_library", {})
        if any(w in vibe_lower for w in ["warm", "festive", "rich", "celebration"]):
            props_key = "warm_festive"
        elif any(w in vibe_lower for w in ["bold", "luxe", "dramatic", "opulent"]):
            props_key = "rich_luxe"
        elif any(w in vibe_lower for w in ["earthy", "grounded", "rustic", "organic"]):
            props_key = "earthy_grounded"
        else:
            props_key = "calm_minimal"
        suggested_props = props_lib.get(props_key, [])
        props_instructions = f"Suggested props ({props_key}): {', '.join(suggested_props[:4])}" if suggested_props else "No specific props needed."

        # Text overlay instructions
        if overlay_text and style_brief.text_overlay.has_text:
            text_overlay_instructions = "Text overlay IS needed for this image."
        else:
            text_overlay_instructions = "No text overlay needed. Do not add any text to the image."

        # Build template variables
        lighting = style_brief.lighting
        lighting_type = lighting.type if hasattr(lighting, "type") else str(lighting)
        lighting_direction = lighting.direction if hasattr(lighting, "direction") else "ambient"
        shadow_style = lighting.shadow_style if hasattr(lighting, "shadow_style") else "soft-diffused"

        # Model vs product-only instructions
        if style_brief.reference_has_model:
            model_instructions = (
                "MODEL/PERSON SHOT: The reference image features a person/model. "
                "Show the saree WORN or DRAPED on a person in a similar pose and framing. "
                "Match the model's styling, posture, and composition from the reference. "
                "The person should look like an Indian woman, styled naturally — not a mannequin. "
                "CRITICAL: Keep the saree's structural layout, design, colors, and motifs EXACTLY "
                "as they are in IMAGE 2. DO NOT hallucinate new patterns or change the border/pallu. "
                "The environment, lighting, and background should match the reference mood."
            )
        else:
            model_instructions = (
                "PRODUCT-ONLY SHOT: The reference is a product/flat-lay style image. "
                "Do NOT include any person or model. Show the EXACT saree from IMAGE 2 as a styled product "
                "photograph — folded, draped, or arranged on a surface with props. Do NOT change its design."
            )

        template_vars = {
            "model_instructions": model_instructions,
            "layout_type": style_brief.layout_type,
            "product_placement": style_brief.composition.product_placement,
            "whitespace": style_brief.composition.whitespace,
            "suggested_bg_for_saree": style_brief.background.suggested_bg_for_saree,
            "surface_texture": style_brief.background.surface_texture or style_brief.background.description,
            "lighting_type": lighting_type,
            "lighting_direction": lighting_direction,
            "shadow_style": shadow_style,
            "palette_name": style_brief.color_mood.palette_name,
            "temperature": style_brief.color_mood.temperature,
            "dominant_colors": ", ".join(style_brief.color_mood.dominant_colors),
            "vibe_words": ", ".join(style_brief.vibe_words),
            "props_instructions": props_instructions,
            "text_overlay_instructions": text_overlay_instructions,
            "overlay_text": overlay_text or "",
            "text_position": style_brief.text_overlay.text_position if style_brief.text_overlay.has_text else "none",
            "variation_note": modifier,
            "aspect_ratio": style_brief.composition.aspect_ratio,
        }

        # Use format_map with a defaultdict so missing keys don't crash
        from collections import defaultdict

        class SafeDict(defaultdict):
            def __missing__(self, key: str) -> str:
                return f"{{{key}}}"

        safe = SafeDict(str, template_vars)
        try:
            return base.format_map(safe)
        except Exception:
            # Fallback: append values if template formatting fails
            return (
                f"{base}\n\n"
                f"Layout: {style_brief.layout_type}\n"
                f"Placement: {style_brief.composition.product_placement}\n"
                f"Background: {style_brief.background.suggested_bg_for_saree}\n"
                f"Lighting: {lighting_type}\n"
                f"Palette: {style_brief.color_mood.palette_name} ({style_brief.color_mood.temperature})\n"
                f"Dominant colors: {', '.join(style_brief.color_mood.dominant_colors)}\n"
                f"Vibe: {', '.join(style_brief.vibe_words)}\n"
                f"Variation modifier: {modifier}\n"
                + (f"Overlay text: {overlay_text}\n" if overlay_text else "")
            )

    def generate_variants(
        self,
        saree_image_url: str,
        reference_image_urls: list[str],
        style_brief: StyleBrief,
        overlay_text: str | None,
    ) -> list[StyledVariant]:
        config = load_brand_config()
        modifiers = config.get("variation_modifiers", [])[:1]

        if self.settings.dry_run:
            variants: list[StyledVariant] = []
            for idx, modifier in enumerate(modifiers, start=1):
                mode = "minimal" if idx == 1 else "warm" if idx == 2 else "editorial"
                item_urls: list[str] = []
                first_image_url = ""
                for position, _ref_url in enumerate(reference_image_urls, start=1):
                    content = _create_placeholder_variant(saree_image_url, mode)
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

        if not self.api_key:
            raise StylingError("Missing GOOGLE_API_KEY or GEMINI_API_KEY")

        generated: list[StyledVariant] = []
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        # Download saree image once (same for all positions)
        try:
            saree_b64, saree_mime = _download_image_as_base64(saree_image_url)
        except Exception as exc:
            raise StylingError(f"Failed to download saree image: {exc}") from exc

        for idx, modifier in enumerate(modifiers, start=1):
            prompt = self._build_prompt(style_brief, overlay_text, modifier)
            item_urls: list[str] = []
            for position, ref_url in enumerate(reference_image_urls, start=1):
                # Download reference image for this carousel position
                try:
                    ref_b64, ref_mime = _download_image_as_base64(ref_url)
                except Exception as exc:
                    raise StylingError(f"Failed to download reference image {position}: {exc}") from exc

                part_style_candidates = self._part_style_candidates()
                parts_by_style = {
                    part_style: self._build_image_parts(
                        prompt=prompt,
                        ref_mime=ref_mime,
                        ref_b64=ref_b64,
                        saree_mime=saree_mime,
                        saree_b64=saree_b64,
                        part_style=part_style,
                    )
                    for part_style in part_style_candidates
                }
                logger.info(
                    "gemini_request_prepared",
                    variant=idx,
                    position=position,
                    total_positions=len(reference_image_urls),
                    candidate_models=self._model_candidates(),
                    candidate_part_styles=part_style_candidates,
                    ref_mime=ref_mime,
                    saree_mime=saree_mime,
                    using_sdk=self._sdk_client is not None,
                )

                sdk_image_bytes = self._request_generation_sdk(
                    prompt=prompt,
                    ref_bytes=base64.b64decode(ref_b64),
                    ref_mime=ref_mime,
                    saree_bytes=base64.b64decode(saree_b64),
                    saree_mime=saree_mime,
                    style_brief=style_brief,
                    variant=idx,
                    position=position,
                )
                if sdk_image_bytes is not None:
                    image_bytes = sdk_image_bytes
                else:
                    data = self._request_generation(
                        parts_by_style=parts_by_style,
                        style_brief=style_brief,
                        headers=headers,
                        variant=idx,
                        position=position,
                    )
                    image_bytes = self._extract_image_bytes(data)
                key = f"styled/post-{uuid.uuid4().hex}/variant-{idx}/item-{position}.jpg"
                item_url = self.storage.upload_bytes(key, image_bytes)
                item_urls.append(item_url)
                logger.info(
                    "gemini_variant_generated",
                    variant=idx,
                    position=position,
                    model=self._runtime_model,
                    part_style=self._runtime_part_style,
                )

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
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"])
        for candidate in candidates:
            finish_reason = candidate.get("finishReason")
            if finish_reason:
                raise StylingError(f"Gemini returned no image (finish_reason={finish_reason})")
        raise StylingError(f"Gemini did not return an image: {json.dumps(response_json)[:200]}")
