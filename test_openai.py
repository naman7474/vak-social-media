"""Quick test for OpenAI Responses API with vision."""
import json
import os
from dotenv import load_dotenv
import httpx

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini-2025-08-07")

if not API_KEY:
    print("ERROR: Set OPENAI_API_KEY in .env")
    exit(1)

# Use a public test image
test_image_url = "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400"

payload = {
    "model": MODEL,
    "input": [
        {"role": "system", "content": "You are an image analysis assistant. Return JSON only."},
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe this image in 2 sentences. Return as JSON with key 'description'."},
                {"type": "input_image", "image_url": test_image_url},
            ],
        },
    ],
    "text": {
        "format": {"type": "json_object"},
    },
}

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

print(f"Testing OpenAI Responses API with model: {MODEL}")
print("Sending request...")

resp = httpx.post("https://api.openai.com/v1/responses", headers=headers, json=payload, timeout=60.0)
print(f"Status: {resp.status_code}")

if resp.status_code != 200:
    print(f"Error: {resp.text[:500]}")
else:
    data = resp.json()
    print(f"Response keys: {list(data.keys())}")
    # Extract text from the output
    output = data.get("output", [])
    for item in output:
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    print(f"Result: {content['text'][:300]}")
