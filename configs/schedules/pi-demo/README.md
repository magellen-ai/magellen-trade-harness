# Operator notes for the PI demo schedule pack.
# Agent trading context stays in instance AGENTS.md + memory/ — not here.

## Apply

```bash
uv run harness schedule apply <instance> --pack pi-demo
```

Ships `research-tick` **disabled** @ 4h. State (`schedule/state/`) is preserved across apply.

## Manual trigger (primary test path)

Force one wake regardless of interval:

```bash
# enable first via local shadow, reload, then:
uv run harness schedule tick <instance> --rule research-tick
```

## Real timer (cron)

Runner should tick often; rules decide what is due:

```cron
* * * * * cd /path/to/magellen-trade-harness && uv run harness schedule tick <instance> >>instances/<instance>/logs/schedule/cron.log 2>&1
```

For a one-shot interval smoke test, put a local shadow with `every: 5m` + `enabled: true`,
reload, wait for a single FIRED line, then set `enabled: false` and reload again.
