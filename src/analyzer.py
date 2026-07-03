"""
数据分析与趋势预测模块

根据历史抓取数据分析服装销售趋势，并预测未来一个月流行走势。
"""

import logging
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Optional

from .google_trends import GoogleTrendsClient
from .product_filters import should_exclude_product
from .profile_utils import get_profile_meta
from .storage import Storage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 饰品/配饰风格关键词映射（英文关键词 → 中文标签）
# ---------------------------------------------------------------------------
STYLE_KEYWORDS = {
    # 风格
    "vintage": "复古",
    "retro": "复古",
    "y2k": "Y2K千禧风",
    "bohemian": "波西米亚",
    "boho": "波西米亚",
    "minimalist": "极简风",
    "gothic": "哥特风",
    "punk": "朋克风",
    "western": "美式西部",
    "cottagecore": "田园风",
    "preppy": "学院风",
    "luxury": "轻奢",
    "elegant": "优雅",
    "dainty": "精致小巧",
    "chunky": "粗链/夸张",
    "delicate": "纤细精致",
    "statement": "夸张型/Statement",
    "layered": "叠戴/层叠",
    "stackable": "可叠戴",
    "adjustable": "可调节",
    "personalized": "个性定制",
    "initial": "字母款",
    "name": "名字款",
    "birthstone": "生辰石",
    "zodiac": "星座",
    "celestial": "星月元素",
    "butterfly": "蝴蝶元素",
    "heart": "心形",
    "evil eye": "恶眼/蓝眼睛",
    "hamsa": "法蒂玛之手",
    # 材质/工艺
    "gold": "金色/镀金",
    "silver": "银色/纯银",
    "rose gold": "玫瑰金",
    "sterling silver": "925纯银",
    "stainless steel": "不锈钢",
    "titanium": "钛钢",
    "pearl": "珍珠",
    "crystal": "水晶",
    "rhinestone": "水钻",
    "cubic zirconia": "锆石",
    "resin": "树脂",
    "acrylic": "亚克力",
    "enamel": "珐琅",
    "beaded": "串珠",
    "woven": "编织",
    "braided": "编绳",
    "crochet": "钩针编织",
    "knit": "针织",
    "cashmere": "羊绒",
    "wool": "羊毛",
    "fleece": "摇粒绒",
    "silk": "真丝",
    "satin": "缎面",
    "velvet": "丝绒",
    "leather": "皮革",
    "faux leather": "仿皮",
    "suede": "麂皮",
    # 图案/颜色
    "floral": "花卉",
    "plaid": "格纹",
    "striped": "条纹",
    "tie-dye": "扎染",
    "solid": "纯色",
    "neon": "荧光色",
    "pastel": "马卡龙色",
    "neutral": "中性色",
    "earth tone": "大地色系",
    "monochrome": "黑白配色",
    "colorful": "多彩",
    "ombre": "渐变色",
    "glitter": "闪光",
    "sequin": "亮片",
    "holographic": "镭射/全息",
}

GARMENT_TYPES = {
    # 围巾/披肩
    "scarf": "围巾",
    "shawl": "披肩",
    "wrap": "披肩/围巾",
    "pashmina": "羊绒围巾",
    "bandana": "方巾/头巾",
    "neckerchief": "领巾",
    "infinity scarf": "环形围巾",
    # 帽子
    "beanie": "毛线帽",
    "beret": "贝雷帽",
    "bucket hat": "渔夫帽",
    "baseball cap": "棒球帽",
    "sun hat": "遮阳帽",
    "straw hat": "草帽",
    "visor": "遮阳帽",
    "fedora": "礼帽",
    "wide brim": "大檐帽",
    "trucker hat": "卡车帽",
    "dad hat": "老爹帽",
    # 手套
    "gloves": "手套",
    "mittens": "连指手套",
    "touchscreen glove": "触屏手套",
    # 头饰/发饰
    "headband": "发箍/头带",
    "hair clip": "发夹",
    "claw clip": "鲨鱼夹/抓夹",
    "barrette": "一字夹",
    "hair tie": "发圈",
    "scrunchie": "大肠发圈",
    "hair pin": "发簪/U型夹",
    "bobby pin": "黑夹子",
    "hair comb": "发梳",
    "tiara": "皇冠/头饰",
    "hair bow": "蝴蝶结发饰",
    "hair band": "发带",
    "turban": "包头巾",
    # 首饰
    "necklace": "项链",
    "pendant": "吊坠",
    "choker": "颈链/Choker",
    "chain": "链条",
    "earring": "耳环",
    "stud": "耳钉",
    "hoop": "圈形耳环",
    "dangle": "垂坠耳环",
    "drop earring": "水滴耳环",
    "ear cuff": "耳骨夹",
    "bracelet": "手链",
    "bangle": "手镯",
    "cuff": "开口手镯",
    "anklet": "脚链",
    "ring": "戒指",
    "band ring": "素圈戒指",
    "signet ring": "印章戒指",
    "brooch": "胸针",
    "pin": "别针/徽章",
    # 配饰
    "belt": "腰带",
    "keychain": "钥匙链",
    "sunglasses": "太阳镜",
    "glasses": "眼镜",
    "watch": "手表",
    "tote bag": "托特包",
    "crossbody": "斜挎包",
    "clutch": "手拿包",
}

SEASONAL_INSIGHTS = {
    1: "1月（冬季高峰期）：围巾、帽子、手套仍是刚需，冬季清仓折扣开始。情人节首饰（心形项链、手链）预热期，提前备货。春季发饰开始上架。",
    2: "2月（情人节爆发）：情人节是首饰全年最大节点之一！心形/玫瑰金/珍珠项链、手链、耳环爆卖。红色/粉色系配饰热销。冬季保暖配饰进入清仓。",
    3: "3月（春季切换期）：围巾从保暖款转向轻薄丝巾/披肩。春季发饰（花卉发夹、彩色发圈）需求上升。太阳镜开始预热。复活节主题配饰有机会。",
    4: "4月（春季主力）：轻薄丝巾、发饰、太阳镜进入旺季。花卉/蝴蝶元素饰品热销。母亲节礼品（珍珠项链、手链套装）预购开始。",
    5: "5月（母亲节爆发）：母亲节是首饰第二大节点！项链、耳环、手链礼品套装爆卖。毕业季也带动首饰/配饰送礼需求。夏季遮阳帽/太阳镜全面启动。",
    6: "6月（夏季配饰旺季）：太阳镜、遮阳帽、草帽进入巅峰期。夏季发饰（大肠发圈、鲨鱼夹）需求量大。父亲节男士配饰（皮带、钥匙链）热销。波西米亚风首饰旺季。",
    7: "7月（Prime Day+盛夏）：Prime Day是配饰大促节点！太阳镜、发饰、平价首饰折扣带来巨量销售。海滩风配饰（贝壳项链、编绳手链）巅峰期。",
    8: "8月（夏末+开学季）：开学季带动年轻人配饰（发饰、平价首饰、双肩包挂件）爆发。夏季款开始清仓，秋季配饰（大地色系、针织发带）预热。",
    9: "9月（秋季切换）：秋冬配饰上新。针织帽、围巾轻薄款开始动销。大地色/酒红色/深色系首饰受追捧。Labor Day促销清仓夏季库存。",
    10: "10月（万圣节+秋冬备货）：万圣节主题配饰（骷髅耳环、蜘蛛网项链、南瓜主题）热销。冬季围巾/帽子/手套开始上量。深色系/格纹围巾需求上升。",
    11: "11月（黑五/圣诞备货）：黑五是全年最大促销！首饰是热门礼品品类，项链/耳环/手链销量暴增。冬季保暖配饰（围巾帽子手套套装）需求巅峰。感恩节聚会配饰需求。",
    12: "12月（圣诞礼物季）：圣诞是首饰/配饰全年最大销售月！礼品套装（项链+耳环、围巾+帽子+手套套装）爆卖。圣诞元素配饰（红/绿/金、雪花、驯鹿）热销。跨年派对亮片/水钻饰品需求高。",
}

SEARCH_STOPWORDS = {
    "women",
    "womens",
    "woman",
    "men",
    "mens",
    "man",
    "girls",
    "girl",
    "boys",
    "boy",
    "kids",
    "kid",
    "pack",
    "packs",
    "set",
    "gift",
    "case",
    "holder",
    "solid",
    "color",
    "pre",
    "tied",
    "adjustable",
    "polarized",
    "fashion",
    "trendy",
    "classic",
    "lightweight",
    "loose",
    "retro",
    "piece",
    "pieces",
}

CATEGORY_SEARCH_DEFAULTS = {
    "scarves": "scarf",
    "cold_weather_hats": "beanie",
    "gloves": "gloves",
    "hair_accessories": "hair accessories",
    "headbands": "headband",
    "hair_clips": "claw clip",
    "sunglasses": "sunglasses",
    "necklaces": "necklace",
    "earrings": "earrings",
    "bracelets": "bracelet",
    "rings": "ring",
    "hats_caps": "baseball cap",
    "belts": "belt",
    "keychains": "keychain",
    "womens_dresses": "dress",
    "womens_tops": "women tops",
    "womens_jeans": "women jeans",
    "womens_jackets": "women jacket",
    "womens_sweaters": "women sweater",
    "womens_activewear": "women activewear",
    "mens_shirts": "men shirt",
    "mens_tshirts": "men t shirt",
    "mens_jeans": "men jeans",
    "mens_jackets": "men jacket",
    "mens_hoodies": "men hoodie",
}


class FashionAnalyzer:
    def __init__(self, storage: Storage, config: dict):
        self.storage = storage
        self.config = config
        self.profile_meta = get_profile_meta(config)
        self.google_trends = GoogleTrendsClient(config)
        self.exclude_keywords = [
            kw.lower() for kw in config.get("report", {}).get("exclude_keywords", [])
        ]
        self.prediction_limit = config.get("prediction", {}).get("top_n", 10)

    def _filter_products(self, products: list[dict]) -> list[dict]:
        return [p for p in products if not self._is_excluded(p.get("name", ""))]

    def _is_excluded(self, product_name: str) -> bool:
        return should_exclude_product(product_name, self.exclude_keywords)

    # ------------------------------------------------------------------
    # 关键词提取
    # ------------------------------------------------------------------
    @staticmethod
    def extract_tags(product_name: str) -> dict:
        name_lower = product_name.lower()
        styles = [
            (kw, label) for kw, label in STYLE_KEYWORDS.items()
            if kw in name_lower
        ]
        garments = [
            (kw, label) for kw, label in GARMENT_TYPES.items()
            if re.search(rf"\b{re.escape(kw)}\b", name_lower)
        ]
        return {
            "styles": styles,
            "garments": garments,
        }

    def _prediction_anchor_keyword(self) -> str:
        return "necklace" if self.profile_meta["id"] == "accessories" else "dress"

    def _build_search_query(self, product: dict) -> str:
        product_name = product.get("name", "")
        tags = self.extract_tags(product_name)
        garment_terms = [kw for kw, _ in tags["garments"]]
        style_terms = [kw for kw, _ in tags["styles"] if kw not in {"solid", "name"}]

        base_term = ""
        if garment_terms:
            base_term = max(garment_terms, key=len)
        else:
            base_term = CATEGORY_SEARCH_DEFAULTS.get(product.get("category", ""), "")

        if not base_term:
            words = re.findall(r"[a-zA-Z]+", product_name.lower())
            filtered_words = [
                word
                for word in words
                if len(word) >= 3 and word not in SEARCH_STOPWORDS
            ]
            base_term = " ".join(filtered_words[:3]).strip()

        if style_terms:
            style_term = max(style_terms, key=len)
            if style_term and style_term not in base_term:
                return f"{style_term} {base_term}".strip()

        return base_term or self._prediction_anchor_keyword()

    @staticmethod
    def _extract_price_value(price_str: Optional[str]) -> Optional[float]:
        if not price_str:
            return None
        match = re.search(r"(\d+\.?\d*)", price_str.replace(",", ""))
        return float(match.group(1)) if match else None

    def _score_prediction_candidate(
        self,
        product: dict,
        trend_asins: set[str],
        new_entry_asins: set[str],
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons = []

        rank = product.get("rank") or 999
        if rank <= 3:
            score += 40
            reasons.append(f"畅销Top{rank}")
        elif rank <= 10:
            score += 28
            reasons.append(f"畅销Top{rank}")
        elif rank <= 20:
            score += 18
        elif rank <= 30:
            score += 8

        mover_pct = product.get("rank_change_pct") or 0
        if mover_pct >= 200:
            score += 35
            reasons.append(f"飙升{int(mover_pct)}%")
        elif mover_pct >= 100:
            score += 24
            reasons.append(f"飙升{int(mover_pct)}%")
        elif mover_pct >= 50:
            score += 14
            reasons.append(f"飙升{int(mover_pct)}%")
        elif mover_pct > 0:
            score += min(10, mover_pct / 10)

        rating = product.get("rating") or 0
        if rating:
            score += rating * 5
            if rating >= 4.5:
                reasons.append(f"评分{rating}")

        review_count = product.get("review_count") or 0
        if review_count:
            score += min(20.0, math.log10(review_count + 1) * 6)
            if review_count >= 3000:
                reasons.append(f"{review_count:,}+评价")

        price_value = self._extract_price_value(product.get("price"))
        if price_value is not None:
            if 8 <= price_value <= 35:
                score += 8
            elif 35 < price_value <= 60:
                score += 4

        asin = product.get("asin")
        if asin and asin in trend_asins:
            score += 12
            reasons.append("近期持续上升")

        if asin and asin in new_entry_asins:
            score += 6
            reasons.append("新上榜")

        return score, reasons[:4]

    def _build_predicted_products(
        self,
        products: list[dict],
        trend_data: dict,
    ) -> tuple[list[dict], str]:
        bestsellers = sorted(
            [p for p in products if p.get("source") == "bestseller"],
            key=lambda x: x.get("rank") or 999,
        )
        movers = sorted(
            [p for p in products if p.get("source") == "mover"],
            key=lambda x: x.get("rank_change_pct") or 0,
            reverse=True,
        )

        candidates: dict[str, dict] = {}
        for product in bestsellers[:40]:
            key = product.get("asin") or (product.get("name") or "").lower()
            candidates[key] = dict(product)

        for product in movers[:40]:
            key = product.get("asin") or (product.get("name") or "").lower()
            existing = candidates.get(key)
            if existing:
                if product.get("rank_change_pct") and not existing.get("rank_change_pct"):
                    existing["rank_change_pct"] = product.get("rank_change_pct")
                if product.get("source") == "mover":
                    existing["mover_rank"] = product.get("rank")
            else:
                merged = dict(product)
                merged["mover_rank"] = product.get("rank")
                candidates[key] = merged

        trend_asins = {
            item.get("asin")
            for item in trend_data.get("trending_products", [])
            if item.get("asin")
        }
        new_entry_asins = {
            item.get("asin")
            for item in trend_data.get("new_entries", [])
            if item.get("asin")
        }

        scored_candidates = []
        for product in candidates.values():
            amazon_score, reasons = self._score_prediction_candidate(
                product,
                trend_asins,
                new_entry_asins,
            )
            search_query = self._build_search_query(product)
            scored_candidates.append(
                {
                    **product,
                    "_amazon_score": round(amazon_score, 1),
                    "_reasons": reasons,
                    "_search_query": search_query,
                }
            )

        scored_candidates.sort(
            key=lambda x: (
                -x["_amazon_score"],
                -(x.get("rank_change_pct") or 0),
                x.get("rank") or 999,
            )
        )

        google_queries = [item["_search_query"] for item in scored_candidates[:20]]
        google_scores, google_status = self.google_trends.fetch_scores(
            google_queries,
            anchor_keyword=self._prediction_anchor_keyword(),
        )

        final_candidates = []
        for product in scored_candidates:
            google_info = google_scores.get(product["_search_query"], {})
            google_score = google_info.get("normalized")
            google_delta = google_info.get("delta")

            total_score = product["_amazon_score"]
            reasons = list(product["_reasons"])
            if google_score is not None:
                total_score += min(30.0, google_score / 4)
                if google_delta and google_delta > 0:
                    total_score += min(8.0, google_delta)
                reasons.append(f"Google热度{google_score}")
                if google_delta and google_delta > 0:
                    reasons.append(f"近月搜索+{google_delta}")

            final_candidates.append(
                {
                    **product,
                    "prediction_score": round(total_score, 1),
                    "google_trend_score": google_score,
                    "google_trend_delta": google_delta,
                    "_prediction_reason": "、".join(reasons[:4]) if reasons else "综合热度稳定",
                }
            )

        final_candidates.sort(
            key=lambda x: (
                -x["prediction_score"],
                -(x.get("google_trend_score") or 0),
                -(x.get("rank_change_pct") or 0),
                x.get("rank") or 999,
            )
        )

        for index, product in enumerate(final_candidates[: self.prediction_limit], start=1):
            product["prediction_rank"] = index

        return final_candidates[: self.prediction_limit], google_status

    # ------------------------------------------------------------------
    # 当日数据汇总
    # ------------------------------------------------------------------
    def generate_daily_summary(self, target_date: Optional[date] = None) -> dict:
        d = target_date or date.today()
        raw_products = self.storage.get_products_by_date(d)

        if not raw_products:
            return {"date": d.isoformat(), "error": "当日无数据"}

        all_products = self._filter_products(raw_products)
        bestsellers = [p for p in all_products if p["source"] == "bestseller"]
        movers = [p for p in all_products if p["source"] == "mover"]

        summary = {
            "date": d.isoformat(),
            "total_products": len(all_products),
            "bestseller_count": len(bestsellers),
            "mover_count": len(movers),
            "categories": self._summarize_by_category(all_products),
            "price_analysis": self._analyze_prices(bestsellers),
            "top_movers": self._top_movers(movers),
            "style_trends": self._analyze_styles(all_products),
            "garment_distribution": self._analyze_garments(all_products),
        }
        return summary

    def _summarize_by_category(self, products: list[dict]) -> dict:
        cats = defaultdict(lambda: {"bestseller_count": 0, "mover_count": 0, "products": []})
        for p in products:
            cat = p["category"]
            cats[cat][f"{p['source']}_count"] += 1
            cats[cat]["products"].append(p)
        return dict(cats)

    def _analyze_prices(self, products: list[dict]) -> dict:
        prices = []
        for p in products:
            if p.get("price"):
                m = re.search(r"(\d+\.?\d*)", p["price"].replace(",", ""))
                if m:
                    prices.append(float(m.group(1)))
        if not prices:
            return {}
        prices.sort()
        n = len(prices)
        return {
            "min": prices[0],
            "max": prices[-1],
            "avg": round(sum(prices) / n, 2),
            "median": prices[n // 2],
            "price_ranges": {
                "$0-15": sum(1 for p in prices if p < 15),
                "$15-30": sum(1 for p in prices if 15 <= p < 30),
                "$30-50": sum(1 for p in prices if 30 <= p < 50),
                "$50-100": sum(1 for p in prices if 50 <= p < 100),
                "$100+": sum(1 for p in prices if p >= 100),
            },
        }

    def _top_movers(self, movers: list[dict], n: int = 10) -> list[dict]:
        sorted_movers = sorted(movers, key=lambda x: x.get("rank_change_pct") or 0, reverse=True)
        return sorted_movers[:n]

    def _analyze_styles(self, products: list[dict]) -> dict:
        style_counter = Counter()
        for p in products:
            tags = self.extract_tags(p["name"])
            for _, label in tags["styles"]:
                style_counter[label] += 1
        return dict(style_counter.most_common(15))

    def _analyze_garments(self, products: list[dict]) -> dict:
        garment_counter = Counter()
        for p in products:
            tags = self.extract_tags(p["name"])
            for _, label in tags["garments"]:
                garment_counter[label] += 1
        return dict(garment_counter.most_common(15))

    # ------------------------------------------------------------------
    # 趋势分析（需要多天数据）
    # ------------------------------------------------------------------
    def analyze_trends(self, days: int = 7) -> dict:
        available_dates = self.storage.get_available_dates()
        if len(available_dates) < 2:
            return {"note": "数据不足2天，暂无法分析趋势。持续运行后将自动生成趋势报告。"}

        trending_up = self._filter_products(self.storage.get_trending_asins(days, min_appearances=2, limit=50))
        trending_monthly = self._filter_products(self.storage.get_trending_asins(days=30, min_appearances=2, limit=50))
        new_entries = self._filter_products(self.storage.get_new_entries(days=3))

        style_trend = self._style_trend_over_time(days)
        garment_trend = self._garment_trend_over_time(days)

        return {
            "data_days": len(available_dates),
            "trending_products": trending_up[:15],
            "trending_monthly": trending_monthly[:20],
            "new_entries": new_entries[:10],
            "style_momentum": style_trend,
            "garment_momentum": garment_trend,
        }

    def _style_trend_over_time(self, days: int) -> dict:
        dates = self.storage.get_available_dates()[:days]
        if len(dates) < 2:
            return {}
        style_by_date = {}
        for d in dates:
            products = self._filter_products(self.storage.get_products_by_date(date.fromisoformat(d)))
            counter = Counter()
            for p in products:
                tags = self.extract_tags(p["name"])
                for _, label in tags["styles"]:
                    counter[label] += 1
            style_by_date[d] = counter

        latest = style_by_date.get(dates[0], Counter())
        earliest = style_by_date.get(dates[-1], Counter())
        momentum = {}
        all_styles = set(latest.keys()) | set(earliest.keys())
        for style in all_styles:
            curr = latest.get(style, 0)
            prev = earliest.get(style, 0)
            if prev > 0:
                change = round((curr - prev) / prev * 100, 1)
            elif curr > 0:
                change = 100.0
            else:
                change = 0
            momentum[style] = {"current": curr, "previous": prev, "change_pct": change}

        return dict(sorted(momentum.items(), key=lambda x: x[1]["change_pct"], reverse=True))

    def _garment_trend_over_time(self, days: int) -> dict:
        dates = self.storage.get_available_dates()[:days]
        if len(dates) < 2:
            return {}
        garment_by_date = {}
        for d in dates:
            products = self._filter_products(self.storage.get_products_by_date(date.fromisoformat(d)))
            counter = Counter()
            for p in products:
                tags = self.extract_tags(p["name"])
                for _, label in tags["garments"]:
                    counter[label] += 1
            garment_by_date[d] = counter

        latest = garment_by_date.get(dates[0], Counter())
        earliest = garment_by_date.get(dates[-1], Counter())
        momentum = {}
        all_garments = set(latest.keys()) | set(earliest.keys())
        for g in all_garments:
            curr = latest.get(g, 0)
            prev = earliest.get(g, 0)
            if prev > 0:
                change = round((curr - prev) / prev * 100, 1)
            elif curr > 0:
                change = 100.0
            else:
                change = 0
            momentum[g] = {"current": curr, "previous": prev, "change_pct": change}

        return dict(sorted(momentum.items(), key=lambda x: x[1]["change_pct"], reverse=True))

    # ------------------------------------------------------------------
    # 未来一个月趋势预测
    # ------------------------------------------------------------------
    def predict_next_month(self, target_date: Optional[date] = None) -> dict:
        d = target_date or date.today()
        current_month = d.month
        next_month = current_month + 1 if current_month < 12 else 1

        seasonal_current = SEASONAL_INSIGHTS.get(current_month, "")
        seasonal_next = SEASONAL_INSIGHTS.get(next_month, "")

        trend_data = self.analyze_trends(days=14)
        summary = self.generate_daily_summary(d)
        current_products = self._filter_products(self.storage.get_products_by_date(d))
        predicted_products, google_status = self._build_predicted_products(
            current_products,
            trend_data,
        )

        rising_styles = []
        if trend_data.get("style_momentum"):
            rising_styles = [
                (style, info)
                for style, info in trend_data["style_momentum"].items()
                if info["change_pct"] > 0
            ][:8]

        rising_garments = []
        if trend_data.get("garment_momentum"):
            rising_garments = [
                (garment, info)
                for garment, info in trend_data["garment_momentum"].items()
                if info["change_pct"] > 0
            ][:8]

        hot_price_range = ""
        if summary.get("price_analysis", {}).get("price_ranges"):
            ranges = summary["price_analysis"]["price_ranges"]
            hot_price_range = max(ranges, key=ranges.get)

        prediction = {
            "generated_date": d.isoformat(),
            "prediction_period": f"{d.isoformat()} 起未来30天",
            "seasonal_context": seasonal_current,
            "seasonal_outlook": seasonal_next,
            "google_trends_status": google_status,
            "rising_styles": [
                {"style": s, "momentum": f"+{info['change_pct']}%"}
                for s, info in rising_styles
            ],
            "rising_garments": [
                {"garment": g, "momentum": f"+{info['change_pct']}%"}
                for g, info in rising_garments
            ],
            "hot_price_range": hot_price_range,
            "predicted_products": predicted_products,
            "recommendations": self._generate_recommendations(
                d, rising_styles, rising_garments, summary, trend_data, google_status
            ),
        }
        return prediction

    def _generate_recommendations(
        self, d: date, rising_styles, rising_garments, summary, trend_data, google_status: str
    ) -> list[str]:
        recs = []
        month = d.month

        if rising_styles:
            top3 = [s for s, _ in rising_styles[:3]]
            recs.append(f"🔥 风格趋势：{'、'.join(top3)} 热度持续上升，建议重点备货相关款式。")

        if rising_garments:
            top3 = [g for g, _ in rising_garments[:3]]
            recs.append(f"💎 品类机会：{'、'.join(top3)} 在畅销榜中占比增长，是近期主力出单品类。")

        price_info = summary.get("price_analysis", {})
        if price_info.get("avg"):
            recs.append(
                f"💰 定价建议：畅销品均价 ${price_info['avg']}，"
                f"中位数 ${price_info.get('median', 'N/A')}。"
                f"建议主力款定价在此区间以保持竞争力。"
            )

        if 3 <= month <= 5:
            recs.append("🌸 春季选品：轻薄丝巾/披肩换季需求大，花卉/蝴蝶元素发饰热销。太阳镜开始上量。母亲节（5月）珍珠/心形首饰是爆款礼品方向。")
        elif 6 <= month <= 8:
            recs.append("☀️ 夏季选品：太阳镜、遮阳帽/草帽是绝对主力。发饰（鲨鱼夹、大肠发圈）需求量大。7月Prime Day重点冲平价首饰和发饰。波西米亚风编绳手链/贝壳项链是夏季爆款方向。")
        elif 9 <= month <= 11:
            recs.append("🍂 秋冬选品：围巾/帽子/手套进入旺季，套装礼盒是高客单价方向。10月万圣节主题配饰（骷髅/蜘蛛/南瓜）可短期冲量。11月黑五是首饰全年最大促销机会，提前备足库存。")
        else:
            recs.append("❄️ 冬季选品：围巾+帽子+手套套装礼盒是圣诞爆款。首饰礼品套装（项链+耳环）送礼需求极高。圣诞元素（红/绿/金/雪花）配饰短期热销。跨年派对水钻/亮片饰品需求上升。")

        top_movers = summary.get("top_movers", [])
        if top_movers:
            mover_names = [m["name"][:40] for m in top_movers[:3]]
            recs.append(
                f"🚀 飙升商品参考：以下商品近期销量飙升，值得研究其卖点和关键词 —— "
                + "；".join(mover_names)
            )

        if google_status != "ok":
            recs.append("🌐 Google 搜索热度当前未稳定获取，预测榜已自动降级为 Amazon 榜单 + 历史趋势综合评分。")

        return recs
