import os
import base64
from dotenv import load_dotenv

load_dotenv()

from vak_bot.pipeline.gemini_styler import GeminiStyler
from vak_bot.schemas import StyleBrief, CompositionSpec, TextOverlaySpec, BackgroundSpec, ColorMoodSpec

styler = GeminiStyler()

# Dummy bytes
saree_bytes = b"dummy_saree"
ref_bytes = b"dummy_ref"

# Style brief dummy
brief = StyleBrief(
    layout_type="flat-lay",
    composition=CompositionSpec(product_placement="center", whitespace="minimal", aspect_ratio="1:1"),
    background=BackgroundSpec(suggested_bg_for_saree="plain", description="plain"),
    lighting="ambient",
    color_mood=ColorMoodSpec(palette_name="warm", temperature="warm", dominant_colors=["red"]),
    vibe_words=["warm"],
    text_overlay=TextOverlaySpec(has_text=False),
    reference_has_model=False,
)

try:
    print("Testing SDK generation...")
    # This will generate an image and print the debug logs from _extract_image_bytes_from_sdk_response
    bytes_out = styler._request_generation_sdk(
        prompt="Create an image of a red cat",
        ref_bytes=ref_bytes,
        ref_mime="image/jpeg",
        saree_bytes=saree_bytes,
        saree_mime="image/jpeg",
        style_brief=brief,
        variant=1,
        position=1
    )
    if bytes_out:
        print(f"Extraction successful: {len(bytes_out)} bytes")
    else:
        print("Extraction returned None")
except Exception as e:
    import traceback
    traceback.print_exc()
