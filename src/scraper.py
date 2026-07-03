"""
Amazon 服装畅销榜爬虫模块

抓取 Best Sellers（畅销榜）和 Movers & Shakers（飙升榜）数据，
包括商品名称、排名、价格、评分、图片等信息。
"""

import io
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

HEADERS_BASE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


@dataclass
class Product:
    rank: int
    name: str
    price: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    asin: Optional[str] = None
    rank_change_pct: Optional[float] = None  # Movers & Shakers 飙升百分比
    category: str = ""
    source: str = "bestseller"  # "bestseller" 或 "mover"


SEASON_MONTHS = {
    "winter": {10, 11, 12, 1, 2, 3},
    "summer": {4, 5, 6, 7, 8, 9},
    "all": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12},
}


class AmazonFashionScraper:
    BASE_URL = "https://www.amazon.com"

    def __init__(self, config: dict):
        scraper_cfg = config.get("scraper", {})
        all_categories = scraper_cfg.get("categories", {})
        self.max_products = scraper_cfg.get("max_products_per_category", 50)
        self.delay_min = scraper_cfg.get("delay_min", 3)
        self.delay_max = scraper_cfg.get("delay_max", 8)
        self.timeout = scraper_cfg.get("timeout", 30)
        self.max_retries = scraper_cfg.get("max_retries", 3)

        storage_cfg = config.get("storage", {})
        self.image_dir = Path(storage_cfg.get("image_dir", "data/images"))
        self.image_max_width = config.get("report", {}).get("image_max_width", 200)
        self.image_quality = config.get("report", {}).get("image_quality", 50)

        current_month = datetime.now().month
        self.categories = {}
        for key, info in all_categories.items():
            season = info.get("season", "all")
            allowed_months = SEASON_MONTHS.get(season, SEASON_MONTHS["all"])
            if current_month in allowed_months:
                self.categories[key] = info

        skipped = len(all_categories) - len(self.categories)
        if skipped:
            logger.info("当前月份 %d 月，跳过 %d 个非当季类目，抓取 %d 个应季类目",
                        current_month, skipped, len(self.categories))

        self.session = requests.Session()
        self._rotate_ua()

    def _rotate_ua(self):
        headers = HEADERS_BASE.copy()
        headers["User-Agent"] = random.choice(USER_AGENTS)
        self.session.headers.update(headers)

    def _random_delay(self):
        delay = random.uniform(self.delay_min, self.delay_max)
        logger.debug("等待 %.1f 秒...", delay)
        time.sleep(delay)

    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        full_url = url if url.startswith("http") else urljoin(self.BASE_URL, url)
        for attempt in range(1, self.max_retries + 1):
            try:
                self._rotate_ua()
                resp = self.session.get(full_url, timeout=self.timeout)
                if resp.status_code == 200:
                    return BeautifulSoup(resp.text, "lxml")
                if resp.status_code == 503:
                    logger.warning("请求被限制 (503)，第 %d 次重试...", attempt)
                    time.sleep(random.uniform(10, 20))
                    continue
                logger.warning("HTTP %d: %s", resp.status_code, full_url)
                return None
            except requests.RequestException as e:
                logger.warning("请求失败 (%s)，第 %d 次重试...", e, attempt)
                time.sleep(random.uniform(5, 10))
        logger.error("多次重试后仍失败: %s", full_url)
        return None

    # ------------------------------------------------------------------
    # Best Sellers 解析
    # ------------------------------------------------------------------
    def _parse_bestsellers(self, soup: BeautifulSoup, category: str) -> list[Product]:
        products = []
        items = soup.select("div[id^='p13n-asin-index-']")
        if not items:
            items = soup.select(".zg-grid-general-faceout")
        if not items:
            items = soup.select("[data-asin]")

        for item in items:
            if len(products) >= self.max_products:
                break
            try:
                product = self._extract_bestseller_item(item, category)
                if product:
                    products.append(product)
            except Exception as e:
                logger.debug("解析商品条目失败: %s", e)
                continue
        return products

    def _extract_bestseller_item(self, item, category: str) -> Optional[Product]:
        rank_el = item.select_one(".zg-bdg-text")
        if rank_el:
            rank_text = rank_el.get_text(strip=True).replace("#", "")
            rank = int(re.sub(r"[^\d]", "", rank_text))
        else:
            rank_span = item.select_one("span.zg-badge-text")
            if rank_span:
                rank = int(re.sub(r"[^\d]", "", rank_span.get_text(strip=True)))
            else:
                return None

        name_el = (
            item.select_one("a.a-link-normal span div")
            or item.select_one("a.a-link-normal span")
            or item.select_one(".p13n-sc-truncate")
            or item.select_one("._cDEzb_p13n-sc-css-line-clamp-3_g3dy1")
        )
        name = name_el.get_text(strip=True) if name_el else "Unknown"

        price_el = item.select_one(".p13n-sc-price") or item.select_one("span._cDEzb_p13n-sc-price_3mJ9Z")
        if not price_el:
            price_el = item.select_one("span.a-color-price")
        price = price_el.get_text(strip=True) if price_el else None

        rating = None
        rating_el = item.select_one("span.a-icon-alt")
        if rating_el:
            m = re.search(r"([\d.]+)", rating_el.get_text())
            if m:
                rating = float(m.group(1))

        review_count = None
        review_el = item.select_one("span.a-size-small") or item.select_one("a.a-size-small")
        if review_el:
            text = review_el.get_text(strip=True).replace(",", "")
            m = re.search(r"(\d+)", text)
            if m:
                review_count = int(m.group(1))

        image_url = None
        for img_el in item.select("img"):
            src = img_el.get("src") or img_el.get("data-src") or ""
            if src and not src.endswith(".gif") and "icon" not in src.lower():
                image_url = src
                break
        if not image_url:
            img_el = item.select_one("img")
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")

        product_url = None
        asin = None
        link_el = item.select_one("a.a-link-normal[href]")
        if link_el:
            href = link_el["href"]
            product_url = urljoin(self.BASE_URL, href)
            m = re.search(r"/dp/([A-Z0-9]{10})", href)
            if m:
                asin = m.group(1)

        if not asin:
            asin = item.get("data-asin") or item.select_one("[data-asin]")
            if hasattr(asin, "get"):
                asin = asin.get("data-asin")

        return Product(
            rank=rank,
            name=name,
            price=price,
            rating=rating,
            review_count=review_count,
            image_url=image_url,
            product_url=product_url,
            asin=asin,
            category=category,
            source="bestseller",
        )

    # ------------------------------------------------------------------
    # Movers & Shakers 解析（飙升榜）
    # ------------------------------------------------------------------
    def _parse_movers(self, soup: BeautifulSoup, category: str) -> list[Product]:
        products = []
        items = soup.select("div[id^='p13n-asin-index-']")
        if not items:
            items = soup.select(".zg-grid-general-faceout")

        for item in items:
            if len(products) >= self.max_products:
                break
            try:
                product = self._extract_mover_item(item, category)
                if product:
                    products.append(product)
            except Exception as e:
                logger.debug("解析飙升榜条目失败: %s", e)
                continue
        return products

    def _extract_mover_item(self, item, category: str) -> Optional[Product]:
        product = self._extract_bestseller_item(item, category)
        if not product:
            return None
        product.source = "mover"

        pct_el = item.select_one("span.zg-percent-change") or item.select_one(".a-size-small .a-color-success")
        if pct_el:
            pct_text = pct_el.get_text(strip=True).replace("%", "").replace(",", "")
            m = re.search(r"(\d+)", pct_text)
            if m:
                product.rank_change_pct = float(m.group(1))
        return product

    # ------------------------------------------------------------------
    # 图片下载
    # ------------------------------------------------------------------
    def download_image(self, image_url: str, asin: str) -> Optional[Path]:
        if not image_url or not asin:
            return None
        self.image_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.image_dir / f"{asin}.jpg"
        if filepath.exists():
            return filepath
        try:
            resp = self.session.get(image_url, timeout=15)
            if resp.status_code == 200:
                img = Image.open(io.BytesIO(resp.content))
                if img.width > self.image_max_width:
                    ratio = self.image_max_width / img.width
                    img = img.resize(
                        (self.image_max_width, int(img.height * ratio)),
                        Image.LANCZOS,
                    )
                img = img.convert("RGB")
                img.save(filepath, "JPEG", quality=self.image_quality)
                return filepath
        except Exception as e:
            logger.debug("图片下载失败 (%s): %s", asin, e)
        return None

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def scrape_all(self) -> dict[str, dict[str, list[Product]]]:
        """
        返回结构：
        {
            "category_key": {
                "bestsellers": [Product, ...],
                "movers": [Product, ...],
            }
        }
        """
        results = {}
        for cat_key, cat_info in self.categories.items():
            cat_name = cat_info.get("name", cat_key)
            logger.info("正在抓取类目: %s", cat_name)
            results[cat_key] = {"bestsellers": [], "movers": []}

            bs_url = cat_info.get("url")
            if bs_url:
                soup = self._fetch_page(bs_url)
                if soup:
                    products = self._parse_bestsellers(soup, cat_key)
                    logger.info("  畅销榜: 抓取到 %d 个商品", len(products))
                    results[cat_key]["bestsellers"] = products
                self._random_delay()

            mv_url = cat_info.get("movers_url")
            if mv_url:
                soup = self._fetch_page(mv_url)
                if soup:
                    movers = self._parse_movers(soup, cat_key)
                    logger.info("  飙升榜: 抓取到 %d 个商品", len(movers))
                    results[cat_key]["movers"] = movers
                self._random_delay()

        # 批量下载图片
        all_products = [
            p
            for cat_data in results.values()
            for source_list in cat_data.values()
            for p in source_list
        ]
        logger.info("开始下载 %d 个商品的图片...", len(all_products))
        for p in all_products:
            if p.image_url and p.asin:
                local = self.download_image(p.image_url, p.asin)
                if local:
                    p.image_local_path = str(local)

        return results
