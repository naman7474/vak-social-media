from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@lru_cache(maxsize=1)
def load_analysis_prompt() -> str:
    return (PROMPTS_DIR / "analysis_prompt.txt").read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def load_caption_prompt() -> str:
    return (PROMPTS_DIR / "caption_prompt.txt").read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def load_styling_prompt() -> str:
    return (PROMPTS_DIR / "gemini_styling_prompt.txt").read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def load_brand_config() -> dict:
    return json.loads((PROMPTS_DIR / "brand_config.json").read_text(encoding="utf-8"))
