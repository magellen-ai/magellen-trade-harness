# paper_ashare — 本地 A 股纸面账户

自建 SQLite 账本模拟券商，给多 agent / 多实验隔离虚拟资金。  
**不是**券商官方仿真；撮合简化（市价≈最新价±滑点）。适合前瞻实验，不当作实盘替代。

## 能力（MVP）

| 项 | 行为 |
|----|------|
| 多账户 | `--account <name>` → `instances/<inst>/paper_ashare/<name>.sqlite`（无实例则 `~/.config/magellen-trade-harness/paper_ashare/`） |
| 市价单 | 立即成交；滑点默认 5bp |
| T+1 | 持仓按 lot + `buy_date`；当日买入不可卖 |
| 手数 | 必须 100 股整数倍 |
| 费用 | 佣金万 2.5（最低 5 元）+ 过户近似 + 卖出印花税 0.05% |
| 涨跌停 | 弱启发式（相对昨收 ±10% 接近板则拒单）；非完整封板模拟 |
| 行情 | 优先 Fuyao（有 Key）→ 东财公开快照 |
| dry-run | 默认；`--live` 才写账本 |

## CLI

```bash
# 开户（每个实验一个 account 名）
uv run paper-ashare --account agent-a accounts init --cash 1000000
uv run paper-ashare accounts list

uv run paper-ashare --account agent-a status
uv run paper-ashare --account agent-a portfolio
uv run paper-ashare --account agent-a order 600519 buy 100 "Thesis: …"
uv run paper-ashare --account agent-a order 600519 buy 100 "Thesis: …" --live
uv run paper-ashare --account agent-a fills
uv run paper-ashare --account agent-a orders
uv run paper-ashare quote 600519.SH 000001.SZ
```

离线自测（不拉行情）：

```bash
uv run paper-ashare --account demo accounts init --force --cash 100000
uv run paper-ashare --account demo order 600519 buy 100 "smoke" --live --fixed-price 1700
uv run paper-ashare --account demo portfolio
```

## 与 ClawStreet / Fuyao 分工

| 工具 | 用途 |
|------|------|
| `fuyao` | 官方结构化行情 / 研究（只读） |
| `paper-ashare` | A 股本地纸面成交与多账户 |
| `clawstreet` | 美股/crypto 竞赛纸面 |

## 明确非目标

- 限价挂单簿、部分成交、集合竞价、精确涨跌停封板  
- UI 自动化 / 逆向同花顺交易  
- 实盘 QMT（以后可另做 broker，账本语义对齐即可）
