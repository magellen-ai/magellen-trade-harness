#!/usr/bin/env bash
# Real grok binary wrapper. Makes the instance its own git root so Grok Build
# does not walk up to the harness repo AGENTS.md. Auth/model stay on ~/.grok.
set -euo pipefail
INSTANCE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INSTANCE"
unset GROK_HOME
if [[ ! -d .git ]]; then
  git init -q
  if [[ ! -f .gitignore ]]; then
    cat > .gitignore <<'EOF'
agent/secrets.env
logs/
audit/
schedule/state/
EOF
  fi
fi
exec grok "$@"
