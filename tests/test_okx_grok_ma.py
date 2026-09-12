"""okx-grok-ma profile scaffolding tests."""

import unittest

from runtime import instance as instance_mod


class OkxGrokMaProfileTest(unittest.TestCase):
    def test_profile_listed_and_merges(self) -> None:
        self.assertIn("okx-grok-ma", instance_mod.list_profiles())
        cfg, harness, profile = instance_mod.build_instance_config("probe", "okx-grok-ma")
        self.assertEqual(profile["harness"], "grok-build")
        self.assertEqual(harness["agent_context"], "AGENTS.md")
        self.assertEqual(cfg["model"], "grok-4.5")
        self.assertIn("okx", cfg["bin"])
        self.assertNotIn("clawstreet", cfg["bin"])
        self.assertEqual(
            cfg["launch"]["argv"][:4],
            ["./bin/grok-exec", "-m", "grok-4.5", "--always-approve"],
        )
        wake = cfg["schedule"]["actions"]["wake-main"]["argv"]
        self.assertEqual(wake[:5], ["./bin/grok-exec", "-m", "grok-4.5", "-p", "{prompt}"])

    def test_skeleton_layout(self) -> None:
        root = instance_mod.profiles_root() / "okx-grok-ma" / "skeleton"
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("OKX", agents)
        self.assertTrue((root / "scripts" / "ma_scan.py").is_file())
        self.assertTrue((root / "memory" / "world_state.md").is_file())


if __name__ == "__main__":
    unittest.main()
