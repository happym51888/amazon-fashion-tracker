"""
服装版 — 一键运行

用法:
    python run_clothing.py              # 抓取 + 分析 + 发邮件
    python run_clothing.py --no-email   # 只抓取分析不发邮件
    python run_clothing.py --schedule   # 每天定时执行
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
clothing_cfg = ROOT / "profiles" / "config-clothing.yaml"
accessories_cfg = ROOT / "profiles" / "config-accessories.yaml"
active_cfg = ROOT / "config.yaml"

backup = None
if active_cfg.exists():
    backup = active_cfg.read_text(encoding="utf-8")

shutil.copy2(clothing_cfg, active_cfg)

try:
    sys.argv[0] = str(ROOT / "run.py")
    exec(open(ROOT / "run.py", encoding="utf-8").read())
finally:
    if backup is not None:
        active_cfg.write_text(backup, encoding="utf-8")
    else:
        # No prior active config: default back to accessories mode to avoid
        # accidentally leaving the whole project in clothing mode.
        shutil.copy2(accessories_cfg, active_cfg)
