# 本实例凭证（给人看）

A 股基本面 / 消息面研究。Grok Build 作 harness。不下单。
鉴权和默认模型用本机 `~/.grok`（会员登录）。工作区不写死模型。

本机还没登过就先在任意目录跑一次 `grok login`。

## 环境

行情密钥从仓库根 `.env` 按 config `env:` 注入：

| 变量 | 用途 |
|------|------|
| `HITHINK_FINANCE_API_KEY` | 同花顺 fuyao 行情 |
| `ANYSEARCH_API_KEY` | AnySearch 网页搜索（可选，提高限额） |
| `TAVILY_API_KEY` | 预留；yichen 不走 Tavily |

可选覆盖：`agent/secrets.env`（权限 600）。

```bash
# 在仓库根
uv run harness instance init <name> --agent ashare-grok-fundamental
uv run harness instance sync-settings <name>
uv run fuyao ping
```

搜索技能装在本实例内（不是全局）：

```yaml
skills_npx:
  - package: mcncarl/yichen-skills
    skill: yichen-unified-search
  - package: anysearch-ai/anysearch-skill
    skill: anysearch
```

`harness instance sync-settings` 读的是**实例** `config.yaml`，不是 profile。改 profile 后要同步改实例，或 `--force` 重建。

yichen 默认找 `~/.agents/skills/anysearch/runtime.conf`。本 harness 用 `ANYSEARCH_RUNTIME_CONFIG` 指到实例内 AnySearch。

## 启动

```bash
uv run harness instance sync-settings <name>
uv run harness instance sync-bin <name>
uv run harness instance launch <name>
# 或实例内：
./bin/grok
./bin/fuyao search 茅台
./bin/fuyao quote 600519.SH
```

用 `./bin/grok`（或 `harness instance launch`），不要在仓库根裸跑 `grok`：会把本仓开发用 `AGENTS.md` 读进研究会话。

## 调度

```bash
uv run harness schedule apply <name>
uv run harness schedule reload <name>
uv run harness schedule tick <name> --rule research-tick
```
