from __future__ import annotations

from .domain import ActionProposal, NormalizedTask, ToolResult


class ResultVerifier:
    def verify(
        self,
        task: NormalizedTask,
        actions: list[ActionProposal],
        results: list[ToolResult],
    ) -> dict[str, object]:
        failed = [result.to_dict() for result in results if not result.success]
        write_actions = [action for action in actions if action.risk.value in ("write", "high")]

        if failed:
            return {
                "status": "failed",
                "task_id": task.task_id,
                "reason": "one or more tool calls failed",
                "failed_results": failed,
            }

        if write_actions:
            return {
                "status": "verified",
                "task_id": task.task_id,
                "reason": "write action completed in mock executor; replace with post-change checks in production",
            }

        return {
            "status": "verified",
            "task_id": task.task_id,
            "reason": "read-only actions completed successfully",
        }

