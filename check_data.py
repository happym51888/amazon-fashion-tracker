import sqlite3, json

conn = sqlite3.connect("data/fashion_tracker.db")
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT category, source, COUNT(*) as cnt FROM products WHERE date=? GROUP BY category, source",
    ("2026-03-08",),
).fetchall()

print("=" * 50)
print("抓取数据统计")
print("=" * 50)
for r in rows:
    print(f"  {r['category']:20s} {r['source']:12s} {r['cnt']}个")

summ = conn.execute(
    "SELECT summary_json, prediction_json FROM daily_summary WHERE date=?",
    ("2026-03-08",),
).fetchone()

if summ:
    d = json.loads(summ[0])
    pa = d.get("price_analysis", {})
    print(f"\n价格均价: ${pa.get('avg', 'N/A')}")
    print(f"价格中位数: ${pa.get('median', 'N/A')}")
    print(f"\n风格热度 TOP5:")
    for style, count in list(d.get("style_trends", {}).items())[:5]:
        print(f"  {style}: {count}")
    print(f"\n品类分布 TOP5:")
    for g, count in list(d.get("garment_distribution", {}).items())[:5]:
        print(f"  {g}: {count}")

    pred = json.loads(summ[1]) if summ[1] else None
    if pred:
        print(f"\n{'=' * 50}")
        print("趋势预测摘要")
        print("=" * 50)
        print(f"季节背景: {pred.get('seasonal_context', '')[:80]}...")
        if pred.get("recommendations"):
            print("\n选品建议:")
            for rec in pred["recommendations"]:
                print(f"  {rec}")

# 打印 Top 5 畅销品
print(f"\n{'=' * 50}")
print("Top 5 畅销商品")
print("=" * 50)
top5 = conn.execute(
    "SELECT rank, name, price, rating, review_count, category FROM products WHERE date=? AND source='bestseller' ORDER BY rank LIMIT 5",
    ("2026-03-08",),
).fetchall()
for r in top5:
    print(f"  #{r['rank']} | {r['name'][:50]} | {r['price']} | ⭐{r['rating']} | {r['review_count']}评价 | {r['category']}")

conn.close()
