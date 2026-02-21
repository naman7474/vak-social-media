from __future__ import annotations

import json

import httpx

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import AnalysisError
from vak_bot.pipeline.prompts import load_analysis_prompt
from vak_bot.schemas import StyleBrief


class OpenAIReferenceAnalyzer:
    def __init__(self) -> None:
        self.settings = get_settings()

    def analyze_reference(self, reference_image_url: str, reference_caption: str | None) -> StyleBrief:
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
        user_text = f"Reference caption: {reference_caption or 'N/A'}"

        payload = {
            "model": self.settings.openai_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": reference_image_url}},
                    ],
                },
            ],
            "temperature": 0.2,
        }

        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=90.0) as client:
                response = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                raw_json = data["choices"][0]["message"]["content"]
                parsed = json.loads(raw_json)
            return StyleBrief.model_validate(parsed)
        except Exception as exc:
            raise AnalysisError(str(exc)) from exc
