# configs/

| Path | Purpose |
|------|---------|
| `harnesses/<id>/` | Thin tool binding: `harness.yaml` (`agent_context`, `process_env`, `materialize`, `launch`) |
| `profiles/<id>/` | Experiment: `profile.yaml` → harness; `config.yaml` (`bin` / `skills` / `env` / `trade`); `skeleton/`; **`schedule/`** |
| `default.yaml` | Trade CLI defaults (dry-run, reasoning length, paper_ashare …) |

Schedule rules are **bound to the profile**. Init seeds `schedule/rules.d/base/` from `configs/profiles/<profile>/schedule/` when empty; re-apply with `harness schedule apply <instance>` (optional `--pack <profile>`).

Harnesses do **not** share a settings schema. The framework only:

1. expands `config.yaml` → `env` (`$VAR` via repo `.env`) into process env (+ optional `process_env`)
2. renders `materialize` templates (`{{name}}`, `{{env.KEY}}`, `{{default_model}}`, …) into the instance
3. links `skills:` / installs `skills_npx:` (project-scoped `npx skills add`, cwd=instance; **no `-g`**)
4. writes `bin/` from profile `bin:` and appends generated **Tools/Rules** onto `agent_context` (`AGENTS.md` / `CLAUDE.md`)

`bin.*.enable` entries are regexes matched with `re.fullmatch` (e.g. `(?!register$).*` excludes `register`).

```bash
uv run harness harnesses list
uv run harness profiles list
uv run harness schedule packs
uv run harness instance init <name> --profile clawstreet-pi-default
uv run harness instance sync-bin <name>   # bin/ + agent context Tools/Rules
uv run harness schedule apply <name>
```
