from __future__ import annotations

import json

import httpx
import structlog

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import CaptionError
from vak_bot.pipeline.prompts import load_caption_prompt
from vak_bot.schemas import CaptionPackage, StyleBrief

logger = structlog.get_logger(__name__)


class ClaudeCaptionWriter:
    def __init__(self) -> None:
        self.settings = get_settings()

    def generate_caption(self, styled_image_url: str, style_brief: StyleBrief, product_info: dict) -> CaptionPackage:
        if self.settings.dry_run:
            hashtags = (
                "#vakstudios #handpaintedsaree #vakclothing #silksaree #artisanmade "
                "#oneofone #sareelovers #slowfashionindia #craftedwithlove #handpaintedfashion "
                "#weddingguest #diwalifashion #indianfashion #handloomlove #limitededition "
                "#madebyhands #wearart #sareestyle #shopindian #consciousfashion"
            )
            return CaptionPackage(
                caption=(
                    "Some pieces don't just dress you, they speak for you. "
                    "This hand-painted Vâk saree was built slowly by hand so every brushstroke stays personal. "
                    "Wear it for an evening celebration or when you simply want to feel unmistakably like yourself."
                ),
                hashtags=hashtags,
                alt_text="Hand-painted saree in warm tones styled on a textured Indian-inspired background with brass props.",
                overlay_text=None,
            )

        if not self.settings.anthropic_api_key:
            raise CaptionError("Missing ANTHROPIC_API_KEY")

        prompt = load_caption_prompt()
        payload = {
            "model": self.settings.claude_model,
            "max_tokens": 900,
            "system": prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": styled_image_url,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Style brief: {style_brief.model_dump_json()}\n"
                                f"Product details: {json.dumps(product_info)}\n\n"
                                "Generate a caption package for this styled image."
                            ),
                        },
                    ],
                }
            ],
        }

        headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            with httpx.Client(timeout=90.0) as client:
                response = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            text = data["content"][0]["text"]
            logger.info("claude_caption_success", model=self.settings.claude_model)
            parsed = json.loads(text)
            return CaptionPackage.model_validate(parsed)
        except Exception as exc:
            logger.error("claude_caption_failed", error=str(exc))
            raise CaptionError(str(exc)) from exc
