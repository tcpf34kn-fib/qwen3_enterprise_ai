from __future__ import annotations

import json
import uuid
from typing import Any

from .classifier import TaskClassifier, _extract_json
from .config import AppConfig
from .domain import (
    ActionProposal,
    Classification,
    NormalizedTask,
    PolicyDecision,
    RiskLevel,
    TaskType,
)
from .event_bus import InMemoryEventBus
from .llm.prompts import PLANNER_SYSTEM_PROMPT
from .llm.qwen_client import QwenClient, QwenUnavailable
from .normalizer import Normalizer
from .policy import PolicyEngine
from .rag import LocalRagService
from .storage import AuditStore
from .tools.base import ToolExecutor
from .verifier import ResultVerifier


class ReasoningPlanner:
    def __init__(self, qwen: QwenClient) -> None:
        self.qwen = qwen

    def plan(
        self,
        task: NormalizedTask,
        classification: Classification,
        rag_hits: list[dict[str, object]],
    ) -> tuple[str, list[ActionProposal], str]:
        try:
            raw = self.qwen.chat(
                [
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "task": task.to_dict(),
                                "classification": classification.to_dict(),
                                "rag_hits": rag_hits,
                            },
                            ensure_ascii=True,
                        ),
                    },
                ],
                json_mode=True,
            )
            data = _extract_json(raw)
            actions = [ActionProposal.from_mapping(item) for item in data.get("actions", [])]
            return (
                str(data.get("summary") or "Qwen3 generated a plan."),
                actions,
                str(data.get("response") or "Plan generated."),
            )
        except (QwenUnavailable, ValueError, TypeError, json.JSONDecodeError):
            return self._fallback_plan(task, classification)

    def _fallback_plan(
        self,
        task: NormalizedTask,
        classification: Classification,
    ) -> tuple[str, list[ActionProposal], str]:
        host = classification.entities.get("host") or classification.entities.get("ip") or "unknown"

        if classification.task_type == TaskType.INCIDENT:
            actions = [
                ActionProposal(
                    tool="icinga2",
                    operation="get_host_status",
                    risk=RiskLevel.READ,
                    parameters={"host": host},
                    reason="check monitoring state before proposing remediation",
                ),
                ActionProposal(
                    tool="librenms",
                    operation="get_device_health",
                    risk=RiskLevel.READ,
                    parameters={"device": host},
                    reason="check device health and interfaces",
                ),
                ActionProposal(
                    tool="grafana",
                    operation="get_dashboard_snapshot",
                    risk=RiskLevel.READ,
                    parameters={"dashboard": "network-overview", "host": host},
                    reason="check recent metric trend",
                ),
            ]
            return (
                "Fallback incident plan created.",
                actions,
                "I will run read-only checks first, then summarize the likely cause.",
            )

        if classification.task_type == TaskType.REPORT:
            return (
                "Fallback report plan created.",
                [
                    ActionProposal(
                        tool="clickhouse",
                        operation="query_netflow_summary",
                        risk=RiskLevel.READ,
                        parameters={"window": "24h", "query": task.text},
                        reason="collect traffic data for report",
                    )
                ],
                "I will collect read-only traffic data for the requested report.",
            )

        if classification.task_type == TaskType.CONFIG_CHANGE:
            return (
                "Fallback config-change plan created.",
                [
                    ActionProposal(
                        tool="ansible",
                        operation="apply_config_change",
                        risk=RiskLevel.WRITE,
                        parameters={"request": task.text, "target": host},
                        reason="configuration change requested by operator",
                        requires_approval=True,
                    )
                ],
                "This is a write action and must be approved before execution.",
            )

        return ("No action plan needed.", [], "No tool action is required.")


class WorkflowEngine:
    def __init__(
        self,
        config: AppConfig,
        normalizer: Normalizer,
        classifier: TaskClassifier,
        planner: ReasoningPlanner,
        rag: LocalRagService,
        policy: PolicyEngine,
        executor: ToolExecutor,
        verifier: ResultVerifier,
        storage: AuditStore,
        event_bus: InMemoryEventBus,
    ) -> None:
        self.config = config
        self.normalizer = normalizer
        self.classifier = classifier
        self.planner = planner
        self.rag = rag
        self.policy = policy
        self.executor = executor
        self.verifier = verifier
        self.storage = storage
        self.event_bus = event_bus

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = self.normalizer.normalize(payload)
        self.storage.create_task(task)
        self._audit(task.task_id, "task_received", task.to_dict())

        classification = self.classifier.classify(task)
        self._audit(task.task_id, "task_classified", classification.to_dict())

        if (
            classification.task_type == TaskType.UNKNOWN
            or classification.confidence < self.config.classifier_min_confidence
        ):
            result = self._escalate(task, classification, "low classifier confidence")
            self.storage.update_task(task.task_id, result["status"], result)
            return result

        if classification.task_type == TaskType.INFO_QUERY:
            result = self._handle_info_query(task, classification)
        else:
            result = self._handle_action_workflow(task, classification)

        self.storage.update_task(task.task_id, result["status"], result)
        return result

    def approve_and_execute(self, approval_id: str, approved_by: str) -> dict[str, Any]:
        approval = self.storage.get_approval(approval_id)
        if not approval:
            raise ValueError("approval request not found")
        if approval["status"] != "pending":
            raise ValueError("approval request is not pending")

        self.storage.set_approval_status(approval_id, "approved", approved_by=approved_by)
        task_row = self.storage.get_task(approval["task_id"])
        if not task_row:
            raise ValueError("task for approval was not found")

        task = NormalizedTask(
            task_id=task_row["task_id"],
            source=task_row["source"],
            text=task_row["text"],
            metadata=task_row.get("payload", {}).get("metadata", {}),
        )
        action = ActionProposal.from_mapping(approval["action"])
        result = self.executor.execute(action)
        verification = self.verifier.verify(task, [action], [result])
        response = {
            "task_id": task.task_id,
            "status": "completed" if result.success else "failed",
            "approval_id": approval_id,
            "executed_action": action.to_dict(),
            "tool_results": [result.to_dict()],
            "verification": verification,
            "response": "Approved action executed." if result.success else "Approved action failed.",
        }
        self._audit(task.task_id, "approval_executed", response)
        self.storage.update_task(task.task_id, response["status"], response)
        return response

    def reject_approval(self, approval_id: str, rejected_by: str) -> dict[str, Any]:
        approval = self.storage.get_approval(approval_id)
        if not approval:
            raise ValueError("approval request not found")
        if approval["status"] != "pending":
            raise ValueError("approval request is not pending")

        self.storage.set_approval_status(approval_id, "rejected", approved_by=rejected_by)
        response = {
            "task_id": approval["task_id"],
            "status": "rejected",
            "approval_id": approval_id,
            "response": "Approval request was rejected; no action executed.",
        }
        self._audit(approval["task_id"], "approval_rejected", response)
        self.storage.update_task(approval["task_id"], "rejected", response)
        return response

    def _handle_info_query(self, task: NormalizedTask, classification: Classification) -> dict[str, Any]:
        rag_answer = self.rag.answer_from_docs(task.text)
        result = {
            "task_id": task.task_id,
            "status": "completed",
            "classification": classification.to_dict(),
            "response": rag_answer["answer"],
            "rag_sources": rag_answer["sources"],
            "actions": [],
            "policy": {"decision": "allow", "reason": "information query does not require tool execution"},
        }
        self._audit(task.task_id, "info_query_answered", result)
        return result

    def _handle_action_workflow(self, task: NormalizedTask, classification: Classification) -> dict[str, Any]:
        rag_hits = [hit.to_dict() for hit in self.rag.search(task.text)]
        summary, actions, planner_response = self.planner.plan(task, classification, rag_hits)
        self._audit(
            task.task_id,
            "actions_proposed",
            {
                "summary": summary,
                "response": planner_response,
                "actions": [action.to_dict() for action in actions],
                "rag_sources": rag_hits,
            },
        )

        policy_result = self.policy.evaluate(actions)
        self._audit(task.task_id, "policy_evaluated", policy_result.to_dict())

        if policy_result.decision == PolicyDecision.BLOCK:
            return {
                "task_id": task.task_id,
                "status": "blocked",
                "classification": classification.to_dict(),
                "summary": summary,
                "response": "Policy blocked the proposed action.",
                "rag_sources": rag_hits,
                "actions": [action.to_dict() for action in actions],
                "policy": policy_result.to_dict(),
            }

        if policy_result.decision == PolicyDecision.REQUIRE_APPROVAL:
            approval_ids = []
            for action in actions:
                approval_id = str(uuid.uuid4())
                self.storage.create_approval(
                    approval_id=approval_id,
                    task_id=task.task_id,
                    action=action,
                    reason=policy_result.reason,
                )
                approval_ids.append(approval_id)
            return {
                "task_id": task.task_id,
                "status": "pending_approval",
                "classification": classification.to_dict(),
                "summary": summary,
                "response": planner_response,
                "rag_sources": rag_hits,
                "actions": [action.to_dict() for action in actions],
                "policy": policy_result.to_dict(),
                "approval_ids": approval_ids,
            }

        results = [self.executor.execute(action) for action in actions]
        verification = self.verifier.verify(task, actions, results)
        self._audit(
            task.task_id,
            "actions_executed",
            {
                "tool_results": [result.to_dict() for result in results],
                "verification": verification,
            },
        )

        final_status = "completed" if all(result.success for result in results) else "failed"
        return {
            "task_id": task.task_id,
            "status": final_status,
            "classification": classification.to_dict(),
            "summary": summary,
            "response": self._compose_response(classification, results, planner_response),
            "rag_sources": rag_hits,
            "actions": [action.to_dict() for action in actions],
            "policy": policy_result.to_dict(),
            "tool_results": [result.to_dict() for result in results],
            "verification": verification,
        }

    def _escalate(self, task: NormalizedTask, classification: Classification, reason: str) -> dict[str, Any]:
        result = {
            "task_id": task.task_id,
            "status": "escalated",
            "classification": classification.to_dict(),
            "response": f"Human escalation required: {reason}.",
            "actions": [],
        }
        self._audit(task.task_id, "human_escalation", result)
        return result

    def _compose_response(
        self,
        classification: Classification,
        results: list[Any],
        planner_response: str,
    ) -> str:
        if classification.task_type == TaskType.INCIDENT:
            failed = [result for result in results if not result.success]
            if failed:
                return "Some read-only checks failed. Escalate to an operator with audit context."
            return "Read-only checks completed. Review tool_results for likely cause and next action."
        if classification.task_type == TaskType.REPORT:
            return "Report data collected. Review tool_results for the generated summary inputs."
        return planner_response

    def _audit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.event_bus.publish(event_type, task_id, payload)
        self.storage.add_audit(task_id, event_type, payload)

