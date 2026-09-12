#!/usr/bin/env bash
# Instance-local Grok Build launcher (materialized). Goes through
# `harness instance launch` (compat env + git init). Auth stays on ~/.grok.
set -euo pipefail
ROOT="{{repo_root}}"
NAME="{{name}}"
cd "$ROOT"
exec uv run harness instance launch "$NAME" -- "$@"
