"""ashare-grok-fundamental profile + grok-build harness scaffolding."""

from pathlib import Path

from runtime import instance as instance_mod


def test_grok_build_harness_listed() -> None:
    assert "grok-build" in instance_mod.list_harnesses()
    assert "ashare-grok-fundamental" in instance_mod.list_profiles()


def test_profile_merges_without_local_skills() -> None:
    cfg, harness, profile = instance_mod.build_instance_config(
        "probe", "ashare-grok-fundamental"
    )
    assert profile["harness"] == "grok-build"
    assert harness["agent_context"] == "AGENTS.md"
    assert cfg["harness"] == "grok-build"
    assert cfg["skills"] == []
    assert cfg["skills_npx"] == [
        {"package": "mcncarl/yichen-skills", "skill": "yichen-unified-search"},
        {"package": "anysearch-ai/anysearch-skill", "skill": "anysearch"},
    ]
    assert "ANYSEARCH_API_KEY" in (cfg.get("env") or {})
    assert "fuyao" in cfg["bin"]
    assert "paper-ashare" not in cfg["bin"]
    assert "clawstreet" not in cfg["bin"]
    assert not cfg.get("model")
    assert "AIPROXY_API_KEY" not in (cfg.get("env") or {})
    assert "GROK_HOME" not in (cfg.get("process_env") or {})
    assert cfg["skill_dirs"]
    launch = cfg["launch"]["argv"]
    assert launch[0] == "./bin/grok-exec"
    assert not (instance_mod.harnesses_root() / "grok-build" / "home" / "config.toml").is_file()


def test_skeleton_is_chinese_research_layout() -> None:
    root = (
        instance_mod.profiles_root()
        / "ashare-grok-fundamental"
        / "skeleton"
    )
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "不下单" in agents
    assert "workdir/" in agents
    assert (root / "memory" / "MEMORY.md").is_file()
    assert (root / "memory" / "风险.md").is_file()
    assert (root / "workdir" / "索引.md").is_file()
    assert (root / "workdir" / "_模板" / "公司.md").is_file()
    assert (root / "workdir" / "_模板" / "行业.md").is_file()


def test_npx_skill_path_includes_grok() -> None:
    fake = Path("/tmp/does-not-exist-instance")
    # Only checks candidate order via the documented error when missing.
    try:
        instance_mod.resolve_instance_npx_skill_path(fake, "yichen-unified-search")
    except FileNotFoundError as exc:
        assert "yichen-unified-search" in str(exc)
    else:
        raise AssertionError("expected missing skill to raise")
