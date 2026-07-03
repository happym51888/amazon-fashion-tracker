import sqlite3, json
from collections import Counter

conn = sqlite3.connect("data/fashion_tracker.db")
conn.row_factory = sqlite3.Row

print("=" * 60)
print("ISSUE 1: Movers without images")
print("=" * 60)
movers = conn.execute(
    "SELECT asin, name, image_url, category FROM products WHERE date='2026-03-08' AND source='mover'"
).fetchall()
has_img = sum(1 for m in movers if m["image_url"])
has_asin = sum(1 for m in movers if m["asin"])
print(f"Total movers: {len(movers)}")
print(f"  with image_url: {has_img}")
print(f"  with asin:      {has_asin}")
if movers:
    print(f"\nSample mover:")
    m = movers[0]
    print(f"  name:  {m['name'][:60]}")
    print(f"  asin:  {m['asin']}")
    print(f"  image: {m['image_url'][:80] if m['image_url'] else 'NONE'}")

from pathlib import Path
img_dir = Path("data/images")
mover_with_local = 0
for m in movers:
    if m["asin"] and (img_dir / f"{m['asin']}.jpg").exists():
        mover_with_local += 1
print(f"  with local image file: {mover_with_local}")

print(f"\n{'=' * 60}")
print("ISSUE 2: Duplicate bestsellers")
print("=" * 60)
bestsellers = conn.execute(
    "SELECT asin, name, category, rank FROM products WHERE date='2026-03-08' AND source='bestseller' ORDER BY rank"
).fetchall()

asin_counts = Counter(b["asin"] for b in bestsellers if b["asin"])
dupes = [(asin, cnt) for asin, cnt in asin_counts.items() if cnt > 1]
print(f"Total bestsellers: {len(bestsellers)}")
print(f"Unique ASINs: {len(asin_counts)}")
print(f"Duplicated ASINs: {len(dupes)}")

if dupes:
    print(f"\nDuplicate details:")
    for asin, cnt in dupes[:10]:
        rows = [b for b in bestsellers if b["asin"] == asin]
        print(f"\n  ASIN {asin} appears {cnt}x:")
        for r in rows:
            print(f"    #{r['rank']} in {r['category']} - {r['name'][:50]}")

conn.close()
