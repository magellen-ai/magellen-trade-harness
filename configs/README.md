# configs/

| Path | Purpose |
|------|---------|
| `harnesses/<id>/` | Thin tool binding: `harness.yaml` (`agent_context`, `process_env`, `materialize`, `launch`) |
| `profiles/<id>/` | Experiment: `config.yaml` (`bin` / `skills` / `env` / `trade`); `skeleton/`; **`schedule/`** |
| `default.yaml` | Trade CLI defaults (dry-run, reasoning length, paper_ashare …) |

Run `uv run harness config check` before creating an instance. It validates
harness/profile/agent/provider references, materialize sources, skill paths,
and registered CLI capabilities without loading secrets or making network calls.

Schedule rules are **bound to the profile**. Init seeds `schedule/rules.d/base/` from `configs/profiles/<profile>/schedule/` when empty; re-apply with `harness schedule apply <instance>` (optional `--pack <profile>`).

Harnesses do **not** share a settings schema. The framework only:

1. expands `config.yaml` → `env` (`$VAR` via repo `.env`) into process env (+ optional `process_env`)
2. renders `materialize` templates (`{{name}}`, `{{env.KEY}}`, `{{default_model}}`, …) into the instance
3. links `skills:` / installs `skills_npx:` (project-scoped `npx skills add`, cwd=instance; **no `-g`**)
4. writes `bin/` from profile `bin:` and appends a compact tool index to `agent_context` (`AGENTS.md` / `CLAUDE.md`); profile rules are kept as written

`bin.*.enable` entries are regexes matched with `re.fullmatch` (e.g. `(?!register$).*` excludes `register`).

```bash
uv run harness harnesses list
uv run harness profiles list
uv run harness schedule packs
uv run harness instance init <name> --agent clawstreet-pi-default
uv run harness instance init <name> --agent ashare-grok-fundamental

uv run harness instance sync-bin <name>   # bin/ + compact agent context tool index
uv run harness schedule apply <name>
```
