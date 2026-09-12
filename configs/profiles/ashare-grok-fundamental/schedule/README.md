# 调度 — ashare-grok-fundamental

绑定本 profile。Agent 研究上下文在实例 `AGENTS.md` + 共用 `memory/` + `workdir/`。

## 套用

```bash
uv run harness schedule apply <instance>
# 或：uv run harness schedule apply <instance> --pack ashare-grok-fundamental
```

自带 `research-tick`，出厂 **关闭**，间隔 4 小时。`schedule/state/` 在 apply 时保留。

## 手工触发

```bash
uv run harness schedule tick <instance> --rule research-tick
```
