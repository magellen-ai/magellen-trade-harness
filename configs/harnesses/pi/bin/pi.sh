#!/usr/bin/env bash
# Instance-local Pi launcher (materialized). Sets PI_CODING_AGENT_* and applies
# project-only flags via `harness instance launch` — do not invoke bare `pi`.
set -euo pipefail
ROOT="{{repo_root}}"
NAME="{{name}}"
cd "$ROOT"
exec uv run harness instance launch "$NAME" -- "$@"
