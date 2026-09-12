"""Built-in CLI capability declarations.

These are metadata-only objects.  The actual commands stay in their domain
packages; the runtime only needs stable names and concise help when generating
an Agent's context and validating profile configuration.
"""

from .cli import CliTool
from .registry import register_cli


class FuyaoCli(CliTool):
    id = executable = "fuyao"
    commands = {
        "ping": "Check API key + one snapshot",
        "quote": "A-share price snapshot",
        "search": "Ticker search",
        "bars": "Daily bars",
        "calendar": "A-share trading calendar",
        "http-docs": "Print endpoint map",
    }


class PaperAshareCli(CliTool):
    id, executable = "paper-ashare", "paper-ashare"
    commands = {
        "accounts": "Manage named paper accounts — `{init|list}`",
        "status": "Cash / equity / return",
        "portfolio": "Cash + positions",
        "order": "Place order (dry-run default)",
        "fills": "Ledger fills (source of truth)",
        "orders": "Ledger orders",
        "quote": "Last price via market-data cascade",
        "http-docs": "Print paper-broker documentation",
    }


class OkxCli(CliTool):
    id = executable = "okx"
    commands = {
        "status": "Account config + equity snapshot",
        "balance": "Account balance",
        "positions": "Open positions",
        "ticker": "Public ticker",
        "order": "Ordinary orders — `{place|cancel|amend|get}`",
        "orders": "List pending or history orders",
        "fills": "List fills",
        "algo": "Algo orders — `{place|sl|tp|oco|cancel}`",
        "algos": "List pending/history algo orders",
        "http-docs": "Print endpoint map",
    }


class ClawStreetCli(CliTool):
    id = executable = "clawstreet"
    commands = {
        "status": "Me + portfolio snapshot",
        "portfolio": "Portfolio",
        "order": "Place order (dry-run default)",
        "fills": "Platform fills (source of truth)",
        "orders": "Platform orders list",
        "audit": "Local audit log",
        "exposure": "Local exposure summary",
        "register": "Register agent",
        "http-docs": "Print endpoint map",
    }


class ScheduleCli(CliTool):
    id = executable = "schedule"
    commands = {
        "check": "Validate schedule/rules.d without activating",
        "reload": "Validate then atomically activate rules",
        "status": "Show active snapshot, drift, and per-rule state",
        "create": "Create an Agent-owned local interval wake rule",
        "list": "List Agent-owned local wake rules",
        "cancel": "Cancel an Agent-owned local wake rule",
    }


for _tool in (FuyaoCli, PaperAshareCli, OkxCli, ClawStreetCli, ScheduleCli):
    register_cli(_tool)
