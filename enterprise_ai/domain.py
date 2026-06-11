from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskType(str, Enum):
    INFO_QUERY = "information_query"
    INCIDENT = "incident"
    REPORT = "report_request"
    CONFIG_CHANGE = "config_change"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskLevel(str, Enum):
    READ = "read"
    NOTIFY = "notify"
    WRITE = "write"
    HIGH = "high"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


def parse_enum(enum_cls: type[Enum], value: Any, default: Enum) -> Enum:
    if isinstance(value, enum_cls):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    for item in enum_cls:
        if normalized in (item.value, item.name.lower()):
            return item
    return default


def public_dict(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [public_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: public_dict(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return public_dict(asdict(value))
    return value


@dataclass
class NormalizedTask:
    task_id: str
    source: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    received_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return public_dict(self)


@dataclass
class Classification:
    task_type: TaskType
    confidence: float
    severity: Severity = Severity.LOW
    entities: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return public_dict(self)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Classification":
        return cls(
            task_type=parse_enum(TaskType, data.get("task_type"), TaskType.UNKNOWN),
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0.0)))),
            severity=parse_enum(Severity, data.get("severity"), Severity.LOW),
            entities=data.get("entities") or {},
            reason=str(data.get("reason") or ""),
        )


@dataclass
class ActionProposal:
    tool: str
    operation: str
    risk: RiskLevel
    parameters: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    requires_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        return public_dict(self)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ActionProposal":
        return cls(
            tool=str(data.get("tool") or ""),
            operation=str(data.get("operation") or ""),
            risk=parse_enum(RiskLevel, data.get("risk"), RiskLevel.READ),
            parameters=data.get("parameters") or {},
            reason=str(data.get("reason") or ""),
            requires_approval=bool(data.get("requires_approval", False)),
        )


@dataclass
class PolicyResult:
    decision: PolicyDecision
    risk: RiskLevel
    reason: str
    blocked_actions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return public_dict(self)


@dataclass
class ToolResult:
    tool: str
    operation: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return public_dict(self)

