"""Tests for the compact generated instance context."""

from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest
from pathlib import Path

from runtime.agent_context import render_tools_markdown
from runtime.instance import build_instance_config, compose_agent_context


class AgentContextTests(unittest.TestCase):
    def test_tool_index_omits_cli_descriptions(self) -> None:
        rendered = render_tools_markdown(
            {"bin": {"clawstreet": {"enable": ["status", "order"]}}}
        )
        self.assertIn("`./bin/clawstreet` — commands: `status`, `order`", rendered)
        self.assertNotIn("Me + portfolio snapshot", rendered)
        self.assertNotIn("Platform fills", rendered)

    def test_compose_keeps_profile_body_and_one_rules_section(self) -> None:
        cfg = {
            "profile": "clawstreet-claude-default",
            "agent_context": "CLAUDE.md",
            "bin": {"clawstreet": {"enable": ["status", "order"]}},
        }
        with TemporaryDirectory(prefix="agent-context-") as temp:
            path = compose_agent_context(Path(temp), cfg)
            body = path.read_text(encoding="utf-8")

        self.assertIn("Paper trader on ClawStreet", body)
        self.assertIn("`./bin/clawstreet` — commands: `status`", body)
        self.assertEqual(body.count("## Rules"), 1)
        self.assertIn("Keep secrets out of output and logs", body)

    def test_research_profile_exposes_read_only_okx_commands(self) -> None:
        cfg, _harness, _profile = build_instance_config(
            "probe", "crypto-news-research", agent_id="crypto-news-grok"
        )
        enabled = cfg["bin"]["okx"]["enable"]
        self.assertNotIn("order", enabled)
        self.assertIn("ticker", enabled)

        with TemporaryDirectory(prefix="agent-context-") as temp:
            path = compose_agent_context(Path(temp), cfg)
            body = path.read_text(encoding="utf-8")
        self.assertNotIn("`order`", body)
        self.assertNotIn("## Rules", body)

    def test_profile_boundaries_are_not_duplicated(self) -> None:
        cfg, _harness, _profile = build_instance_config(
            "probe", "okx-grok-ma", agent_id="okx-grok-ma"
        )
        with TemporaryDirectory(prefix="agent-context-") as temp:
            path = compose_agent_context(Path(temp), cfg)
            body = path.read_text(encoding="utf-8")
        self.assertIn("## 边界", body)
        self.assertNotIn("Keep secrets out of output and logs", body)


if __name__ == "__main__":
    unittest.main()
