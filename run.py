"""
Amazon 服装趋势追踪器 — 主入口

用法:
    python run.py              # 立即执行一次抓取+分析+发送
    python run.py --schedule   # 启动定时任务，每天定时执行
    python run.py --no-email   # 只抓取分析，不发邮件（调试用）
    python run.py --report-only # 不抓取，只根据已有数据生成报告
"""

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.scraper import AmazonFashionScraper
from src.storage import Storage
from src.analyzer import FashionAnalyzer
from src.reporter import ReportGenerator
from src.profile_utils import get_profile_meta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("FashionTracker")


def load_config() -> dict:
    cfg_path = ROOT / "config.yaml"
    if not cfg_path.exists():
        logger.error("❌ 找不到 config.yaml，请先从 config.example.yaml 复制并填写配置")
        sys.exit(1)
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def configure_logging(config: dict) -> None:
    log_path = config.get("logging", {}).get("log_file")
    handlers = [logging.StreamHandler()]

    if log_path:
        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def run_once(config: dict, send_email: bool = True, scrape: bool = True):
    """执行一次完整流程：抓取 → 存储 → 分析 → 生成报告 → 发邮件"""
    storage = Storage(config)
    today = date.today()
    profile_meta = get_profile_meta(config)

    try:
        if scrape:
            logger.info("=" * 60)
            logger.info("开始抓取 Amazon %s数据 (%s)", profile_meta["log_label"], today.isoformat())
            logger.info("=" * 60)

            scraper = AmazonFashionScraper(config)
            raw_data = scraper.scrape_all()

            all_products = []
            for cat_data in raw_data.values():
                all_products.extend(cat_data.get("bestsellers", []))
                all_products.extend(cat_data.get("movers", []))

            if not all_products:
                logger.warning("⚠️ 未抓取到任何数据，可能被 Amazon 限制。请稍后重试。")
                return

            storage.save_products(all_products, today)
            logger.info("✅ 数据抓取完成，共 %d 个商品", len(all_products))

        # 分析
        logger.info("开始数据分析...")
        analyzer = FashionAnalyzer(storage, config)
        summary = analyzer.generate_daily_summary(today)
        trends = analyzer.analyze_trends(days=14)
        prediction = analyzer.predict_next_month(today)

        storage.save_daily_summary(today, summary, prediction)
        logger.info("✅ 分析完成")

        # 生成报告
        logger.info("生成 HTML 报告...")
        reporter = ReportGenerator(config)
        all_today = storage.get_products_by_date(today)
        html = reporter.build_html(summary, prediction, trends, all_today)

        report_path = reporter.save_html_report(html)
        logger.info("✅ 报告已保存: %s", report_path)

        # 发送邮件
        if send_email:
            logger.info("发送邮件...")
            image_paths = None
            if config.get("report", {}).get("embed_images", False):
                image_dir = Path(config.get("storage", {}).get("image_dir", "data/images"))
                image_paths = list(image_dir.glob("*.jpg"))[:50] if image_dir.exists() else []
            reporter.send_email(html, image_paths=image_paths)

        logger.info("🎉 本次任务全部完成！")

    except Exception as e:
        logger.exception("❌ 执行过程中发生错误: %s", e)
    finally:
        storage.close()


def run_scheduled(config: dict):
    """启动定时调度，每天在指定时间执行"""
    try:
        import schedule
    except ImportError:
        logger.error("请安装 schedule: pip install schedule")
        sys.exit(1)

    run_time = config.get("schedule", {}).get("run_time", "08:00")
    logger.info("🕐 定时任务已启动，每天 %s 执行", run_time)
    logger.info("按 Ctrl+C 停止")

    schedule.every().day.at(run_time).do(run_once, config=config)

    # 如果今天还没运行过且当前时间已过执行时间，立即运行一次
    try:
        storage = Storage(config)
        dates = storage.get_available_dates()
        storage.close()
        if not dates or dates[0] != date.today().isoformat():
            logger.info("今日尚未执行，立即运行一次...")
            run_once(config)
    except Exception:
        pass

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Amazon 趋势追踪器")
    parser.add_argument("--schedule", action="store_true", help="启动定时调度模式")
    parser.add_argument("--no-email", action="store_true", help="不发送邮件（调试用）")
    parser.add_argument("--report-only", action="store_true", help="仅生成报告，不重新抓取")
    args = parser.parse_args()

    config = load_config()
    configure_logging(config)

    if args.schedule:
        run_scheduled(config)
    else:
        run_once(
            config,
            send_email=not args.no_email,
            scrape=not args.report_only,
        )


if __name__ == "__main__":
    main()
