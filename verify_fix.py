import sqlite3
from collections import Counter
from pathlib import Path

conn = sqlite3.connect("data/fashion_tracker.db")
conn.row_factory = sqlite3.Row

print("=== Mover images check (2026-03-09) ===")
movers = conn.execute(
    "SELECT asin, image_url FROM products WHERE date='2026-03-09' AND source='mover'"
).fetchall()
gif_count = sum(1 for m in movers if m["image_url"] and m["image_url"].endswith(".gif"))
jpg_count = sum(1 for m in movers if m["image_url"] and not m["image_url"].endswith(".gif"))
local_count = sum(1 for m in movers if m["asin"] and (Path("data/images") / f"{m['asin']}.jpg").exists())
print(f"  Total: {len(movers)}, GIF(arrows): {gif_count}, Real images: {jpg_count}, Local files: {local_count}")

print("\n=== Dedup check ===")
bestsellers = conn.execute(
    "SELECT asin, name, category, rank FROM products WHERE date='2026-03-09' AND source='bestseller' ORDER BY rank"
).fetchall()
asin_counts = Counter(b["asin"] for b in bestsellers if b["asin"])
dupes = sum(1 for cnt in asin_counts.values() if cnt > 1)
print(f"  Total rows: {len(bestsellers)}, Unique ASINs: {len(asin_counts)}, Duplicated: {dupes}")

seen = set()
deduped = []
for b in sorted(bestsellers, key=lambda x: x["rank"]):
    if b["asin"] not in seen:
        seen.add(b["asin"])
        deduped.append(b)
print(f"  After dedup for report: {len(deduped)} unique products (top 20 shown)")

conn.close()
