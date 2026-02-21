# Vâk Instagram Automation Bot — Developer Specification

**Version:** 1.1
**Date:** February 21, 2026
**Project:** Telegram → Instagram automation pipeline for @vakstudios.in

---

## 1. What This Is

An automated pipeline that lets non-technical team members (wife + brother) create on-brand Instagram posts for Vâk — a hand-painted saree brand — by simply pasting an inspiration link into a Telegram bot. The system analyzes the reference post, styles a real saree photo to match the aesthetic, writes an on-brand caption, and posts to Instagram after approval.

**Critical constraint:** Vâk sells hand-painted, one-of-one sarees. The saree in every post must be a real product photo. AI is used for styling, backgrounds, layout, and captions — never to generate fake saree images.

---

## 2. Users

| User | Role | Tech Comfort |
|------|------|--------------|
| Wife | Primary operator — discovers inspiration, selects sarees, approves posts | Non-technical. Uses Telegram daily. |
| Brother | Secondary operator — same workflow | Non-technical. Uses Telegram daily. |
| Founder (you) | Setup, maintenance, system prompt updates | Technical. Manages backend. |

---

## 3. High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        TELEGRAM BOT                             │
│                                                                 │
│  User sends:                                                    │
│  1. Instagram/Pinterest inspiration link                        │
│  2. Real saree photo(s) to feature                              │
│  3. (Optional) Product name or code                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STEP 1: DOWNLOAD                              │
│                    Tool: DataBright API                          │
│                                                                 │
│  - Download the reference post image(s)                         │
│  - Extract caption text if available                            │
│  - Extract hashtags from original post                          │
│  - Store: reference_image, reference_caption, source_url        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STEP 2: ANALYZE                               │
│                    Tool: ChatGPT API (GPT-4o)                   │
│                                                                 │
│  Input: reference_image + reference_caption                     │
│  Output: style_brief (JSON)                                     │
│                                                                 │
│  Extracts:                                                      │
│  - Layout type (flat-lay, draped, on-model, close-up, grid)     │
│  - Color mood (warm/cool/neutral + dominant colors)             │
│  - Composition (product placement, text position, whitespace)   │
│  - Background style (solid, textured, lifestyle scene, props)   │
│  - Text overlay style (font mood, placement, size relative)     │
│  - Content format (single image, carousel, before-after)        │
│  - Lighting (natural, studio, golden hour, moody)               │
│  - Overall vibe in 2-3 words                                    │
│                                                                 │
│  Does NOT generate any image or image prompt.                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                STEP 3 + 4: STYLE IMAGE + TEXT OVERLAY            │
│                Tool: Gemini Nano Banana Pro API                  │
│                Model: gemini-3-pro-image-preview                 │
│                                                                 │
│  Input:                                                         │
│  - real_saree_photo(s)                                          │
│  - reference_image (as visual context)                          │
│  - style_brief (from Step 2)                                    │
│  - overlay_text (if reference had text)                         │
│                                                                 │
│  What it does:                                                  │
│  - Takes the real saree photo as the primary subject            │
│  - Uses the reference image as style/mood guidance              │
│  - Generates new background matching the reference aesthetic    │
│  - Applies color grading, lighting, and composition             │
│  - Adds props/staging elements appropriate for Indian context   │
│  - Renders text overlay directly in image if needed             │
│    (Nano Banana Pro has best-in-class text rendering)           │
│  - Maintains exact saree appearance (no AI alteration)          │
│                                                                 │
│  Generates 2-3 variations for user to pick from.                │
│  Output resolution: 4:5 aspect ratio for Instagram (1080x1350) │
│  or 1:1 (1080x1080) based on reference format.                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STEP 5: WRITE CAPTION                         │
│                    Tool: Claude API (Sonnet 4.5)                 │
│                                                                 │
│  Input: styled_image + style_brief + product_info               │
│  Output: instagram_caption + hashtags + alt_text                │
│                                                                 │
│  Uses Vâk brand voice system prompt (see Section 7).            │
│  Generates caption, 20-25 hashtags, and alt text.               │
│  If text overlay is needed, also generates overlay text.        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STEP 6: APPROVAL                              │
│                    Tool: Telegram Bot                            │
│                                                                 │
│  Bot sends back to user:                                        │
│  - 2-3 styled image options (numbered)                          │
│  - The caption                                                  │
│  - Suggested posting time                                       │
│                                                                 │
│  User actions:                                                  │
│  - "1" / "2" / "3" → select image variant                      │
│  - "edit caption" → triggers caption re-edit flow               │
│  - "approve" → moves to posting                                 │
│  - "redo" → reruns from Step 3 with new variations              │
│  - "cancel" → kills the job                                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STEP 7: POST                                  │
│                    Tool: Meta Graph API (Instagram)              │
│                                                                 │
│  - Uploads selected image to Instagram via Meta API             │
│  - Applies caption + hashtags                                   │
│  - Sets alt text for accessibility                              │
│  - Logs: post URL, timestamp, product featured, reference used  │
│                                                                 │
│  Optional: Also post to Facebook page simultaneously.           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Telegram Bot — User Interface Specification

### 4.1 Starting a New Post

User sends a message to the bot with:

```
[Instagram/Pinterest link]
+ attached saree photo(s)
```

Or for products already in the database:

```
[Instagram/Pinterest link]
VAK-042
```

Where `VAK-042` is a product code that maps to photos in the product database.

**Bot response:**

```
Got it! Analyzing the reference post and styling your saree.
This usually takes 2-3 minutes. I'll send you options when ready.

Reference: [thumbnail of downloaded post]
Saree: [thumbnail of uploaded saree photo]
```

### 4.2 Approval Interface

Bot sends:

```
Here are your options for this post:

[Image 1] [Image 2] [Image 3]

Caption:
"[generated caption text]"

Hashtags:
#handpaintedsaree #vakstudios ... (20-25 tags)

Suggested time: Today 6:30 PM (peak engagement)

Reply with:
• 1, 2, or 3 → pick an image
• "edit caption" → change the caption
• "redo" → generate new options
• "cancel" → discard
```

### 4.3 Caption Edit Flow

User sends: `edit caption`

Bot responds:

```
What would you like to change?
• "shorter" → make it more concise
• "more festive" → add festive tone
• "add price" → include ₹ price
• Or just type what you want changed
```

### 4.4 Final Confirmation

After image selection:

```
Ready to post:

[Selected image]
[Final caption]

Post now? Or schedule for 6:30 PM?

Reply:
• "post now"
• "schedule" → posts at suggested time
• "schedule [time]" → e.g. "schedule 8pm tomorrow"
```

### 4.5 Multiple Sarees (Carousel)

User sends multiple saree photos → bot creates a carousel post.

```
[Instagram link]
[Photo 1] [Photo 2] [Photo 3]
```

Bot generates styled versions of each maintaining consistent background/mood across the set.

### 4.6 Quick Commands

| Command | What it does |
|---------|-------------|
| `/start` | Welcome message + instructions |
| `/help` | Shows available commands |
| `/recent` | Shows last 5 posts made via bot |
| `/queue` | Shows scheduled but not-yet-posted items |
| `/cancel [id]` | Cancel a scheduled post |
| `/products` | Lists product codes from database |
| `/stats` | Basic engagement stats for recent posts |

---

## 5. Tech Stack & API Details

### 5.1 Core Infrastructure

| Component | Tool | Purpose |
|-----------|------|---------|
| Bot interface | Telegram Bot API | User interaction |
| Backend server | Node.js or Python (FastAPI) | Orchestration |
| Task queue | Redis + Bull (Node) or Celery (Python) | Async job processing |
| Database | PostgreSQL or Supabase | Product catalog, post logs, user sessions |
| File storage | AWS S3 or Cloudflare R2 | Store images (reference, product, styled output) |

### 5.2 External APIs

| API | Used In | Purpose | Estimated Cost |
|-----|---------|---------|----------------|
| **DataBright** | Step 1 | Download Instagram/Pinterest posts | Check current pricing |
| **OpenAI GPT-4o** | Step 2 | Analyze reference image, extract style brief | ~$0.01-0.03 per analysis |
| **Gemini Nano Banana Pro** | Step 3+4 | Style product photos + text overlay using reference as guide | ~$0.05-0.10 per generation |
| **Claude API (Sonnet 4.5)** | Step 5 | Caption writing in Vâk brand voice | ~$0.01-0.02 per caption |
| **Meta Graph API** | Step 7 | Post to Instagram + Facebook | Free (requires app review) |

### 5.3 DataBright Setup (Step 1)

DataBright is used to download public Instagram/Pinterest post content.

**Input:** Post URL
**Output needed:**
- High-resolution image(s) from the post
- Caption text
- Hashtags
- Account name (for internal reference only — never repost attribution)

**Error handling:**
- Private account → tell user "Can't access this post, it might be private"
- Stories/Reels → tell user "This bot works with image posts only. For reels, use the video bot (coming soon)"
- Pinterest → extract the image, ignore the description (Pinterest captions are usually SEO spam)

### 5.4 Meta Graph API Setup (Step 7)

**Requirements:**
- Facebook Business Page connected to Instagram Professional Account
- Meta App with `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` permissions
- Long-lived page access token (refresh every 60 days — build auto-refresh)

**Posting flow:**
1. Upload image to a public URL (S3/R2)
2. Create media container: `POST /{ig-user-id}/media` with `image_url`, `caption`, `alt_text`
3. Publish: `POST /{ig-user-id}/media_publish` with container ID
4. For carousels: create individual containers first, then carousel container

**Rate limits:** 25 posts per 24-hour period (more than enough for Vâk)

---

## 6. Product Database Schema

Every saree should be stored with its details so the bot can pull info when writing captions.

```sql
CREATE TABLE products (
    id              SERIAL PRIMARY KEY,
    product_code    VARCHAR(20) UNIQUE NOT NULL,    -- e.g., "VAK-042"
    product_name    VARCHAR(200),                   -- e.g., "Serene Saree in Indigo Lotus"
    product_type    VARCHAR(50),                    -- saree, kurta set, dupatta
    fabric          VARCHAR(100),                   -- e.g., "Pure mulberry silk"
    colors          TEXT,                            -- primary colors, comma-separated
    motif           VARCHAR(200),                   -- e.g., "lotus", "abstract", "paisley"
    artisan_name    VARCHAR(100),
    days_to_make    INTEGER,
    technique       VARCHAR(200),                   -- e.g., "layered brushwork"
    price           DECIMAL(10,2),
    shopify_url     VARCHAR(500),
    status          VARCHAR(20) DEFAULT 'active',   -- active, sold, archived
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE product_photos (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER REFERENCES products(id),
    photo_url       VARCHAR(500) NOT NULL,          -- S3/R2 URL
    photo_type      VARCHAR(30),                    -- hero, detail, drape, flat-lay, model
    is_primary      BOOLEAN DEFAULT FALSE,
    uploaded_at     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE posts (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER REFERENCES products(id),
    reference_url   VARCHAR(500),                   -- inspiration post link
    reference_image VARCHAR(500),                   -- downloaded reference image URL
    style_brief     JSONB,                          -- output from ChatGPT analysis
    styled_image    VARCHAR(500),                   -- final styled image URL
    caption         TEXT,
    hashtags        TEXT,
    alt_text        TEXT,
    instagram_post_id VARCHAR(100),
    instagram_url   VARCHAR(500),
    posted_at       TIMESTAMP,
    posted_by       VARCHAR(50),                    -- telegram user who approved
    status          VARCHAR(20) DEFAULT 'draft',    -- draft, approved, scheduled, posted, failed
    created_at      TIMESTAMP DEFAULT NOW()
);
```

---

## 7. System Prompts

### 7.1 ChatGPT — Reference Analysis Prompt (Step 2)

```
You are a visual design analyst for an Indian hand-painted saree brand called Vâk.

You will receive an Instagram or Pinterest post image. Your job is to analyze
the visual style and extract a structured brief that will be used to style
a REAL product photo in a similar aesthetic.

You are NOT generating any images. You are only describing what you see so
another tool can recreate the style with a different product.

Analyze and return a JSON object with these fields:

{
  "layout_type": "flat-lay | draped | on-model | close-up | grid | lifestyle",
  "composition": {
    "product_placement": "center | left-third | right-third | diagonal | scattered",
    "whitespace": "minimal | moderate | generous",
    "text_area": "top | bottom | left | right | overlay-center | none",
    "aspect_ratio": "1:1 | 4:5 | 9:16"
  },
  "color_mood": {
    "temperature": "warm | cool | neutral",
    "dominant_colors": ["#hex1", "#hex2", "#hex3"],
    "palette_name": "earthy | jewel-toned | pastel | monochrome | vibrant | muted"
  },
  "background": {
    "type": "solid-color | gradient | textured | lifestyle-scene | props | natural",
    "description": "Brief description, e.g., 'marble surface with dried flowers and gold accessories'",
    "suggested_bg_for_saree": "A more specific suggestion adapted for a saree, e.g., 'warm beige textured surface with marigold petals and brass diya'"
  },
  "lighting": "natural-soft | natural-harsh | studio | golden-hour | moody-dark | backlit",
  "text_overlay": {
    "has_text": true/false,
    "text_style": "serif | sans-serif | handwritten | none",
    "text_position": "top-left | center | bottom | none",
    "text_purpose": "product-name | price | tagline | quote | none"
  },
  "content_format": "single-image | carousel | before-after | collage",
  "vibe_words": ["elegant", "festive", "minimal"],
  "adaptation_notes": "Any specific notes on how to adapt this style for a hand-painted saree. E.g., 'The reference uses a flat-lay with jewelry props — for a saree, drape it partially and add traditional Indian accessories like bangles or a small brass bowl.'"
}

Important rules:
- Be specific about colors. Use hex codes.
- Think about how a SAREE would look in this style, not the original product.
- The "suggested_bg_for_saree" should always feel Indian and appropriate for handloom/artisan products.
- If the reference has a model, note the pose and framing but understand we will use product-only shots, not AI models.
- Always suggest props that are realistic for an Indian context (brass items, flowers like marigold/jasmine, fabric textures, traditional accessories).
```

### 7.2 Gemini Nano Banana Pro — Image Styling + Text Overlay (Step 3+4)

**Model:** `gemini-3-pro-image-preview`
**API:** Google Gemini API (or Vertex AI for production)

Nano Banana Pro accepts both text prompts and reference images as input. This is the core advantage — you send the real saree photo + the reference post image, and it generates a styled version that borrows the aesthetic of the reference while preserving the actual saree.

**Key capabilities used:**
- Image-to-image editing with reference context (supports up to 14 reference images)
- Accurate text rendering directly in the image (best-in-class for overlays)
- Aspect ratio control: `"4:5"` for Instagram feed, `"1:1"` for square, `"9:16"` for stories
- Resolution up to 4K
- Style transfer from reference without altering the primary subject

**API call structure (Python):**

```python
from google import genai
from google.genai import types
from PIL import Image
import io

client = genai.Client()

def style_saree_image(saree_photo_path, reference_image_path, style_brief, overlay_text=None):
    """
    Generate a styled product image using Gemini Nano Banana Pro.
    
    Args:
        saree_photo_path: Path to the real saree product photo
        reference_image_path: Path to the downloaded reference/inspiration image
        style_brief: JSON dict from ChatGPT analysis (Step 2)
        overlay_text: Optional text to render on the image
    """
    
    # Load images
    saree_image = Image.open(saree_photo_path)
    reference_image = Image.open(reference_image_path)
    
    # Build the prompt from style_brief
    prompt = build_styling_prompt(style_brief, overlay_text)
    
    response = client.models.generate_content(
        model="gemini-3-pro-image-preview",
        contents=[
            reference_image,   # Reference for style/mood
            saree_image,        # The actual product to feature
            prompt
        ],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            generation_config={
                "aspectRatio": style_brief["composition"]["aspect_ratio"].replace(":", "_"),
                "resolution": "2K"
            }
        )
    )
    
    # Extract generated image
    for part in response.parts:
        if part.inline_data is not None:
            return part.as_image()
    
    return None
```

**Prompt construction function:**

```python
def build_styling_prompt(style_brief, overlay_text=None):
    """
    Converts the ChatGPT style_brief JSON into a Gemini image prompt.
    """
    
    base_prompt = f"""
I'm providing two images:
1. REFERENCE IMAGE (first image): This is a style reference. Match its overall 
   aesthetic, mood, composition, and background style. DO NOT copy its product.
2. SAREE PHOTO (second image): This is the actual product. This saree MUST appear 
   exactly as it is — do not alter, repaint, reshape, or modify the saree in any way.
   Preserve every hand-painted detail, brushstroke, color, and texture exactly.

YOUR TASK: Place the saree from the second image into a new styled composition 
that matches the visual aesthetic of the reference image.

STYLE INSTRUCTIONS:
- Layout: {style_brief['layout_type']}
- Product placement: {style_brief['composition']['product_placement']}
- Background: {style_brief['background']['suggested_bg_for_saree']}
- Lighting: {style_brief['lighting']}
- Color mood: {style_brief['color_mood']['palette_name']}, {style_brief['color_mood']['temperature']} tones
- Dominant colors in background: {', '.join(style_brief['color_mood']['dominant_colors'])}
- Whitespace: {style_brief['composition']['whitespace']}
- Vibe: {', '.join(style_brief['vibe_words'])}

CRITICAL RULES:
- The saree fabric, painting, colors, and details must be IDENTICAL to the input photo.
- Only change what SURROUNDS the saree (background, props, lighting, staging).
- Keep the image clean and professional — suitable for an Instagram post.
- Use props that feel authentically Indian: brass items, marigolds, jasmine, 
  traditional accessories, silk fabric accents, diyas, etc.
- No watermarks, no logos, no artificial-looking elements.
"""
    
    if overlay_text:
        text_brief = style_brief.get('text_overlay', {})
        base_prompt += f"""

TEXT OVERLAY:
- Render this text ON the image: "{overlay_text}"
- Font style: {text_brief.get('text_style', 'serif')}
- Position: {text_brief.get('text_position', 'bottom')}
- Use the Vâk brand colors: deep charcoal (#2C2C2C) or warm cream (#F5F0E8) 
  depending on background contrast.
- Text must be crisp, legible, and elegantly placed.
- Do not obscure the saree with text.
"""
    
    return base_prompt
```

**Generating multiple variations:**

Run the API call 3 times with slight prompt variations to give the user options:

```python
VARIATION_MODIFIERS = [
    "Make the composition feel minimal and elegant with generous whitespace.",
    "Add a warm, intimate feeling with close-up framing and rich textures.",
    "Go for a bold, editorial look with dramatic lighting and strong contrast."
]

async def generate_variations(saree_photo, reference_image, style_brief, overlay_text=None):
    variations = []
    for modifier in VARIATION_MODIFIERS:
        modified_brief = style_brief.copy()
        modified_brief['variation_note'] = modifier
        result = await style_saree_image(
            saree_photo, reference_image, modified_brief, overlay_text
        )
        if result:
            variations.append(result)
    return variations
```

**Saree preservation check (post-generation):**

After generating, validate that the saree wasn't altered. Use a simple perceptual comparison:

```python
from skimage.metrics import structural_similarity as ssim
import numpy as np

def verify_saree_preserved(original_saree, generated_image, threshold=0.6):
    """
    Compare the saree region in the generated image against the original.
    Returns True if saree appears preserved, False if it may have been altered.
    
    Note: This is a safety net, not a perfect check. Flag for manual review
    if it fails rather than auto-rejecting.
    """
    # Convert to grayscale for comparison
    orig_gray = np.array(original_saree.convert('L'))
    gen_gray = np.array(generated_image.convert('L'))
    
    # Resize to match if needed
    # ... (resize logic)
    
    score = ssim(orig_gray, gen_gray)
    return score >= threshold
```

### 7.3 Claude — Caption Writing Prompt (Step 5)

```
You are the social media voice of Vâk (pronounced vaahk), a hand-painted
clothing brand for Indian women who dress with intention.

BRAND BASICS:
- Vâk is Sanskrit for "voice." Tagline: "Your clothes speak before you do."
- Every piece is hand-painted by artisans over days, not minutes.
- Each piece is one of one — unique and unrepeatable.
- Three pillars: VOICE (your clothes say something), HAND (made by hands),
  ONE (each piece is one of a kind).

TARGET AUDIENCE:
Indian women, 28-45, in metros/tier-1 cities or NRIs. They appreciate craft,
are tired of seeing the same prints everywhere. They buy for occasions but
also for themselves. They understand handmade value.

VOICE RULES:
- Warm, confident, personal, simple.
- Talk directly using "you."
- Describe how it feels to wear the piece.
- Mention the time and craft that went into making it.
- Be friendly, like talking to a friend.
- Keep Indian occasions and styling in mind.

DO NOT:
- Use fancy fashion words ("exquisite," "timeless elegance," "must-have,"
  "ethereal," "resplendent").
- Write long complicated sentences.
- Sound stiff or formal.
- Use ALL CAPS or too many exclamation marks.
- Lecture about sustainability.
- Over-explain Indian culture (she already knows).
- Use emojis excessively (max 2-3 per caption, at the end if at all).

CAPTION STRUCTURE:
1. Hook line (1 sentence that makes her stop scrolling)
2. 1-2 sentences about the piece — what makes it special, how it was made
3. 1 sentence about how/where to wear it
4. Soft CTA (never aggressive sales language)
5. Line break, then hashtags

HASHTAG RULES:
- 20-25 hashtags
- Mix of: brand (#vakstudios #handpaintedsaree #vakclothing),
  product (#silksaree #handloomsaree), occasion (#diwalifashion #weddingguest),
  discovery (#indianfashion #artisanmade #oneofone #sareelovers),
  and niche (#handpaintedfashion #craftedwithlove #slowfashionindia)
- Never use generic tags like #fashion #style #beautiful

ALT TEXT:
Write a 1-2 sentence description of the image for accessibility.
Mention: the product type, colors, visible design elements, and staging.

---

You will receive:
1. The styled product image
2. The style brief (JSON) from the reference analysis
3. Product details (name, fabric, technique, artisan, days to make, price)

Write:
1. Instagram caption (following structure above)
2. 20-25 hashtags
3. Alt text
4. If text overlay is needed: the overlay text (max 6 words, impactful)

Return as JSON:
{
  "caption": "...",
  "hashtags": "#tag1 #tag2 ...",
  "alt_text": "...",
  "overlay_text": "..." or null
}
```

---

## 8. Error Handling

| Error | What happens | User sees |
|-------|-------------|-----------|
| DataBright fails to download | Retry once. If fails again, notify user. | "Couldn't download that post. Try a different link or send me a screenshot instead." |
| Private/deleted post | Detect and inform. | "That post seems to be private or deleted. Can you try another one?" |
| Reel/Video link | Detect media type. | "This looks like a reel/video. This bot handles image posts — the video bot is coming soon!" |
| ChatGPT analysis fails | Retry with fallback prompt. | "Taking a bit longer than usual. Hang tight..." |
| Gemini styling fails | Retry with simplified prompt. If persistent, try without reference image (just style_brief text). | "Styling is taking longer. Trying a different approach..." |
| Gemini alters the saree | SSIM check fails. Flag for manual review. | "The styled image didn't look right. Let me try again with a different approach..." |
| Claude caption fails | Retry. If persistent, use a simpler fallback prompt. | "Almost there, just polishing the caption..." |
| Meta API post fails | Log error. Retry once. | "Posting failed. I've saved your post — want me to try again or you can post manually?" |
| Rate limit (Meta) | Queue for later. | "Instagram is rate-limiting us. I've scheduled this for [next available time]." |
| User sends no saree photo | Ask for it. | "Got the inspiration! Now send me the saree photo(s) you want to feature." |
| Unsupported link (not IG/Pinterest) | Inform user. | "I work best with Instagram and Pinterest links. Can you send one of those?" |

---

## 9. Config & Environment Variables

```env
# Telegram
TELEGRAM_BOT_TOKEN=xxx
ALLOWED_USER_IDS=123456,789012          # Only wife + brother can use the bot

# DataBright
DATABRIGHT_API_KEY=xxx

# OpenAI
OPENAI_API_KEY=xxx
OPENAI_MODEL=gpt-4o

# Gemini (Nano Banana Pro)
GOOGLE_API_KEY=xxx
GEMINI_IMAGE_MODEL=gemini-3-pro-image-preview

# Anthropic (Claude)
ANTHROPIC_API_KEY=xxx
CLAUDE_MODEL=claude-sonnet-4-5-20250514

# Meta / Instagram
META_APP_ID=xxx
META_APP_SECRET=xxx
META_PAGE_ACCESS_TOKEN=xxx
INSTAGRAM_BUSINESS_ACCOUNT_ID=xxx

# Storage
S3_BUCKET=vak-bot-images
S3_REGION=ap-south-1
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx

# Database
DATABASE_URL=postgresql://user:pass@host:5432/vak_bot

# Brand Config
BRAND_NAME=Vâk
BRAND_INSTAGRAM_HANDLE=@vakstudios
BRAND_WEBSITE=https://vakstudios.in
DEFAULT_POSTING_TIMEZONE=Asia/Kolkata
```

---

## 10. Security & Access Control

- **Whitelist Telegram users.** Only specific user IDs (wife, brother, you) can interact with the bot. All others get: "This bot is private. Visit vakstudios.in to shop."
- **Never expose API keys** in Telegram messages or logs.
- **Store tokens securely** — use environment variables, never hardcode.
- **Meta token refresh** — build an auto-refresh mechanism for the 60-day page access token. Alert you on Telegram 7 days before expiry.
- **Rate limiting** — max 10 posts per day per user to prevent accidental spam.
- **Image retention** — auto-delete reference images after 30 days (you don't own them). Keep styled outputs and product photos indefinitely.

---

## 11. Future Additions (Phase 2)

These are not part of the initial build but should be architected for:

### 11.1 Video/Reels Bot
- Same Telegram interface
- Uses Veo 3.1 or Runway for video generation from product photos
- Adds motion to styled product images (fabric flowing, zoom-ins)
- Caption + trending audio suggestion

### 11.2 Story Auto-Poster
- Auto-generate Instagram Stories from new posts
- "New drop" template, "Behind the scenes" template
- Scheduled story sequences

### 11.3 Analytics Dashboard
- Track which reference styles perform best
- Which sarees get most engagement
- Best posting times for Vâk's audience
- Weekly summary sent to Telegram

### 11.4 Shopify Integration
- Auto-pull new products into the product database
- When a saree is posted, auto-link to Shopify product page
- Mark products as "sold" when inventory hits 0

### 11.5 Pinterest Auto-Post
- Same styled images, different caption format
- Post to Pinterest boards automatically

---

## 12. Testing Checklist Before Launch

- [ ] Bot responds to `/start` and `/help`
- [ ] Bot rejects unauthorized users
- [ ] Instagram public post link downloads correctly
- [ ] Pinterest link downloads correctly
- [ ] Private post shows appropriate error
- [ ] Reel/video link shows appropriate error
- [ ] ChatGPT analysis returns valid JSON
- [ ] Gemini Nano Banana Pro generates styled images with real saree preserved
- [ ] Gemini handles text overlay when reference has text
- [ ] Gemini produces correct aspect ratio (4:5 for feed, 1:1 for square)
- [ ] SSIM saree preservation check passes on generated images
- [ ] Claude generates caption in correct brand voice
- [ ] All 3 image variants display in Telegram
- [ ] Image selection (1/2/3) works
- [ ] "edit caption" flow works
- [ ] "redo" regenerates from Step 3
- [ ] "cancel" clears the job
- [ ] "post now" publishes to Instagram successfully
- [ ] "schedule" queues post for correct time
- [ ] Carousel post with multiple sarees works
- [ ] Product code lookup from database works
- [ ] Posted Instagram URL is logged in database
- [ ] Error messages are friendly, not technical
- [ ] Full flow completes in under 3 minutes

---

## 13. Estimated Costs Per Post

| Component | Cost |
|-----------|------|
| DataBright (1 download) | ~₹1-2 |
| ChatGPT 4o (1 analysis) | ~₹2-3 |
| Gemini Nano Banana Pro (3 variations) | ~₹12-25 (~$0.05-0.10 × 3 calls) |
| Claude Sonnet 4.5 (1 caption) | ~₹1-2 |
| S3 storage | Negligible |
| **Total per post** | **~₹16-32** |

At 5 posts per week = ~₹350-650/month in API costs. No monthly subscriptions needed — everything is pay-per-use.

---

## 14. Folder Structure (Suggested)

```
vak-bot/
├── bot/
│   ├── telegram_handler.py      # Telegram bot logic
│   ├── commands.py              # /start, /help, /recent, etc.
│   └── approval_flow.py         # Image selection, caption edit, posting
├── pipeline/
│   ├── downloader.py            # DataBright integration
│   ├── analyzer.py              # ChatGPT reference analysis
│   ├── gemini_styler.py         # Gemini Nano Banana Pro — styling + text overlay
│   ├── saree_validator.py       # SSIM check to verify saree wasn't altered
│   ├── caption_writer.py        # Claude integration
│   └── poster.py                # Meta Graph API posting
├── database/
│   ├── models.py                # SQLAlchemy/ORM models
│   ├── migrations/              # Database migrations
│   └── seed_products.py         # Initial product data load
├── prompts/
│   ├── analysis_prompt.txt      # ChatGPT system prompt
│   ├── gemini_styling_prompt.txt # Gemini Nano Banana Pro prompt template
│   ├── caption_prompt.txt       # Claude system prompt
│   └── brand_config.json        # Colors, fonts, hashtag sets, variation modifiers
├── config/
│   ├── settings.py              # Environment variable loading
│   └── .env                     # API keys (gitignored)
├── storage/
│   └── s3_client.py             # Image upload/download
├── workers/
│   └── task_queue.py            # Async job processing
├── tests/
│   ├── test_download.py
│   ├── test_analysis.py
│   ├── test_styling.py
│   ├── test_caption.py
│   └── test_posting.py
├── requirements.txt
├── docker-compose.yml
└── README.md
```

---

## 15. One Important Note for the Developer

The entire value of Vâk is that every saree is hand-painted and one of a kind. If at any point the pipeline makes the saree look AI-generated, edited, or different from the actual product — the system has failed. The saree photo must always be the real, unaltered product. AI only touches the background, staging, layout, and text. Never the saree itself.

Build a check: after Gemini Nano Banana Pro styling, run a quick SSIM (structural similarity) comparison between the saree region in the original photo and the styled output. If similarity drops below a threshold, flag it for manual review instead of sending it to the user. The SSIM validation code is included in Section 7.2 above.

---

*Document prepared for developer handoff. For brand voice questions, refer to the Vâk Product Copy Generator system prompt or ask the founder.*