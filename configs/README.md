# configs/

| Path | Purpose |
|------|---------|
| `harnesses/<id>/` | Thin tool binding (`harness.yaml`: launch, skill_dirs, settings, default wake actions) |
| `profiles/<id>/` | Experiment pack (`profile.yaml` → harness; `config.yaml`; `skeleton/` e.g. CLAUDE.md) |
| `schedules/<id>/` | Schedule strategy packs applied into `instances/*/schedule/rules.d/base/` |
| `default.yaml` | ClawStreet CLI trade defaults (dry-run, reasoning length) |

```bash
uv run harness harnesses list
uv run harness profiles list
uv run harness schedule packs
uv run harness instance init <name> --profile clawstreet-claude-default
```
