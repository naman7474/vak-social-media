"""
Seed the products table from Products.csv (Shopify export).

Assigns product codes VAK-001 through VAK-007 and inserts all product photos.
Idempotent: skips products whose code already exists.

Usage:
    python seed_products.py
"""
from __future__ import annotations

import csv
import re
import sys
from html import unescape

from vak_bot.db.session import SessionLocal
from vak_bot.db.models import Product, ProductPhoto

CSV_PATH = "Products.csv"

# Strip HTML tags for cleaner text
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(raw: str) -> str:
    return unescape(_TAG_RE.sub("", raw or "")).strip()


def _extract_fabric(metafield: str) -> str | None:
    """Extract fabric name from Shopify metafield like 'shopify--fabric.jimmy-choo'."""
    if not metafield:
        return None
    parts = metafield.split(".")
    if len(parts) >= 2:
        return parts[-1].replace("-", " ").title()
    return metafield


def _extract_colors(metafield: str) -> str | None:
    """Extract colors from Shopify metafield like 'shopify--color-pattern.pink, shopify--color-pattern.floral'."""
    if not metafield:
        return None
    colors = []
    for item in metafield.split(","):
        item = item.strip()
        parts = item.split(".")
        if len(parts) >= 2:
            colors.append(parts[-1].replace("-", " ").title())
    return ", ".join(colors) if colors else None


def _extract_motif(tagline: str, title: str) -> str | None:
    """Derive motif from tagline or title."""
    # Try to extract flower/motif names from the title
    lower = title.lower()
    motifs = []
    for word in ["tulip", "flora", "chameli", "chrysanthemum", "rose", "hibiscus"]:
        if word in lower:
            motifs.append(word.title())
    return ", ".join(motifs) if motifs else None


def _estimate_days(making_text: str) -> int | None:
    """Extract days_to_make from 'the making' description."""
    if not making_text:
        return None
    match = re.search(r"(\w+)\s+days?", making_text.lower())
    if match:
        word_to_num = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        word = match.group(1)
        if word.isdigit():
            return int(word)
        return word_to_num.get(word)
    return None


def seed():
    # Parse CSV — group rows by Shopify product ID
    products_data: dict[str, dict] = {}  # keyed by shopify ID
    product_order: list[str] = []  # preserve order

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            shopify_id = row["ID"]
            is_top_row = row.get("Top Row", "").strip().lower() == "true"
            image_url = row.get("Image Src", "").strip()

            if shopify_id not in products_data:
                products_data[shopify_id] = {
                    "title": row["Title"],
                    "handle": row["Handle"],
                    "url": row.get("URL", ""),
                    "body_html": row.get("Body HTML", ""),
                    "fabric_metafield": row.get("Metafield: shopify.fabric [list.metaobject_reference]", ""),
                    "color_metafield": row.get("Metafield: shopify.color-pattern [list.metaobject_reference]", ""),
                    "tagline": row.get("Metafield: custom.tagline [single_line_text_field]", ""),
                    "making": row.get("Metafield: custom.the_making [multi_line_text_field]", ""),
                    "product_detail_ref": row.get("Metafield: custom.product_details [metaobject_reference]", ""),
                    "images": [],
                }
                product_order.append(shopify_id)

            if image_url:
                products_data[shopify_id]["images"].append({
                    "url": image_url,
                    "position": int(row.get("Image Position", 1)),
                    "is_primary": is_top_row or int(row.get("Image Position", 1)) == 1,
                })

    # Assign product codes VAK-001, VAK-002, etc.
    code_map: dict[str, str] = {}
    for idx, shopify_id in enumerate(product_order, start=1):
        code_map[shopify_id] = f"VAK-{idx:03d}"

    # Insert into DB
    with SessionLocal() as session:
        inserted = 0
        skipped = 0

        for shopify_id in product_order:
            data = products_data[shopify_id]
            code = code_map[shopify_id]

            existing = session.query(Product).filter(Product.product_code == code).first()
            if existing:
                print(f"  SKIP {code} ({data['title']}) — already exists")
                skipped += 1
                continue

            fabric_raw = data.get("product_detail_ref", "") or data.get("fabric_metafield", "")
            fabric = None
            if fabric_raw:
                # e.g. "product_details.pure-silk-organza" → "Pure Silk Organza"
                parts = fabric_raw.split(".")
                fabric = parts[-1].replace("-", " ").title() if len(parts) >= 2 else fabric_raw

            product = Product(
                product_code=code,
                product_name=data["title"],
                product_type="Saree",
                fabric=fabric,
                colors=_extract_colors(data["color_metafield"]),
                motif=_extract_motif(data["tagline"], data["title"]),
                artisan_name=None,  # Not in CSV
                days_to_make=_estimate_days(data["making"]),
                technique="Hand-painted",
                price=None,  # Not in CSV export
                shopify_url=data["url"],
                status="active",
            )
            session.add(product)
            session.flush()  # get product.id

            # Add photos
            for img in sorted(data["images"], key=lambda x: x["position"]):
                session.add(ProductPhoto(
                    product_id=product.id,
                    photo_url=img["url"],
                    photo_type="product",
                    is_primary=img["is_primary"],
                ))

            print(f"  ✅ {code} — {data['title']} ({len(data['images'])} photos, fabric={fabric}, days={product.days_to_make})")
            inserted += 1

        session.commit()
        print(f"\nDone! Inserted: {inserted}, Skipped: {skipped}")

    # Print summary
    print("\n📋 Product Code Reference:")
    print("-" * 60)
    for shopify_id in product_order:
        data = products_data[shopify_id]
        code = code_map[shopify_id]
        print(f"  {code}  →  {data['title']}")


if __name__ == "__main__":
    seed()
