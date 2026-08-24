# Operator notes — ashare-pi-demo schedule pack

Agent trading context stays in instance `AGENTS.md` + `memory/` — not here.

## Apply

```bash
uv run harness schedule apply <instance> --pack ashare-pi-demo
```

Ships `research-tick` **disabled** @ 4h. State (`schedule/state/`) is preserved across apply.

## Manual trigger (primary test path)

```bash
# enable via local shadow (enabled: true), reload, then:
uv run harness schedule tick <instance> --rule research-tick
```

## Real timer (cron)

```cron
* * * * * cd /path/to/magellen-trade-harness && uv run harness schedule tick <instance> >>instances/<instance>/logs/schedule/cron.log 2>&1
```
