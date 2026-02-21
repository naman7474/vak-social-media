"""Quick local test for Bright Data API."""
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("DATABRIGHT_API_KEY", "")
if not API_TOKEN:
    print("ERROR: Set DATABRIGHT_API_KEY in .env")
    exit(1)

url = "https://www.instagram.com/p/DU-C4wjgXwZ/"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
}

data = json.dumps({
    "input": [{"url": url}],
})

print(f"Calling Bright Data with URL: {url}")
print("Waiting for response (may take 10-30s)...")

response = requests.post(
    "https://api.brightdata.com/datasets/v3/scrape?dataset_id=gd_lk5ns7kz21pck8jpis&notify=false&include_errors=true&format=json",
    headers=headers,
    data=data,
)

print(f"\nStatus: {response.status_code}")
print(f"Content-Type: {response.headers.get('content-type')}")
print(f"\nRaw response (first 1000 chars):\n{response.text[:1000]}")

try:
    result = response.json()
    print(f"\nType: {type(result)}")
    if isinstance(result, list):
        print(f"Length: {len(result)}")
        if result:
            print(f"\nFirst item keys: {list(result[0].keys())}")
    elif isinstance(result, dict):
        print(f"Keys: {list(result.keys())}")
    print(f"\nFull JSON:\n{json.dumps(result, indent=2)[:3000]}")
except Exception as e:
    print(f"Failed to parse JSON: {e}")
