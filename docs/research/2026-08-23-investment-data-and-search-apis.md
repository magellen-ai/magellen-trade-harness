# 投资数据接口与网络搜寻接口调研

**调研日期**：2026-08-23  
**仓库**：`magellen-trade-harness`  
**用途**：为「基本面研究 Agent」选型（L1 资料员 → L2 分析员），服务可读可复盘的研究备忘；交易侧仍走 ClawStreet 纸面，不接真实资金自动下单，不做 ML 选股。  
**范围**：美股为主；行情 / 基本面 / SEC filings / 新闻与网页搜索 / Agent 封装；并对照近期热门开源投资 Agent 数据栈。

---

## 0. 项目约束摘要（选型滤镜）

来自 `AGENTS.md`、`docs/project-notes/大纲.md`、`基本面分析Agent.md`：

| 要 | 不要 |
|----|------|
| 10-K/季报原文入口 + 可核验出处 | 高频 tick / 做市级延迟 |
| 粗估值指标、财报结构化数字 | ML 选股、因子挖掘 |
| 网页/财经新闻检索 | 真实资金自动下单 |
| Python SDK / CLI / MCP 便于 coding agent 调用 | 一上来接 Bloomberg 级终端 |

**因此**：优先「免费或低成本 + 出处可追溯 + Agent 可脚本化」；Polygon/Massive 等偏行情流水的方案降权。

---

## 1. Top 推荐（≤8）

费用与额度以官方页面为准；调研日快照，上线前请再核验。

| # | 候选 | 用途 | 接入难度 | 费用（快照） | 需 Key | 契合度 | 主要风险 |
|---|------|------|----------|--------------|--------|--------|----------|
| 1 | **yfinance** | 美股报价、历史 K 线、粗基本面/概况 | 低 | 免费（无官方 SLA） | 否 | ★★★★★ MVP | 非官方 API；Yahoo 侧随时变更；商用条款需自核 |
| 2 | **SEC EDGAR `data.sec.gov`** | submissions、XBRL companyfacts、10-K/10-Q 入口 | 中（需 User-Agent、限速） | 免费，无 key | 否 | ★★★★★ MVP | 原文多为 HTML/iXBRL；需遵守 fair access；解析成本在己方 |
| 3 | **edgartools** | 在官方 EDGAR 之上做 Python 友好封装（10-K/8-K/XBRL/13F 等） | 低–中 | 开源 MIT；底层走 SEC | 否* | ★★★★★ MVP | 依赖 SEC 可用性；大文件下载需缓存与礼貌限速 |
| 4 | **Tavily Search API** | Agent 友好网页搜索 + 抽取（公司新闻、研报入口、行业页） | 低 | 常见宣传约 1k credits/月免费档；付费按 credits（第三方对比常见 ~$8/1k） | 是 | ★★★★★ MVP | 非财经垂类；摘要不可当财报事实；价格页口径不一需以官网为准 |
| 5 | **Financial Modeling Prep (FMP)** | 标准化财报、比率、公司 profile、EOD | 低 | Free ~250 calls/天（偏美股 EOD）；Starter 起约 $19/月 | 是 | ★★★★ 第二阶段 | 免费档权限/历史深度受限；数据需抽查 vs SEC |
| 6 | **Finnhub** | 报价、公司新闻、日历、部分基本面 | 低 | Free ~60 calls/分（条款常标非商用）；付费档自约 $50/月起 | 是 | ★★★★ 第二阶段 | 免费档 ToS/历史深度限制；全量基本面多在付费 |
| 7 | **Alpha Vantage**（含官方 MCP） | 行情/overview/新闻情绪；**官方 MCP** 利于 Claude/Cursor | 低 | Free ~25 req/天；Premium 自约 $49.99/月 | 是 | ★★★ 可选 | 免费额度对 Agent 多轮调用极易打满 |
| 8 | **Financial Datasets** | 面向 AI agent 的价格+财报+filings+新闻一体 API；有 MCP/OpenAPI | 低 | Credits $20/1k req；Build $200/月 | 是 | ★★★ 按需 | MVP 成本偏高；强绑定单一供应商 |

\*edgartools 本身不强制第三方 key；SEC 要求合规的 User-Agent（通常含联系邮箱）。

**可核验主链接**

- yfinance：https://github.com/ranaroussi/yfinance  
- SEC EDGAR APIs：https://www.sec.gov/search-filings/edgar-application-programming-interfaces  
- edgartools：https://github.com/dgunning/edgartools · 文档 https://edgartools.readthedocs.io/  
- Tavily：https://www.tavily.com/  
- FMP pricing：https://site.financialmodelingprep.com/pricing-plans · docs https://site.financialmodelingprep.com/developer/docs  
- Finnhub：https://finnhub.io/ · pricing https://finnhub.io/pricing  
- Alpha Vantage：https://www.alphavantage.co/ · MCP https://mcp.alphavantage.co/ · support https://www.alphavantage.co/support/  
- Financial Datasets：https://www.financialdatasets.ai/ · pricing https://www.financialdatasets.ai/pricing · docs https://docs.financialdatasets.ai/introduction  

---

## 2. 分层建议

### 2.1 MVP 必接（默认组合，3 个以内）

**推荐默认组合：**

1. **yfinance** — 价格、K 线、公司概况与粗指标  
2. **edgartools（底层 SEC EDGAR）** — 10-K/10-Q/8-K 原文与结构化 XBRL  
3. **Tavily** — 网页/新闻检索与正文抽取（证据链第二来源）

对应大纲 L1「资料员」最小闭环：报价事实 + 官方 filings + 可引用网页证据。  
密钥仅需 Tavily；行情与 filings 可零第三方数据订阅启动。

### 2.2 第二阶段

| 候选 | 何时引入 |
|------|----------|
| **FMP** | yfinance 粗指标不够稳、需要更干净的 statements/ratios API |
| **Finnhub** | 需要公司新闻流、earnings calendar，且能接受 ToS |
| **Brave Search API** | 想要更便宜、可预期的通用搜索（约 $5/1k，官方对比文常见） |
| **Alpha Vantage MCP** | 已用 Claude Code / Cursor，希望零封装挂 MCP（接受低免费额度） |
| **FRED** | 需要宏观利率/通胀（TradingAgents 已列为可选）https://fred.stlouisfed.org/docs/api/api_key.html |

### 2.3 可忽略（对本项目现阶段）

| 候选 | 原因 |
|------|------|
| **Massive（原 Polygon.io）** | 强项是美股 tick/聚合与低延迟；基本面研究非刚需。Free Stocks Basic：5 calls/min、约 2 年历史。https://massive.com/pricing |
| **Bloomberg / Refinitiv / FactSet** | 成本与合规过重 |
| **纯社交媒体情绪栈（X 实时、StockTwits 主依赖）** | 噪声高、授权复杂；基本面备忘仅作可选附录 |
| **Intrinio / Tiingo 等中端付费** | 与 FMP/Finnhub 重叠；无差异化刚需前不扩面 |
| **自建全量 EDGAR 镜像** | MVP 过重；先用 edgartools + 单票按需拉取 |

---

## 3. 分类候选详表

### 3.1 市场 / 行情

| 名称 | 能力 | Agent 封装 | 授权/成本 | 链接 | 备注 |
|------|------|------------|-----------|------|------|
| yfinance | 报价、历史 OHLCV、info/fast_info | Python `pip install yfinance` | Apache-2.0 库；数据来自 Yahoo（非正式公开 API） | https://github.com/ranaroussi/yfinance | ~25k★（2026-08-23） |
| Massive (Polygon) | 美股实时/历史、期权等 | REST/WS；官方 Python 客户端生态成熟 | Free Basic $0；Starter ~$29/mo | https://massive.com/ · https://massive.com/pricing | 2025-10 起 Polygon 品牌迁至 Massive；旧 `api.polygon.io` 仍可用（以官方公告为准） |
| Alpha Vantage | 日线/指标/overview | REST + **官方 MCP** | Free ~25/天 | https://www.alphavantage.co/ | 适合 demo，不适合密集 Agent loop |
| Finnhub | 报价、candle、部分实时 | REST + Python SDK | Free ~60/min | https://finnhub.io/docs/api | 偏行情+新闻一体 |
| FMP | EOD/实时（付费档） | REST | Free 250/天 EOD | https://site.financialmodelingprep.com/developer/docs | 基本面更亮眼 |
| OpenBB | 多源聚合平台 | Python Platform + Workspace；有 agent 实验仓 | 开源平台；具体数据源各有 key | https://github.com/OpenBB-finance/OpenBB | ~72k★；适合以后统一入口，MVP 过重 |

### 3.2 基本面 / Filings / SEC

| 名称 | 能力 | Agent 封装 | 授权/成本 | 链接 | 备注 |
|------|------|------------|-----------|------|------|
| SEC `data.sec.gov` | submissions JSON、companyfacts、frames | 原生 HTTPS JSON；无官方 SDK | 免费无 key；须 User-Agent + 限速政策 | https://www.sec.gov/search-filings/edgar-application-programming-interfaces | **权威出处** |
| edgartools | 10-K/8-K/XBRL/Form4/13F 等 | 一流 Python API | MIT | https://github.com/dgunning/edgartools | ~2.6k★；强烈推荐作 SEC 封装层 |
| sec-api.io | 全文检索、抽取、stream | Python `sec-api`；另宣 MCP | 商业；有免费试用（额度以官网为准） | https://sec-api.io/ · https://github.com/janlukasschroeder/sec-api-python | 全文搜索强；付费前用官方+edgartools 即可 |
| FMP Fundamentals | income/balance/cashflow、ratios | REST | Free 有限；付费扩历史与全球 | 同上 FMP | 第二阶段「干净数字」 |
| Financial Datasets | statements、metrics、filings、earnings | REST + **hosted MCP** + OpenAPI | $20/1k 或 $200/mo | https://docs.financialdatasets.ai/introduction | ai-hedge-fund 默认栈 |

**SEC 接入要点（不确定处已标明）**

- 官方明确：`data.sec.gov` **不需要 API key**。  
- 开发者须遵守 SEC Privacy & Security / fair access（见 Developer FAQs：https://www.sec.gov/os/webmaster-faq#developers）。常见实践是自定义 User-Agent 并控制并发；**具体数值以 SEC 当前政策为准，本文不编造硬限额**。  
- 原文入口也可人工核验：https://www.sec.gov/search-filings  

### 3.3 新闻 / 舆情 / 网页搜索

| 名称 | 能力 | Agent 封装 | 授权/成本 | 链接 | 备注 |
|------|------|------------|-----------|------|------|
| Tavily | search / extract / crawl / research | REST、Python、MCP 生态广泛 | 有免费档；付费 credits | https://www.tavily.com/ | Agent 默认搜索首选之一 |
| Brave Search API | 通用网页搜索、LLM context 端点 | REST | 约 $5/1k；月赠额度见官网 | https://brave.com/search/api/ · 对比文 https://brave.com/learn/best-search-api-2026/ | 成本可预期 |
| Exa | 语义/neural 搜索 + contents | REST | 免费档较大但计费项多（第三方称 search≈$7/1k） | https://exa.ai/（请以官网定价为准） | 深检索强；预算需盯 contents 附加费 |
| Serper / SerpAPI | Google SERP 结构化 | REST | Serper 常见约 $50/50k；SerpAPI 更高 | https://serper.dev/ · https://serpapi.com/ | 要「谷歌第一页」时用 |
| Finnhub News | 公司/市场新闻 | REST | 含在 Finnhub 套餐 | https://finnhub.io/docs/api | 财经垂类补充 |
| Alpha Vantage News & Sentiment | 新闻+情绪分 | REST/MCP | 计入 AV 配额 | https://www.alphavantage.co/ | 额度紧 |
| X/Twitter | 舆情信号 | 官方 API 付费；或只读 cookie CLI（本机已有 bird 等） | 官方昂贵；第三方 ToS 风险 | 官方开发者文档另查 | **基本面 MVP 可忽略**；若做附录需单独授权评估 |

---

## 4. Agent 友好封装对照

| 形态 | 适合本仓库的方式 | 示例 |
|------|------------------|------|
| **Python SDK** | instance skill / 小脚本，CLI 包装后给 agent | yfinance、edgartools、finnhub-python |
| **CLI** | 与现有 `clawstreet`/`harness` 风格一致，最利于 Pi/Claude | 自研 thin wrapper：`fundamentals quote AAPL` |
| **MCP server** | Claude Code / Cursor 直接挂工具 | Alpha Vantage 官方 MCP；Financial Datasets `mcp.financialdatasets.ai`；社区 Tavily MCP |
| **OpenAPI** | 生成客户端或给 agent 读 schema | Financial Datasets 宣称 `financialdatasets.ai/openapi.json` |
| **聚合平台** | 后期统一多源 | OpenBB Platform（https://github.com/OpenBB-finance/OpenBB） |

**对本项目的建议形态**：MVP 先做 **Python 库 + 薄 CLI skill**（与 ClawStreet CLI 一致、可审计）；MCP 作为可选第二条通道，避免 Agent 上下文被几十个工具淹没。

---

## 5. 对标热门投资 Agent 数据栈

核验时间：2026-08-23（GitHub `gh api` / README）。

| 项目 | Stars（约） | 数据栈（公开 README/env） | 来源 |
|------|-------------|---------------------------|------|
| **TauricResearch/TradingAgents** | ~99k | 行情侧大量依赖 **Yahoo Finance** 覆盖多市场 ticker；可选 **Alpha Vantage**、**FRED**、Polymarket 等 vendor；LLM 多供应商 | https://github.com/TauricResearch/TradingAgents · arXiv:2412.20138 · `.env.example` 含 `ALPHA_VANTAGE`/`FRED` |
| **virattt/ai-hedge-fund** | ~63k | 默认 **Financial Datasets**（价格、基本面、earnings）；社区 issue 讨论 Yahoo 等免费替代 | https://github.com/virattt/ai-hedge-fund · https://www.financialdatasets.ai/ |
| **OpenBB-finance/OpenBB** | ~72k | 开源数据平台 + Workspace；另有 `agents-for-openbb` / experimental agent | https://github.com/OpenBB-finance/OpenBB |
| **AI4Finance-Foundation/FinRobot** | ~7.8k | 金融 LLM agent 平台（多数据源插件化，具体以仓库 docs 为准） | https://github.com/AI4Finance-Foundation/FinRobot |
| **TradingAgents-CN / AShare 系** | 数万–三千★ 级 fork | A 股免费源（东财/新浪等）；美股研究参考价值有限 | 例：https://github.com/hsliuping/TradingAgents-CN |

**X/Twitter 近况（抽样，2026-08 下旬）**

- 仍有开发者讨论 yfinance 无 key 便利性，以及 A 股 TradingAgents 变体「免 API 费用」数据源（例：帖文提及 TradingAgents-Astock，2026-08-22）。  
- 语义检索「AI trading data stack」噪声大，**以 GitHub 星标项目 README 为准**，不把营销帖当选型依据。

**启示（对齐本项目）**

- 热门项目要么 **Yahoo 免费起步**（TradingAgents），要么 **Financial Datasets 一站式付费**（ai-hedge-fund）。  
- 本项目更强调 **SEC 原文可复盘** → 应显式加入 **EDGAR/edgartools**，这是多数「交易框架」README 写得不够的一块。  
- 不要照搬多 Agent 辩论大厅；大纲已排除「一上来多 Agent 仿真交易室」。

---

## 6. MVP 选型结论

### 默认组合（≤3）

| 角色 | 选型 | 理由 |
|------|------|------|
| 行情 + 粗基本面 | **yfinance** | 零 key、Python 成熟、够写研究备忘里的价格与粗框估值 |
| Filings / 年报原文 | **edgartools → SEC EDGAR** | 满足「证据必须有出处」；免费且权威 |
| 新闻 / 网页 | **Tavily** | Agent 检索+抽取一体；唯一必要的搜索 key |

### 明确不做（MVP）

- 不上 Massive/Polygon 实时流  
- 不上 X 社交主信号  
- 不买 Financial Datasets Build 档（除非试点中证明三件套不够且愿意 $200/月）  
- 不引入 OpenBB 全家桶（可作为第三阶段「统一数据平面」再评）

### 建议的下一工程步骤（文档级，非本任务实现）

1. 在 `skills/` 增加只读 skill：`quote` / `filings` / `web_search` 三个动词，密钥只进 `instances/<name>/agent/secrets.env`。  
2. 备忘模板字段强制：每条证据带 URL 或 accession number。  
3. 第二阶段若 yfinance 财务字段经常空/错，再加 FMP 作「数字层」备份，仍以 SEC 原文为冲突时的裁判。

---

## 7. 风险与合规备忘

- **绝不**把 API key 写入 git、audit 明文或 agent 对话；本仓库惯例见 `AGENTS.md`。  
- yfinance / 非官方抓取：生产与商用前自行阅读 Yahoo 与库的许可；研究原型可接受，对外产品需谨慎。  
- SEC：礼貌限速、缓存 10-K、声明 User-Agent。  
- 搜索 API 返回的摘要：**不能**替代 10-K 原文；Agent 提示词应要求「未打开原文则标未证实」（与大纲一致）。  
- ClawStreet 交易与研究数据源解耦：下单仍只走 `uv run clawstreet`。

---

## 8. 调研方法与局限

- 已读：仓库 `AGENTS.md`、`README.md`、`instances/pi-test/AGENTS.md`、`docs/project-notes/大纲.md`、`基本面分析Agent.md`。  
- 渠道：官方文档页、GitHub `gh api`/`gh search`、公开评测/对比文、X 关键词抽样。  
- **未做**：付费账号实测 QPS、数据正确性 spot-check、浏览器登录态抓取。  
- AnySearch 本机 runtime 未配置，公共网页检索改用内置 `web_search`/`web_fetch`；不影响以官方 URL 为准的结论。  
- 凡标「约 / 常见宣传 / 第三方对比」的价格，**以上线前官方定价页为准**。

---

## 9. 附录：快速决策树

```text
只要单票研究备忘？
  ├─ 要官方年报/季报 → edgartools / SEC
  ├─ 要价格与粗指标 → yfinance
  └─ 要新闻与二手研究入口 → Tavily（或 Brave）

yfinance 财务经常对不上？
  └─ 加 FMP 或 Financial Datasets，冲突时以 SEC 为准

需要 Claude 里点选工具、少写代码？
  └─ 试 Alpha Vantage MCP 或 Financial Datasets MCP（看好额度）

做高频/盘口？
  └─ 本项目不需要；去看 Massive — 但那是另一条产品线
```

---

**文档版本**：v1.0  
**产出路径**：`docs/research/2026-08-23-investment-data-and-search-apis.md`  
**机器可读候选**：`docs/research/sources-investment-apis.jsonl`
