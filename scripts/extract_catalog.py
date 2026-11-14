"""
Extract the full Okhtein catalog from the public Shopify feed.

Outputs (in data/):
  products.json    - every product, cleaned, with description / dimensions / details
  products.csv     - same data as a spreadsheet (one row per product)
  categories.json  - product types with counts + Shopify collections and which products are in each

Run:  python scripts/extract_catalog.py
Uses only the Python standard library.
"""

import csv
import html
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

STORE = "https://eg.okhtein.com"
OUT = Path(__file__).resolve().parent.parent / "data"

# Shopify tags used for internal marketing; not useful for the customer.
INTERNAL_TAGS = {
    "scale-up",
    "meta ads",
    "jewelry meta ads",
    "acc meta ads",
    "facebookcommerce",
    "store_only",
    "drafted",
    "duplicate_plp",
    "sync",
    "refresh",
    "farfetch",
    "x jewelry",
    "non_jewelry",
    "paris shoot",
}

# Some products have no product_type; guess it from the title (checked in order).
TITLE_TO_CATEGORY = [
    ("minaudiere", "Minaudiere"),
    ("bucket", "Bucket Bag"),
    ("backpack", "Backpack"),
    ("clutch", "Clutch"),
    ("cardholder", "Cardholder"),
    ("wallet", "Wallet"),
    ("sleeve", "Sleeve"),
    ("charm", "Charm"),
    ("shades", "Eyewear"),
    ("sunglass", "Eyewear"),
    ("shopper", "Top Handle Bag"),
    ("duo", "Top Handle Bag"),
    ("tote", "Tote Bag"),
    ("earring", "Earring"),
    ("ring", "Ring"),
    ("bracelet", "Bracelet"),
    ("necklace", "Necklace"),
    ("belt", "Belt"),
]


def get_json(url, retries=6):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (catalog extract)"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == retries - 1:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 2**attempt * 3  # 3, 6, 12, 24s...
            print(f"  rate limited, waiting {wait}s")
            time.sleep(wait)


def fetch_all(path, key):
    """Shopify paginates at 250 items per page."""
    items, page = [], 1
    while True:
        batch = get_json(f"{STORE}{path}?limit=250&page={page}")[key]
        if not batch:
            return items
        items += batch
        page += 1


def html_to_text(raw):
    text = re.sub(r"<(br|/p|/li|/div)[^>]*>", "\n", raw or "", flags=re.I)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def clean_product(p):
    # Okhtein writes the body as: description <!-- split --> dimensions <!-- split --> details
    parts = [html_to_text(x) for x in re.split(r"<!--\s*split\s*-->", p.get("body_html") or "")]
    parts = [x for x in parts if x]
    description = parts[0] if parts else ""
    dimensions = next((x for x in parts[1:] if re.search(r"\b[HWD]\s*:", x)), "")
    details = "\n".join(x for x in parts[1:] if x != dimensions)

    full_text = "\n".join(parts)
    color = re.search(r"Colou?r\s*:\s*([^\n]+)", full_text, flags=re.I)

    category = (p.get("product_type") or "").strip()
    category_inferred = False
    if not category:
        title = p["title"].lower()
        category = next((c for k, c in TITLE_TO_CATEGORY if k in title), "Other")
        category_inferred = True

    variants = p.get("variants") or []
    prices = [float(v["price"]) for v in variants] or [0.0]
    compare = max((float(v.get("compare_at_price") or 0) for v in variants), default=0.0)

    return {
        "id": p["id"],
        "handle": p["handle"],
        "title": p["title"].strip(),
        "url": f"{STORE}/products/{p['handle']}",
        "category": category,
        "category_inferred": category_inferred,
        "color": color.group(1).strip() if color else "",
        "price_min": min(prices),
        "price_max": max(prices),
        "compare_at_price": compare if compare > min(prices) else None,  # original price if on sale
        "currency": "EGP",
        "available": any(v.get("available") for v in variants),
        "variants": [
            {
                "title": v["title"],
                "sku": v.get("sku"),
                "price": float(v["price"]),
                "available": v.get("available"),
            }
            for v in variants
        ],
        "description": description,
        "dimensions": dimensions,
        "details": details,
        "tags": [t for t in p.get("tags", []) if t.lower() not in INTERNAL_TAGS],
        "images": [img["src"] for img in p.get("images") or []],
        "published_at": p.get("published_at"),
        "collections": [],  # filled below
    }


def main():
    OUT.mkdir(exist_ok=True)

    print("Fetching products...")
    products = [clean_product(p) for p in fetch_all("/products.json", "products")]
    by_id = {p["id"]: p for p in products}
    print(f"  {len(products)} products ({sum(p['available'] for p in products)} in stock)")

    print("Fetching collections (one request each, takes a minute)...")
    collections = []
    for c in fetch_all("/collections.json", "collections"):
        try:
            members = fetch_all(f"/collections/{c['handle']}/products.json", "products")
        except Exception as e:
            print(f"  skip {c['handle']}: {e}")
            continue
        ids = [m["id"] for m in members if m["id"] in by_id]
        for pid in ids:
            by_id[pid]["collections"].append(c["handle"])
        collections.append(
            {
                "handle": c["handle"],
                "title": c["title"],
                "description": html_to_text(c.get("description") or ""),
                "url": f"{STORE}/collections/{c['handle']}",
                "product_count": len(ids),
                "product_handles": [by_id[i]["handle"] for i in ids],
            }
        )
        time.sleep(1)  # be polite to the store (Shopify returns 429 if we go faster)
    print(f"  {len(collections)} collections")

    # Category summary from product types
    categories = {}
    for p in products:
        c = categories.setdefault(
            p["category"], {"total": 0, "in_stock": 0, "price_min": None, "price_max": None}
        )
        c["total"] += 1
        c["in_stock"] += p["available"]
        c["price_min"] = min(filter(None, [c["price_min"], p["price_min"]]))
        c["price_max"] = max(filter(None, [c["price_max"], p["price_max"]]))
    categories = dict(sorted(categories.items(), key=lambda kv: -kv[1]["total"]))

    (OUT / "products.json").write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "categories.json").write_text(
        json.dumps({"product_types": categories, "collections": collections}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with open(
        OUT / "products.csv", "w", newline="", encoding="utf-8-sig"
    ) as f:  # utf-8-sig opens fine in Excel
        cols = [
            "handle",
            "title",
            "category",
            "color",
            "price_min",
            "price_max",
            "compare_at_price",
            "available",
            "sizes",
            "tags",
            "collections",
            "url",
            "image",
            "description",
            "dimensions",
            "details",
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for p in products:
            sizes = [v["title"] for v in p["variants"] if v["title"] != "Default Title"]
            w.writerow(
                {
                    **{k: p[k] for k in cols if k in p},
                    "sizes": ", ".join(sizes),
                    "tags": ", ".join(p["tags"]),
                    "collections": ", ".join(p["collections"]),
                    "image": p["images"][0] if p["images"] else "",
                }
            )

    print(f"Done -> {OUT}")


if __name__ == "__main__":
    main()
