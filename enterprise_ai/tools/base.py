from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain import ActionProposal, ToolResult


class ToolAdapter(ABC):
    name: str

    @abstractmethod
    def run(self, operation: str, parameters: dict[str, object]) -> ToolResult:
        raise NotImplementedError


class ToolExecutor:
    def __init__(self, adapters: dict[str, ToolAdapter]) -> None:
        self.adapters = adapters

    def execute(self, action: ActionProposal) -> ToolResult:
        adapter = self.adapters.get(action.tool)
        if not adapter:
            return ToolResult(
                tool=action.tool,
                operation=action.operation,
                success=False,
                error="tool adapter is not registered",
            )

        return adapter.run(action.operation, action.parameters)

