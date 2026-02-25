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

# Motion constraints per video type — ensures realistic, constrained movement
VIDEO_TYPE_MOTION_CONSTRAINTS: dict[str, str] = {
    "fabric-flow": (
        "- Only the edges and loose fabric should move — the core painted area stays stable\n"
        "- Movement should be subtle, like a gentle indoor breeze, not outdoor wind\n"
        "- The pallu can lift 5-10 degrees, no more — we're showing elegance, not a storm\n"
        "- Fabric should move like real silk: fluid, with weight, not like digital cloth\n"
        "- Light should play across the fabric naturally as it moves"
    ),
    "close-up": (
        "- Camera movement only — the saree itself remains completely still\n"
        "- Zoom should be gradual (think 8 seconds to go from wide to detail)\n"
        "- Focus rack naturally as depth changes\n"
        "- The painted details should become MORE visible, not blur\n"
        "- Pull-back should be even slower than the zoom-in"
    ),
    "lifestyle": (
        "- If a model is shown, she moves slowly and deliberately — this is editorial, not runway\n"
        "- The saree moves as real fabric would: weight in the pleats, flow in the pallu\n"
        "- Movement should showcase the drape, not obscure the painted details\n"
        "- Camera can track or follow, but smoothly — no handheld shake\n"
        "- Background should have subtle depth and blur, keeping focus on the saree"
    ),
    "reveal": (
        "- The lift should feel like real hands lifting real fabric — natural, with weight\n"
        "- As fabric rises, the painted details should become more visible, not less\n"
        "- Unfurling should be slow enough to appreciate each design element\n"
        "- Fabric should not stretch, warp, or behave unnaturally\n"
        "- Final drape position should show the saree's best features"
    ),
}

# Variation modifiers — currently generate a single output variation.
VIDEO_VARIATION_MODIFIERS: list[str] = [
    "Use slow, gentle camera movement. Dreamy and meditative pacing.",
]

# Path to the prompt template file
PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent.parent / "prompts" / "veo_video_prompt.txt"


class VeoGenerator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.api_key = self.settings.google_api_key or self.settings.gemini_api_key
        self._client = None
        if genai and self.api_key and not self.settings.dry_run:
            self._client = genai.Client(api_key=self.api_key)

    # ── Prompt Building ────────────────────────────────────────────────────

    def _load_prompt_template(self) -> str:
        """Load the Veo prompt template from file."""
        if PROMPT_TEMPLATE_PATH.exists():
            return PROMPT_TEMPLATE_PATH.read_text()
        # Fallback to minimal template if file not found
        logger.warning("veo_prompt_template_not_found", path=str(PROMPT_TEMPLATE_PATH))
        return "{base_motion_prompt}\n\nSTYLE: {palette_name}, {temperature}\nCAMERA: {camera_motion}\nPACING: {pacing}"

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

        video_type = video_type or "fabric-flow"
        base_motion = VIDEO_TYPE_PROMPTS.get(video_type, VIDEO_TYPE_PROMPTS["fabric-flow"])
        motion_constraints = VIDEO_TYPE_MOTION_CONSTRAINTS.get(video_type, VIDEO_TYPE_MOTION_CONSTRAINTS["fabric-flow"])

        # Extract all fields from style brief
        brief = style_brief
        video_analysis = brief.video_analysis

        # Defaults for video analysis fields
        camera_motion = "slow-pan"
        pacing = "slow-dreamy"
        motion_type = "fabric-flow"
        motion_elements = "gentle fabric movement, light playing across the surface"
        audio_mood = "ambient-nature"
        recommended_duration = "8"
        video_adaptation_notes = "Showcase the hand-painted details with subtle, elegant motion."

        # Override with actual video analysis if available
        if video_analysis:
            camera_motion = video_analysis.camera_motion or camera_motion
            pacing = video_analysis.pacing or pacing
            motion_type = video_analysis.motion_type or motion_type
            motion_elements = video_analysis.motion_elements or motion_elements
            audio_mood = video_analysis.audio_mood or audio_mood
            recommended_duration = str(video_analysis.recommended_duration or recommended_duration)
            video_adaptation_notes = video_analysis.video_adaptation_notes or video_adaptation_notes

        # Extract lighting details
        lighting_type = "natural-soft"
        lighting_direction = "side-left"
        shadow_style = "soft-diffused"
        if hasattr(brief, "lighting") and brief.lighting:
            if hasattr(brief.lighting, "type"):
                lighting_type = brief.lighting.type or lighting_type
            elif isinstance(brief.lighting, dict):
                lighting_type = brief.lighting.get("type", lighting_type)
            else:
                lighting_type = str(brief.lighting)

            if hasattr(brief.lighting, "direction"):
                lighting_direction = brief.lighting.direction or lighting_direction
            elif isinstance(brief.lighting, dict):
                lighting_direction = brief.lighting.get("direction", lighting_direction)

            if hasattr(brief.lighting, "shadow_style"):
                shadow_style = brief.lighting.shadow_style or shadow_style
            elif isinstance(brief.lighting, dict):
                shadow_style = brief.lighting.get("shadow_style", shadow_style)

        # Build the template variables
        template_vars = {
            "video_type": video_type,
            "base_motion_prompt": base_motion,
            "motion_constraints": motion_constraints,
            "palette_name": brief.color_mood.palette_name if brief.color_mood else "warm",
            "temperature": brief.color_mood.temperature if brief.color_mood else "warm",
            "suggested_bg_for_saree": brief.background.suggested_bg_for_saree if brief.background else "neutral warm background",
            "lighting_type": lighting_type,
            "lighting_direction": lighting_direction,
            "shadow_style": shadow_style,
            "camera_motion": camera_motion,
            "motion_type": motion_type,
            "motion_elements": motion_elements,
            "pacing": pacing,
            "audio_mood": audio_mood,
            "vibe_words": ", ".join(brief.vibe_words) if brief.vibe_words else "elegant, luxurious, handcrafted",
            "video_adaptation_notes": video_adaptation_notes,
            "recommended_duration": recommended_duration,
        }

        # Load and fill template
        template = self._load_prompt_template()
        try:
            prompt = template.format(**template_vars)
        except KeyError as e:
            logger.warning("veo_prompt_template_missing_key", key=str(e))
            # Fall back to simple prompt on template error
            prompt = f"{base_motion}\n\nCamera: {camera_motion}\nPacing: {pacing}\nMood: {template_vars['palette_name']}"

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
        negative_prompt: str | None = None,
    ) -> str:
        """
        Generate a video using Veo 3.1 from a styled product image.

        Returns: path to the generated MP4 file.
        """
        from vak_bot.pipeline.prompts import load_brand_config

        aspect_ratio = aspect_ratio or self.settings.veo_default_aspect_ratio
        resolution = resolution or self.settings.veo_default_resolution

        if negative_prompt is None:
            config_data = load_brand_config()
            neg_prompts = config_data.get("negative_prompts", {})
            negative_prompt = ", ".join(
                neg_prompts.get("universal", []) +
                neg_prompts.get("product_protection", []) +
                neg_prompts.get("brand_aesthetic", []) +
                neg_prompts.get("cultural_sensitivity", [])
            )

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
            negative_prompt=negative_prompt,
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

    def generate_multi_scene_ad(
        self,
        styled_frame_path: str,
        style_brief: StyleBrief,
        ad_structure: str = "30_second_reel",
    ) -> list[dict]:
        """Generate a series of scenes for a multi-scene ad."""
        from vak_bot.pipeline.prompts import load_brand_config
        config = load_brand_config()
        presets = config.get("video_presets", {}).get("ad_structures", {})
        
        # Fall back to default if specified preset doesn't exist
        structure = presets.get(ad_structure, presets.get("30_second_reel", []))
        
        scenes: list[dict] = []
        failures: list[str] = []
        
        # Re-use reference paths for extensions if possible, but Veo usually works better sequence by sequence
        # Here we just generate each scene described in the preset as an independent 8s video
        # In a more advanced setup, we would extend the previous scene's result.
        
        for i, scene_def in enumerate(structure, start=1):
            scene_type = scene_def.get("scene_type", "fabric-flow")
            base_prompt = self.build_video_prompt(style_brief, scene_type)
            modifier = scene_def.get("motion_modifier", "")
            duration = scene_def.get("duration", 8)
            
            full_prompt = f"{base_prompt}\n\nguidance_weight: High\nMOTION STYLE: {modifier}"
            
            logger.info(f"veo_generating_scene", index=i, type=scene_type)
            try:
                # Assuming generating independent video chunks, can be stitched later
                result_path = self.generate_reel_from_styled_image(
                    styled_frame_path=styled_frame_path,
                    video_prompt=full_prompt,
                    # Short scenes just get full 8s generation but stitched appropriately
                )
                scenes.append({
                    "id": f"scene_{i}",
                    "path": result_path,
                    "duration": duration,
                    "type": scene_type
                })
            except Exception as e:
                failures.append(f"Scene {i} failed: {str(e)}")
                logger.warning("veo_scene_generation_failed", scene=i, error=str(e))
                # Stop rendering further scenes if one fails
                break

        if not scenes and failures:
            raise VeoGenerationError(f"Failed to generate ad scenes: {' | '.join(failures)}")
            
        return scenes
