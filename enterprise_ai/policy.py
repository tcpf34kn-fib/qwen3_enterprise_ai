from __future__ import annotations

from .config import AppConfig
from .domain import ActionProposal, PolicyDecision, PolicyResult, RiskLevel


ALLOWED_OPERATIONS: dict[str, dict[str, RiskLevel]] = {
    "grafana": {
        "get_dashboard_snapshot": RiskLevel.READ,
        "query_metric": RiskLevel.READ,
    },
    "icinga2": {
        "get_host_status": RiskLevel.READ,
        "get_service_status": RiskLevel.READ,
    },
    "librenms": {
        "get_device_health": RiskLevel.READ,
        "get_interface_status": RiskLevel.READ,
    },
    "clickhouse": {
        "query_netflow_summary": RiskLevel.READ,
    },
    "ansible": {
        "dry_run_config_change": RiskLevel.READ,
        "apply_config_change": RiskLevel.WRITE,
    },
    "ticket": {
        "create_or_update": RiskLevel.NOTIFY,
    },
    "email": {
        "send_message": RiskLevel.NOTIFY,
    },
    "telegram": {
        "send_message": RiskLevel.NOTIFY,
    },
}


class PolicyEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def evaluate(self, actions: list[ActionProposal]) -> PolicyResult:
        if not actions:
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                risk=RiskLevel.READ,
                reason="no action requested",
            )

        highest_risk = RiskLevel.READ
        blocked: list[dict[str, object]] = []
        requires_approval = False

        for action in actions:
            tool_ops = ALLOWED_OPERATIONS.get(action.tool)
            if not tool_ops or action.operation not in tool_ops:
                blocked.append(
                    {
                        "tool": action.tool,
                        "operation": action.operation,
                        "reason": "operation is not in allow-list",
                    }
                )
                continue

            effective_risk = tool_ops[action.operation]
            action.risk = effective_risk
            highest_risk = _max_risk(highest_risk, effective_risk)

            if action.requires_approval or effective_risk in (RiskLevel.WRITE, RiskLevel.HIGH):
                requires_approval = True

        if blocked:
            return PolicyResult(
                decision=PolicyDecision.BLOCK,
                risk=highest_risk,
                reason="one or more actions are not allowed",
                blocked_actions=blocked,
            )

        if requires_approval and self.config.require_approval_for_write:
            return PolicyResult(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                risk=highest_risk,
                reason="write or high-risk action requires approval",
            )

        if highest_risk == RiskLevel.READ and not self.config.auto_approve_read_only:
            return PolicyResult(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                risk=highest_risk,
                reason="read-only auto approval is disabled",
            )

        return PolicyResult(
            decision=PolicyDecision.ALLOW,
            risk=highest_risk,
            reason="all actions are allowed by policy",
        )


def _max_risk(left: RiskLevel, right: RiskLevel) -> RiskLevel:
    order = {
        RiskLevel.READ: 1,
        RiskLevel.NOTIFY: 2,
        RiskLevel.WRITE: 3,
        RiskLevel.HIGH: 4,
    }
    return left if order[left] >= order[right] else right

