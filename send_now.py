"""立即发送报告邮件"""

import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("SendNow")

import yaml
from src.storage import Storage
from src.analyzer import FashionAnalyzer
from src.reporter import ReportGenerator
from src.profile_utils import get_profile_meta

with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

storage = Storage(config)
available = storage.get_available_dates()
if not available:
    logger.error("No data found!")
    sys.exit(1)

data_date = date.fromisoformat(available[0])
logger.info("Data date: %s", data_date)

analyzer = FashionAnalyzer(storage, config)
summary = analyzer.generate_daily_summary(data_date)
trends = analyzer.analyze_trends(days=14)
prediction = analyzer.predict_next_month(data_date)

reporter = ReportGenerator(config)
profile_meta = get_profile_meta(config)
all_products = storage.get_products_by_date(data_date)
logger.info("Products: %d", len(all_products))

html = reporter.build_html(summary, prediction, trends, all_products)
subject = f"{profile_meta['header_icon']} {profile_meta['report_title']} - {data_date.isoformat()}"

if reporter.send_email(html, subject=subject):
    logger.info("SUCCESS! Email sent to %s", reporter.recipients)
else:
    logger.error("Send failed.")

storage.close()
