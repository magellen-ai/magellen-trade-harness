# Risks

- Demo only. Never flip to live OKX keys from this instance without an explicit human grant.
- `--live` on `./bin/okx` means **OKX simulated**, not dry-run.
- Slippage / fee on tiny notionals can dominate; keep sizes small.
- MA lag: late crosses after a move — skip chase if already extended.
