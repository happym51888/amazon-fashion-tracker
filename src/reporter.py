"""
HTML 邮件报告生成与发送模块

生成美观的中文 HTML 邮件报告，通过 SMTP 发送并支持可选图片内嵌。
"""

import logging
import math
import mimetypes
import smtplib
import ssl
from datetime import date
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from jinja2 import Template

from .product_filters import should_exclude_product
from .profile_utils import get_profile_meta

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML 邮件模板
# ---------------------------------------------------------------------------
REPORT_TEMPLATE = Template("""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body { margin: 0; padding: 0; background: #f4f5f7; font-family: -apple-system, "Microsoft YaHei", "PingFang SC", sans-serif; color: #1f2430; }
  .container { max-width: 820px; margin: 0 auto; background: #ffffff; }
  .header { background: linear-gradient(135deg, #0f3460, #16213e); padding: 30px 28px; color: #ffffff; }
  .header h1 { margin: 0 0 8px; font-size: 24px; }
  .header .sub { color: #c8d6f0; font-size: 13px; line-height: 1.7; }
  .section { padding: 24px 28px; border-bottom: 1px solid #ebedf0; }
  .section-title { margin: 0 0 8px; font-size: 20px; color: #0f3460; }
  .section-desc { margin: 0 0 16px; font-size: 13px; color: #667085; line-height: 1.7; }
  .summary-box { background: #f8faff; border: 1px solid #dbe7ff; border-radius: 10px; padding: 16px 18px; font-size: 14px; line-height: 1.9; white-space: pre-line; }
  .stat-strip { margin-top: 14px; font-size: 12px; color: #c8d6f0; line-height: 1.8; }
  .product-row { width: 100%; margin: 0 0 14px; border: 1px solid #e9edf3; border-collapse: separate; border-spacing: 0; background: #fcfdff; border-radius: 10px; }
  .product-image-cell { width: 156px; padding: 14px; background: #ffffff; vertical-align: top; }
  .product-image { display: block; width: 128px; height: 128px; object-fit: contain; margin: 0 auto; }
  .product-info { padding: 14px 16px; vertical-align: top; }
  .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; color: #ffffff; margin-right: 8px; }
  .badge-hot { background: #e94560; }
  .badge-mover { background: #16a34a; }
  .badge-prediction { background: #f59e0b; }
  .pill { display: inline-block; background: #f2f4f7; color: #475467; padding: 4px 8px; border-radius: 999px; font-size: 11px; margin: 4px 6px 0 0; }
  .name { margin: 10px 0 8px; font-size: 15px; line-height: 1.6; font-weight: 700; }
  .name a { color: #1f2430; text-decoration: none; }
  .name a:hover { text-decoration: underline; }
  .meta { font-size: 12px; color: #667085; line-height: 1.8; }
  .reason { margin-top: 10px; font-size: 12px; color: #c2410c; line-height: 1.7; font-weight: 600; }
  .footer { background: #f8f9fc; padding: 18px 28px; text-align: center; font-size: 12px; color: #98a2b3; }
  @media (max-width: 600px) {
    .product-row, .product-row tbody, .product-row tr, .product-image-cell, .product-info { display: block; width: 100% !important; box-sizing: border-box; }
    .product-image { width: 150px; height: 150px; }
  }
</style>
</head>
<body>
{% macro render_row(p, badge_text, badge_class, mode='hot', google_status='ok') -%}
<table class="product-row" role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td class="product-image-cell" width="156">
      {% if p.product_url %}<a href="{{ p.product_url }}" target="_blank">{% endif %}
      {% if p.image_url %}
      <img class="product-image" src="{{ p.image_url }}" alt="{{ p.name[:40] }}" loading="lazy">
      {% else %}
      <div class="product-image" style="line-height:128px; text-align:center; color:#98a2b3;">暂无图片</div>
      {% endif %}
      {% if p.product_url %}</a>{% endif %}
    </td>
    <td class="product-info">
      <div>
        <span class="badge {{ badge_class }}">{{ badge_text }}</span>
        {% if p.price %}<span class="pill">价格 {{ p.price }}</span>{% endif %}
        {% if p.rating %}<span class="pill">评分 {{ p.rating }}</span>{% endif %}
        {% if p.review_count %}<span class="pill">{{ p.review_count }} 评价</span>{% endif %}
        <span class="pill">{{ category_names.get(p.category, p.category) }}</span>
        {% if mode == 'mover' and p.rank_change_pct %}<span class="pill">飙升 {{ p.rank_change_pct }}%</span>{% endif %}
        {% if mode == 'mover' and p.rank_improvement %}<span class="pill">近14天上升 {{ p.rank_improvement }} 位</span>{% endif %}
        {% if mode == 'prediction' %}
          {% if p.google_trend_score is not none %}
          <span class="pill">Google热度 {{ p.google_trend_score }}</span>
          {% elif google_status != 'ok' %}
          <span class="pill">Google热度暂不可用</span>
          {% endif %}
        {% endif %}
      </div>
      <div class="name">
        {% if p.product_url %}<a href="{{ p.product_url }}" target="_blank">{{ p.name[:120] }}</a>{% else %}{{ p.name[:120] }}{% endif %}
      </div>
      <div class="meta">
        亚马逊榜单名次 {{ p.rank or '-' }}
        {% if p.mover_rank %} · 飙升榜名次 {{ p.mover_rank }}{% endif %}
        {% if mode == 'mover' and p.appearances %} · 连续上榜 {{ p.appearances }} 天{% endif %}
        {% if mode == 'prediction' and p.google_trend_delta %}
          · 近月搜索变化 {{ '%+g'|format(p.google_trend_delta) }}
        {% endif %}
        {% if p._search_query %} · 搜索词 {{ p._search_query }}{% endif %}
      </div>
      {% if mode == 'prediction' and p._prediction_reason %}
      <div class="reason">预测依据：{{ p._prediction_reason }}</div>
      {% elif mode == 'mover' %}
      <div class="reason">飙升依据：{% if p.rank_change_pct %}官方飙升榜显示涨幅 {{ p.rank_change_pct }}%{% elif p.rank_improvement %}近 14 天榜位上升 {{ p.rank_improvement }} 位{% else %}进入飙升池{% endif %}</div>
      {% endif %}
    </td>
  </tr>
</table>
{%- endmacro %}
<div class="container">
  <div class="header">
    <h1>{{ header_icon }} {{ report_title }}</h1>
    <div class="sub">{{ report_date }} | {{ season_label }} | 美国站 Amazon 榜单</div>
    <div class="stat-strip">
      畅销榜 {{ summary.bestseller_count }} 款
      {% if summary.mover_count is not none %} · 飙升榜 {{ summary.mover_count }} 款{% endif %}
      {% if summary.price_analysis and summary.price_analysis.avg %} · 均价 ${{ summary.price_analysis.avg }} · 中位数 ${{ summary.price_analysis.median }}{% endif %}
    </div>
  </div>

  {% if top_bestsellers %}
  <div class="section">
    <h2 class="section-title">🔥 爆款 1-{{ top_bestsellers|length }}</h2>
    <p class="section-desc">按 Amazon 畅销榜顺序展示，每条保留图片、价格、评分、评价数和类目信息。</p>
    {% for p in top_bestsellers %}
      {{ render_row(p, "爆款 #" ~ loop.index, "badge-hot", "hot") }}
    {% endfor %}
  </div>
  {% endif %}

  {% if top_movers %}
  <div class="section">
    <h2 class="section-title">🚀 飙升爆款 1-{{ top_movers|length }}</h2>
    <p class="section-desc">{{ mover_section_note }}</p>
    {% for p in top_movers %}
      {{ render_row(p, "飙升 #" ~ loop.index, "badge-mover", "mover") }}
    {% endfor %}
  </div>
  {% endif %}

  {% if predicted_products %}
  <div class="section">
    <h2 class="section-title">🔮 预测 1-{{ predicted_products|length }}</h2>
    <p class="section-desc">
      基于爆款榜、飙升榜、历史趋势和 Google 搜索热度综合评分。
      {% if google_trends_status != 'ok' %}当前 Google 热度未稳定获取，本次自动降级为 Amazon 趋势预测。{% endif %}
    </p>
    {% for p in predicted_products %}
      {{ render_row(p, "预测 #" ~ loop.index, "badge-prediction", "prediction", google_trends_status) }}
    {% endfor %}
  </div>
  {% endif %}

  {% if executive_summary %}
  <div class="section">
    <h2 class="section-title">📝 总结</h2>
    <div class="summary-box">{{ executive_summary }}</div>
  </div>
  {% endif %}

  <div class="footer">
    <p>此邮件由 {{ report_title }} 自动生成</p>
    <p>数据仅供选品参考，不构成采购承诺</p>
  </div>
</div>
</body>
</html>
""")


class ReportGenerator:
    def __init__(self, config: dict):
        self.config = config
        self.profile_meta = get_profile_meta(config)
        report_cfg = config.get("report", {})
        prediction_cfg = config.get("prediction", {})
        email_cfg = config.get("email", {})
        self.smtp_server = email_cfg.get("smtp_server", "smtp.qq.com")
        self.smtp_port = email_cfg.get("smtp_port", 465)
        self.use_ssl = email_cfg.get("use_ssl", True)
        self.sender = email_cfg.get("sender", "")
        self.password = email_cfg.get("password", "")
        self.recipients = email_cfg.get("recipients", [])
        self.top_n = report_cfg.get("top_n", 20)
        self.bestseller_limit = report_cfg.get("bestseller_limit", self.top_n)
        self.mover_limit = report_cfg.get("mover_limit", self.top_n)
        self.prediction_limit = prediction_cfg.get("top_n", 10)
        self.embed_images = report_cfg.get("embed_images", False)
        self.exclude_keywords = [
            kw.lower() for kw in report_cfg.get("exclude_keywords", [])
        ]

    def _is_excluded(self, product_name: str) -> bool:
        return should_exclude_product(product_name, self.exclude_keywords)

    @staticmethod
    def _dedupe_by_asin(products: list[dict], sort_key: str, ascending: bool = True) -> list[dict]:
        seen = set()
        deduped = []
        sorted_list = sorted(
            products,
            key=lambda x: x.get(sort_key) or 0,
            reverse=not ascending,
        )
        for p in sorted_list:
            asin = p.get("asin")
            if asin and asin in seen:
                continue
            if asin:
                seen.add(asin)
            deduped.append(p)
        return deduped

    @staticmethod
    def _global_dedupe(products: list[dict]) -> list[dict]:
        """按 ASIN 或名称去重，保留首次出现"""
        seen = set()
        result = []
        for p in products:
            dedupe_key = p.get("asin") or (p.get("name") or "").strip().lower()
            if dedupe_key in seen:
                continue
            if dedupe_key:
                seen.add(dedupe_key)
            result.append(p)
        return result

    def _group_by_category(self, products: list[dict], category_names: dict) -> list[dict]:
        """按类目分组，每组内按 rank 排序"""
        from collections import OrderedDict
        groups = OrderedDict()
        for p in products:
            cat = p.get("category", "other")
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(p)
        result = []
        for cat_key, items in groups.items():
            result.append({
                "key": cat_key,
                "name": category_names.get(cat_key, cat_key),
                "products": sorted(items, key=lambda x: x.get("rank") or 999)[:10],
            })
        return result

    @staticmethod
    def _extract_price_value(price_str: Optional[str]) -> Optional[float]:
        if not price_str:
            return None
        import re

        match = re.search(r"(\d+\.?\d*)", price_str.replace(",", ""))
        return float(match.group(1)) if match else None

    def _score_comprehensive_product(self, product: dict) -> tuple[float, str]:
        score = 0.0
        reasons = []

        rank = product.get("rank") or 999
        if rank <= 3:
            score += 40
            reasons.append(f"榜单Top{rank}")
        elif rank <= 10:
            score += 32
            reasons.append(f"榜单Top{rank}")
        elif rank <= 20:
            score += 20
        elif rank <= 30:
            score += 10

        mover_pct = product.get("rank_change_pct") or 0
        if mover_pct >= 200:
            score += 28
            reasons.append(f"飙升{int(mover_pct)}%")
        elif mover_pct >= 100:
            score += 20
            reasons.append(f"飙升{int(mover_pct)}%")
        elif mover_pct >= 50:
            score += 12

        rating = product.get("rating") or 0
        if rating:
            score += rating * 6
            if rating >= 4.6:
                reasons.append(f"评分{rating}")

        review_count = product.get("review_count") or 0
        if review_count:
            score += min(24.0, math.log10(review_count + 1) * 8)
            if review_count >= 5000:
                reasons.append(f"{review_count:,}+评价")
            elif review_count >= 1000:
                reasons.append(f"{review_count:,}评价")

        price_value = self._extract_price_value(product.get("price"))
        if price_value is not None:
            if 10 <= price_value <= 35:
                score += 10
                reasons.append("主流价格带")
            elif 35 < price_value <= 60:
                score += 6

        return score, "、".join(reasons[:3]) if reasons else "综合表现稳定"

    def _build_comprehensive_ranking(self, products: list[dict]) -> list[dict]:
        scored = []
        for product in products:
            score, reason = self._score_comprehensive_product(product)
            scored.append({**product, "_score": round(score, 1), "_reason": reason})

        scored.sort(
            key=lambda x: (
                -x["_score"],
                -(x.get("rank_change_pct") or 0),
                -(x.get("rating") or 0),
                -(x.get("review_count") or 0),
                x.get("rank") or 999,
            )
        )

        ranking = []
        seen = set()
        for product in scored:
            dedupe_key = product.get("asin") or (product.get("name") or "").lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            ranking.append(product)
            if len(ranking) >= self.top_n:
                break

        for index, product in enumerate(ranking, start=1):
            product["overall_rank"] = index
        return ranking

    def _generate_executive_summary(
        self,
        summary: dict,
        top_bestsellers: list,
        top_movers: list,
        predicted_products: list,
        prediction: dict,
        category_names: dict,
    ) -> str:
        """生成老板可直接阅读的简短总结"""
        lines = []
        d = summary.get("date", "")
        lines.append(f"{d} 共跟踪畅销商品 {summary.get('bestseller_count', 0)} 款。")

        price = summary.get("price_analysis", {})
        if price.get("avg"):
            lines.append(
                f"当前主流价格带在 ${price['avg']} 均价附近，中位数 ${price.get('median', 'N/A')}。"
            )

        if top_bestsellers:
            top_names = [
                f"{category_names.get(p.get('category'), p.get('category', '未知类目'))} / {p['name'][:24]}"
                for p in top_bestsellers[:3]
            ]
            lines.append(f"今日爆款头部集中在：{'；'.join(top_names)}。")

        if top_movers:
            mover = top_movers[0]
            mover_label = category_names.get(mover.get("category"), mover.get("category", "未知类目"))
            if mover.get("rank_change_pct"):
                lines.append(
                    f"飙升最强的是 {mover_label} 类目商品《{mover['name'][:28]}》，涨幅 {mover['rank_change_pct']}%。"
                )
            elif mover.get("rank_improvement"):
                lines.append(
                    f"近 14 天上升最快的是 {mover_label} 类目商品《{mover['name'][:28]}》，榜位提升 {mover['rank_improvement']} 位。"
                )

        if predicted_products:
            prediction_names = [p["name"][:24] for p in predicted_products[:3]]
            lines.append(f"未来 30 天建议优先关注：{'、'.join(prediction_names)}。")

        if prediction.get("google_trends_status") != "ok":
            lines.append("Google 搜索热度当前未稳定获取，本次预测已自动回退到 Amazon 榜单与历史趋势综合评分。")

        return "\n".join(lines)

    def _predict_hot_picks(self, all_bestsellers: list, summary: dict, prediction: dict) -> list[dict]:
        """预测可能成为爆款的单品"""
        picks = []
        for p in all_bestsellers:
            score = 0
            review_count = p.get("review_count") or 0
            rating = p.get("rating") or 0
            rank = p.get("rank") or 999

            if rank <= 5:
                score += 30
            elif rank <= 15:
                score += 15

            if rating >= 4.5:
                score += 20
            elif rating >= 4.0:
                score += 10

            if review_count >= 10000:
                score += 25
            elif review_count >= 3000:
                score += 15
            elif review_count >= 500:
                score += 5

            price_str = p.get("price", "")
            if price_str:
                import re
                m = re.search(r"(\d+\.?\d*)", price_str.replace(",", ""))
                if m:
                    price_val = float(m.group(1))
                    if 5 <= price_val <= 25:
                        score += 15
                    elif 25 < price_val <= 50:
                        score += 8

            name_lower = (p.get("name") or "").lower()
            hot_terms = ["set", "pack", "gift", "trendy", "viral", "aesthetic",
                         "y2k", "vintage", "boho", "pearl", "gold", "layered",
                         "claw clip", "scrunchie", "chunky", "statement"]
            for term in hot_terms:
                if term in name_lower:
                    score += 5

            picks.append({**p, "_score": score})

        picks.sort(key=lambda x: x["_score"], reverse=True)

        seen = set()
        unique_picks = []
        for p in picks:
            asin = p.get("asin")
            if asin in seen:
                continue
            seen.add(asin)
            reason = []
            rank = p.get("rank") or 999
            if rank <= 5:
                reason.append(f"排名Top{rank}")
            if (p.get("rating") or 0) >= 4.5:
                reason.append(f"高评分{p['rating']}")
            rc = p.get("review_count") or 0
            if rc >= 3000:
                reason.append(f"{rc}+评价验证")
            price_str = p.get("price", "")
            if price_str:
                import re
                m = re.search(r"(\d+\.?\d*)", price_str.replace(",", ""))
                if m and float(m.group(1)) <= 25:
                    reason.append("高性价比")
            p["_reason"] = "、".join(reason) if reason else "综合评分高"
            unique_picks.append(p)
            if len(unique_picks) >= 6:
                break
        return unique_picks

    def build_html(
        self,
        summary: dict,
        prediction: dict,
        trends: dict,
        all_products: list[dict],
    ) -> str:
        filtered = [p for p in all_products if not self._is_excluded(p.get("name", ""))]

        bestsellers = sorted(
            [p for p in filtered if p["source"] == "bestseller"],
            key=lambda x: x.get("rank") or 999,
        )
        bestsellers = self._global_dedupe(bestsellers)
        movers = sorted(
            [p for p in filtered if p["source"] == "mover"],
            key=lambda x: x.get("rank_change_pct") or 0,
            reverse=True,
        )
        movers = self._global_dedupe(movers)
        mover_section_note = "按 Amazon 飙升幅度排序，重点看哪些款式正在突然放量。"
        top_movers = movers[: self.mover_limit]
        if not top_movers and trends and trends.get("trending_products"):
            mover_section_note = "Amazon 飙升榜当日可用数据较少，以下改用近 14 天持续上升商品补齐。"
            top_movers = [
                {**item, "rank": item.get("latest_rank") or item.get("rank")}
                for item in trends.get("trending_products", [])[: self.mover_limit]
            ]

        category_names = {}
        for key, info in self.config.get("scraper", {}).get("categories", {}).items():
            category_names[key] = info.get("name", key)

        month = date.today().month
        if self.profile_meta["id"] == "accessories":
            if month in {10, 11, 12, 1, 2, 3}:
                season_label = "❄️ 冬季模式（围巾/帽子/手套 + 首饰/配饰）"
            else:
                season_label = "☀️ 夏季模式（头饰/发饰/太阳镜 + 首饰/配饰）"
        else:
            season_label = self.profile_meta["season_label"]

        predicted_products = (prediction.get("predicted_products") or [])[: self.prediction_limit]
        executive_summary = self._generate_executive_summary(
            summary,
            bestsellers[: self.bestseller_limit],
            top_movers,
            predicted_products,
            prediction,
            category_names,
        )

        html = REPORT_TEMPLATE.render(
            report_date=summary.get("date", date.today().isoformat()),
            summary=summary,
            top_bestsellers=bestsellers[: self.bestseller_limit],
            top_movers=top_movers,
            mover_section_note=mover_section_note,
            predicted_products=predicted_products,
            google_trends_status=prediction.get("google_trends_status", "unavailable"),
            category_names=category_names,
            season_label=season_label,
            executive_summary=executive_summary,
            report_title=self.profile_meta["report_title"],
            header_icon=self.profile_meta["header_icon"],
        )
        return html

    def send_email(
        self,
        html_content: str,
        subject: Optional[str] = None,
        image_paths: Optional[list[Path]] = None,
    ):
        if not self.sender or not self.password:
            logger.error("邮件配置不完整，请检查 config.yaml 中的 email 配置")
            return False

        report_date = date.today().isoformat()
        if not subject:
            subject = f"{self.profile_meta['header_icon']} {self.profile_meta['report_title']} - {report_date}"

        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)

        msg_alt = MIMEMultipart("alternative")
        msg.attach(msg_alt)
        msg_alt.attach(MIMEText(html_content, "html", "utf-8"))

        if self.embed_images and image_paths:
            for img_path in image_paths:
                try:
                    p = Path(img_path)
                    if not p.exists():
                        continue
                    mime_type = mimetypes.guess_type(str(p))[0] or "image/jpeg"
                    maintype, subtype = mime_type.split("/")
                    with open(p, "rb") as f:
                        img_data = MIMEImage(f.read(), _subtype=subtype)
                    img_data.add_header("Content-ID", f"<{p.stem}>")
                    img_data.add_header("Content-Disposition", "inline", filename=p.name)
                    msg.attach(img_data)
                except Exception as e:
                    logger.debug("嵌入图片失败 (%s): %s", img_path, e)

        try:
            if self.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=context) as server:
                    server.login(self.sender, self.password)
                    server.sendmail(self.sender, self.recipients, msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.sender, self.password)
                    server.sendmail(self.sender, self.recipients, msg.as_string())
            logger.info("✅ 邮件发送成功 -> %s", ", ".join(self.recipients))
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("❌ 邮件认证失败，请检查发件人账号和授权码")
        except smtplib.SMTPException as e:
            logger.error("❌ 邮件发送失败: %s", e)
        except Exception as e:
            logger.error("❌ 邮件发送异常: %s", e)
        return False

    def save_html_report(self, html_content: str, output_dir: Optional[str] = None) -> Path:
        out_dir = output_dir or self.config.get("report", {}).get("output_dir") or self.profile_meta["report_dir"]
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        filepath = out / f"report_{self.profile_meta['id']}_{date.today().isoformat()}.html"
        filepath.write_text(html_content, encoding="utf-8")
        logger.info("报告已保存至: %s", filepath)
        return filepath
