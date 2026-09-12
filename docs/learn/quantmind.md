# QuantMind 对照：给 24h Agent 补量化基建

- 日期：2026-08-30
- 上游：https://github.com/qusong0627/QuantMind
- 本地源码：`/home/huangyihang/code/learn/QuantMind/repo/`（浅克隆；完整历史：`git -C …/repo fetch --unshallow`）
- 本仓现状：harness + 短回合盯盘已经能转；缺的是 **Agent 可调用的量化原语**，不是另一套量化平台

## 1. 我们要什么 / 不要什么

目标：全天候交易 Agent。盯盘、唤醒、记忆、下单是 runtime；均线、因子、回测、信号质量是 **skill / 基础设施**。Agent 消费量化结果，而不是每轮自己从零算一遍 MACD。

QuantMind 是反例里的正例：它把「数据 → 因子 → 训练 → 打分 → 回测 → 下单 → 监控」做成了一台产品。可取的是这条链的**分层和验收**，不可取的是把链做成 Docker 单体、13 种模型工场、通达信桥。

明确不搬：

| 不搬 | 原因 |
|------|------|
| 四服务 Docker 单体 / Electron 大盘 | 本仓是薄 harness × 多 profile，不是 SaaS |
| 13 模型工场 + Optuna + Stacking | 现阶段要的是可解释信号，不是 ML 选股产品 |
| RD-Agent / AutoAlpha 整套 | 贵、重、和「短回合 wake」抢上下文；因子演化以后当可选 tool |
| TradingAgents 七分析师辩论 | 和已定的短回合调度冲突；研报编排另说 |
| QMT / 通达信 Windows 桥 | A 股实盘通道本仓已用 paper + 以后再谈官方仿真 |
| 300+ 维特征 / L2 / VPIN | 没有本地特征库之前，先把 OHLCV + 少量指标做对 |

## 2. 两边差在哪

```text
QuantMind:  数据中枢 → 特征表 → 信号/模型 → IC 回填 → 预检 → 本地账本 → 券商桥
本仓现在:   远程行情 CLI → Agent 看盘 →（偶尔 ma_scan/macd_scan）→ broker CLI → audit
```

本仓已经够用的：

- 调度：`schedule` 的 trigger × condition × wake，flock、journal、local 遮蔽
- 执行：`okx` 服务层、`paper_ashare`、`clawstreet`；默认 dry-run
- 行情入口：`fuyao`（A 股）、OKX ticker / 条件脚本里的 K 线、yfinance `bars.py`
- 记忆：`world_state` / journal / 软限额

缺的、又正好是 24h Agent 会踩的：

| 缺口 | 现在的样子 | 24h 时会怎样 |
|------|------------|--------------|
| K 线没有统一契约 | `fuyao bars`、yfinance `bars.py`、OKX 各写各的 | 换市场就要换脚本，scan 和复盘对不上 |
| 指标是一次性脚本 | `okx-grok-ma` 的 `ma_scan.py` 自算 SMA | 回测、盯盘、研究三套数 |
| 信号不是对象 | 交叉出现就 wake，没有落库存档 | 无法问「这根金叉后来涨了没」 |
| 没有预检 | tick 到了就叫模型 | 行情断了、夜盘休市、密钥失效仍会下单 |
| 行情几乎不缓存 | 每轮打远程 API | 抖动或限流时 Agent 失明 |
| 意图未先落库 | audit 多半是 CLI 事后账 | 券商超时会丢「到底下没下」 |

## 3. 可取之处（按对我们的价值）

### 3.1 把中间层做成对象，而不是 prompt

QuantMind 的 Engine 不负责「想」，只负责特征、推理、回测；Trade 只负责单和仓。本仓应对齐成：

- **行情 / 特征 / 信号**：库 + CLI，schedule 的 condition 和 Agent 都调同一套
- **执行**：继续走现有 broker
- **Agent**：解释信号、写 reasoning、决定做不做、改 memory

信号建议最小字段：`ts, symbol, name, value, bar, source, horizon`。先落在实例目录（jsonl / sqlite），不要一上来上 PG。

对照：`backend/services/engine/`、`backend/shared/model_registry.py`（样本外 Rank IC / ICIR 才能自动进默认池）。我们不需要模型注册表，但需要「信号没有事后成绩单就不能当默认策略」。

### 3.2 离线、在线用同一套算子

他们推理链路是：HistoryBuffer 补窗 → DataAdapter 算特征 → 模型（`docs/模型推理服务设计与链路文档.md`）。  
本仓的 `ma_scan.py` 只服务「现在有没有新交叉」。下一步应是：`indicators.sma` / `macd` 一份实现，scan、replay、research 三个入口共用。

### 3.3 开盘前预检，而不是 tick 即交易

`backend/services/trade/routers/real_trading_preflight.py` 查连通性、镜像、密钥、行情心跳、信号就绪。K8s 那套不要。24h Agent 需要的预检是：

1. 数据新鲜度（最近一根 K 是否过期）
2. 交易时段 / 日历（A 股休市 vs 加密 24h）
3. broker `status` / 模拟盘标记
4. kill-switch、日限额、软限额
5. 信号源是否产出过（而不是 Agent 现场发明）

预检失败：condition 直接 skip，不要 wake LLM。

### 3.4 先写本地意图，再出网

他们的约定：外部报单前必须本地落库。本仓 `audit/` 是操作副本，不是意图表。补一层 `intent`（symbol / side / qty / reasoning / idempotency / state）再调 `OkxService`，超时才能对账。

### 3.5 数据中枢：本地是主、API 是补

QuantDB = 本地 parquet + DuckDB，Qlib 二进制是派生产物（`quantdb_hub.py`、`qlib_data_builder.py`、`quantdb_daily_sync.py`）。  
本仓 Fuyao / OKX 继续当权威源，但 24h 循环应读**本地 bars 缓存**，同步脚本单独跑。先 sqlite 或 parquet，不必上 Qlib。

### 3.6 代码一层适配，不要统一成他们的 `SH600036`

他们强制前缀式，禁止 `600036.SH`。我们已有三套：`600519.SH`（Fuyao）、`X:BTCUSD`（ClawStreet）、`BTC-USDT`（OKX）。学的是「内部一种、出口适配」，不是改代号。

### 3.7 纸面规则 + 回放

他们有本地 T+1 撮合和「时光回放」。`paper_ashare` 已有 T+1 / 费用 / 弱涨跌停。加密 24h 要补的是手续费、滑点、资金费；回放优先用来验收 **scan → 会不会下那笔单**，不是做完整组合回测。

### 3.8 策略是版本化制品

`strategy_storage.py` 是策略 CRUD 唯一入口。本仓对应物是 profile 里的 `scripts/` + schedule condition，而不是只写在 `AGENTS.md`。Agent 可以改参数，不能每轮重写指标定义。

## 4. 落地规划（插在现有 runtime 上，不另起平台）

原则：量化能力进 `src/marketdata/`、`src/quant/`（新）、实例 `scripts/`；Agent 只多几个 CLI。继续 `uv run`，默认 dry-run。

主试验场仍是加密 24h（`okx-grok-demo` / 以后的 always-on），A 股用 Fuyao + paper 对照。

### P0 — 原语（先补，24h 才敢无人值守）

1. **统一 K 线契约**：`ts, open, high, low, close, volume, symbol, interval, source`。OKX / Fuyao / yfinance 都适配到它。
2. **共用指标库**：SMA、EMA、MACD、RSI；`ma_scan.py` 改成调库。
3. **信号事件**：实例内 jsonl；condition 读「新事件」而不是临时算完就扔。
4. **`preflight` CLI**：数据年龄、broker ping、时段、kill-switch。失败则 schedule skip。

验收：同一段 BTC 1H，scan 与 replay 的金叉时间戳一致；断网或 K 线过期时 tick 不 wake。

### P1 — 给 Agent 的量化 skill

5. 把「扫描」收成库：universe + 指标 + 去重状态，不再每个 profile 复制一份。
6. 极简 replay：历史 bars → 指标 → 「当时会发出的信号 / 会下的单」。
7. 信号事后账：未来 N 根的收益或命中，写回事件（穷人版 IC，先别上截面 Rank IC）。
8. 本地 bars 缓存：同步与读取分开；tick 默认读缓存。

验收：Agent 能问「过去 7 天金叉几次、之后 12 小时赚没赚」，答案来自文件不是临场回忆。

### P2 — 质量与对账

9. 下单意图表：先本地 `pending`，成功/拒绝/未知可对。
10. 纸面更像市场：加密费用与资金费；A 股涨跌停 / 停牌按需加硬。
11. 小宇宙特征表（可选）：10～20 个标的 × 少量价量指标，parquet 即可。
12. Qlib **只在**真要做 A 股多因子截面时再接；接的是「特征 → 回测」，不是模型工场。

### P3 — 明确后置

RD-Agent、十三模型、TradingAgents 辩论、通达信 / QMT。需要时当只读对照，不当本仓依赖。

## 5. 建议阅读顺序（对着 clone）

先地图，后模块。不要先起他们的 Docker。

1. `repo/docs/development/architecture.md` — 四服务各管一段
2. `repo/CLAUDE.md` 里数据平台 / 同步脚本段落
3. `repo/backend/services/engine/data_platform/` — 本地 parquet 为主
4. `repo/docs/模型推理服务设计与链路文档.md` — 离在线同一套特征
5. `repo/backend/shared/model_registry.py` 里 IC/ICIR 门禁
6. `repo/backend/services/trade/routers/real_trading_preflight.py` — 预检清单
7. `repo/docs/实盘模拟交易操作指南.md` — 模拟 / 实盘 / 回放怎么分
8. `repo/backend/shared/strategy_storage.py` — 策略唯一入口

读的时候只记：接口边界、落库时机、失败怎么停。不记 UI 和部署脚本。

## 6. 日志

- 2026-08-30：clone 放到 `~/code/learn/QuantMind/repo`；笔记改放本文件。结论：学分层与验收，P0 先做统一 K 线、共用指标、信号落库、预检。
