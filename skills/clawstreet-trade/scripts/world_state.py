#!/usr/bin/env python3
"""Refresh memory/world_state.md from platform + local exposure (machine-generated).

Run from instance cwd (or with HARNESS_INSTANCE set):

  uv run python .agents/skills/clawstreet-trade/scripts/world_state.py
  uv run python …/world_state.py --out memory/world_state.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _repo_src() -> Path:
    # skills/.../scripts → repo root is parents[4] when linked as skills/clawstreet-trade
    # instance .agents/skills/clawstreet-trade/scripts → still find via clawstreet package
    return Path(__file__).resolve()


def _ensure_import() -> None:
    # Prefer installed package (uv run); fallback to repo src/
    try:
        import competitions.clawstreet  # noqa: F401
        return
    except ImportError:
        pass
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "src"
        if (candidate / "competitions" / "clawstreet").is_dir():
            sys.path.insert(0, str(candidate))
            return


def _find_instance() -> Optional[Path]:
    from competitions.clawstreet.secrets import find_instance_root

    return find_instance_root()


def _load_trade_config(inst: Path) -> dict[str, Any]:
    cfg_path = inst / "config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    with open(cfg_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        return {}
    trade = raw.get("trade") or {}
    return trade if isinstance(trade, dict) else {}


def _pos_rows(positions: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        rows.append(
            {
                "symbol": pos.get("symbol"),
                "qty": pos.get("qty"),
                "avg": pos.get("avg_cost") or pos.get("avg_price"),
                "mv": pos.get("market_value") or pos.get("mv"),
            }
        )
    return rows


def render_markdown(
    *,
    instance: str,
    book_tag: Optional[str],
    soft_limit: Optional[float],
    per_order_max: Optional[float],
    cash: float,
    equity: float,
    book_positions: list[dict[str, Any]],
    other_positions: list[dict[str, Any]],
    exposure: dict[str, Any],
    generated_at: str,
) -> str:
    live_used = float(exposure.get("live_used_usd") or 0)
    remaining = None if soft_limit is None else soft_limit - live_used
    lines = [
        "# world_state — machine snapshot",
        "",
        f"_Generated: `{generated_at}` (UTC). Agent: **read-only** — do not hand-edit._",
        "",
        "## Account",
        "",
        f"- Instance: `{instance}`",
        f"- Book tag: `{book_tag or '(none)'}`",
        f"- Cash: `${cash:,.2f}`",
        f"- Equity: `${equity:,.2f}`",
        "",
        "## Soft limit (this book)",
        "",
    ]
    if soft_limit is not None:
        lines.append(f"- Soft limit: `${soft_limit:,.2f}`")
        lines.append(f"- Live used (local audit): `${live_used:,.2f}`")
        lines.append(f"- Remaining: `${(remaining or 0):,.2f}`")
    else:
        lines.append("- Soft limit: _(not configured)_")
        lines.append(f"- Live used (local audit): `${live_used:,.2f}`")
    if per_order_max is not None:
        lines.append(f"- Per-order max: `${per_order_max:,.2f}`")
    lines.append(
        f"- Dry-run intent today: `${float(exposure.get('dry_run_intent_usd_today') or 0):,.2f}`"
    )
    lines.append(
        f"- Counts: live_orders={exposure.get('live_order_count')} "
        f"dry_run_today={exposure.get('dry_run_order_count_today')}"
    )
    lines.extend(["", "## Positions — this book (audit-attributed)", ""])
    lines.append(
        "Attribution is **local audit live fills for this book_tag**, not platform tags. "
        "Unattributed account positions (incl. historical residuals) are under **other**."
    )
    lines.append("")
    if book_positions:
        lines.append("| Symbol | Qty | Avg | Note |")
        lines.append("|--------|-----|-----|------|")
        for p in book_positions:
            lines.append(
                f"| {p.get('symbol')} | {p.get('qty')} | {p.get('avg')} | book |"
            )
    else:
        lines.append("_(none)_")
    lines.extend(["", "## Positions — account other / historical", ""])
    if other_positions:
        lines.append("| Symbol | Qty | Avg | Note |")
        lines.append("|--------|-----|-----|------|")
        for p in other_positions:
            lines.append(
                f"| {p.get('symbol')} | {p.get('qty')} | {p.get('avg')} | "
                f"do not 'fix' |"
            )
    else:
        lines.append("_(none)_")
    lines.extend(
        [
            "",
            "## Ops",
            "",
            "- Refresh: wake `before` hook or "
            "`uv run python .agents/skills/clawstreet-trade/scripts/world_state.py`",
            "- Exposure CLI: `./bin/clawstreet exposure --json`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Refresh memory/world_state.md")
    parser.add_argument(
        "--out",
        default="memory/world_state.md",
        help="Output path relative to instance (default memory/world_state.md)",
    )
    parser.add_argument("--json", action="store_true", help="Also print JSON summary to stdout")
    args = parser.parse_args(argv[1:])

    _ensure_import()
    from competitions.clawstreet.audit import AuditLog, compute_exposure
    from competitions.clawstreet.client import ClawStreetClient
    from competitions.clawstreet.secrets import load_secrets_into_environ

    inst = _find_instance()
    if inst is None:
        print("Error: no instance root (set HARNESS_INSTANCE or cwd under instances/)", file=sys.stderr)
        return 1

    try:
        load_secrets_into_environ()
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    trade = _load_trade_config(inst)
    book_tag = trade.get("book_tag")
    soft_limit = trade.get("soft_limit_usd")
    per_order = trade.get("per_order_max_usd")
    _ = trade.get("symbol_prefix")  # domain hint lives in AGENTS.md / RiskGate

    client = ClawStreetClient()
    try:
        portfolio = client.get_portfolio()
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching portfolio: {e}", file=sys.stderr)
        return 1

    cash = float(portfolio.get("cash") or 0)
    equity = float(portfolio.get("equity") or 0)
    positions = _pos_rows(list(portfolio.get("positions") or []))

    audit = AuditLog(str(inst / "audit" / "events.jsonl"))
    entries = audit.read_entries(limit=None) if audit.enabled else []
    exposure = compute_exposure(entries, book_tag=book_tag)

    # Attribution: only symbols with live (non dry-run) submitted orders for this
    # book_tag count as "this book". Everything else on the shared account is
    # "other / historical" (e.g. residual 0.002 BTC from early API probes).
    book_symbols: set[str] = set()
    for e in entries:
        if book_tag is not None and e.get("book_tag") != book_tag:
            continue
        if e.get("event") == "order.submitted" and not e.get("dry_run"):
            sym = e.get("symbol")
            if sym:
                book_symbols.add(str(sym))

    book_positions = []
    other_positions = []
    for p in positions:
        sym = str(p.get("symbol") or "")
        if sym in book_symbols:
            book_positions.append(p)
        else:
            other_positions.append(p)

    generated_at = datetime.now(timezone.utc).isoformat()
    md = render_markdown(
        instance=inst.name,
        book_tag=book_tag,
        soft_limit=float(soft_limit) if soft_limit is not None else None,
        per_order_max=float(per_order) if per_order is not None else None,
        cash=cash,
        equity=equity,
        book_positions=book_positions,
        other_positions=other_positions,
        exposure=exposure,
        generated_at=generated_at,
    )

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = inst / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)

    if args.json:
        print(
            json.dumps(
                {
                    "instance": inst.name,
                    "book_tag": book_tag,
                    "cash": cash,
                    "equity": equity,
                    "exposure": exposure,
                    "path": str(out_path),
                    "generated_at": generated_at,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
