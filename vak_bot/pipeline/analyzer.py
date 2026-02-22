from __future__ import annotations

import httpx
import structlog

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import AnalysisError
from vak_bot.pipeline.llm_utils import (
    extract_openai_response_text,
    normalize_openai_model,
    parse_json_object,
)
from vak_bot.pipeline.prompts import load_analysis_prompt, load_video_analysis_prompt
from vak_bot.schemas import StyleBrief

logger = structlog.get_logger(__name__)


class OpenAIReferenceAnalyzer:
    def __init__(self) -> None:
        self.settings = get_settings()

    def analyze_reference(self, reference_image_url: str, reference_caption: str | None, is_video: bool = False) -> StyleBrief:
        if self.settings.dry_run:
            return StyleBrief.model_validate(
                {
                    "layout_type": "flat-lay",
                    "composition": {
                        "product_placement": "center",
                        "whitespace": "moderate",
                        "text_area": "bottom",
                        "aspect_ratio": "4:5",
                    },
                    "color_mood": {
                        "temperature": "warm",
                        "dominant_colors": ["#CFAF7A", "#F5E8D0", "#2C2C2C"],
                        "palette_name": "earthy",
                    },
                    "background": {
                        "type": "textured",
                        "description": "Beige textured surface with brass accents",
                        "suggested_bg_for_saree": "Warm neutral cloth backdrop with marigold petals and brass diya",
                    },
                    "lighting": "natural-soft",
                    "text_overlay": {
                        "has_text": False,
                        "text_style": "none",
                        "text_position": "none",
                        "text_purpose": "none",
                    },
                    "content_format": "single-image",
                    "vibe_words": ["elegant", "warm", "artisan"],
                    "adaptation_notes": "Keep saree fully accurate; add Indian props around it only.",
                }
            )

        if not self.settings.openai_api_key:
            raise AnalysisError("Missing OPENAI_API_KEY")

        prompt = load_analysis_prompt()
        if is_video:
            video_addon = load_video_analysis_prompt()
            if video_addon:
                prompt = f"{prompt}\n\n{video_addon}"
        user_text = f"Reference caption: {reference_caption or 'N/A'}"

        # Use the OpenAI Responses API (newer format for gpt-4.1+ and gpt-5 models)
        model = normalize_openai_model(self.settings.openai_model)
        if model != self.settings.openai_model:
            logger.info("openai_model_normalized", configured=self.settings.openai_model, normalized=model)
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_text},
                        {"type": "input_image", "image_url": reference_image_url},
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_object",
                },
            },
        }

        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=90.0) as client:
                response = client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                raw_text = extract_openai_response_text(data)
                logger.info("openai_analysis_success", model=model, response_id=data.get("id"))
                parsed = parse_json_object(raw_text)
            return StyleBrief.model_validate(parsed)
        except httpx.HTTPStatusError as exc:
            body_preview = exc.response.text[:400] if exc.response is not None else ""
            logger.error(
                "openai_analysis_http_error",
                model=model,
                status_code=exc.response.status_code if exc.response is not None else None,
                body_preview=body_preview,
            )
            raise AnalysisError(str(exc)) from exc
        except Exception as exc:
            logger.error("openai_analysis_failed", model=model, error=str(exc))
            raise AnalysisError(str(exc)) from exc
