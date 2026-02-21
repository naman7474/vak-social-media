from __future__ import annotations

import json
import re
from typing import Any

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.DOTALL)

# Matches unescaped newlines inside JSON string values
_UNESCAPED_NEWLINE_RE = re.compile(r'(?<=")([^"]*?)\n([^"]*?)(?=")', re.DOTALL)

_OPENAI_MODEL_ALIASES = {
    "gpt-5-mini-latest": "gpt-5-mini",
    "gpt-5-mini-latest-mode": "gpt-5-mini",
    "gpt5-mini": "gpt-5-mini",
    "gpt-5-mini-mode": "gpt-5-mini",
    "gpt-5-mini": "gpt-5-mini",
}

_GEMINI_IMAGE_MODEL_ALIASES = {
    "nano-banana": "gemini-2.5-flash-image",
    "nano-banana-latest": "gemini-2.5-flash-image",
    "gemini-nano-banana": "gemini-2.5-flash-image",
    "nano-banana-pro": "gemini-3-pro-image-preview",
    "nano-banana-pro-latest": "gemini-3-pro-image-preview",
    "gemini-nano-banana-pro": "gemini-3-pro-image-preview",
    "gemini-nano-banana-pro-mode": "gemini-3-pro-image-preview",
    "gemini-3-pro-image": "gemini-3-pro-image-preview",
}

_CLAUDE_MODEL_ALIASES = {
    "claude-sonet": "claude-sonnet-4-6",
    "claude-sonnet": "claude-sonnet-4-6",
    "claude-sonet-latest": "claude-sonnet-4-6",
    "claude-sonet-latest-mode": "claude-sonnet-4-6",
    "claude-sonnet-latest": "claude-sonnet-4-6",
    "claude-sonnet-latest-mode": "claude-sonnet-4-6",
    "claude-sonnet-4-latest": "claude-sonnet-4-6",
    "claude-sonnet-4-20250514": "claude-sonnet-4-6",
    "claude-sonnet-4-5-20250514": "claude-sonnet-4-6",
}


def _normalize_alias_key(model: str) -> str:
    key = re.sub(r"[\s_]+", "-", model.strip().lower())
    return re.sub(r"-+", "-", key)


def normalize_openai_model(model: str) -> str:
    cleaned = model.strip()
    return _OPENAI_MODEL_ALIASES.get(_normalize_alias_key(cleaned), cleaned)


def normalize_gemini_image_model(model: str) -> str:
    cleaned = model.strip()
    return _GEMINI_IMAGE_MODEL_ALIASES.get(_normalize_alias_key(cleaned), cleaned)


def normalize_claude_model(model: str) -> str:
    cleaned = model.strip()
    key = _normalize_alias_key(cleaned)
    return _CLAUDE_MODEL_ALIASES.get(key, cleaned)


def _repair_json(text: str) -> str:
    """Attempt to fix common LLM JSON issues: unescaped newlines, trailing commas, single quotes."""
    repaired = text
    # Replace literal newlines inside string values with \n
    repaired = re.sub(
        r'"((?:[^"\\]|\\.)*)"',
        lambda m: '"' + m.group(1).replace('\n', '\\n').replace('\r', '\\r') + '"',
        repaired,
    )
    # Remove trailing commas before } or ]
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    return repaired


def parse_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if not candidate:
        raise ValueError("Empty model response")

    candidate = _CODE_FENCE_RE.sub("", candidate).strip()
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Model response is not a JSON object")
    except json.JSONDecodeError:
        # Try repairing common LLM JSON errors
        try:
            repaired = _repair_json(candidate)
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Try extracting a JSON object from mixed text
        decoder = json.JSONDecoder()
        for idx, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[idx:])
            except json.JSONDecodeError:
                # Try with repair on the substring
                try:
                    repaired_sub = _repair_json(candidate[idx:])
                    parsed, _ = decoder.raw_decode(repaired_sub)
                except json.JSONDecodeError:
                    continue
            if isinstance(parsed, dict):
                return parsed
        raise


def extract_openai_response_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    texts: list[str] = []
    output_items = payload.get("output")
    if isinstance(output_items, list):
        for item in output_items:
            if not isinstance(item, dict):
                continue

            direct_text = item.get("text")
            if isinstance(direct_text, str) and direct_text.strip():
                texts.append(direct_text.strip())

            content_blocks = item.get("content")
            if not isinstance(content_blocks, list):
                continue
            for block in content_blocks:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                block_text = block.get("text")
                if block_type in {"output_text", "text"} and isinstance(block_text, str) and block_text.strip():
                    texts.append(block_text.strip())

    if texts:
        return "\n".join(texts)
    raise ValueError("OpenAI response did not contain text output")


def extract_anthropic_response_text(payload: dict[str, Any]) -> str:
    content_blocks = payload.get("content")
    if not isinstance(content_blocks, list):
        raise ValueError("Anthropic response did not contain content blocks")

    texts: list[str] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        block_text = block.get("text")
        if isinstance(block_text, str) and block_text.strip():
            texts.append(block_text.strip())

    if texts:
        return "\n".join(texts)
    raise ValueError("Anthropic response did not contain text output")
