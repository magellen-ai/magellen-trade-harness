# Schedule — ashare-pi-paper

Bound to this profile. Agent trading context stays in instance `AGENTS.md` + `memory/`.

## Apply

```bash
uv run harness schedule apply <instance>
# or: uv run harness schedule apply <instance> --pack ashare-pi-paper
```

Ships `research-tick` **disabled** @ 4h. State (`schedule/state/`) is preserved across apply.

## Manual trigger

```bash
uv run harness schedule tick <instance> --rule research-tick
```
