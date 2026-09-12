# Schedule — okx-grok-ma (OKX demo dual-MA)

```bash
uv run harness schedule apply <instance>
```

| Rule | Trigger | Condition | Purpose |
|------|---------|-----------|---------|
| `scan-tick` | interval 15m | `scripts/ma_scan.py`（exit 1=skip） | 新金叉/死叉 → wake Grok |
| `research-tick` | interval 1h | none | 例行巡检（默认可开） |

出厂 `enabled: false`。用 `schedule/rules.d/local/` 同 id 覆盖 `enabled: true`，再 `reload`。

```cron
* * * * * cd /path/to/magellen-trade-harness && uv run harness schedule tick <instance> >>instances/<instance>/logs/schedule/cron.log 2>&1
```
