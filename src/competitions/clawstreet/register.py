"""Register a new ClawStreet agent and store the one-time API key.

Never prints api_key. Prefer writing into an instance agent/ directory.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from .secrets import GLOBAL_SECRETS, agent_dir, instance_secrets_path

ENDPOINT = "https://www.clawstreet.io/v1/me/agents"

DEFAULT_PAYLOAD = {
    "name": "Magellen Research",
    "ticker": "MRES",
    "bio": (
        "Fundamental-research paper trader. Evidence and thesis first, then orders. "
        "No ML stock picking. No real-money auto trading. Human-auditable reasoning on every trade."
    ),
    "model": "Grok",
    "framework": "Custom Harness",
    "strategy": (
        "Research-first paper trading on liquid US equities. Build an evidence-backed thesis "
        "(business quality, growth drivers, valuation band, key risks), require human-auditable "
        "reasoning on every order, size positions conservatively, and avoid ML factor picking "
        "or high-frequency technical churn."
    ),
    "personality": (
        "Patient, skeptical, concise. Prefers boring evidence over hype. Will hold cash when "
        "the thesis is weak, and explains the bear case before buying."
    ),
    "strategy_tags": ["fundamental", "research", "long-bias", "us-equities"],
}


def _post_register(payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {e.code}: {err}") from e
    return data


def _extract(data: dict[str, Any]) -> tuple[str, str, Optional[str], Optional[str]]:
    api_key = data.get("api_key")
    agent = data.get("agent") if isinstance(data.get("agent"), dict) else {}
    bot_id = (
        data.get("bot_id")
        or data.get("id")
        or data.get("agent_id")
        or agent.get("id")
        or agent.get("bot_id")
    )
    claim_url = data.get("claim_url") or agent.get("claim_url")
    verification_code = data.get("verification_code") or agent.get("verification_code")
    if not api_key or not bot_id:
        raise RuntimeError(
            f"unexpected register response keys={sorted(data.keys())}; "
            "api_key/bot_id missing"
        )
    return str(api_key), str(bot_id), claim_url, verification_code


def write_secrets_file(
    path: Path,
    api_key: str,
    agent_id: str,
    *,
    name: str,
    ticker: str,
    claim_url: Optional[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# ClawStreet agent secrets — do not commit / print\n"
        f"CLAWSTREET_API_KEY={api_key}\n"
        f"CLAWSTREET_AGENT_ID={agent_id}\n"
        f"CLAWSTREET_BOT_ID={agent_id}\n"
        f"CLAWSTREET_AGENT_NAME={name}\n"
        f"CLAWSTREET_AGENT_TICKER={ticker}\n"
    )
    if claim_url:
        text += f"CLAWSTREET_CLAIM_URL={claim_url}\n"
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def register_agent(
    *,
    instance_root: Optional[Path] = None,
    name: Optional[str] = None,
    ticker: Optional[str] = None,
    force: bool = False,
    payload_overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Register a new ClawStreet agent. Returns public metadata only."""
    payload = dict(DEFAULT_PAYLOAD)
    if name:
        payload["name"] = name
    if ticker:
        payload["ticker"] = ticker
    if payload_overrides:
        payload.update(payload_overrides)

    if instance_root is not None:
        dest = instance_secrets_path(instance_root)
        public_path = agent_dir(instance_root) / "public.json"
    else:
        dest = GLOBAL_SECRETS
        public_path = GLOBAL_SECRETS.parent / "clawstreet_agent.json"

    if dest.exists() and not force:
        raise FileExistsError(
            f"REFUSING: secrets already exist at {dest}. Pass --force to overwrite."
        )

    data = _post_register(payload)
    api_key, bot_id, claim_url, verification_code = _extract(data)

    write_secrets_file(
        dest,
        api_key,
        bot_id,
        name=payload["name"],
        ticker=payload["ticker"],
        claim_url=claim_url,
    )

    public = {
        "name": payload["name"],
        "ticker": payload["ticker"],
        "model": payload.get("model"),
        "framework": payload.get("framework"),
        "agent_id": bot_id,
        "claim_url": claim_url,
        "verification_code": verification_code,
        "secrets_path": str(dest),
        "has_api_key": True,
    }
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(public_path, 0o600)

    # Clear sensitive locals
    del api_key
    del data

    return public
