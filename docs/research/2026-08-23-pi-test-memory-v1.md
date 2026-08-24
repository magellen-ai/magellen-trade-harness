# pi-test 记忆机制 v1

日期：2026-08-23  
范围：`instances/pi-test`（Pi harness；`config.yaml` 已有 `memory.kind=files`, `path=memory`）  
原则：**少而稳**；服务交易研究复盘，不是通用第二大脑。本轮只做约定 + 常驻 md 骨架，不写自动流水线、不引入向量库/数据库。

---

## 1. 问题

交易 agent 跨 session / schedule tick 需要记住：

- 当前仓位叙事之外的**开放论点**（thesis）
- **已做过的决策与复盘**（避免重复试错）
- **关注名单与风险门槛**

但不能违反仓库 Context control：`AGENTS.md` 必须保持精简，禁止把运维噪声、密钥、注册/launch 细节塞进交易上下文。

当前状态：

- `config.yaml` 声明了 `memory/`，目录为空
- Pi launch 使用 `--no-context-files` + `--append-system-prompt AGENTS.md` → **只有 `AGENTS.md` 自动注入**；`memory/*` 不会进 system prompt，必须按需 `read`
- `configs/schedules/default/research-tick.yaml` 已要求 tick 时读/写 `memory/`（仍是约定，无代码强制）

---

## 2. 对标摘要

### 2.1 OpenClaw

来源：官方 docs `concepts/memory` + 本机 `~/.openclaw/workspace/{AGENTS.md,MEMORY.md,memory/*.md}`。

| 层 | 文件 | 作用 |
|----|------|------|
| 操作手册 | `AGENTS.md` | 何时读/写记忆；禁止事项；不堆具体事实 |
| 长期压缩 | `MEMORY.md` | 耐久事实与决策精华；**不是**原始日志 |
| 工作层 | `memory/YYYY-MM-DD.md` | 当日/昨日细节；按需检索，不全量注入 |
| （可选） | 向量/hybrid search、dreaming 晋升 | 重型；v1 不做 |

关键教训：

- **磁盘才是真相**；“心里记一下”跨 session 无效
- `AGENTS.md` 写政策；`MEMORY.md` 写压缩事实；日笔记吸收噪声
- `MEMORY.md` 过大时截断注入 → 信号是该蒸馏，不是继续堆

本机 OpenClaw main agent 也把「记忆维护规则」放在 `AGENTS.md`，具体项目状态放 `PROJECT_CONTEXT.md` / `MEMORY.md`，与本仓 Context control 一致。

### 2.2 Hermes

来源：Hermes 文档 Persistent Memory / Which File Does What。

| 层 | 文件 | 作用 |
|----|------|------|
| 身份 | `SOUL.md` | 人格（交易实例不需要） |
| 指令 | `AGENTS.md` / `.hermes.md` | 项目规则（自动注入） |
| 有界记忆 | `MEMORY.md` + `USER.md` | **硬字符预算**（约 2200 / 1375）；session 开始冻结快照 |
| 历史 | SQLite FTS session search | 按需搜旧对话；v1 不做 |

关键教训：

- **硬预算逼迫压缩**；满了就合并/删旧，而不是静默截断丢事实
- 不存 trivia、可再查的公开事实、大段 raw dump
- 已在 `AGENTS.md` 里的内容不要再抄进记忆

### 2.3 GitHub / 业界 AGENTS.md 实践

共性（GitHub Blog 2.5k 样本、Augment、voxos「plain text memory」等）：

- 文件记忆已成为主流；RAG 不是默认第一步
- **渐进披露**：根指令短，细节进按需加载的 reference
- 常见拆分：`DECISIONS.md` / journal、known issues、session 状态
- 坏模式：把 README/架构全文塞进常驻上下文；自动生成巨无无 curation

### 2.4 对标 → 本实例取舍

| 借鉴 | 采用方式 | 明确不做（v1） |
|------|----------|----------------|
| OpenClaw 分层：政策 / 压缩长期 / 工作细节 | `AGENTS.md` 政策 + `memory/MEMORY.md` + journal/watchlist/risks | daily `YYYY-MM-DD.md` 全自动注入、dreaming、向量索引 |
| Hermes 有界 + 跳过 trivia | `MEMORY.md` 软上限（见下）；写入前自问是否耐久 | 硬编码 char 拦截工具、USER.md 人格档案、session SQLite |
| 开源 progressive disclosure | 记忆**不**进 system prompt；tick/开场主动读 | 把 memory 内容合并进 `AGENTS.md` |

---

## 3. v1 方案

### 3.1 分层（谁进上下文）

```
AGENTS.md          ← 每次 session 自动注入（薄：工具 + 规则 + 记忆政策）
memory/MEMORY.md   ← 开场 / research-tick 必读（压缩长期）
memory/*.md 其它   ← 按任务读；写后不必回注 AGENTS
platform fills/orders + audit/  ← 账户与操作真相，不替代记忆叙事
```

**与 Context control 的对齐：**

- 交易角色上下文仍以精简 `AGENTS.md` 为准
- 记忆是**按需工作集**，不是第二份 system prompt
- 密钥、register、launch、env map 仍禁止进入 `AGENTS.md` 与 `memory/`

**潜在分歧（保留精简优先）：**

- OpenClaw 常把 `MEMORY.md` bootstrap 注入；本实例 **故意不注入**，因 Pi 已 `--no-context-files`，且实验目标是比较「薄上下文 + 主动读文件」行为。若日后发现 agent 经常忘记读 memory，优先加强 `AGENTS.md` 开场 checklist / schedule prompt，而不是扩大自动注入面。

### 3.2 常驻文件职责

| 文件 | 职责 | 读写节奏 | 体量目标 |
|------|------|----------|----------|
| `memory/MEMORY.md` | 长期压缩事实：实例约束、现行策略立场、已验证教训、未决但跨日有效的结论 | **每个** research tick / 新会话开场先读；有耐久变化时改写（合并旧条，勿只追加） | 软上限 ~80 行 / ~4KB；超出先蒸馏 |
| `memory/trade-journal.md` | 决策与交易复盘（含 dry-run）；append-only 日志 | 每次下单意图或明确「不交易」结论后追加一条 | 可增长；旧条目不删，重要教训晋升到 `MEMORY.md` |
| `memory/watchlist.md` | 关注标的 / 开放 thesis / 待验证检查点 | 开场扫一眼；论点增减时更新 | 保持「现行名单」短；归档掉过期项到 journal |
| `memory/risks.md` | 组合/规则风险、杀跌条件、`--live` 授权状态 | 开仓前必读；风险变化时更新 | 短；过期风险删或标 `[closed]` |

不设 `USER.md` / `SOUL.md`：交易实例不是私人助理。  
不设每日 `YYYY-MM-DD.md`（v1）：journal 已覆盖「带日期的工作记录」；若日后 tick 噪声过大，再加 daily 工作层（对标 OpenClaw），仍不自动注入。

### 3.3 维护流程

**开场 / schedule research-tick（读）：**

1. `./bin/clawstreet status` + `portfolio`（账户真相）
2. 读 `memory/MEMORY.md`
3. 扫 `watchlist.md`、`risks.md`
4. 若要复盘近期动作：读 `trade-journal.md` 尾部 + `fills`/`orders`/`audit`

**何时写：**

| 事件 | 写哪里 |
|------|--------|
| 形成或否定一条跨日有效的结论 / 教训 | 更新 `MEMORY.md`（改写，去重） |
| 决定下单、改仓、或明确 hold 并写了公开 reasoning | `trade-journal.md` 追加一条 |
| 新关注标的 / thesis / pending check | `watchlist.md` |
| 风险阈值、止损逻辑、`--live` 授权/撤回 | `risks.md`（`--live` 授权必须写清范围与过期条件） |
| 用户说「记住这个」（且与交易相关） | 落入上表对应文件；不要只回嘴上答应 |

**晋升（轻量 curation，人手或 agent 自觉）：**

- journal 里重复出现的教训 → 收成 `MEMORY.md` 一条
- watchlist 项验证完毕或放弃 → 移出名单，一行结论进 journal 或 MEMORY
- `MEMORY.md` 超软上限 → 删过时细节，只留现行有效句

**禁止：**

- API key、`secrets.env`、代理密钥、任何可鉴权秘密
- 把平台可查的全量成交明细抄进记忆（用 CLI 查）
- 把 register / launch / env / harness 运维写进记忆
- 用记忆替代 `fills`/`orders` 作为成交真相
- 为「显得完整」灌水；空模板保持空，有事实再写

### 3.4 与 schedule 的关系

`research-tick` prompt 已要求读/写 `memory/`。v1 不改 schedule runner；实例启用该规则后，agent 应按 `AGENTS.md` 记忆章节把内容落到上表四文件（而不是随意新建一堆 md）。

`--live` 默认仍禁止；仅当 `risks.md`（或 MEMORY）中有**未过期、范围明确**的授权时，tick 才可 live。

---

## 4. Profile skeleton 补丁建议（本轮不改）

优先改的是活实例 `instances/pi-test/`。稳定后可把同一「记忆维护」短章节同步到：

`configs/profiles/clawstreet-pi-default/skeleton/AGENTS.md`

并可选在 profile 文档里注明 init 后应存在的 `memory/*.md` 模板（或 init 时从 `configs/.../memory-templates/` 拷贝——那是后续脚手架工作，非 v1）。

Claude profile（`CLAUDE.md`）若要对齐，保持同一文件职责表，避免双标准。

---

## 5. 后续选项（仅文档，不实现）

1. **软预算工具**：对 `MEMORY.md` 做行数/字符检查（Hermes 风格），超限在 tick 日志告警  
2. **daily 工作层**：`memory/YYYY-MM-DD.md`，只给高噪声实验用  
3. **memory_search**：对 `memory/` 做 BM25 或轻量向量（OpenClaw memory-core 类）——仅当文件多到 grep 不够时  
4. **compaction flush**：会话压缩前提醒写盘（OpenClaw memoryFlush）  
5. 把模板纳入 `harness instance init` materialize —— 等 pi-test 跑通几周再定

---

## 6. 验收对照

| 标准 | 状态 |
|------|------|
| 设计文档含对标 + v1 + 维护流程 | 本文件 |
| `instances/pi-test/AGENTS.md` 有记忆维护规则 | 已补章节 |
| `memory/` 常驻 md 模板可用 | `MEMORY.md` / `trade-journal.md` / `watchlist.md` / `risks.md` |
| 不与 Context control 冲突 | 记忆按需读；AGENTS 只增政策短文 |
| 无 secrets；无 runtime/DB/流水线代码 | 遵守 |
