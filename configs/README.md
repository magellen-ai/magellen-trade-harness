# configs/

| Path | Purpose |
|------|---------|
| `harnesses/<id>/` | Thin tool binding: `harness.yaml` (`skill_dirs`, `env_from`, `process_env`, `materialize`, `launch`, default wake actions) + template files referenced by `materialize` |
| `profiles/<id>/` | Experiment pack (`profile.yaml` → harness; `config.yaml`; `skeleton/` e.g. `CLAUDE.md` / `AGENTS.md`) |
| `schedules/<id>/` | Schedule strategy packs applied into `instances/*/schedule/rules.d/base/` (`default`, `pi-demo`, `ashare-pi-demo`, …) |
| `default.yaml` | Trade CLI defaults (dry-run, reasoning length, paper_ashare …) |

Harnesses do **not** share a settings schema. The framework only:

1. expands `env_from` (`$VAR` via repo `.env`) into process env (+ optional `process_env`)
2. renders `materialize` templates (`{{name}}`, `{{env.KEY}}`, …) into the instance
3. links `skills:` from repo `skills/`, and installs `skills_npx:` via **project-scoped**
   `npx skills add` with cwd=instance (into instance `.agents/skills/`; **no `-g`**)

```yaml
# profile config.yaml example
skills:
  - paper-ashare-trade
skills_npx:
  - package: HiThink-Tech/Financial-API
    skill: hithink-finance
# or: - HiThink-Tech/Financial-API@hithink-finance
```

`harness instance sync-settings|sync-skills` (and launch with `sync_before`) runs
`npx skills update -p -y` then re-adds each `skills_npx` entry **inside that instance**.
Do **not** vendor those skills under repo `skills/`, and do **not** use npx global installs
for harness-managed skills.

```bash
uv run harness harnesses list
uv run harness profiles list
uv run harness schedule packs
uv run harness instance init <name> --profile clawstreet-claude-default
uv run harness instance init <name> --profile clawstreet-pi-default
uv run harness instance init <name> --profile ashare-pi-paper
```
