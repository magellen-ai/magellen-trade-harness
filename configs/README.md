# configs/

| Path | Purpose |
|------|---------|
| `harnesses/<id>/` | Thin tool binding: `harness.yaml` (`skill_dirs`, `env_from`, `process_env`, `materialize`, `launch`, default wake actions) + template files referenced by `materialize` |
| `profiles/<id>/` | Experiment pack (`profile.yaml` → harness; `config.yaml`; `skeleton/` e.g. `CLAUDE.md` / `AGENTS.md`) |
| `schedules/<id>/` | Schedule strategy packs applied into `instances/*/schedule/rules.d/base/` |
| `default.yaml` | ClawStreet CLI trade defaults (dry-run, reasoning length) |

Harnesses do **not** share a settings schema. The framework only:

1. expands `env_from` (`$VAR` via repo `.env`) into process env (+ optional `process_env`)
2. renders `materialize` templates (`{{name}}`, `{{env.KEY}}`, …) into the instance

```bash
uv run harness harnesses list
uv run harness profiles list
uv run harness schedule packs
uv run harness instance init <name> --profile clawstreet-claude-default
uv run harness instance init <name> --profile clawstreet-pi-default
```
