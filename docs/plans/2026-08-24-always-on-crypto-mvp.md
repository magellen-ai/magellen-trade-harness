# Always-on 加密交易 Agent MVP — 可执行计划

- 日期：2026-08-24
- 主试验场：`instances/pi-test`（Pi harness + ClawStreet MRES 纸面账号）
- 状态：**Week1 T1–T5 已落地**（2026-08-24）；进入 3–7 天 always-on 观察期
- 相关笔记：`docs/project-notes/CONTEXT.md`、`docs/project-notes/基本面分析Agent.md`

---

## 1. 目标 / 非目标

### 目标

1. 把 `pi-test` 从「手工 wake 的 demo」升级为 **无人值守 always-on 加密纸面交易 agent**：cron 驱动 scan / research / risk 三类 tick，连续跑 3–7 天不需要人工救火。
2. **Memory Protocol 升级**：从 4 个手写 markdown 升到 `world_state / working_set / journal / thesis` 协议，其中 world_state 由脚本机器生成，wake 时按需注入，禁止塞全历史。
3. **Strategy Pack v0**：MACD 金叉入池 + 新闻/情绪佐证 + 简单共振才给建议；决策输出结构化为 `action / signals / reasoning / invalidation / size_hint`。
4. **软限额 + audit 标签代码化**：单实例名义敞口软限额约 **$20k**（MRES 总权益约 $100k 的 1/5），所有订单（含 dry-run）在本地 audit 带实例/策略标签，为后续美股 agent 并行共用同一 MRES 账号打基础。
5. 加密跑稳后，以同一套 profile/pack 机制**低成本复制出美股实例**并行。



### 非目标（本期明确不做）

- 不做真实资金自动下单；`--live` 仅指 ClawStreet 纸面单，且默认路径仍是 dry-run。
- 不做期货/期权；不做 ML/因子策略；策略允许简陋，本期验证的是 runtime 不是 alpha。
- 不做长驻闲聊式 LLM 进程；只做短回合 schedule 唤醒。
- 不做向量库/自动记忆流水线；memory 仍是文件约定 + 脚本生成快照。
- 不改平台侧：ClawStreet 订单 payload 不加字段（平台不支持 tag），归因全靠本地。
- 不动 A 股线（`fuyao` / `paper-ashare` / `ashare-pi-test`）和对照实例 `mres-reuse`。

---



## 2. 现状盘点（基于真实代码，2026-08-24）



### 已具备（不需要新造）


| 能力         | 位置                                  | 现状                                                                                                                                                                                                                                                                                       |
| ---------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 调度引擎       | `src/runtime/schedule.py`           | interval/cron 触发、**condition 脚本门控**（exit 0 放行，stdout 经 `{condition_output}` 注入 prompt）、named action（`config.yaml → schedule.actions`）、`context_files` @path 注入（Pi 用 argv 模式）、flock 防重入、`state/journal.jsonl` 事件流、`apply --pack` 原子换包、local 遮蔽 base。时钟 E2E 已过（2026-08-24 首火/次火间隔 ~5m 已验证） |
| Pi wake 绑定 | `instances/pi-test/config.yaml`     | `schedule.actions.wake-main` 已配好：before 钩子 sync-settings → `pi -p {prompt} -c --approve --no-* --skill .agents/skills`；`process_env_policy: minimal`，隔离 `.pi/agent`                                                                                                                      |
| 交易 CLI     | `src/competitions/clawstreet/`      | `order` 默认 dry-run、`--live` 显式、Idempotency-Key、`fills/orders` 平台真相、本地 `audit/events.jsonl`                                                                                                                                                                                               |
| Memory v1  | `instances/pi-test/memory/`         | `MEMORY.md`（curated ≤80 行）/ `watchlist.md` / `risks.md`（含 LIVE grant 约定）/ `trade-journal.md`；读写规则已写进实例 `AGENTS.md`                                                                                                                                                                       |
| 现有 pack    | `configs/schedules/pi-demo/`        | `research-tick`：4h interval、出厂 disabled、`context_files` 注入 MEMORY/watchlist/risks                                                                                                                                                                                                        |
| 搜索 skill   | `skills/investment-search/scripts/` | `quote.py`（yfinance 即时报价，支持 `X:BTCUSD` 映射）、`search.py`（Tavily）                                                                                                                                                                                                                           |




### 缺口（本计划要补的）


| 缺口                       | 证据                                                                                                                                                                                             |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **无任何名义/敞口限额**           | `risk.py` 的 `RiskGate.check()` 只验证 reasoning ≥10 字符 + decision 基本字段；`should_dry_run` 只看 `--live` 开关。$20k 软限额纯靠 prompt 自觉                                                                       |
| **audit 无归因标签**          | `audit.py` 的 `write_event()` 字段为 ts/event/competition/decision_id/symbol/side/qty/reasoning/dry_run/order_id/idempotency_key，**没有 instance / strategy / book_tag**。两个实例共用 MRES 后无法按 agent 汇总敞口 |
| **决策 schema 不含策略字段**     | `decision.py` 的 `Decision` 无 `signals / invalidation / size_hint`；`thesis_source` 默认 "manual" 且 CLI 未暴露                                                                                        |
| **无历史 K 线 → MACD 算不了**   | `quote.py` 只有 fast_info 即时报价；`client.py` 只有 `/v1/quotes` 即时价，无 bars 端点。MACD 需要新的 bars/scan 脚本                                                                                                  |
| **memory 无 world_state** | 现 4 个文件全靠 agent 手写；没有机器生成的「现金/持仓/本 agent 已用额度/当日单数」快照，wake 时 agent 需自己跑 status+portfolio 且无额度概念                                                                                                |
| **无生产 pack、cron 未挂**     | `pi-demo` 只有一条 disabled 的 research-tick；时钟烟测后 cron 已卸。没有 scan/risk 分层                                                                                                                          |
| **共享账号历史噪音**             | MRES 上有早期探 API 留下的 `X:BTCUSD` 0.002，不属于任何实例的 book                                                                                                                                              |


---



## 3. 架构设计



### 3.1 Online Loop（三类 tick，全部走现有 schedule 引擎）

新建 pack `configs/schedules/crypto-always-on/`，三条规则；cron 每分钟挂 `uv run harness schedule tick pi-test`（flock 已防重入）。


| 规则              | 触发                             | condition（省 LLM 的关键）                                                                                                | action                                                                                               |
| --------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `scan-tick`     | interval 1h                    | **script**：跑 `macd_scan.py`（纯 Python，不烧 LLM）。无新信号 exit 1 → 整条跳过；有信号 exit 0，候选 JSON 走 `{condition_output}` 注入 prompt | `wake-main`：对候选做新闻/情绪佐证 + 共振判断 + 至多一笔 dry-run 单 + 写 journal                                          |
| `research-tick` | interval 4h                    | 无（无条件唤醒）                                                                                                            | `wake-main`：常规巡检——读 world_state/working_set，复核持仓与 thesis，维护 watchlist，可下至多一笔单                        |
| `risk-tick`     | cron `0 9,21 * * *`（每日两次，本机时区） | 无                                                                                                                   | `wake-main`：**只减不加**——对账 world_state vs 平台 portfolio、检查软限额占用与 thesis 失效条件、发现非本实例持仓漂移只告警写 journal 不动手 |


设计要点：

- 每条规则 `action.context_files` 注入 `memory/world_state.md` + `memory/working_set.md` + `memory/risks.md`（MEMORY.md 仅 research-tick 注入）；`wake-main` 已有 before 钩子，再加一个 before 钩子跑 world_state 刷新脚本，保证 agent 醒来时快照是新的。
- 三条规则出厂 `enabled: false`，在 `pi-test` 的 `local/` 层逐条 shadow 启用（先 scan+research，稳一天再开 risk）——符合「base 归 pack、local 归 operator」的既有约定。
- LLM 成本控制：scan-tick 靠 condition 门控，无信号日约只烧 6 次 research/risk wake。



### 3.2 Memory Protocol（world_state / working_set / journal / thesis）


| 文件                                     | 生产者                                                    | 内容                                                                | 注入方式                                 |
| -------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------- | ------------------------------------ |
| `memory/world_state.md`                | **脚本生成**（`world_state.py`，wake 前 before 钩子刷新），agent 只读 | 现金、权益、持仓（区分「本实例 book」与「账号其他持仓」）、本实例已用名义 vs $20k 软限额、当日本实例单数、生成时间戳 | 每次 wake `context_files` 注入           |
| `memory/working_set.md`                | agent 手写（由现 `watchlist.md` 升级改名，保留 git 历史不重要，直接迁移内容）   | 今日候选（含 MACD 入池时间与信号值）、进行中调查、待验证事项；过期项必须删除                         | 每次 wake 注入                           |
| `memory/trade-journal.md`              | agent 追加                                               | 每次 tick 一条结构化决策块（见 3.3 输出 schema），含 hold                          | 不注入，按需 tail                          |
| `memory/thesis/<symbol>.md`            | agent 手写                                               | 每标的观点 + 证据 + **失效条件（invalidation）** + size 逻辑；平仓后归档删除             | 不自动注入，prompt 要求决策前读对应标的              |
| `memory/MEMORY.md` / `memory/risks.md` | agent 手写（沿用现有约定）                                       | 长期教训 / kill 条件与 LIVE grant                                        | risks 每次注入；MEMORY 仅 research-tick 注入 |


原则：**机器能算的（world_state）绝不让 LLM 手抄**；每次 wake 注入量固定且小（world_state + working_set + risks ≈ 百行级）；全历史永不注入。实例 `AGENTS.md` 与 profile skeleton 的 memory 章节同步改写。

### 3.3 Strategy Pack v0（MACD 入池 + 情绪 + 共振）

策略脚本放 `skills/investment-search/scripts/`（复用现有 skill，不新开）：

- `bars.py SYMBOL [--interval 1h --lookback 60d]`：yfinance 历史 K 线 → JSON（复用 `quote.py` 的 `X:BTCUSD → BTC-USD` 映射）。
- `macd_scan.py SYMBOL...`：对固定加密池（v0 定 `X:BTCUSD X:ETHUSD X:SOLUSD`，写在规则的 condition 命令里）计算 MACD(12,26,9)；**新出现金叉/死叉**才 exit 0 并输出候选 JSON（symbol、方向、DIF/DEA、柱状值、收盘价）；无新信号 exit 1。去重靠脚本内比对上次信号状态文件（`memory/.macd_state.json`，机器文件，不进注入）。

共振与情绪判断留在 wake 内由 agent 做（v0 不写死打分公式）：

1. condition 注入的 MACD 候选 = 技术面一票；
2. agent 用 `search.py` 查该标的近 24h 新闻/情绪 = 消息面一票；
3. 价格相对近期区间位置（bars.py 输出可判断）= 位置一票；
4. **至少两票同向才允许建议开仓**，否则 hold 并写明缺哪票。

决策输出 schema（v0 落在 trade-journal 结构约定 + audit 字段，不改平台 payload）：

```
action: buy|sell|hold
signals: {macd: …, sentiment: …, position: …}
reasoning: 人话论证（同时作为订单 reasoning 提交）
invalidation: 失效条件（同步进 thesis 文件）
size_hint: 名义 USD（≤ 软限额剩余额度；v0 单笔上限 $2k 名义）
```

`Decision` dataclass 增加可选字段 `strategy` / `signals` / `invalidation` / `size_hint`（只进本地 audit，不进平台请求体）。

### 3.4 Soft Limit + Audit（同账号并行的地基）

**归因模型**：平台 `fills/orders` = 账号真相（无 tag 能力）；本地 `audit/events.jsonl` = 实例归因真相。两者靠 idempotency_key 关联——live 单的 key 改为 `pi-test--<uuid>` 前缀，audit 已记录 key，事后可与平台 orders 对上。

**改动点**：

1. `config.yaml`（instance 级，profile 提供默认）新增：

```yaml
trade:
  cli: bin/clawstreet
  default_dry_run: true
  book_tag: crypto-pi        # 实例 book 标签
  soft_limit_usd: 20000      # 名义敞口软限额
  per_order_max_usd: 2000    # 单笔名义上限（v0 保守值）
```

1. `audit.py`：`write_event` 增加 `instance`（来自 `find_instance_root()`）、`book_tag`、`strategy`、`notional_usd` 字段；旧条目无这些字段，读取时容错。
2. `risk.py`：`RiskGate` 新增敞口检查（**仅 live 单强制，dry-run 只警告**）：
  - 本实例已用名义 = 从本地 audit 累计本 book 的 live 成交净敞口（buy 加 sell 减，按下单时名义估算）；
  - 新单名义 = qty × 当前价（`client.get_quotes`）；
  - `已用 + 新单 > soft_limit_usd` 或 `新单 > per_order_max_usd` → 拒单，audit 记 `order.rejected_local` 并写明超限数值。
3. `cli.py`：`order` 自动带上 config 的 book_tag / soft limit，新增可选 `--strategy`；`audit` 子命令支持 `--tag` 过滤；新增 `clawstreet exposure` 只读命令输出本实例已用额度（world_state.py 与 risk-tick 复用它）。
4. `world_state.py`（放 `skills/clawstreet-trade/scripts/`）：调 status/portfolio/exposure，渲染 `memory/world_state.md`。

**软限额语义**：这是防呆护栏不是精确风控——按下单时名义计价，不随市值浮动重算（risk-tick 负责发现大幅漂移并提示人工）。账号剩余约 $60k 额度留给人工/实验/未来美股 agent，代码不管。

---



## 4. Week1 可派工任务

任务间依赖：T1 → T2 → T4；T3 与 T1/T2 并行；T5 在 T1–T4 之后。每个任务独立可验收、可单独派给一个 coding agent。


| #              | 任务                           | 改动文件                                                                                                                                                                                                      | 验收                                                                                                                      |
| -------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **T1**         | 软限额 + audit 标签               | `src/competitions/clawstreet/risk.py`、`audit.py`、`decision.py`、`cli.py`、`client.py`（idempotency 前缀）；`configs/profiles/clawstreet-pi-default/config.yaml` + `instances/pi-test/config.yaml` 加 `trade.`* 字段 | 单测：超限 live 单被拒且 audit 记录超限原因；dry-run 只警告；`clawstreet exposure` 输出正确；audit 条目带 instance/book_tag/strategy；旧 audit 条目读取不炸 |
| **T2**         | world_state 生成 + memory 协议升级 | 新增 `skills/clawstreet-trade/scripts/world_state.py`；`instances/pi-test/memory/`（watchlist→working_set 迁移、建 `thesis/`）；改 profile skeleton `AGENTS.md` 与实例 `AGENTS.md` 的 memory 章节                          | 手跑脚本生成 `world_state.md`，数字与 `status`/`portfolio`/`exposure` 一致；区分本 book 与账号历史 0.002 BTC                                 |
| **T3**         | Strategy v0 脚本               | 新增 `skills/investment-search/scripts/bars.py`、`macd_scan.py`；更新该 skill 的 `SKILL.md`                                                                                                                       | `bars.py X:BTCUSD` 出合法 JSON；`macd_scan.py` 对历史数据能正确判定金叉；重复运行不重报同一信号（状态文件去重）；无信号 exit 1                                  |
| **T4**         | 生产 pack + cron 上线            | 新增 `configs/schedules/crypto-always-on/`（scan/research/risk 三条规则 + prompt）；`pi-test` `apply --pack` + local 启用 + 挂 cron                                                                                   | `schedule check` 零 error；`tick --rule` 手工触发三条规则各成功一次（scan 无信号时 CONDITION_SKIP、有信号时注入候选）；cron 挂上后 journal 连续正常           |
| **T5**（P1，可延后） | 日报/复盘工具                      | 新脚本汇总当日 journal + audit + exposure 成一页日报（进 `logs/` 或 stdout）                                                                                                                                              | 一条命令看清当天 tick 数、决策数、额度占用、异常                                                                                             |


Week1 外（明确排后）：美股实例复制、`concurrency: queue`、决策 schema 进平台 payload、研究备忘模板。

---



## 5. 验收标准（上线后连续观察 3–7 天）

**Runtime 稳定性（硬指标）**

- [ ] cron tick 连续 ≥3 天运行，`schedule/state/journal.jsonl` 无连续 `fire_error`（偶发单次失败允许，需在下一 tick 自愈）；无 lock 死锁（`tick_skipped reason=lock_held` 不连续出现）。
- [ ] 每天 research-tick 6 次、risk-tick 2 次全部 FIRED；scan-tick 门控正常（有信号才 wake，journal 里 `condition_skip` 与 `fired` 比例合理）。
- [ ] 每次 wake 都在 `trade-journal.md` 留下含完整 schema（action/signals/reasoning/invalidation/size_hint）的条目，hold 也写。

**Memory 协议**

- [ ] world_state 每次 wake 前刷新，时间戳新鲜；risk-tick 对账 world_state vs 平台 portfolio 无未解释差异。
- [ ] `MEMORY.md` 保持 ≤80 行、无 secrets；期间至少 1 条教训从 journal 提炼进 MEMORY；working_set 无 3 天以上的僵尸条目。

**软限额与审计**

- [ ] 人工构造一笔超 $20k 的 live 单 → 被拒 + audit `order.rejected_local`；构造一笔超 $2k 单笔上限 → 同样被拒。
- [ ] 期间所有订单（含 dry-run）audit 均带 book_tag；`clawstreet audit --tag crypto-pi` 能完整还原本实例操作序列；live 单可通过 idempotency 前缀在平台 orders 中对上。

**开美股的判据**：以上全绿连续 3 天（保守 7 天）→ 用同一 profile 机制 init 美股实例（另 $20k 软限额、`book_tag: equity-`*、美股时段 cron 规则），加密实例不停机。

---



## 6. 同账号并行风险（MRES 共用，加密 + 美股）


| 风险              | 说明                                  | 缓解                                                                                                                  |
| --------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| 持仓归因模糊          | 平台 portfolio 不分实例；已有历史 0.002 BTC 噪音 | 本地 audit + book_tag 为归因唯一真相；world_state 明确列「账号其他持仓」；上线前把历史持仓记入 `MEMORY.md` 基线，agent 不得「修复」不属于自己的仓位                  |
| 同标的冲突           | 两 agent 对同一 symbol 反向互耗或同向叠加超总限额    | **symbol 分域是主防线**：加密实例只准 `X:`*，美股实例只准股票（写进各自 AGENTS.md + RiskGate 可加 symbol 白名单前缀校验）；risk-tick 发现本 book 外持仓变化只告警不动手 |
| 软限额是软的          | agent 绕过 CLI 直接 HTTP 下单则限额失效        | AGENTS.md 明令 CLI 为唯一下单路径；audit 对不上平台 orders 时（risk-tick 对账）视为红线事件人工介入                                               |
| 平台限流共享          | 429 配额、~5s 相同订单 409，是账号级不是实例级       | 沿用现有 429 退避规则；两实例 tick 时刻错开（cron 分钟错位）                                                                              |
| 无协调改共享逻辑        | 已定案约束：共享仓位变更必须写 journal             | 双实例都开 risk-tick；重大再平衡保留人工节点，不给 agent                                                                                |
| dry-run 不占额度的错觉 | dry-run 单不进敞口累计，agent 可能误判剩余额度      | world_state 同时展示「live 已用」与「当日 dry-run 意向名义」两个数                                                                      |


---



## 7. 下一步第一刀：改哪些文件

第一刀 = **T1（软限额 + audit 标签）**，因为它是并行安全的地基、纯 Python 可单测、不依赖 LLM 调试：

1. `src/competitions/clawstreet/risk.py` — RiskGate 加 `soft_limit_usd` / `per_order_max_usd` 敞口检查（live 强制、dry-run 警告）
2. `src/competitions/clawstreet/audit.py` — 事件加 `instance` / `book_tag` / `strategy` / `notional_usd`；新增按 tag 汇总敞口的读取函数
3. `src/competitions/clawstreet/decision.py` — 可选字段 `strategy` / `signals` / `invalidation` / `size_hint`
4. `src/competitions/clawstreet/cli.py` — order 接入限额与标签、`--strategy` 参数、新 `exposure` 子命令、`audit --tag`
5. `src/competitions/clawstreet/client.py` — live 单 idempotency_key 加实例前缀
6. `configs/profiles/clawstreet-pi-default/config.yaml` 与 `instances/pi-test/config.yaml` — `trade.book_tag` / `soft_limit_usd` / `per_order_max_usd`

紧随其后（同周）：`skills/clawstreet-trade/scripts/world_state.py`（T2）、`skills/investment-search/scripts/{bars,macd_scan}.py`（T3）、`configs/schedules/crypto-always-on/`（T4）。