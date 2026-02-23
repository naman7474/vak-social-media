"""Veo 3.1 video generation — image-to-video, scene extension, prompt building."""

from __future__ import annotations

import time as _time
import uuid
from pathlib import Path

import structlog

from vak_bot.config import get_settings
from vak_bot.pipeline.errors import VeoGenerationError, VeoTimeoutError
from vak_bot.schemas import StyleBrief

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # allow import without SDK installed (e.g. tests)
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment, misc]

logger = structlog.get_logger(__name__)


# ── Video type preset prompts ──────────────────────────────────────────────

VIDEO_TYPE_PROMPTS: dict[str, str] = {
    "fabric-flow": (
        "Gentle breeze causes the sheer saree fabric to flow and billow softly. "
        "The pallu lifts and catches light, revealing the translucency and "
        "hand-painted details. Camera slowly pans across the fabric. "
        "Soft ambient sound of fabric rustling."
    ),
    "close-up": (
        "Slow cinematic zoom into the hand-painted details on the saree, "
        "revealing individual brushstrokes and color variations. Camera pulls "
        "back slowly to show the full drape. Soft, meditative ambient music."
    ),
    "lifestyle": (
        "A graceful woman wearing the saree takes a slow step forward, "
        "the fabric flowing with her movement. Warm natural lighting. "
        "Shallow depth of field. Cinematic fashion film aesthetic. "
        "Soft ambient sounds."
    ),
    "reveal": (
        "The saree starts flat on a surface, then is slowly lifted by "
        "an unseen hand, revealing its full drape and hand-painted motifs. "
        "Camera tracks the fabric as it unfurls. Studio lighting. "
        "Satisfying fabric movement sounds."
    ),
}

# Variation modifiers — currently generate a single output variation.
VIDEO_VARIATION_MODIFIERS: list[str] = [
    "Use slow, gentle camera movement. Dreamy and meditative pacing.",
]


class VeoGenerator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.api_key = self.settings.google_api_key or self.settings.gemini_api_key
        self._client = None
        if genai and self.api_key and not self.settings.dry_run:
            self._client = genai.Client(api_key=self.api_key)

    # ── Prompt Building ────────────────────────────────────────────────────

    def build_video_prompt(self, style_brief: StyleBrief, video_type: str | None = None) -> str:
        """Build a Veo prompt from the style brief's video analysis."""

        # Auto-detect video type from brief if not specified
        if not video_type:
            if style_brief.video_analysis:
                video_type = style_brief.video_analysis.recommended_video_type
            else:
                layout = style_brief.layout_type
                if layout == "close-up":
                    video_type = "close-up"
                elif layout in {"on-model", "lifestyle"}:
                    video_type = "lifestyle"
                elif layout == "flat-lay":
                    video_type = "reveal"
                else:
                    video_type = "fabric-flow"

        base_motion = VIDEO_TYPE_PROMPTS.get(video_type or "fabric-flow", VIDEO_TYPE_PROMPTS["fabric-flow"])

        # Layer in style brief details
        brief = style_brief
        camera_motion = "slow pan"
        pacing = "slow and dreamy"
        if brief.video_analysis:
            camera_motion = brief.video_analysis.camera_motion
            pacing = brief.video_analysis.pacing

        lighting_str = brief.lighting_type if hasattr(brief, "lighting_type") else str(brief.lighting)

        prompt = f"""\
{base_motion}

STYLE CONTEXT:
- Color mood: {brief.color_mood.palette_name}, {brief.color_mood.temperature} tones
- Background: {brief.background.suggested_bg_for_saree}
- Lighting: {lighting_str}
- Vibe: {', '.join(brief.vibe_words)}
- Camera motion: {camera_motion}
- Pacing: {pacing}

CRITICAL RULES:
- The saree fabric, hand-painted details, and colors must remain EXACTLY as shown
  in the starting image. Do not alter, repaint, or modify the saree.
- Keep the video clean and elegant — luxury fashion brand aesthetic.
- No watermarks, no logos, no text overlays.
- Indian context — any props should feel authentic (brass, flowers, silk).
- Cinematic quality, editorial fashion film look.
- Portrait orientation (9:16) for Instagram Reels."""

        return prompt.strip()

    # ── Image-to-Video Generation ──────────────────────────────────────────

    def _extract_generated_video(self, operation) -> object:
        """Extract downloadable video content from an operation or raise a typed error."""
        op_error = getattr(operation, "error", None)
        response = getattr(operation, "response", None) or getattr(operation, "result", None)
        if response is None:
            raise VeoGenerationError(f"Veo returned no response (error={op_error})")

        generated_videos = getattr(response, "generated_videos", None)
        if generated_videos is None and isinstance(response, dict):
            generated_videos = response.get("generated_videos") or response.get("generatedSamples") or response.get("videos")

        if not generated_videos:
            rai_filtered_count = getattr(response, "rai_media_filtered_count", None)
            rai_filtered_reasons = getattr(response, "rai_media_filtered_reasons", None)
            if isinstance(response, dict):
                if rai_filtered_count is None:
                    rai_filtered_count = response.get("rai_media_filtered_count") or response.get("raiMediaFilteredCount")
                if rai_filtered_reasons is None:
                    rai_filtered_reasons = response.get("rai_media_filtered_reasons") or response.get("raiMediaFilteredReasons")

            details = [f"error={op_error}"]
            if rai_filtered_count:
                details.append(f"rai_filtered_count={rai_filtered_count}")
            if rai_filtered_reasons:
                details.append(f"rai_filtered_reasons={rai_filtered_reasons}")

            raise VeoGenerationError(f"Veo returned no generated videos ({', '.join(details)})")

        generated_video = generated_videos[0]
        video = getattr(generated_video, "video", None)
        if video is None and isinstance(generated_video, dict):
            video = generated_video.get("video")
        if not video:
            raise VeoGenerationError("Veo response did not include downloadable video content")
        return video

    def generate_reel_from_styled_image(
        self,
        styled_frame_path: str,
        video_prompt: str,
        reference_images: list[str] | None = None,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
    ) -> str:
        """
        Generate a video using Veo 3.1 from a styled product image.

        Returns: path to the generated MP4 file.
        """
        aspect_ratio = aspect_ratio or self.settings.veo_default_aspect_ratio
        resolution = resolution or self.settings.veo_default_resolution

        if self.settings.dry_run:
            dummy_path = f"/tmp/veo_dryrun_{uuid.uuid4().hex[:8]}.mp4"
            Path(dummy_path).write_bytes(b"\x00" * 1024)
            logger.info("veo_dry_run", output=dummy_path)
            return dummy_path

        if not self._client:
            raise VeoGenerationError("Veo client not initialised (missing GOOGLE_API_KEY)")

        import mimetypes

        mime_type, _ = mimetypes.guess_type(styled_frame_path)
        img_bytes = Path(styled_frame_path).read_bytes()

        start_frame = genai_types.Image(
            image_bytes=img_bytes,
            mime_type=mime_type or "image/jpeg",
        )

        config = genai_types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )

        operation = self._client.models.generate_videos(
            model=self.settings.veo_model,
            prompt=video_prompt,
            image=start_frame,
            config=config,
        )

        # Poll until done
        poll_interval = self.settings.veo_poll_interval_seconds
        max_duration = self.settings.veo_max_poll_duration_seconds
        elapsed = 0

        while not operation.done:
            if elapsed >= max_duration:
                raise VeoTimeoutError(f"Veo generation timed out after {elapsed}s")
            _time.sleep(poll_interval)
            elapsed += poll_interval
            operation = self._client.operations.get(operation)

        if getattr(operation, "error", None):
            raise VeoGenerationError(f"Veo generation failed: {operation.error}")

        generated_video = self._extract_generated_video(operation)
        self._client.files.download(file=generated_video)

        output_path = f"/tmp/veo_output_{uuid.uuid4().hex[:8]}.mp4"
        generated_video.save(output_path)

        logger.info("veo_generation_complete", output=output_path, elapsed_seconds=elapsed)
        return output_path

    # ── Scene Extension ────────────────────────────────────────────────────

    def extend_reel(self, original_video_path: str, continuation_prompt: str) -> str:
        """
        Extend a previously generated Veo video by 8 more seconds.
        Note: Scene extension is limited to 720p resolution.
        """
        if self.settings.dry_run:
            dummy_path = f"/tmp/veo_extended_dryrun_{uuid.uuid4().hex[:8]}.mp4"
            Path(dummy_path).write_bytes(b"\x00" * 2048)
            return dummy_path

        if not self._client:
            raise VeoGenerationError("Veo client not initialised")

        video_file = self._client.files.upload(file=original_video_path)

        operation = self._client.models.generate_videos(
            model=self.settings.veo_model,
            prompt=continuation_prompt,
            video=video_file,
        )

        poll_interval = self.settings.veo_poll_interval_seconds
        max_duration = self.settings.veo_max_poll_duration_seconds
        elapsed = 0

        while not operation.done:
            if elapsed >= max_duration:
                raise VeoTimeoutError(f"Veo extension timed out after {elapsed}s")
            _time.sleep(poll_interval)
            elapsed += poll_interval
            operation = self._client.operations.get(operation)

        if getattr(operation, "error", None):
            raise VeoGenerationError(f"Veo extension failed: {operation.error}")

        generated_video = self._extract_generated_video(operation)
        self._client.files.download(file=generated_video)

        output_path = f"/tmp/veo_extended_{uuid.uuid4().hex[:8]}.mp4"
        generated_video.save(output_path)

        logger.info("veo_extension_complete", output=output_path, elapsed_seconds=elapsed)
        return output_path

    # ── Generate 2 Variations ──────────────────────────────────────────────

    def generate_reel_variations(
        self,
        styled_frame_path: str,
        style_brief: StyleBrief,
        video_type: str | None = None,
        reference_image_path: str | None = None,
    ) -> list[str]:
        """Generate Reel video variation(s)."""

        base_prompt = self.build_video_prompt(style_brief, video_type)
        variations: list[str] = []
        failures: list[str] = []

        for modifier in VIDEO_VARIATION_MODIFIERS:
            full_prompt = f"{base_prompt}\n\nMOTION STYLE: {modifier}"

            try:
                result = self.generate_reel_from_styled_image(
                    styled_frame_path=styled_frame_path,
                    video_prompt=full_prompt,
                    reference_images=[reference_image_path] if reference_image_path else None,
                )
                if result:
                    variations.append(result)
            except (VeoGenerationError, VeoTimeoutError) as exc:
                failures.append(f"[{modifier}] {exc}")
                logger.warning("veo_variation_failed", error=str(exc), modifier=modifier)
                continue

        if not variations and failures:
            raise VeoGenerationError(
                "No video variation was successfully generated. "
                f"Failure details: {' | '.join(failures)}"
            )

        return variations
