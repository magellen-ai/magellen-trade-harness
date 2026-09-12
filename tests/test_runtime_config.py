"""Tests for the runtime configuration boundary."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from runtime.config import ConfigError, ModelRef, validate_repository, write_yaml
from runtime.tools import get_cli


class ModelRefTests(unittest.TestCase):
    def test_parse_and_qualify(self) -> None:
        ref = ModelRef.parse("magellen/grok-4.5")
        assert ref is not None
        self.assertEqual(ref.provider, "magellen")
        self.assertEqual(ref.name, "grok-4.5")
        self.assertEqual(ref.qualified, "magellen/grok-4.5")

    def test_bare_reference_is_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            ModelRef.parse("grok-4.5")


class RepositoryValidationTests(unittest.TestCase):
    def _repository(self) -> Path:
        temp_dir = TemporaryDirectory(prefix="harness-config-")
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        (root / "configs" / "harnesses" / "demo").mkdir(parents=True)
        (root / "configs" / "profiles" / "demo" / "skeleton").mkdir(parents=True)
        (root / "configs" / "agents" / "demo").mkdir(parents=True)
        (root / "configs" / "providers").mkdir(parents=True)
        write_yaml(
            root / "configs" / "harnesses" / "demo" / "harness.yaml",
            {"agent_context": "AGENTS.md", "launch": {"argv": ["demo"]}},
        )
        write_yaml(
            root / "configs" / "profiles" / "demo" / "config.yaml",
            {"harness": "demo", "skills": [], "tools": ["schedule"]},
        )
        write_yaml(
            root / "configs" / "agents" / "demo" / "agent.yaml",
            {"profile": "demo", "harness": "demo"},
        )
        write_yaml(
            root / "configs" / "providers" / "demo.yaml",
            {"protocol": "openai-compatible", "models": ["demo"]},
        )
        return root

    def test_valid_repository_has_no_errors(self) -> None:
        root = self._repository()
        self.assertEqual(validate_repository(root), [])

    def test_unknown_harness_is_reported(self) -> None:
        root = self._repository()
        write_yaml(
            root / "configs" / "profiles" / "demo" / "config.yaml",
            {"harness": "missing", "skills": [], "tools": ["schedule"]},
        )
        issues = validate_repository(root)
        self.assertTrue(any("unknown harness" in issue.message for issue in issues))


class CliMetadataTests(unittest.TestCase):
    def test_registered_tools_expose_command_help_without_importing_cli(self) -> None:
        commands = get_cli("okx").command_helps()
        self.assertIn("ticker", commands)
        self.assertIn("order", commands)


if __name__ == "__main__":
    unittest.main()
