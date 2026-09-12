# Agent ops — {{name}}

OKX demo dual-MA on Grok Build (`grok-4.5`).

## Secrets

Prefer `agent/secrets.env` (and/or repo `.env` via profile `env:`):

```bash
OKX_APIKEY=...
OKX_API_SECRET=...
OKX_PASSPHRASE=...
OKX_SIMULATED=1
OKX_HTTP_PROXY=http://127.0.0.1:7890
```

Demo keys must be created under OKX **模拟交易**. Live keys + `OKX_SIMULATED=1` → `50101`.

## Launch

```bash
uv run harness instance launch {{name}}
# or
cd instances/{{name}} && ./bin/grok
```

## Schedule

```bash
uv run harness schedule apply {{name}}
# enable rules via local shadows, then:
uv run harness schedule reload {{name}}
uv run harness schedule tick {{name}} --rule scan-tick
```

Cron (every minute; flock inside tick):

```cron
* * * * * cd REPO && uv run harness schedule tick {{name}} >>instances/{{name}}/logs/schedule/cron.log 2>&1
```
