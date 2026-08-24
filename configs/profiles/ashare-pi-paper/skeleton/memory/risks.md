# Risks & live gates

Read before sizing or `--live`. Mark resolved items `[closed]`.
`--live` authorization must be explicit, scoped, and dated.

## Portfolio / rule risks

- [ ] Slippage / fees / limit-up heuristics are simplified
- [ ] T+1: same-day buys cannot be sold
- [ ] Public quote fallbacks may lag or fail; prefer fuyao when keyed
- [ ] (concentration, event window, …)

## Position invalidation

| Symbol | Invalidation | Action if hit | Status |
|--------|--------------|---------------|--------|
|        |              |               | open   |

## `--live` authorization

Default: **no live paper orders** (CLI still defaults to dry-run).

To allow live paper ledger writes, add an unexpired block:

```text
## LIVE grant — YYYY-MM-DD
- Scope: symbols / max qty / max notionals
- Account: default
- Expires: YYYY-MM-DD or “after N live fills”
- Granted by:
- Revoked: (date + reason) | active
```

_(no active LIVE grant)_
