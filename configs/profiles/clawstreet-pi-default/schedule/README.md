# Schedule — clawstreet-pi-default (crypto always-on)

Bound to this profile. Lives at `configs/profiles/clawstreet-pi-default/schedule/`.

## Apply

```bash
# uses instance config.yaml → profile
uv run harness schedule apply <instance>
# or explicit:
uv run harness schedule apply <instance> --pack clawstreet-pi-default
```

Ships three rules **disabled** by default:

| Rule | Trigger | Condition | Purpose |
|------|---------|-----------|---------|
| `scan-tick` | interval 1h | `macd_scan.py` (exit 1 = skip) | MACD cross → wake |
| `research-tick` | interval 4h | none | Routine patrol |
| `risk-tick` | cron `0 9,21 * * *` | none | Reduce-only reconcile |

Enable via `schedule/rules.d/local/` shadows (`enabled: true`), then reload.

## Cron

```cron
* * * * * cd /path/to/magellen-trade-harness && uv run harness schedule tick <instance> >>instances/<instance>/logs/schedule/cron.log 2>&1
```
