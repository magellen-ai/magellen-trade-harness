from __future__ import annotations

import argparse
from pathlib import Path
from typing import ClassVar


class CliTool:
    id: str = ""
    executable: str = ""
    commands: ClassVar[dict[str, str]] = {}

    def parser(self) -> argparse.ArgumentParser | None:
        return None

    def command_helps(self) -> dict[str, str]:
        """Short command descriptions used when composing Agent context."""
        if self.commands:
            return dict(self.commands)
        parser = self.parser()
        if parser is None:
            return {}
        from ..agent_context import _subcommand_helps

        return _subcommand_helps(parser)

    def install(self, instance_dir: Path) -> None:
        return None

    def wrapper_argv(self, args: list[str]) -> list[str]:
        return ["uv", "run", self.executable, *args]

    def skill_paths(self) -> list[Path]:
        return []
