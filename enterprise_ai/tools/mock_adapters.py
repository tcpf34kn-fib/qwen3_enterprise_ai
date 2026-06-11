from __future__ import annotations

from .base import ToolAdapter, ToolExecutor
from ..domain import ToolResult


class GrafanaAdapter(ToolAdapter):
    name = "grafana"

    def run(self, operation: str, parameters: dict[str, object]) -> ToolResult:
        return ToolResult(
            tool=self.name,
            operation=operation,
            success=True,
            data={
                "dashboard": parameters.get("dashboard", "network-overview"),
                "summary": "No abnormal metric spike in the mock dashboard.",
            },
        )


class Icinga2Adapter(ToolAdapter):
    name = "icinga2"

    def run(self, operation: str, parameters: dict[str, object]) -> ToolResult:
        host = parameters.get("host") or "unknown"
        return ToolResult(
            tool=self.name,
            operation=operation,
            success=True,
            data={
                "host": host,
                "state": "down" if host != "unknown" else "unknown",
                "last_check": "mock",
                "plugin_output": "Host unreachable in mock status check.",
            },
        )


class LibreNmsAdapter(ToolAdapter):
    name = "librenms"

    def run(self, operation: str, parameters: dict[str, object]) -> ToolResult:
        return ToolResult(
            tool=self.name,
            operation=operation,
            success=True,
            data={
                "device": parameters.get("device") or parameters.get("host") or "unknown",
                "cpu": "normal",
                "memory": "normal",
                "interfaces": "one uplink has no carrier in mock data",
            },
        )


class ClickHouseAdapter(ToolAdapter):
    name = "clickhouse"

    def run(self, operation: str, parameters: dict[str, object]) -> ToolResult:
        return ToolResult(
            tool=self.name,
            operation=operation,
            success=True,
            data={
                "window": parameters.get("window", "24h"),
                "top_talkers": [
                    {"src": "10.0.0.10", "dst": "8.8.8.8", "gb": 12.4},
                    {"src": "10.0.0.22", "dst": "1.1.1.1", "gb": 8.1},
                ],
            },
        )


class AnsibleAdapter(ToolAdapter):
    name = "ansible"

    def run(self, operation: str, parameters: dict[str, object]) -> ToolResult:
        if operation == "dry_run_config_change":
            return ToolResult(
                tool=self.name,
                operation=operation,
                success=True,
                data={"changed": False, "diff": "mock dry-run diff"},
            )
        if operation == "apply_config_change":
            return ToolResult(
                tool=self.name,
                operation=operation,
                success=True,
                data={"changed": True, "rollback_id": "mock-rollback-001"},
            )
        return ToolResult(
            tool=self.name,
            operation=operation,
            success=False,
            error="unsupported mock ansible operation",
        )


class NotificationAdapter(ToolAdapter):
    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, operation: str, parameters: dict[str, object]) -> ToolResult:
        return ToolResult(
            tool=self.name,
            operation=operation,
            success=True,
            data={"sent": True, "target": parameters.get("target", "default")},
        )


def build_mock_executor() -> ToolExecutor:
    adapters: dict[str, ToolAdapter] = {
        "grafana": GrafanaAdapter(),
        "icinga2": Icinga2Adapter(),
        "librenms": LibreNmsAdapter(),
        "clickhouse": ClickHouseAdapter(),
        "ansible": AnsibleAdapter(),
        "ticket": NotificationAdapter("ticket"),
        "email": NotificationAdapter("email"),
        "telegram": NotificationAdapter("telegram"),
    }
    return ToolExecutor(adapters=adapters)

