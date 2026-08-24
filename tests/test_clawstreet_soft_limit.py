"""Unit tests for soft-limit RiskGate + audit exposure (no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from competitions.clawstreet.audit import AuditLog, compute_exposure
from competitions.clawstreet.decision import Decision
from competitions.clawstreet.risk import RiskGate


class SoftLimitTests(unittest.TestCase):
    def test_live_rejects_over_soft_limit(self) -> None:
        gate = RiskGate({"soft_limit_usd": 20000, "per_order_max_usd": 2000})
        d = Decision.create("X:BTCUSD", "buy", 1.0, "Enough reasoning here for gate.")
        ok, err, warn = gate.check(
            d, dry_run=False, notional_usd=2500, used_notional_usd=0
        )
        self.assertFalse(ok)
        self.assertIn("per_order_max_usd", err or "")
        self.assertIsNone(warn)

    def test_live_rejects_book_overflow(self) -> None:
        gate = RiskGate({"soft_limit_usd": 20000, "per_order_max_usd": 5000})
        d = Decision.create("X:BTCUSD", "buy", 0.1, "Enough reasoning here for gate.")
        ok, err, _ = gate.check(
            d, dry_run=False, notional_usd=1500, used_notional_usd=19000
        )
        self.assertFalse(ok)
        self.assertIn("soft_limit_usd", err or "")

    def test_dry_run_warns_only(self) -> None:
        gate = RiskGate({"soft_limit_usd": 20000, "per_order_max_usd": 2000})
        d = Decision.create("X:BTCUSD", "buy", 1.0, "Enough reasoning here for gate.")
        ok, err, warn = gate.check(
            d, dry_run=True, notional_usd=5000, used_notional_usd=18000
        )
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertIsNotNone(warn)
        self.assertIn("per_order_max_usd", warn or "")

    def test_audit_tags_and_exposure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            audit = AuditLog(str(path))
            d = Decision.create(
                "X:BTCUSD",
                "buy",
                0.01,
                "Path check with tags.",
                strategy="macd-v0",
                book_tag="crypto-pi",
            ).to_dict()
            audit.write_event(
                "order.submitted",
                d,
                {"order_id": "o1", "idempotency_key": "pi-test--abc"},
                dry_run=False,
                instance="pi-test",
                book_tag="crypto-pi",
                strategy="macd-v0",
                notional_usd=1000.0,
            )
            audit.write_event(
                "order.dry_run",
                d,
                {"order_id": "dry-run-mock"},
                dry_run=True,
                instance="pi-test",
                book_tag="crypto-pi",
                strategy="macd-v0",
                notional_usd=500.0,
            )
            # Legacy row without new fields must not crash
            with open(path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": "2026-01-01T00:00:00+00:00",
                            "event": "order.submitted",
                            "symbol": "AAPL",
                            "side": "buy",
                            "qty": 1,
                            "dry_run": False,
                        }
                    )
                    + "\n"
                )

            entries = audit.read_entries(book_tag="crypto-pi")
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["book_tag"], "crypto-pi")

            all_entries = audit.read_entries()
            exp = compute_exposure(all_entries, book_tag="crypto-pi")
            self.assertEqual(exp["live_used_usd"], 1000.0)
            self.assertEqual(exp["dry_run_intent_usd_today"], 500.0)
            self.assertGreaterEqual(exp["skipped_missing_notional"], 0)

            # sell reduces exposure
            audit.write_event(
                "order.submitted",
                {**d, "side": "sell"},
                {"order_id": "o2"},
                dry_run=False,
                book_tag="crypto-pi",
                notional_usd=200.0,
            )
            all_entries = audit.read_entries()
            exp2 = compute_exposure(all_entries, book_tag="crypto-pi")
            self.assertEqual(exp2["live_used_usd"], 800.0)


if __name__ == "__main__":
    unittest.main()
