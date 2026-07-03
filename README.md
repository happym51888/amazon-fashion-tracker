# Amazon 服装趋势追踪器

自动追踪 Amazon 美国站服装品类畅销榜和飙升榜数据，生成包含商品图片、销量排名、飙升率、风格趋势分析和未来流行预测的每日邮件报告。专为中国外贸服装卖家设计。

## 功能

| 功能 | 说明 |
|------|------|
| **畅销榜抓取** | 每日抓取 Amazon 服装类 Best Sellers 排行榜数据 |
| **飙升榜抓取** | 抓取 Movers & Shakers 数据，获取销量增长百分比 |
| **商品图片** | 自动下载并嵌入商品主图到邮件 |
| **价格分析** | 统计畅销品价格分布、均价、中位数 |
| **风格标签** | 自动识别商品风格标签（复古、运动休闲、极简风等） |
| **品类统计** | T恤、连衣裙、牛仔裤等品类热度排行 |
| **趋势分析** | 基于多天数据追踪排名变化，发现持续上升的商品 |
| **流行预测** | 结合当前数据趋势 + 季节因素，预测未来30天流行方向 |
| **邮件推送** | 每天定时发送精美 HTML 邮件报告 |
| **数据积累** | SQLite 持久化存储，数据越多分析越准 |

## 快速开始

### 1. 安装依赖

```bash
cd dialogues/20260308-1420-amazon-fashion-tracker
pip install -r requirements.txt
```

### 2. 配置

复制配置模板并编辑：

```bash
cp config.example.yaml config.yaml
```

**必须修改的配置项：**

```yaml
email:
  smtp_server: "smtp.qq.com"          # 你的邮箱SMTP服务器
  smtp_port: 465
  sender: "your_email@qq.com"         # 发件人邮箱
  password: "your_authorization_code"  # 授权码（非登录密码）
  recipients:
    - "boss@example.com"              # 收件人邮箱
```

**邮箱授权码获取方式：**

- **QQ邮箱**: 设置 → 账户 → POP3/SMTP服务 → 开启 → 生成授权码
- **163邮箱**: 设置 → POP3/SMTP/IMAP → 开启 → 设置授权码
- **Gmail**: 需开启两步验证 → 生成应用专用密码

### 3. 运行

```bash
# 立即执行一次（抓取 + 分析 + 发邮件）
python run.py

# 调试模式（不发邮件，只看抓取和分析结果）
python run.py --no-email

# 仅根据已有数据重新生成报告
python run.py --report-only

# 启动定时任务（每天 08:00 自动执行）
python run.py --schedule
```

## 项目结构

```
├── config.example.yaml   # 配置模板
├── config.yaml           # 你的实际配置（需自行创建，已在 .gitignore 中）
├── requirements.txt      # Python 依赖
├── run.py                # 主入口脚本
├── src/
│   ├── scraper.py        # Amazon 爬虫（畅销榜 + 飙升榜）
│   ├── storage.py        # SQLite 数据存储
│   ├── analyzer.py       # 数据分析 + 趋势预测
│   └── reporter.py       # HTML 报告生成 + 邮件发送
└── data/                 # 运行后自动生成
    ├── fashion_tracker.db    # SQLite 数据库
    ├── images/               # 商品图片缓存
    └── reports/              # HTML 报告存档
```

## 邮件报告内容

每封日报邮件包含以下板块：

1. **今日概览** — 畅销/飙升商品数量、均价、价格分布图
2. **畅销榜 Top 20** — 带图片的商品卡片，显示排名、价格、评分
3. **销量飙升榜** — 24h 内销量增长最猛的商品（含增长百分比）
4. **风格热度排行** — 当前最热门的服装风格标签
5. **品类分布** — 哪类服装在畅销榜中占比最高
6. **未来30天趋势预测** — 季节分析 + 上升风格/品类 + 选品建议
7. **持续上升商品** — 连续多天排名攀升的潜力商品（需积累数据）

## 自动运行（Windows 计划任务）

如果你不想一直开着命令行窗口，可以用 Windows 计划任务：

1. 打开"任务计划程序"（搜索 `taskschd.msc`）
2. 创建基本任务 → 命名"Amazon服装追踪"
3. 触发器选"每天"，时间设为早上 8:00
4. 操作选"启动程序"：
   - 程序: `python`
   - 参数: `run.py`
   - 起始位置: 本项目的绝对路径

## 注意事项

- **首次运行**只有当天的数据快照，趋势分析需要至少 2-3 天数据积累
- 连续运行 7 天以上后，趋势预测会越来越精准
- Amazon 有反爬机制，默认每次请求间隔 3-8 秒随机延迟
- 如果频繁遇到 503 错误，可在 `config.yaml` 中增大 `delay_min` 和 `delay_max`
- 商品图片会缓存到本地，重复商品不会重复下载
- 建议配合 VPN/代理使用以确保稳定访问 Amazon 美国站

## 扩展方向

- 增加更多子类目（童装、运动装、内衣等）— 在 `config.yaml` 的 `categories` 中添加
- 接入 Amazon Product Advertising API 获取更详细的销量数据
- 添加关键词监控功能（追踪特定搜索词的排名变化）
- 集成 Keepa API 获取历史价格曲线
- 添加微信/钉钉推送通道
