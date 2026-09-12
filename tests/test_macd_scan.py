"""Unit tests for MACD cross detection (no network)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


def _load_macd():
    path = (
        Path(__file__).resolve().parents[1]
        / "configs"
        / "profiles"
        / "clawstreet-pi-default"
        / "skeleton"
        / "scripts"
        / "macd_scan.py"
    )
    spec = importlib.util.spec_from_file_location("macd_scan", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MacdCrossTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_macd()

    def test_detect_golden_on_synthetic_dif_dea(self) -> None:
        # Prior: dif <= dea; last: dif > dea
        dif = [None, None, -1.0, -0.5, 0.1]
        dea = [None, None, 0.0, 0.0, 0.0]
        self.assertEqual(self.m.detect_cross(dif, dea), "golden")

    def test_detect_death_on_synthetic_dif_dea(self) -> None:
        dif = [None, None, 1.0, 0.5, -0.1]
        dea = [None, None, 0.0, 0.0, 0.0]
        self.assertEqual(self.m.detect_cross(dif, dea), "death")

    def test_no_cross(self) -> None:
        dif = [None, 1.0, 1.1, 1.2]
        dea = [None, 0.0, 0.0, 0.0]
        self.assertIsNone(self.m.detect_cross(dif, dea))

    def test_macd_series_length(self) -> None:
        closes = [float(i) for i in range(1, 80)]
        dif, dea, hist = self.m.macd_series(closes)
        self.assertEqual(len(dif), len(closes))
        self.assertEqual(len(dea), len(closes))
        self.assertEqual(len(hist), len(closes))
        self.assertIsNotNone(dif[-1])
        self.assertIsNotNone(dea[-1])


if __name__ == "__main__":
    unittest.main()
