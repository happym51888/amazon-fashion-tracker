"""
Google Trends 热度抓取。

优先尝试查询美国区 Google Trends，用于给预测商品增加搜索热度参考。
如果本机网络无法访问 Google，则静默降级，不影响日报主流程。
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from statistics import mean

import requests

logger = logging.getLogger(__name__)

_JSON_PREFIX = ")]}',"


class GoogleTrendsClient:
    def __init__(self, config: dict):
        prediction_cfg = config.get("prediction", {})
        self.enabled = prediction_cfg.get("google_trends_enabled", True)
        self.geo = prediction_cfg.get("google_geo", "US")
        self.timeframe = prediction_cfg.get("google_timeframe", "today 3-m")
        self.timeout = prediction_cfg.get("google_timeout", 4)
        self.hl = prediction_cfg.get("google_hl", "en-US")
        self.tz = prediction_cfg.get("google_tz", 360)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                "Accept-Language": f"{self.hl},en;q=0.9",
            }
        )
        self._service_available: bool | None = None

    def fetch_scores(
        self, keywords: list[str], anchor_keyword: str | None = None
    ) -> tuple[dict[str, dict], str]:
        cleaned = []
        seen = set()
        for keyword in keywords:
            term = (keyword or "").strip()
            if not term:
                continue
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(term)

        if not self.enabled or not cleaned:
            return {}, "disabled"

        if not self._check_service_available():
            return {}, "unavailable"

        results: dict[str, dict] = {}
        batch_size = 4 if anchor_keyword else 5
        for idx in range(0, len(cleaned), batch_size):
            batch = cleaned[idx : idx + batch_size]
            try:
                batch_results = self._fetch_batch(batch, anchor_keyword)
            except Exception as exc:
                logger.info("Google Trends 查询失败，自动降级: %s", exc)
                return results, "partial" if results else "unavailable"
            results.update(batch_results)

        return results, "ok" if results else "unavailable"

    def _check_service_available(self) -> bool:
        if self._service_available is not None:
            return self._service_available

        try:
            resp = self.session.get(
                "https://trends.google.com/trends/",
                timeout=self.timeout,
            )
            self._service_available = resp.ok
        except requests.RequestException as exc:
            logger.info("Google Trends 当前不可达，将跳过热度评分: %s", exc)
            self._service_available = False

        return self._service_available

    def _fetch_batch(
        self, keywords: list[str], anchor_keyword: str | None = None
    ) -> dict[str, dict]:
        comparison_keywords = list(keywords)
        if (
            anchor_keyword
            and anchor_keyword.strip()
            and anchor_keyword.lower() not in {kw.lower() for kw in comparison_keywords}
            and len(comparison_keywords) < 5
        ):
            comparison_keywords.append(anchor_keyword.strip())

        payload = {
            "comparisonItem": [
                {"keyword": kw, "geo": self.geo, "time": self.timeframe}
                for kw in comparison_keywords
            ],
            "category": 0,
            "property": "",
        }
        explore_data = self._request_json(
            "https://trends.google.com/trends/api/explore",
            {"hl": self.hl, "tz": self.tz, "req": json.dumps(payload, separators=(",", ":"))},
        )

        widgets = explore_data.get("widgets", [])
        widget = next((item for item in widgets if item.get("id") == "TIMESERIES"), None)
        if not widget:
            raise RuntimeError("Google Trends 未返回 TIMESERIES widget")

        timeline_data = self._request_json(
            "https://trends.google.com/trends/api/widgetdata/multiline",
            {
                "hl": self.hl,
                "tz": self.tz,
                "req": json.dumps(widget["request"], separators=(",", ":")),
                "token": widget["token"],
            },
        )

        timeline = timeline_data.get("default", {}).get("timelineData", [])
        series_map = {kw: [] for kw in comparison_keywords}
        for point in timeline:
            values = point.get("value", [])
            for idx, value in enumerate(values):
                if idx >= len(comparison_keywords):
                    continue
                if isinstance(value, (int, float)):
                    series_map[comparison_keywords[idx]].append(float(value))

        anchor_values = series_map.get(anchor_keyword or "", [])
        anchor_avg = mean(anchor_values) if anchor_values else None

        batch_results = {}
        for keyword in keywords:
            values = series_map.get(keyword, [])
            if not values:
                continue

            recent_window = values[-4:] if len(values) >= 4 else values
            previous_window = values[-8:-4] if len(values) >= 8 else values[:-4]

            current = round(mean(recent_window), 1)
            previous = round(mean(previous_window), 1) if previous_window else current
            delta = round(current - previous, 1)
            normalized = current
            if anchor_avg and anchor_avg > 0:
                normalized = round(current / anchor_avg * 100, 1)

            batch_results[keyword] = {
                "current": current,
                "previous": previous,
                "delta": delta,
                "normalized": normalized,
            }

        return batch_results

    def _request_json(self, url: str, params: dict) -> dict:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        text = resp.text.lstrip()
        if text.startswith(_JSON_PREFIX):
            text = text[len(_JSON_PREFIX) :].lstrip()
        return json.loads(text)
