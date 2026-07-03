"""
SQLite 数据持久化模块

存储每日抓取的商品数据，用于历史对比和趋势分析。
"""

import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .scraper import Product

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, config: dict):
        db_path = Path(config.get("storage", {}).get("db_path", "data/fashion_tracker.db"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                category    TEXT NOT NULL,
                source      TEXT NOT NULL,   -- 'bestseller' / 'mover'
                rank        INTEGER NOT NULL,
                name        TEXT NOT NULL,
                asin        TEXT,
                price       TEXT,
                rating      REAL,
                review_count INTEGER,
                image_url   TEXT,
                product_url TEXT,
                rank_change_pct REAL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_products_date ON products(date);
            CREATE INDEX IF NOT EXISTS idx_products_asin ON products(asin);
            CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
            CREATE INDEX IF NOT EXISTS idx_products_date_cat ON products(date, category, source);

            CREATE TABLE IF NOT EXISTS daily_summary (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL UNIQUE,
                summary_json TEXT NOT NULL,
                prediction_json TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()

    def save_products(self, products: list[Product], scrape_date: Optional[date] = None):
        d = (scrape_date or date.today()).isoformat()
        self.conn.execute("DELETE FROM products WHERE date = ?", (d,))
        rows = [
            (
                d,
                p.category,
                p.source,
                p.rank,
                p.name,
                p.asin,
                p.price,
                p.rating,
                p.review_count,
                p.image_url,
                p.product_url,
                p.rank_change_pct,
            )
            for p in products
        ]
        self.conn.executemany(
            """INSERT INTO products
               (date, category, source, rank, name, asin, price, rating, review_count,
                image_url, product_url, rank_change_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()
        logger.info("已保存 %d 条商品记录 (%s)", len(rows), d)

    def get_products_by_date(
        self, target_date: date, category: Optional[str] = None, source: Optional[str] = None
    ) -> list[dict]:
        sql = "SELECT * FROM products WHERE date = ?"
        params: list = [target_date.isoformat()]
        if category:
            sql += " AND category = ?"
            params.append(category)
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY rank ASC"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def get_product_history(self, asin: str, days: int = 30) -> list[dict]:
        """获取某商品最近 N 天的排名历史"""
        sql = """
            SELECT date, rank, category, source, price, rating, review_count
            FROM products
            WHERE asin = ?
            ORDER BY date DESC
            LIMIT ?
        """
        return [dict(r) for r in self.conn.execute(sql, (asin, days)).fetchall()]

    def get_category_history(self, category: str, source: str, days: int = 14) -> list[dict]:
        """获取某类目最近 N 天的全部上榜商品"""
        sql = """
            SELECT * FROM products
            WHERE category = ? AND source = ?
              AND date >= date('now', ?)
            ORDER BY date DESC, rank ASC
        """
        return [dict(r) for r in self.conn.execute(sql, (category, source, f"-{days} days")).fetchall()]

    def get_trending_asins(self, days: int = 7, min_appearances: int = 2, limit: int = 30) -> list[dict]:
        """找出最近 N 天内排名持续上升的商品（含图片和价格）"""
        sql = """
            WITH ranked AS (
                SELECT asin, name, category, date, rank, price, rating,
                       review_count, image_url, product_url,
                       ROW_NUMBER() OVER (PARTITION BY asin ORDER BY date DESC) as rn
                FROM products
                WHERE source = 'bestseller' AND asin IS NOT NULL
                  AND date >= date('now', ?)
            ),
            trends AS (
                SELECT asin, name, category, price, rating, review_count, image_url, product_url,
                       MAX(CASE WHEN rn = 1 THEN rank END) AS latest_rank,
                       MAX(CASE WHEN rn = (SELECT MAX(rn) FROM ranked r2 WHERE r2.asin = ranked.asin)
                            THEN rank END) AS earliest_rank,
                       COUNT(*) AS appearances
                FROM ranked
                GROUP BY asin
                HAVING COUNT(*) >= ?
            )
            SELECT *, (earliest_rank - latest_rank) AS rank_improvement
            FROM trends
            WHERE rank_improvement > 0
            ORDER BY rank_improvement DESC
            LIMIT ?
        """
        return [dict(r) for r in self.conn.execute(sql, (f"-{days} days", min_appearances, limit)).fetchall()]

    def get_new_entries(self, days: int = 3) -> list[dict]:
        """找出最近 N 天内首次上榜的商品"""
        sql = """
            SELECT p.*
            FROM products p
            WHERE p.date = date('now')
              AND p.source = 'bestseller'
              AND p.asin NOT IN (
                  SELECT DISTINCT asin FROM products
                  WHERE date < date('now', ?) AND asin IS NOT NULL
              )
              AND p.asin IS NOT NULL
            ORDER BY p.rank ASC
        """
        return [dict(r) for r in self.conn.execute(sql, (f"-{days} days",)).fetchall()]

    def get_available_dates(self) -> list[str]:
        sql = "SELECT DISTINCT date FROM products ORDER BY date DESC"
        return [r["date"] for r in self.conn.execute(sql).fetchall()]

    def save_daily_summary(self, target_date: date, summary: dict, prediction: Optional[dict] = None):
        self.conn.execute(
            """INSERT OR REPLACE INTO daily_summary (date, summary_json, prediction_json)
               VALUES (?, ?, ?)""",
            (target_date.isoformat(), json.dumps(summary, ensure_ascii=False),
             json.dumps(prediction, ensure_ascii=False) if prediction else None),
        )
        self.conn.commit()

    def get_past_summaries(self, days: int = 7) -> list[dict]:
        sql = """
            SELECT * FROM daily_summary
            WHERE date >= date('now', ?)
            ORDER BY date DESC
        """
        rows = self.conn.execute(sql, (f"-{days} days",)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["summary"] = json.loads(d["summary_json"])
            d["prediction"] = json.loads(d["prediction_json"]) if d.get("prediction_json") else None
            result.append(d)
        return result

    def close(self):
        self.conn.close()
