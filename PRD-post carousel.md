# Vâk Instagram Automation Bot — Video/Reels Addendum

**Version:** 2.0  
**Date:** February 22, 2026  
**Extends:** PRD v1.1 (Image Post Pipeline)  
**New Capability:** Instagram Reels via Veo 3.1

---

## 1. What This Adds

A parallel pipeline inside the same Telegram bot that generates short-form video (Instagram Reels) from product photos + inspiration references. The user experience is identical to the image post flow — paste a link, send a saree photo, approve, post. The bot **auto-detects** whether the reference is an image post or a Reel from the URL pattern and routes to the correct pipeline automatically. No extra commands needed.

**Same critical constraint applies:** The saree must always be a real product photo. Veo 3.1 uses the styled product image (from Gemini) as the starting frame, then adds motion. The saree is never AI-generated from scratch.

---

## 2. Why Video Matters for Vâk

Instagram's algorithm heavily favors Reels — they get 2-3x the reach of static posts. For a brand selling one-of-one hand-painted pieces, video does something photos can't: it shows the fabric moving, the sheer organza catching light, the brushwork detail as the camera pans. This is what converts browsers into buyers.

---

## 3. High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        TELEGRAM BOT                             │
│                                                                 │
│  User sends (same as image pipeline — no new commands):         │
│  1. Instagram/Pinterest link (image OR Reel — auto-detected)    │
│  2. Real saree photo(s) to feature                              │
│  3. (Optional) Product name or code                             │
│                                                                 │
│  The bot detects the media type from the URL and routes         │
│  automatically — no /reel command required.                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                 STEP 0: DETECT & ROUTE (NEW)                    │
│                 Tool: URL pattern matching + DataBright          │
│                                                                 │
│  URL Detection:                                                 │
│  - instagram.com/reel/ or /reels/ → VIDEO pipeline              │
│  - instagram.com/p/             → IMAGE pipeline                │
│  - pinterest.com/pin/           → Check media type after        │
│                                   download (video or image)     │
│                                                                 │
│  Override options:                                               │
│  - User sends image link + "make it a reel" → VIDEO pipeline   │
│  - User sends reel link + "just the photo" → IMAGE pipeline    │
│  - During image approval, user can say "reel this" → re-route  │
│                                                                 │
│  Fallback: If media type is ambiguous after download,           │
│  check MIME type of downloaded file (video/* → Reel).           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STEP 1: DOWNLOAD                              │
│                    Tool: DataBright API                          │
│                                                                 │
│  - Download the reference post media (image or video)           │
│  - Confirm media type from downloaded file MIME type            │
│    (reinforces Step 0 URL detection)                            │
│  - If Reel: extract video file + thumbnail for analysis         │
│  - Extract caption text, hashtags                               │
│  - Store: reference_media, reference_caption, source_url,       │
│           detected_media_type ("image" | "reel")                │
│                                                                 │
│  If download reveals a video when URL suggested image           │
│  (or vice versa), trust the downloaded file's MIME type.        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STEP 2: ANALYZE                               │
│                    Tool: ChatGPT API (GPT-4o)                   │
│                                                                 │
│  Input: reference_media + reference_caption                     │
│  Output: video_style_brief (JSON) — extended version            │
│                                                                 │
│  Everything from the image pipeline PLUS:                       │
│  - Camera motion (slow pan, zoom-in, static, orbit, tilt)      │
│  - Motion type (fabric flow, model walk, reveal, flat-to-drape) │
│  - Pacing (slow/dreamy, medium/editorial, fast/energetic)       │
│  - Audio mood (ambient, classical, upbeat, silence)             │
│  - Transition style (if reference reel has cuts)                │
│  - Duration recommendation (4s, 6s, or 8s)                     │
│                                                                 │
│  If reference is a video, analyze 3-4 keyframes for style.     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 3: STYLE STARTING FRAME                       │
│              Tool: Gemini Nano Banana Pro API                   │
│              (Same as image pipeline — Step 3+4)                │
│                                                                 │
│  Input: real_saree_photo + reference_image + style_brief        │
│  Output: styled_start_frame (1080x1920 for 9:16 Reels)         │
│                                                                 │
│  This is the SAME Gemini styling step from the image pipeline.  │
│  The only difference:                                           │
│  - Aspect ratio is 9:16 (portrait) for Reels instead of 4:5    │
│  - Generates 1 styled image (not 3 variations — Veo is slower) │
│  - Composition optimized for video (room for camera movement)   │
│                                                                 │
│  The styled image becomes the FIRST FRAME of the Veo video.    │
│  SSIM saree preservation check still runs here.                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 4: GENERATE VIDEO                             │
│              Tool: Veo 3.1 API (Google Gemini API)              │
│              Model: veo-3.1-generate-preview                    │
│                                                                 │
│  Input:                                                         │
│  - styled_start_frame (from Step 3)                             │
│  - video_prompt (built from video_style_brief)                  │
│  - (Optional) reference_images for style guidance (up to 3)     │
│                                                                 │
│  Config:                                                        │
│  - Aspect ratio: 9:16 (portrait for Reels)                     │
│  - Resolution: 1080p                                            │
│  - Duration: 8 seconds (default) or as recommended              │
│                                                                 │
│  Capabilities used:                                             │
│  - Image-to-video: Start frame → animated video                 │
│  - Reference images: Up to 3 images for style consistency       │
│  - Native audio: Ambient sound generated automatically          │
│  - Scene extension: Chain 8s clips for longer Reels             │
│                                                                 │
│  Generates 2 video variations (different motion styles).        │
│  Video generation is ASYNC — takes 2-5 minutes.                 │
│                                                                 │
│  Output: 2 MP4 files (8s each, 1080p, 9:16)                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 5: WRITE CAPTION + REEL METADATA              │
│              Tool: Claude API (Sonnet 4.5)                      │
│              (Extended from image pipeline)                      │
│                                                                 │
│  Input: styled_frame + video_style_brief + product_info         │
│  Output: caption + hashtags + alt_text + audio_suggestion       │
│                                                                 │
│  Same brand voice as image captions, PLUS:                      │
│  - Shorter hook (Reels need first-line hooks for autoplay)      │
│  - Audio suggestion (trending audio category or ambient)        │
│  - Cover frame timestamp recommendation                         │
│  - Reel-optimized hashtags (more discovery-focused)             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 6: APPROVAL                                   │
│              Tool: Telegram Bot                                 │
│                                                                 │
│  Bot sends back to user:                                        │
│  - 2 video previews (as video messages in Telegram)             │
│  - The start frame as a still image                             │
│  - The caption                                                  │
│  - Suggested posting time                                       │
│                                                                 │
│  User actions:                                                  │
│  - "1" / "2" → select video variant                             │
│  - "extend" → generate 8s more (scene extension)               │
│  - "edit caption" → triggers caption re-edit                    │
│  - "approve" → moves to posting                                 │
│  - "redo" → reruns from Step 3 with new styled frame            │
│  - "cancel" → kills the job                                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 7: POST AS REEL                               │
│              Tool: Meta Graph API (Instagram Reels)              │
│                                                                 │
│  - Upload video to S3 (public URL required)                     │
│  - Create Reel container:                                       │
│    POST /{ig-user-id}/media                                     │
│      ?media_type=REELS                                          │
│      &video_url={s3-video-url}                                  │
│      &caption={caption}                                         │
│      &share_to_feed=true                                        │
│      &thumb_offset={milliseconds}                               │
│  - Poll container status until FINISHED                         │
│  - Publish: POST /{ig-user-id}/media_publish                   │
│  - Log: post URL, timestamp, product, reference used            │
│                                                                 │
│  Video requirements for Instagram Reels:                        │
│  - Format: MP4 (H.264 codec)                                   │
│  - Max duration: 90 seconds                                     │
│  - Aspect ratio: 9:16                                           │
│  - Min resolution: 540x960                                      │
│  - Max file size: 1 GB                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Telegram Bot — Video UI (Auto-Detected)

### 4.1 Auto-Detection — User Sees No Difference

The user sends the **exact same message** as they would for an image post:

```
[Instagram link]
+ attached saree photo(s)
```

Or with product code:

```
[Instagram link]
VAK-042
```

The bot detects the URL type and responds accordingly.

**If Reel link detected:**

```
🎬 That's a Reel! I'll create a video for this one.

This takes a bit longer than images — usually 4-6 minutes
because video generation needs time.

I'll style the photo first, then animate it. Sit tight.

Reference: [thumbnail from reel]
Saree: [thumbnail of uploaded photo]
```

**If image link detected:** Same as current image pipeline (no change).

### 4.2 URL Detection Logic

```python
import re
from urllib.parse import urlparse

def detect_media_type(url: str) -> str:
    """
    Detect whether a URL points to an image post or a Reel/video.
    
    Returns: "reel" | "image" | "unknown"
    """
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    # Instagram
    if "instagram.com" in parsed.netloc:
        if "/reel/" in path or "/reels/" in path:
            return "reel"
        elif "/p/" in path:
            return "image"
        elif "/tv/" in path:  # IGTV (legacy, treat as video)
            return "reel"
    
    # Pinterest — can't tell from URL alone, need to check after download
    if "pinterest.com" in parsed.netloc or "pin.it" in parsed.netloc:
        return "unknown"  # Resolve after DataBright download
    
    return "unknown"


def confirm_media_type_from_download(file_path: str, url_hint: str) -> str:
    """
    Confirm media type from the downloaded file's MIME type.
    Falls back to URL hint if MIME is ambiguous.
    """
    import mimetypes
    mime, _ = mimetypes.guess_type(file_path)
    
    if mime and mime.startswith("video/"):
        return "reel"
    elif mime and mime.startswith("image/"):
        # But user might still want a Reel from an image reference
        return "image"
    
    # Fallback to URL detection
    return detect_media_type(url_hint)
```

### 4.3 Override: User Wants a Reel from an Image Reference

If the reference is an image post but the user wants video output, they can say so naturally at any point:

**During initial send:**
```
User: [instagram.com/p/... image link]
      [saree photo]
      make it a reel
```

Bot detects "make it a reel" / "reel" / "video" / "reels" in the message and routes to video pipeline.

**During image approval (post-generation):**
```
Bot: Here are your options for this post:
     [Image 1] [Image 2] [Image 3]
     ...

User: reel this

Bot: Nice — I'll turn option 1 into a Reel.
     Using it as the starting frame for video. ~3-4 minutes...
```

This re-routes mid-flow: takes the already-styled image as the Veo start frame, skipping Step 3 entirely.

**Keyword triggers for video override:**
- "make it a reel"
- "reel this"
- "video"
- "make a reel"
- "reel instead"
- "want a video"

### 4.4 Override: User Wants a Photo from a Reel Reference

If the reference is a Reel but the user only wants a styled image:

```
User: [instagram.com/reel/... reel link]
      [saree photo]
      just the photo

Bot: Got it — I'll use the Reel as style reference but make an image post.
     Analyzing the reference now...
```

**Keyword triggers for image override:**
- "just the photo"
- "image only"
- "no video"
- "photo post"
- "static"

### 4.5 Video Type Selection (Auto + Optional Override)

The bot auto-picks the video type based on the ChatGPT analysis (Step 2). But during approval, the user can request a different style:

```
Bot: Here are your Reel options:
     [Video 1 — Fabric Flow] [Video 2 — Slow Pan]
     ...

User: redo close-up

Bot: Got it — regenerating with a close-up zoom style. ~4 minutes...
```

Available video types (same as before):
- `fabric-flow` → Gentle breeze, pallu flowing, fabric catching light
- `close-up` → Slow zoom into brushwork detail, then pull back
- `lifestyle` → Lifestyle scene — someone walking, fabric in motion
- `reveal` → Flat fabric that unfurls into a draped saree

### 4.6 Video Approval Interface

Bot sends:

```
Here are your Reel options:

[Video 1 — Fabric Flow] [Video 2 — Slow Pan]

Start frame:
[Still image preview]

Caption:
"[generated caption]"

Hashtags:
#handpaintedsaree #vakstudios ... (20-25 tags)

Audio: Native ambient (fabric rustle + soft music)
Suggested time: Today 7:00 PM (peak Reels engagement)

Reply with:
• 1 or 2 → pick a video
• "extend" → add 8 more seconds to your pick
• "edit caption" → change the caption
• "redo" → regenerate with a new starting frame
• "redo close-up" → regenerate with a specific motion style
• "cancel" → discard
```

### 4.7 Scene Extension Flow

User sends: `extend 1`

Bot responds:

```
Extending video 1 by 8 seconds. This will continue
from where the first clip ends. ~3 minutes...
```

Then sends the extended 16-second video for approval.

### 4.8 Updated Quick Commands

| Command | What it does |
|---------|-------------|
| `/start` | Welcome message + instructions (unchanged) |
| `/help` | Shows available commands — updated to mention auto-detection |
| `/recent` | Shows last 5 posts — now includes Reels with 🎬 icon |
| `/queue` | Shows scheduled items — includes pending video jobs |
| `/cancel [id]` | Cancel a scheduled post or video generation job |
| `/products` | Lists product codes (unchanged) |
| `/stats` | Engagement stats — now includes Reel views and reach |
| `/reelqueue` | Shows pending video generation jobs specifically |

**Note:** `/reel` is NOT a required command. It exists only as an optional shortcut if the user wants to force video output from an image reference:

```
/reel [image link]
VAK-042
```

This is the same as sending the link + "make it a reel".

---

## 5. Veo 3.1 API Integration

### 5.1 Core: Image-to-Video Generation

```python
import time
from google import genai
from google.genai import types
from PIL import Image

client = genai.Client()

def generate_reel_from_styled_image(
    styled_frame_path: str,
    video_prompt: str,
    reference_images: list = None,
    aspect_ratio: str = "9:16",
    resolution: str = "1080p"
):
    """
    Generate a video using Veo 3.1 from a styled product image.
    
    Args:
        styled_frame_path: Path to the styled saree image (from Gemini Step 3)
        video_prompt: Motion/animation prompt built from video_style_brief
        reference_images: Optional list of up to 3 reference image paths
        aspect_ratio: "9:16" for Reels (portrait), "16:9" for landscape
        resolution: "720p", "1080p", or "4k"
    
    Returns:
        Path to generated MP4 file
    """
    
    # Load the styled start frame
    start_frame = Image.open(styled_frame_path)
    
    # Build config
    config = types.GenerateVideosConfig(
        aspect_ratio=aspect_ratio,
        resolution=resolution,
    )
    
    # Add reference images if provided (for style consistency)
    if reference_images:
        config.reference_images = [
            Image.open(ref_path) for ref_path in reference_images[:3]
        ]
    
    # Generate video (async operation)
    operation = client.models.generate_videos(
        model="veo-3.1-generate-preview",
        prompt=video_prompt,
        image=start_frame,
        config=config,
    )
    
    # Poll until done (typically 2-5 minutes)
    while not operation.done:
        time.sleep(10)
        operation = client.operations.get(operation)
    
    # Save the generated video
    generated_video = operation.response.generated_videos[0]
    client.files.download(file=generated_video.video)
    
    output_path = f"/tmp/veo_output_{int(time.time())}.mp4"
    generated_video.video.save(output_path)
    
    return output_path
```

### 5.2 Scene Extension (for Longer Reels)

```python
def extend_reel(original_video_path: str, continuation_prompt: str):
    """
    Extend a previously generated Veo video by 8 more seconds.
    Uses the last frame of the original as the starting point.
    
    Note: Scene extension is limited to 720p resolution.
    """
    
    # Load the original video as a File object
    video_file = client.files.upload(file=original_video_path)
    
    operation = client.models.generate_videos(
        model="veo-3.1-generate-preview",
        prompt=continuation_prompt,
        video=video_file,  # Veo continues from the last second
    )
    
    while not operation.done:
        time.sleep(10)
        operation = client.operations.get(operation)
    
    generated_video = operation.response.generated_videos[0]
    client.files.download(file=generated_video.video)
    
    output_path = f"/tmp/veo_extended_{int(time.time())}.mp4"
    generated_video.video.save(output_path)
    
    return output_path
```

### 5.3 Video Prompt Builder

```python
# Video type presets for Vâk sarees
VIDEO_TYPE_PROMPTS = {
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

# Variation modifiers (run 2 generations with different motion styles)
VIDEO_VARIATION_MODIFIERS = [
    "Use slow, gentle camera movement. Dreamy and meditative pacing.",
    "Use subtle dynamic movement. Slightly more energy, editorial pacing.",
]


def build_video_prompt(video_style_brief: dict, video_type: str = None) -> str:
    """
    Build a Veo prompt from the ChatGPT video_style_brief.
    
    Args:
        video_style_brief: JSON from Step 2 analysis
        video_type: One of fabric-flow, close-up, lifestyle, reveal.
                    If None, picks best match from the brief.
    """
    
    # Auto-detect video type from brief if not specified
    if not video_type:
        layout = video_style_brief.get("layout_type", "draped")
        if layout == "close-up":
            video_type = "close-up"
        elif layout == "on-model" or layout == "lifestyle":
            video_type = "lifestyle"
        elif layout == "flat-lay":
            video_type = "reveal"
        else:
            video_type = "fabric-flow"  # default
    
    base_motion = VIDEO_TYPE_PROMPTS[video_type]
    
    # Layer in style brief details
    brief = video_style_brief
    
    prompt = f"""
{base_motion}

STYLE CONTEXT:
- Color mood: {brief['color_mood']['palette_name']}, {brief['color_mood']['temperature']} tones
- Background: {brief['background']['suggested_bg_for_saree']}
- Lighting: {brief['lighting']}
- Vibe: {', '.join(brief['vibe_words'])}
- Camera motion: {brief.get('camera_motion', 'slow pan')}
- Pacing: {brief.get('pacing', 'slow and dreamy')}

CRITICAL RULES:
- The saree fabric, hand-painted details, and colors must remain EXACTLY as shown
  in the starting image. Do not alter, repaint, or modify the saree.
- Keep the video clean and elegant — luxury fashion brand aesthetic.
- No watermarks, no logos, no text overlays.
- Indian context — any props should feel authentic (brass, flowers, silk).
- Cinematic quality, editorial fashion film look.
- Portrait orientation (9:16) for Instagram Reels.
"""
    
    return prompt.strip()


async def generate_reel_variations(
    styled_frame_path: str,
    video_style_brief: dict,
    video_type: str = None,
    reference_image_path: str = None,
):
    """Generate 2 video variations with different motion styles."""
    
    base_prompt = build_video_prompt(video_style_brief, video_type)
    variations = []
    
    ref_images = [reference_image_path] if reference_image_path else None
    
    for modifier in VIDEO_VARIATION_MODIFIERS:
        full_prompt = f"{base_prompt}\n\nMOTION STYLE: {modifier}"
        
        result = generate_reel_from_styled_image(
            styled_frame_path=styled_frame_path,
            video_prompt=full_prompt,
            reference_images=ref_images,
            aspect_ratio="9:16",
            resolution="1080p",
        )
        
        if result:
            variations.append(result)
    
    return variations
```

---

## 6. Updated ChatGPT Analysis Prompt (Step 2 — Video Extension)

Add these fields to the existing `style_brief` JSON when the `/reel` command is used:

```
You are also analyzing this reference for VIDEO generation.
In addition to the standard style_brief fields, add:

{
  ... (all existing fields from image pipeline) ...
  
  "video_analysis": {
    "camera_motion": "slow-pan | zoom-in | zoom-out | orbit | tilt-up | tilt-down | static | tracking",
    "motion_type": "fabric-flow | model-walk | reveal | product-rotate | parallax | morph",
    "motion_elements": "What should be moving? e.g., 'fabric flowing in breeze', 'camera slowly zooming into brushwork detail', 'pallu lifting and falling'",
    "pacing": "slow-dreamy | medium-editorial | fast-energetic",
    "audio_mood": "ambient-nature | soft-classical | modern-minimal | upbeat | silence",
    "transition_style": "none | fade | cut | zoom-through",
    "recommended_duration": "4 | 6 | 8",
    "recommended_video_type": "fabric-flow | close-up | lifestyle | reveal",
    "video_adaptation_notes": "How to adapt this reference style into a saree video. E.g., 'The reference uses a slow zoom on jewelry — for a saree, zoom into the painted motif detail then pull back to show full drape.'"
  }
}

IMPORTANT for video analysis:
- For saree videos, fabric movement is always the hero. Suggest motion
  that showcases the hand-painting: gentle breeze, slow unfurling, light play.
- If the reference is a Reel/video, describe the camera movement and pacing
  you observe. If it's a static image, suggest video movement that would
  complement the mood.
- Always suggest SLOW or MEDIUM pacing for luxury handmade products.
  Fast pacing feels cheap — Vâk is the opposite.
```

---

## 7. Updated Claude Caption Prompt (Step 5 — Reels)

```
When writing captions for REELS (video posts), adjust your approach:

REEL CAPTION STRUCTURE:
1. Hook line — MUST grab attention in first line (shown before "...more")
   This is MORE important for Reels because people see it during autoplay.
   Make it curiosity-driven or emotion-driven.
2. 1-2 sentences about the piece
3. Soft CTA — "Save this for your next [occasion]" works well for Reels
4. Line break, then hashtags

REEL-SPECIFIC RULES:
- Shorter overall (150-200 words max, not 200-300)
- First line is everything — it shows during autoplay. Make it count.
- Add 2-3 Reels-discovery hashtags: #reelsinstagram #fashionreels
  #sareedraping #handpaintedfashion
- Suggest a cover frame description (for the Reels thumbnail)
- If the video has native audio from Veo, caption should acknowledge
  the sensory experience: "Turn your sound on" or similar

GOOD REEL HOOKS:
- "Three days of painting. Eight seconds of magic."
- "This is what hand-painted looks like in motion."
- "No two pieces will ever move the same way."
- "The brushwork you can't see in photos."

BAD REEL HOOKS:
- "Check out our latest saree!" (generic)
- "New arrival alert! 🚨" (aggressive)
- "This exquisite piece..." (too formal)

Return as JSON:
{
  "caption": "...",
  "hashtags": "#tag1 #tag2 ...",
  "alt_text": "Video showing a hand-painted [color] [fabric] saree with [motif] in motion, fabric flowing gently...",
  "cover_frame_description": "Best frame for thumbnail — e.g., 'the moment the pallu catches light at 3 seconds'",
  "thumb_offset_ms": 3000
}
```

---

## 8. Meta Graph API — Posting Reels

### 8.1 Reel Posting Flow

```python
import requests
import time

def post_reel_to_instagram(
    video_s3_url: str,
    caption: str,
    thumb_offset_ms: int = 0,
    share_to_feed: bool = True,
):
    """
    Post a video as an Instagram Reel via Meta Graph API.
    
    Args:
        video_s3_url: Public URL of the MP4 video on S3
        caption: Full caption with hashtags
        thumb_offset_ms: Millisecond offset for cover thumbnail
        share_to_feed: If True, Reel appears in both Feed and Reels tab
    
    Returns:
        dict with instagram_post_id and permalink
    """
    
    IG_USER_ID = os.environ["INSTAGRAM_BUSINESS_ACCOUNT_ID"]
    ACCESS_TOKEN = os.environ["META_PAGE_ACCESS_TOKEN"]
    API_VERSION = "v21.0"
    BASE_URL = f"https://graph.facebook.com/{API_VERSION}"
    
    # Step 1: Create Reel media container
    container_response = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media",
        params={
            "media_type": "REELS",
            "video_url": video_s3_url,
            "caption": caption,
            "share_to_feed": str(share_to_feed).lower(),
            "thumb_offset": thumb_offset_ms,
            "access_token": ACCESS_TOKEN,
        }
    )
    
    container_id = container_response.json()["id"]
    
    # Step 2: Poll container status until video is processed
    max_retries = 30
    for _ in range(max_retries):
        status_response = requests.get(
            f"{BASE_URL}/{container_id}",
            params={
                "fields": "status_code",
                "access_token": ACCESS_TOKEN,
            }
        )
        status = status_response.json().get("status_code")
        
        if status == "FINISHED":
            break
        elif status == "ERROR":
            raise Exception("Instagram video processing failed")
        
        time.sleep(10)  # Video processing takes time
    
    # Step 3: Publish the Reel
    publish_response = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media_publish",
        params={
            "creation_id": container_id,
            "access_token": ACCESS_TOKEN,
        }
    )
    
    post_id = publish_response.json()["id"]
    
    # Step 4: Get permalink
    permalink_response = requests.get(
        f"{BASE_URL}/{post_id}",
        params={
            "fields": "permalink",
            "access_token": ACCESS_TOKEN,
        }
    )
    
    return {
        "instagram_post_id": post_id,
        "permalink": permalink_response.json().get("permalink"),
    }
```

### 8.2 Video Requirements for Instagram Reels

| Parameter | Requirement |
|-----------|------------|
| Format | MP4 (H.264) — Veo 3.1 outputs this natively |
| Audio codec | AAC — Veo 3.1's native audio is compatible |
| Aspect ratio | 9:16 (portrait) |
| Min resolution | 540 x 960 |
| Recommended | 1080 x 1920 (what we generate) |
| Max duration | 90 seconds |
| Our duration | 8 seconds (extendable to 16s, 24s, etc.) |
| Max file size | 1 GB |
| Our typical size | ~15-30 MB for 8s at 1080p |

---

## 9. Database Schema Extension

```sql
-- Extend the posts table for video content
ALTER TABLE posts ADD COLUMN media_type VARCHAR(10) DEFAULT 'image';  
-- 'image' or 'reel'

ALTER TABLE posts ADD COLUMN video_url VARCHAR(500);  
-- S3 URL of the final video

ALTER TABLE posts ADD COLUMN video_style_brief JSONB;  
-- Extended brief with video_analysis fields

ALTER TABLE posts ADD COLUMN video_type VARCHAR(20);  
-- fabric-flow, close-up, lifestyle, reveal

ALTER TABLE posts ADD COLUMN start_frame_url VARCHAR(500);  
-- The styled image used as Veo's starting frame

ALTER TABLE posts ADD COLUMN video_duration INTEGER;  
-- Duration in seconds (8, 16, 24, etc.)

ALTER TABLE posts ADD COLUMN thumb_offset_ms INTEGER DEFAULT 0;
-- Cover frame offset for Instagram

-- Track video generation jobs (they take longer than images)
CREATE TABLE video_jobs (
    id              SERIAL PRIMARY KEY,
    post_id         INTEGER REFERENCES posts(id),
    veo_operation_id VARCHAR(200),    -- Veo's async operation identifier
    status          VARCHAR(20) DEFAULT 'pending',  
    -- pending, generating, done, failed, extended
    variation_number INTEGER,         -- 1 or 2
    video_url       VARCHAR(500),     -- S3 URL once complete
    generation_time_seconds INTEGER,  -- How long Veo took
    prompt_used     TEXT,             -- Full prompt sent to Veo
    created_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP
);
```

---

## 10. Updated Folder Structure

```
vak-bot/
├── bot/
│   ├── telegram_handler.py
│   ├── commands.py              # Updated: /help mentions auto-detection
│   └── approval_flow.py         # Updated: video approval + "reel this" mid-flow
├── pipeline/
│   ├── route_detector.py        # NEW: URL pattern detection + MIME type check
│   ├── downloader.py            # Updated: handle video references, confirm media type
│   ├── analyzer.py              # Updated: video_analysis fields when routed to video
│   ├── gemini_styler.py         # Updated: 9:16 aspect when routed to video
│   ├── saree_validator.py
│   ├── veo_generator.py         # NEW: Veo 3.1 video generation
│   ├── video_stitcher.py        # NEW: Concatenate extended clips
│   ├── caption_writer.py        # Updated: Reel caption mode when media_type=reel
│   └── poster.py                # Updated: REELS media_type posting
├── prompts/
│   ├── analysis_prompt.txt      # Updated with video_analysis section
│   ├── analysis_prompt_video.txt # NEW: Video-specific analysis additions
│   ├── gemini_styling_prompt.txt
│   ├── veo_video_prompt.txt     # NEW: Veo prompt templates
│   ├── caption_prompt.txt       # Updated with Reel caption rules
│   └── brand_config.json        # Updated with video type presets
├── ... (rest unchanged)
```

---

## 11. Error Handling (Video-Specific)

| Error | What happens | User sees |
|-------|-------------|-----------|
| URL type ambiguous | Download first, then check MIME type. If still unclear, ask user. | "I can't tell if this is a photo or video post. Want me to make an image post or a Reel?" |
| Reel download fails (private/deleted) | Same as image pipeline error handling. | "That Reel seems to be private or deleted. Can you try another one?" |
| User says "reel this" but no styled image exists yet | Start from Step 3 with 9:16 aspect ratio. | "Got it — switching to Reel mode. Give me 4-5 minutes..." |
| Veo generation fails | Retry once with simplified prompt. If fails again, offer image-only post. | "Video generation hit a snag. Want me to try again, or should I make this an image post instead?" |
| Veo takes too long (>10 min) | Keep polling but warn user. | "Still generating — Veo is taking longer than usual. I'll send it as soon as it's ready." |
| Generated video is low quality | Run a quick frame check. Flag if blurry. | "The video didn't come out great. Let me try with a different motion style..." |
| Saree looks different in video | Compare first frame to styled image. | "The video altered the saree too much. Regenerating with tighter constraints..." |
| Instagram Reel upload fails | Retry once. Check video format. | "Instagram couldn't process the video. I've saved it — want me to try again?" |
| Video too large for IG | Compress with ffmpeg before upload. | (Handled silently — user never sees this) |
| Scene extension fails | Inform user, offer the original 8s clip. | "Couldn't extend the video. Want to post the 8-second version instead?" |

---

## 12. Estimated Costs Per Reel

| Component | Cost |
|-----------|------|
| DataBright (1 download) | ~₹1-2 |
| ChatGPT 4o (1 video analysis) | ~₹3-4 |
| Gemini Nano Banana Pro (1 start frame, 9:16) | ~₹5-10 |
| Veo 3.1 (2 video variations × 8s × 1080p) | ~₹40-80 (~$0.50 per 1080p video × 2) |
| Claude Sonnet 4.5 (1 reel caption) | ~₹1-2 |
| S3 storage (video files) | ~₹1-2 |
| **Total per Reel** | **~₹50-100** |

At 3 Reels per week = ~₹600-1200/month. More expensive than image posts but Reels get 2-3x the reach, so the ROI is significantly better.

---

## 13. Config & Environment Variables (New Additions)

```env
# Veo 3.1 (uses the same Google API key as Gemini)
GOOGLE_API_KEY=xxx                          # Same key works for both Gemini + Veo
VEO_MODEL=veo-3.1-generate-preview
VEO_DEFAULT_RESOLUTION=1080p
VEO_DEFAULT_ASPECT_RATIO=9:16
VEO_POLL_INTERVAL_SECONDS=10
VEO_MAX_POLL_DURATION_SECONDS=600           # 10 minute timeout

# Video processing
FFMPEG_PATH=/usr/bin/ffmpeg                 # For video compression/concatenation
MAX_REEL_DURATION_SECONDS=90                # Instagram max
DEFAULT_REEL_DURATION_SECONDS=8             # Single clip
```

---

## 14. Testing Checklist (Video-Specific)

**Auto-Detection:**
- [ ] Instagram Reel URL (`/reel/`) auto-routes to video pipeline
- [ ] Instagram image URL (`/p/`) auto-routes to image pipeline
- [ ] Pinterest video pin auto-detected after download (MIME check)
- [ ] Pinterest image pin auto-detected after download
- [ ] "make it a reel" with image URL overrides to video pipeline
- [ ] "just the photo" with Reel URL overrides to image pipeline
- [ ] "reel this" during image approval re-routes mid-flow
- [ ] `/reel` shortcut command works as optional override
- [ ] Unknown URLs fall back gracefully with user prompt

**Video Generation:**
- [ ] ChatGPT analysis returns valid video_analysis JSON
- [ ] Gemini generates 9:16 styled start frame
- [ ] SSIM check passes on start frame
- [ ] Veo 3.1 generates video from styled start frame
- [ ] Veo uses reference image for style guidance
- [ ] Both video variations are different (not duplicates)
- [ ] Video is 8 seconds, 1080p, 9:16
- [ ] Native audio is present in generated video

**Telegram UI:**
- [ ] Videos display correctly in Telegram
- [ ] Video selection (1/2) works
- [ ] "extend" generates continuation clip
- [ ] Extended clips are visually continuous
- [ ] "redo close-up" regenerates with specified motion style
- [ ] Claude generates Reel-optimized caption with hook

**Posting:**
- [ ] Reel uploads to Instagram successfully via Graph API
- [ ] Reel appears in both Feed and Reels tab
- [ ] Cover thumbnail uses correct frame offset
- [ ] Caption and hashtags display correctly

**General:**
- [ ] "redo" regenerates from Step 3 (new start frame)
- [ ] "cancel" clears all video jobs
- [ ] Error handling works for Veo failures
- [ ] Full Reel flow completes in under 8 minutes
- [ ] Video files are cleaned up from /tmp after posting

---

## 15. Timeline & Phasing

### Phase 1: Basic Reels with Auto-Detection (Week 1-2)
- URL pattern detection (`route_detector.py`)
- MIME type confirmation after DataBright download
- Natural language override parsing ("make it a reel", "just the photo")
- Veo 3.1 integration with image-to-video
- Single 8-second clips
- 2 variations per request
- Reel posting via Meta Graph API
- Telegram approval flow (same UX as image, auto-routed)
- Update original PRD's Reel error message (was: "video bot coming soon"
  → now: auto-routes to video pipeline)

### Phase 2: Extended Reels (Week 3)
- Scene extension (chain multiple 8s clips)
- Video concatenation with ffmpeg
- Longer Reels up to 24 seconds

### Phase 3: Polish (Week 4)
- Audio selection (mute Veo audio + suggest trending audio)
- Cover frame optimization
- A/B testing which video types perform best
- Reels analytics tracking in the dashboard

---

## 16. Important Note for the Developer

The same rule from the image pipeline applies here, but it's even more critical for video: **the saree must look real**. Veo 3.1 may try to "improve" or stylize the fabric in motion. If the hand-painted details blur, morph, or change color during the video, that clip is unusable.

The safest approach: always use the Gemini-styled image as the starting frame (which has already passed SSIM validation), and keep the Veo prompt focused on camera/environmental motion rather than changing the product itself. Words like "the saree remains perfectly still while the camera moves" or "gentle breeze on the pallu edge only" help constrain Veo from modifying the core product.

Build a first-frame comparison check: extract frame 1 of the generated video and compare it to the styled start image. If SSIM drops below 0.7, flag it.

---

*This addendum extends PRD v1.1. For brand voice, product database, and base pipeline details, refer to the original document.*