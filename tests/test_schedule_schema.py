"""Pure schedule trigger tests."""

from __future__ import annotations

from datetime import datetime
import unittest

from runtime.schedule_schema import cron_matches, parse_cron, parse_interval


class ScheduleSchemaTests(unittest.TestCase):
    def test_interval_units(self) -> None:
        self.assertEqual(parse_interval("30s"), 30)
        self.assertEqual(parse_interval("2h"), 7200)
        with self.assertRaises(ValueError):
            parse_interval("0m")

    def test_cron_matches_local_time(self) -> None:
        spec = parse_cron("0 9 * * 1-5")
        self.assertTrue(cron_matches(spec, datetime(2026, 9, 7, 9, 0)))
        self.assertFalse(cron_matches(spec, datetime(2026, 9, 6, 9, 0)))

    def test_invalid_cron_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_cron("every morning")


if __name__ == "__main__":
    unittest.main()
