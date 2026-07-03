"""
配置档案辅助工具

统一判断当前运行的是饰品版还是服装版，并提供对应的显示文案。
"""

from __future__ import annotations


def detect_profile(config: dict) -> str:
    categories = config.get("scraper", {}).get("categories", {})
    category_keys = set(categories.keys())
    db_path = str(config.get("storage", {}).get("db_path", "")).lower()

    if "clothing" in db_path:
        return "clothing"
    if any(key.startswith(("womens_", "mens_")) for key in category_keys):
        return "clothing"
    return "accessories"


def get_profile_meta(config: dict) -> dict:
    profile = detect_profile(config)
    if profile == "clothing":
        return {
            "id": "clothing",
            "report_title": "Amazon 服装趋势日报",
            "short_title": "服装趋势日报",
            "header_icon": "👗",
            "log_label": "服装",
            "season_label": "👗 服装模式（女装 / 男装 / 连衣裙 / 上衣等）",
            "report_dir": "data/reports_clothing",
        }

    return {
        "id": "accessories",
        "report_title": "Amazon 饰品配饰趋势日报",
        "short_title": "饰品配饰趋势日报",
        "header_icon": "📿",
        "log_label": "饰品配饰",
        "season_label": "❄️ 冬季模式（围巾/帽子/手套 + 首饰/配饰）",
        "report_dir": "data/reports_accessories",
    }
