import sqlite3
from collections import Counter

conn = sqlite3.connect("data/fashion_tracker.db")
conn.row_factory = sqlite3.Row

print("=== Accessories data ===")
products = conn.execute(
    "SELECT asin, name, category, source, rank FROM products WHERE date='2026-03-09' ORDER BY rank"
).fetchall()
print(f"Total rows: {len(products)}")

asin_counts = Counter(p["asin"] for p in products if p["asin"])
dupes = [(asin, cnt) for asin, cnt in asin_counts.most_common() if cnt > 1]
print(f"Unique ASINs: {len(asin_counts)}")
print(f"Duplicated ASINs: {len(dupes)}")

if dupes:
    print(f"\nDuplicate examples (top 10):")
    for asin, cnt in dupes[:10]:
        rows = [p for p in products if p["asin"] == asin]
        cats = [f"{r['category']}({r['source']})" for r in rows]
        print(f"  {asin} x{cnt}: {rows[0]['name'][:50]}")
        print(f"    in: {', '.join(cats)}")

print(f"\n=== By category & source ===")
cat_src = Counter((p["category"], p["source"]) for p in products)
for (cat, src), cnt in sorted(cat_src.items()):
    print(f"  {cat:20s} {src:12s} {cnt}")

conn.close()
