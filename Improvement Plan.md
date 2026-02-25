# Vâk Bot Pipeline — File-by-File Change Guide

## Overview: What's Wrong and What Changes

After auditing every file in your codebase, here are the root causes of your problems and the exact files that need changes.

**Problem 1: Brand context is fragmented** — `brand_config.json` has colors and props, but the actual brand DNA (voice, identity, product rules, forbidden aesthetics) lives scattered across `caption_prompt.txt`, `gemini_styling_prompt.txt`, and `veo_video_prompt.txt`. Each prompt reinvents the brand context independently, leading to inconsistency.

**Problem 2: Image generation can still alter the saree** — Your current approach sends both the saree and reference image to Gemini and asks it to "preserve the saree." This is a prayer, not a guarantee. Gemini sometimes modifies the hand-painted details despite the prompt. The SSIM threshold of 0.6 is too low to catch subtle changes.

**Problem 3: Video generation produces generic 8-second clips** — `veo_generator.py` generates a single variation with a single modifier. The prompts are descriptive but not cinematically specific enough for Veo 3.1 (missing f-stop, lens length, color temperature — the vocabulary Veo actually responds to). There's no mechanism for multi-scene ads.

**Problem 4: No brand guardian** — Outputs go straight from generation to human review. There's no automated check that the content matches Vâk's brand identity before it reaches the user in Telegram.

---

## FILE 1: `prompts/brand_config.json`

### Current State
Has brand basics, colors, typography, visual identity, props library, and variation modifiers. This is good but incomplete — it's missing the critical product protection rules and brand voice that every pipeline stage needs.

### Changes Required

Add these new top-level sections to the existing JSON:

```json
{
  "brand": { ... },
  "colors": { ... },
  "typography": { ... },
  "visual_identity": { ... },

  "product_rules": {
    "sacred_principle": "The hand-painted saree must NEVER be altered by AI. Every brushstroke is the artisan's original work.",
    "ai_may_change": ["background", "lighting", "staging", "environment", "shadows", "props", "composition"],
    "ai_must_never_change": ["saree fabric texture", "painted motifs", "color of saree", "zari/border patterns", "fabric weave", "drape structure"],
    "validation_thresholds": {
      "image_ssim_minimum": 0.85,
      "image_lpips_maximum": 0.15,
      "video_first_frame_ssim": 0.80,
      "video_clip_similarity": 0.85
    }
  },

  "negative_prompts": {
    "universal": [
      "blurry, low quality, distorted, watermark, text artifacts, AI artifacts",
      "oversaturated colors, HDR look, Instagram filter aesthetic",
      "cartoon, illustration, digital painting, 3D render"
    ],
    "product_protection": [
      "altered fabric pattern, changed motif, modified brushstrokes",
      "synthetic fabric texture, machine-printed pattern, digital art style",
      "wrong drape physics, stiff fabric, plastic-looking material"
    ],
    "brand_aesthetic": [
      "neon colors, pop art, minimalist stark white, fast-fashion look",
      "Western haute couture runway, industrial setting",
      "discount store aesthetic, marketplace listing look, Meesho/Amazon style"
    ],
    "cultural_sensitivity": [
      "orientalist tropes, exoticized imagery, costume-like presentation",
      "inauthentic Indian setting, Bollywood kitsch, cheap decoration"
    ]
  },

  "video_presets": {
    "ad_structures": {
      "30_second_reel": {
        "scenes": [
          {"name": "hook", "duration_sec": 3, "type": "close-up", "purpose": "Stop the scroll — extreme detail of hand-painting"},
          {"name": "origin", "duration_sec": 7, "type": "lifestyle", "purpose": "Show the artisan's world or the saree in context"},
          {"name": "reveal", "duration_sec": 10, "type": "reveal", "purpose": "Full product reveal with elegant camera movement"},
          {"name": "drape", "duration_sec": 7, "type": "fabric-flow", "purpose": "Fabric in motion, showing weight and texture"},
          {"name": "close", "duration_sec": 3, "type": "close-up", "purpose": "Final detail shot, brand moment"}
        ],
        "transition": "dissolve",
        "transition_duration_sec": 1.5
      },
      "15_second_reel": {
        "scenes": [
          {"name": "hook", "duration_sec": 3, "type": "close-up", "purpose": "Macro detail of brushwork"},
          {"name": "reveal", "duration_sec": 7, "type": "fabric-flow", "purpose": "Saree in motion"},
          {"name": "close", "duration_sec": 5, "type": "reveal", "purpose": "Full product + brand moment"}
        ],
        "transition": "dissolve",
        "transition_duration_sec": 1.0
      }
    },
    "ffmpeg_transitions": {
      "luxury_dissolve": "xfade=transition=dissolve:duration=1.5",
      "fade_black": "xfade=transition=fadeblack:duration=1.0",
      "smooth_left": "xfade=transition=smoothleft:duration=1.0"
    }
  },

  "voice": {
    "tone": "warm, reverent, personal, unhurried",
    "personality": ["artisanal", "meditative", "rooted", "refined"],
    "sentence_style": "short, sensory, evocative — 12 words or fewer per sentence",
    "vocabulary_preferred": ["crafted", "painted", "brushstroke", "palette", "atelier", "heirloom", "canvas of silk"],
    "vocabulary_forbidden": ["exquisite", "timeless elegance", "must-have", "ethereal", "resplendent", "stunning", "amazing", "shop now", "hurry", "limited time", "best-seller"],
    "emoji_policy": "maximum 2-3 per caption, at the end if at all",
    "cta_style": "invitation not command — 'Discover', 'Explore', 'Experience'"
  }
}
```

**Why**: Every pipeline stage (`analyzer.py`, `gemini_styler.py`, `veo_generator.py`, `caption_writer.py`) already calls `load_brand_config()`. By centralizing product rules, negative prompts, video presets, and voice guidelines here, all stages read from one source of truth instead of each prompt file reinventing the brand context.

---

## FILE 2: `prompts/gemini_styling_prompt.txt`

### Current State
Very comprehensive prompt with good layout/lighting/composition instructions. But the critical "NEVER alter the saree" rules are buried in the middle and stated just once.

### Changes Required

**Change 1**: Add negative prompt injection at the TOP of the prompt (before any creative instructions):

Find the section that starts with:
```
I'm providing two images:
```

Add BEFORE it:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE RULE — READ THIS FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are creating product photography for Vâk Studios, a luxury hand-painted saree brand.
The saree in IMAGE 2 was painted by hand by an artisan over several days.
Every brushstroke is deliberate and irreplaceable.

YOUR #1 JOB: The saree from IMAGE 2 must appear PIXEL-IDENTICAL in your output.
- Same colors, same motifs, same texture, same fabric weave
- Same zari borders, same pallu design, same painted details
- If you cannot preserve the saree exactly, produce nothing

You may ONLY change: background, lighting angle, staging, props, composition, shadows.
You must NEVER change: the saree itself in any way whatsoever.

NEGATIVE PROMPT (things that must NOT appear in the output):
{negative_prompts}
```

**Change 2**: In `gemini_styler.py` → `_build_prompt()`, inject the negative prompts from brand_config:

```python
# Add after the existing props_instructions line:
negative_prompts = config.get("negative_prompts", {})
all_negatives = []
for category, prompts in negative_prompts.items():
    all_negatives.extend(prompts)
negative_prompt_text = "\n".join(f"- {neg}" for neg in all_negatives)
```

Then add `negative_prompts=negative_prompt_text` to the template variables dict.

**Change 3**: Add product-specific descriptors to the prompt. After the `PROPS` section, add:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BRAND IDENTITY — Vâk Studios
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is for Vâk (Sanskrit for "voice"). Tagline: "Your clothes speak before you do."
Three pillars: VOICE (your clothes say something), HAND (made by hands), ONE (each piece is one of a kind).

The image should feel:
- Like a curated art gallery, not a retail catalog
- Warm and tactile — you can almost feel the fabric
- Indian at its core but modern in composition
- Premium but not pretentious — quiet confidence

Brand colors for backgrounds/accents (NOT for the saree):
- Deep charcoal: #2C2C2C
- Warm cream: #F5F0E8
- Warm gold: #C9A96E
- Deep maroon: #6B2D3E
- Muted terracotta: #B87351
- Sage green: #7A8B6F

NEVER use: neon, electric blue, hot pink, pure white #FFFFFF, pure black #000000
```

---

## FILE 3: `vak_bot/pipeline/gemini_styler.py`

### Current State
The `_build_prompt()` method assembles the template but doesn't inject negative prompts or brand identity from config. The `generate_variants()` method uses `modifiers[:1]` — only generating 1 variant instead of 3.

### Changes Required

**Change 1**: In `_build_prompt()`, inject negative prompts and brand context:

```python
def _build_prompt(self, style_brief: StyleBrief, overlay_text: str | None, modifier: str) -> str:
    base = load_styling_prompt()
    config = load_brand_config()

    # NEW: Build negative prompt block from brand config
    negative_prompts = config.get("negative_prompts", {})
    all_negatives = []
    for category, prompts in negative_prompts.items():
        all_negatives.extend(prompts)
    negative_prompt_text = "\n".join(f"- {neg}" for neg in all_negatives)

    # NEW: Build brand color context
    brand_colors = config.get("colors", {})
    secondary = brand_colors.get("secondary", {})
    brand_color_text = ", ".join(f"{name}: {hex_val}" for name, hex_val in secondary.items())

    # ... existing props logic ...

    # Add to template variables (in the format dict at the bottom):
    # "negative_prompts": negative_prompt_text,
    # "brand_accent_colors": brand_color_text,
```

**Change 2**: Fix variant count — change `modifiers[:1]` back to at least `[:2]`:

```python
# Current (line in generate_variants):
modifiers = config.get("variation_modifiers", [])[:1]

# Change to:
modifiers = config.get("variation_modifiers", [])[:3]
```

**Change 3**: Raise the SSIM threshold. In the orchestrator, validator is created with `threshold=0.6`. This is too low — a score of 0.6 means 40% of the saree region may have changed. Change to at least 0.75:

This change is in `orchestrator.py` (see File 6 below), but noting here since it's related to the styling pipeline.

---

## FILE 4: `prompts/veo_video_prompt.txt`

### Current State
Very detailed template with good motion constraints and realism requirements. But it's missing the cinematographic vocabulary that Veo 3.1 actually responds to (f-stop, focal length, color temperature, film stock), and it lacks product-specific descriptors.

### Changes Required

**Change 1**: Rewrite `VIDEO_TYPE_PROMPTS` in `veo_generator.py` with cinema-specific vocabulary:

```python
VIDEO_TYPE_PROMPTS: dict[str, str] = {
    "fabric-flow": (
        "Close-up shot at f/2.8, 85mm lens. A hand-painted silk saree catches "
        "a gentle indoor breeze, the pallu lifting 5-10 degrees and settling "
        "with natural silk weight. Warm directional light from upper left at "
        "3200K color temperature creates golden highlights on the fabric surface. "
        "Individual hand-painted brushstrokes and zari thread visible. "
        "Camera performs a subtle slow pan right. Shallow depth of field with "
        "soft bokeh background. Film grain texture. "
        "SFX: delicate silk fabric rustling, soft ambient room tone."
    ),
    "close-up": (
        "Extreme macro shot at f/1.8, 100mm macro lens. Camera begins on a "
        "wide view of the hand-painted saree detail, then performs a very slow "
        "8-second dolly-in revealing individual brushstrokes, color layering, "
        "and thread texture of the hand-painted motif. The fabric is completely "
        "still — only the camera moves. Warm side lighting reveals the textile "
        "surface dimension. Natural focus rack as depth changes. "
        "Color temperature 3500K. Subtle film grain. "
        "SFX: silence with very soft ambient room tone."
    ),
    "lifestyle": (
        "Medium shot at f/2.0, 50mm lens. A woman wearing the hand-painted "
        "saree takes one slow, deliberate step. The silk fabric flows with "
        "natural weight — pleats hold their structure, pallu drapes with gravity. "
        "Warm natural window light, golden hour quality at 3200K. Shallow depth "
        "of field, background in soft bokeh. Camera tracks smoothly on gimbal. "
        "Editorial fashion film aesthetic. The hand-painted details on the saree "
        "remain sharp and unchanged throughout the movement. "
        "SFX: soft footstep, fabric movement, ambient room sounds."
    ),
    "reveal": (
        "Medium-wide shot at f/2.8, 35mm lens. The saree begins folded on a "
        "surface, then is slowly lifted by a hand from below frame, unfurling "
        "to reveal the full drape and hand-painted motifs. Camera tracks upward "
        "following the fabric. Warm directional studio light. The painted design "
        "becomes more visible as the fabric opens. Natural fabric weight and "
        "physics — silk, not digital cloth. "
        "SFX: satisfying fabric unfurling, soft room ambience."
    ),
}
```

**Change 2**: In the template file `veo_video_prompt.txt`, add a product descriptor section BEFORE the VIDEO TYPE section:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BRAND: Vâk Studios — Luxury Hand-Painted Sarees
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This video is for a luxury Indian brand where every saree is hand-painted by
a named artisan over multiple days. The product in the starting image is REAL
and must be treated as sacred — every brushstroke, every color, every motif
must remain exactly as shown in frame 1 through the entire video.

THE STARTING IMAGE IS THE GROUND TRUTH. The final frame must match it exactly.
Only the camera angle, lighting shadows, and fabric position in space should
differ — never the design.

NEGATIVE PROMPT: blurry, distorted patterns, altered colors, morphing texture,
incorrect pattern placement, wrong fabric color, missing embroidery, fabric
distortion, AI-generated look, synthetic texture, plastic fabric.
```

**Change 3**: Add `negative_prompt` to the Veo API call in `generate_reel_from_styled_image()`:

```python
# In veo_generator.py, generate_reel_from_styled_image method:
config = genai_types.GenerateVideosConfig(
    aspect_ratio=aspect_ratio,
    resolution=resolution,
    negative_prompt=(
        "blurry, distorted patterns, altered colors, morphing texture, "
        "incorrect pattern placement, wrong fabric color, missing embroidery, "
        "fabric distortion, synthetic look, AI artifacts, warping"
    ),
)
```

The Veo 3.1 API supports `negative_prompt` in `GenerateVideosConfig` — your current code doesn't use it.

---

## FILE 5: `vak_bot/pipeline/veo_generator.py`

### Current State
Only generates 1 variation (`VIDEO_VARIATION_MODIFIERS` has only 1 entry). No support for multi-scene generation. No reference images passed to Veo for consistency. No negative prompt in API config.

### Changes Required

**Change 1**: Restore 2 variation modifiers:

```python
VIDEO_VARIATION_MODIFIERS: list[str] = [
    "Slow, meditative camera movement. Every second feels luxurious. f/2.0 shallow depth of field.",
    "Subtle editorial energy. Purposeful camera tracking. f/2.8 with moderate depth.",
]
```

**Change 2**: Add negative prompt to `generate_reel_from_styled_image()`:

```python
def generate_reel_from_styled_image(
    self,
    styled_frame_path: str,
    video_prompt: str,
    reference_images: list[str] | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
) -> str:
    # ... existing code until config creation ...

    config = genai_types.GenerateVideosConfig(
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        # NEW: Add negative prompt for product protection
        negative_prompt=(
            "blurry, distorted patterns, altered colors, morphing texture, "
            "wrong fabric color, missing motifs, fabric distortion, "
            "synthetic texture, AI artifacts, warping, color shift"
        ),
    )

    # NEW: Add reference images for style consistency
    ref_image_params = []
    if reference_images:
        for ref_path in reference_images[:3]:
            ref_bytes = Path(ref_path).read_bytes()
            ref_mime, _ = mimetypes.guess_type(ref_path)
            ref_image_params.append(
                genai_types.VideoGenerationReferenceImage(
                    image=genai_types.Image(
                        image_bytes=ref_bytes,
                        mime_type=ref_mime or "image/jpeg",
                    ),
                    reference_type="asset",
                )
            )

    if ref_image_params:
        config.reference_images = ref_image_params

    # ... rest of existing code ...
```

**Change 3**: Add a new method for multi-scene ad generation:

```python
def generate_multi_scene_ad(
    self,
    styled_frame_path: str,
    style_brief: StyleBrief,
    ad_structure: str = "30_second_reel",
) -> list[dict]:
    """Generate multiple scenes for a longer ad, returning paths and metadata."""
    from vak_bot.pipeline.prompts import load_brand_config

    config = load_brand_config()
    ad_presets = config.get("video_presets", {}).get("ad_structures", {})
    structure = ad_presets.get(ad_structure)

    if not structure:
        # Fallback to single 8-second clip
        path = self.generate_reel_from_styled_image(
            styled_frame_path=styled_frame_path,
            video_prompt=self.build_video_prompt(style_brief),
        )
        return [{"path": path, "scene": "single", "duration": 8}]

    scenes = []
    for scene_def in structure["scenes"]:
        scene_prompt = self.build_video_prompt(
            style_brief,
            video_type=scene_def["type"],
        )
        # Prepend the scene purpose for better context
        scene_prompt = (
            f"SCENE PURPOSE: {scene_def['purpose']}\n"
            f"TARGET DURATION: {scene_def['duration_sec']} seconds\n\n"
            + scene_prompt
        )

        try:
            path = self.generate_reel_from_styled_image(
                styled_frame_path=styled_frame_path,
                video_prompt=scene_prompt,
            )
            scenes.append({
                "path": path,
                "scene": scene_def["name"],
                "duration": scene_def["duration_sec"],
                "type": scene_def["type"],
            })
        except (VeoGenerationError, VeoTimeoutError) as exc:
            logger.warning("multi_scene_failed", scene=scene_def["name"], error=str(exc))
            continue

    return scenes
```

---

## FILE 6: `vak_bot/pipeline/orchestrator.py`

### Current State
Orchestrates the full pipeline but uses `SareeValidator(threshold=0.6)` for images and `threshold=0.7` for video. These are too low. Also, the video pipeline doesn't pass reference images to Veo.

### Changes Required

**Change 1**: Raise validation thresholds:

```python
# In run_generation_pipeline():
validator = SareeValidator(threshold=0.75)  # was 0.6

# In run_video_generation_pipeline():
validator = SareeValidator(threshold=0.75)  # was 0.6
video_validator = SareeValidator(threshold=0.75)  # was 0.7
```

Better yet, read from brand_config:

```python
from vak_bot.pipeline.prompts import load_brand_config

config = load_brand_config()
thresholds = config.get("product_rules", {}).get("validation_thresholds", {})
image_threshold = thresholds.get("image_ssim_minimum", 0.75)
video_threshold = thresholds.get("video_first_frame_ssim", 0.75)

validator = SareeValidator(threshold=image_threshold)
video_validator = SareeValidator(threshold=video_threshold)
```

**Change 2**: In `run_video_generation_pipeline()`, pass the reference image to Veo for style consistency. Find the video generation step:

```python
# Current code:
video_paths = veo.generate_reel_variations(
    styled_frame_path=styled_frame_path,
    style_brief=style_brief,
    video_type=post.video_type,
)

# Change to (pass reference image):
ref_image_path = None
if post.reference_image:
    import tempfile
    ref_bytes = _fetch_bytes(post.reference_image)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as ref_tf:
        ref_tf.write(ref_bytes)
        ref_image_path = ref_tf.name
    tmp_paths.append(ref_image_path)

video_paths = veo.generate_reel_variations(
    styled_frame_path=styled_frame_path,
    style_brief=style_brief,
    video_type=post.video_type,
    reference_image_path=ref_image_path,
)
```

**Change 3**: Add a new pipeline function for multi-scene ads. After `run_video_generation_pipeline`, add:

```python
def run_multi_scene_ad_pipeline(post_id: int, chat_id: int, ad_structure: str = "30_second_reel") -> None:
    """Generate a multi-scene ad (30s or 15s) by creating discrete scenes and stitching."""
    veo = VeoGenerator()
    captioner = ClaudeCaptionWriter()
    video_validator = SareeValidator(threshold=0.75)
    storage = R2StorageClient()

    with SessionLocal() as session:
        post = session.get(Post, post_id)
        if not post or not post.styled_image:
            send_text(chat_id, "No styled image available for ad creation.")
            return

        post.status = PostStatus.PROCESSING.value
        post.media_type = "reel"
        session.commit()

        try:
            style_brief = StyleBrief.model_validate(post.style_brief or {})
            styled_bytes = _fetch_bytes(post.styled_image)

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                tf.write(styled_bytes)
                styled_frame_path = tf.name

            # Generate all scenes
            send_text(chat_id, f"🎬 Generating {ad_structure} ad — this will take 5-10 minutes...")
            scenes = veo.generate_multi_scene_ad(
                styled_frame_path=styled_frame_path,
                style_brief=style_brief,
                ad_structure=ad_structure,
            )

            if len(scenes) < 2:
                send_text(chat_id, "Could only generate 1 scene. Sending as a standard Reel instead.")
                # Fall back to single clip posting
                return

            # Stitch scenes with FFmpeg
            from vak_bot.pipeline.video_stitcher import stitch_scenes
            final_path = stitch_scenes(
                scene_paths=[s["path"] for s in scenes],
                transition="dissolve",
                transition_duration=1.5,
            )

            # Upload and send for review
            final_bytes = Path(final_path).read_bytes()
            key = f"videos/post-{post_id}/ad-{uuid.uuid4().hex[:8]}.mp4"
            video_url = storage.upload_bytes(key, final_bytes, content_type="video/mp4")

            post.video_url = video_url
            session.commit()

            send_text(chat_id, f"✅ {len(scenes)}-scene ad generated ({sum(s['duration'] for s in scenes)}s total)")
            # Send video for review...

        except Exception as exc:
            post.status = PostStatus.FAILED.value
            post.error_message = str(exc)
            session.commit()
            send_text(chat_id, f"Ad generation failed: {str(exc)[:200]}")
```

---

## FILE 7: `vak_bot/pipeline/video_stitcher.py`

### Current State
Has `extract_first_frame()` and `compress_video()` but no scene stitching with transitions.

### Changes Required

Add the `stitch_scenes()` function:

```python
import subprocess
import uuid
from pathlib import Path

import structlog

from vak_bot.config import get_settings

logger = structlog.get_logger(__name__)


def stitch_scenes(
    scene_paths: list[str],
    transition: str = "dissolve",
    transition_duration: float = 1.5,
    fps: int = 24,
) -> str:
    """Stitch multiple video scenes into a single video with transitions.

    Args:
        scene_paths: List of paths to MP4 files to stitch
        transition: FFmpeg xfade transition type (dissolve, fadeblack, smoothleft)
        transition_duration: Duration of each transition in seconds
        fps: Target framerate

    Returns:
        Path to the stitched output file
    """
    settings = get_settings()
    ffmpeg = settings.ffmpeg_path

    if len(scene_paths) < 2:
        return scene_paths[0]

    # Build FFmpeg filter complex for xfade transitions
    inputs = []
    for i, path in enumerate(scene_paths):
        inputs.extend(["-i", path])

    # Normalize all inputs to same framerate
    filter_parts = []
    for i in range(len(scene_paths)):
        filter_parts.append(f"[{i}:v]settb=AVTB,fps={fps}[v{i}]")

    # Chain xfade transitions
    # Each clip is ~8s, transition starts at (clip_duration - transition_duration)
    clip_duration = 8.0  # Veo default
    prev_label = "v0"
    offset = clip_duration - transition_duration

    for i in range(1, len(scene_paths)):
        out_label = f"t{i}" if i < len(scene_paths) - 1 else "vout"
        filter_parts.append(
            f"[{prev_label}][v{i}]xfade=transition={transition}"
            f":duration={transition_duration}:offset={offset}"
            f",format=yuv420p[{out_label}]"
        )
        prev_label = out_label
        offset += clip_duration - transition_duration

    filter_complex = "; ".join(filter_parts)
    output_path = f"/tmp/stitched_{uuid.uuid4().hex[:8]}.mp4"

    cmd = [
        ffmpeg,
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_label}]",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "medium",
        "-y",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.error("ffmpeg_stitch_failed", stderr=result.stderr[:500])
        raise RuntimeError(f"FFmpeg stitching failed: {result.stderr[:200]}")

    logger.info("scenes_stitched", output=output_path, scene_count=len(scene_paths))
    return output_path
```

---

## FILE 8: `prompts/caption_prompt.txt`

### Current State
Good brand voice guidelines but they're self-contained — they don't reference `brand_config.json`. The forbidden words list is incomplete.

### Changes Required

**Change 1**: Add a `BRAND DNA` section at the top that matches the config:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BRAND DNA — Vâk Studios
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Brand: Vâk (Sanskrit for "voice"). Tagline: "Your clothes speak before you do."
Pillars: VOICE (your clothes say something), HAND (made by hands), ONE (each piece is one of a kind).
Personality: artisanal, meditative, rooted, refined.
Heritage: Hand-painted sarees created by trained artists who blend traditional Indian motifs with contemporary brushwork.

Think of Vâk's Instagram as a quiet art gallery — not a retail store.
Every post should make the viewer pause and feel something.
```

**Change 2**: Expand the "DO NOT" section with the full forbidden vocabulary:

```
DO NOT:
- Use these banned words: "exquisite", "timeless elegance", "must-have",
  "ethereal", "resplendent", "stunning", "amazing", "gorgeous", "breathtaking",
  "jaw-dropping", "game-changer", "obsessed", "slay", "iconic"
- Use salesy language: "shop now", "hurry", "limited time", "best-seller",
  "discount", "offer", "deal", "grab yours", "don't miss out"
- Mention the price explicitly in the caption
- Use more than 2-3 emojis, and never as the first character
- Start the caption with a question (this is overused on Instagram)
- Use the word "we" — Vâk speaks as a singular voice
```

---

## FILE 9: `vak_bot/pipeline/caption_writer.py`

### Current State
Works well but the Claude system prompt is loaded from file only — it doesn't get augmented with dynamic brand context from `brand_config.json`.

### Changes Required

**Change 1**: Inject brand voice from config into the system prompt:

```python
def generate_caption(self, styled_image_url: str, style_brief: StyleBrief,
                      product_info: dict, is_reel: bool = False) -> CaptionPackage:
    # ... existing dry_run code ...

    prompt = load_caption_prompt()

    # NEW: Inject brand voice from config
    config = load_brand_config()
    voice = config.get("voice", {})
    if voice:
        voice_injection = (
            f"\n\nBRAND VOICE SETTINGS (from brand config):\n"
            f"Tone: {voice.get('tone', 'warm')}\n"
            f"Preferred vocabulary: {', '.join(voice.get('vocabulary_preferred', []))}\n"
            f"FORBIDDEN vocabulary: {', '.join(voice.get('vocabulary_forbidden', []))}\n"
            f"Emoji policy: {voice.get('emoji_policy', 'maximum 2-3')}\n"
            f"CTA style: {voice.get('cta_style', 'invitation not command')}\n"
        )
        prompt = prompt + voice_injection

    if is_reel:
        prompt += "\n\n" + _REEL_CAPTION_ADDON

    # ... rest of existing code ...
```

---

## FILE 10: `prompts/analysis_prompt.txt` (ChatGPT reference analysis)

### Current State
Good structured output but doesn't include brand context for the analyzer. The analyzer doesn't know Vâk's color palette, so it can't suggest brand-appropriate backgrounds.

### Changes Required

Add after the existing "Important rules:" section:

```
BRAND CONTEXT (use this to make better suggestions):
This analysis is for Vâk Studios, a luxury hand-painted saree brand.
Brand color palette for backgrounds/staging:
- Deep charcoal: #2C2C2C
- Warm cream: #F5F0E8
- Warm gold: #C9A96E
- Deep maroon: #6B2D3E
- Muted terracotta: #B87351
- Sage green: #7A8B6F
- Brass accent: #D4A843
- Jasmine white: #FEFCF3

When suggesting "suggested_bg_for_saree", use these colors as anchors.
When suggesting props, always suggest Indian-context items:
brass diyas, marigold/jasmine flowers, terracotta items, carved wood,
raw silk fabric, antique jewelry, woven baskets, handmade paper.

NEVER suggest:
- Western props (wine glasses, modern vases, minimalist objects)
- Neon or electric colors in backgrounds
- Industrial or stark white settings
- Anything that reads as fast-fashion or mass-market
```

---

## FILE 11: `vak_bot/pipeline/saree_validator.py`

### Current State
Uses basic SSIM comparison. No LPIPS support. No CLIP-based video frame validation.

### Changes Required

**Change 1**: Add LPIPS as a secondary check (requires adding `lpips` to requirements.txt):

```python
import io
from PIL import Image
import numpy as np
from skimage.metrics import structural_similarity

try:
    import lpips
    import torch
    _LPIPS_AVAILABLE = True
except ImportError:
    _LPIPS_AVAILABLE = False


class SareeValidator:
    def __init__(self, threshold: float = 0.75, lpips_threshold: float = 0.15):
        self.threshold = threshold
        self.lpips_threshold = lpips_threshold
        self._lpips_fn = None
        if _LPIPS_AVAILABLE:
            self._lpips_fn = lpips.LPIPS(net='alex')

    def verify_preserved(self, original_bytes: bytes, generated_bytes: bytes) -> tuple[bool, float]:
        orig = np.array(Image.open(io.BytesIO(original_bytes)).convert("L"))
        gen = np.array(Image.open(io.BytesIO(generated_bytes)).convert("L"))

        # Resize to match
        if orig.shape != gen.shape:
            gen_img = Image.open(io.BytesIO(generated_bytes)).convert("L")
            gen_img = gen_img.resize((orig.shape[1], orig.shape[0]))
            gen = np.array(gen_img)

        ssim_score = structural_similarity(orig, gen, data_range=255)

        # If LPIPS is available, use it as a secondary check
        lpips_passed = True
        if self._lpips_fn and ssim_score >= self.threshold:
            orig_rgb = np.array(Image.open(io.BytesIO(original_bytes)).convert("RGB")) / 255.0
            gen_rgb = np.array(Image.open(io.BytesIO(generated_bytes)).convert("RGB"))
            gen_pil = Image.fromarray(gen_rgb).resize((orig_rgb.shape[1], orig_rgb.shape[0]))
            gen_rgb = np.array(gen_pil) / 255.0

            orig_t = torch.from_numpy(orig_rgb).permute(2, 0, 1).unsqueeze(0).float() * 2 - 1
            gen_t = torch.from_numpy(gen_rgb).permute(2, 0, 1).unsqueeze(0).float() * 2 - 1
            lpips_score = self._lpips_fn(orig_t, gen_t).item()
            lpips_passed = lpips_score < self.lpips_threshold

        is_valid = ssim_score >= self.threshold and lpips_passed
        return is_valid, ssim_score
```

---

## FILE 12: `vak_bot/config/settings.py`

### Changes Required

Add new settings for multi-scene ads:

```python
# Multi-scene ad settings
ad_default_structure: str = Field(default="30_second_reel", alias="AD_DEFAULT_STRUCTURE")
ad_scene_timeout_seconds: int = Field(default=300, alias="AD_SCENE_TIMEOUT_SECONDS")
```

---

## FILE 13: `vak_bot/workers/tasks.py`

### Changes Required

Add a new task for multi-scene ad generation:

```python
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 1})
def generate_ad_task(self, post_id: int, chat_id: int, ad_structure: str = "30_second_reel") -> None:
    logger.info("generate_ad_task_start post_id=%s structure=%s", post_id, ad_structure)
    run_multi_scene_ad_pipeline(post_id=post_id, chat_id=chat_id, ad_structure=ad_structure)
```

And import the new function:

```python
from vak_bot.pipeline.orchestrator import (
    # ... existing imports ...
    run_multi_scene_ad_pipeline,
)
```

---

## Summary: Priority Order of Changes

### Must-Do First (biggest impact on quality):

| Priority | File | Change | Impact |
|----------|------|--------|--------|
| 1 | `brand_config.json` | Add product_rules, negative_prompts, voice, video_presets | All pipeline stages get consistent brand context |
| 2 | `gemini_styler.py` | Inject negative prompts, fix variant count to 3 | Images stop deviating from brand |
| 3 | `orchestrator.py` | Raise SSIM thresholds from 0.6 → 0.75 | Catches saree alterations that currently slip through |
| 4 | `veo_generator.py` | Add negative_prompt to API, cinema vocabulary in presets, 2 variations | Videos become brand-specific, not generic |
| 5 | `veo_video_prompt.txt` | Add brand identity section, product descriptors | Veo gets Vâk context instead of generic luxury |

### Do Next (30-60 second ads):

| Priority | File | Change | Impact |
|----------|------|--------|--------|
| 6 | `veo_generator.py` | Add `generate_multi_scene_ad()` method | Enables 30s/60s ad creation |
| 7 | `video_stitcher.py` | Add `stitch_scenes()` with FFmpeg transitions | Assembles multi-scene ads |
| 8 | `orchestrator.py` | Add `run_multi_scene_ad_pipeline()` | Full pipeline for long ads |
| 9 | `tasks.py` | Add `generate_ad_task` | Telegram trigger for ad generation |

### Polish (brand guardian, better captions):

| Priority | File | Change | Impact |
|----------|------|--------|--------|
| 10 | `caption_writer.py` | Inject brand voice from config | Captions match brand DNA consistently |
| 11 | `analysis_prompt.txt` | Add Vâk color palette and prop context | Analyzer suggests brand-appropriate styling |
| 12 | `saree_validator.py` | Add LPIPS secondary check | Catches perceptual changes SSIM misses |
| 13 | `gemini_styling_prompt.txt` | Add brand identity section | Gemini knows who it's working for |