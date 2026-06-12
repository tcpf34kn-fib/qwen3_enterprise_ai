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
        missing_post_checks = [
            result.to_dict()
            for action, result in zip(actions, results)
            if action.risk.value in ("write", "high") and not _post_check_passed(result)
        ]

        if failed:
            return {
                "status": "failed",
                "task_id": task.task_id,
                "reason": "one or more tool calls failed",
                "failed_results": failed,
            }

        if missing_post_checks:
            return {
                "status": "needs_post_check",
                "task_id": task.task_id,
                "reason": "write action completed but no passing post-change check was provided",
                "pending_results": missing_post_checks,
            }

        if write_actions:
            return {
                "status": "verified",
                "task_id": task.task_id,
                "reason": "write action completed and post-change checks passed",
            }

        return {
            "status": "verified",
            "task_id": task.task_id,
                "reason": "read-only actions completed successfully",
        }


def _post_check_passed(result: ToolResult) -> bool:
    post_check = result.data.get("post_check")
    if not isinstance(post_check, dict):
        return False
    return post_check.get("status") == "passed"
