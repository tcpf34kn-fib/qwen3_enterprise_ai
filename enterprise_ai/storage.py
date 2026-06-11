from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .domain import ActionProposal, NormalizedTask, utc_now_iso


class AuditStore:
    """File-backed audit store for local development.

    The workflow only depends on this class interface. For production, replace it
    with a PostgreSQL, SQLite, or event-store implementation that keeps the same
    methods.
    """

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_state(self._empty_state())

    def create_task(self, task: NormalizedTask) -> None:
        now = utc_now_iso()
        with self._lock:
            state = self._read_state()
            state["tasks"][task.task_id] = {
                "task_id": task.task_id,
                "status": "received",
                "source": task.source,
                "text": task.text,
                "payload": task.to_dict(),
                "result": None,
                "created_at": now,
                "updated_at": now,
            }
            self._write_state(state)

    def update_task(self, task_id: str, status: str, result: dict[str, Any]) -> None:
        with self._lock:
            state = self._read_state()
            task = state["tasks"].setdefault(
                task_id,
                {
                    "task_id": task_id,
                    "status": "unknown",
                    "source": "unknown",
                    "text": "",
                    "payload": {},
                    "result": None,
                    "created_at": utc_now_iso(),
                },
            )
            task["status"] = status
            task["result"] = result
            task["updated_at"] = utc_now_iso()
            self._write_state(state)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read_state()["tasks"].get(task_id)

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            tasks = list(self._read_state()["tasks"].values())
        tasks.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return tasks[:limit]

    def add_audit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._lock:
            state = self._read_state()
            events = state["audit_events"]
            events.append(
                {
                    "id": len(events) + 1,
                    "task_id": task_id,
                    "event_type": event_type,
                    "payload": payload,
                    "created_at": utc_now_iso(),
                }
            )
            self._write_state(state)

    def list_audit(self, task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._read_state()["audit_events"])
        if task_id:
            events = [event for event in events if event["task_id"] == task_id]
        events.sort(key=lambda item: item.get("id", 0), reverse=True)
        return events[:limit]

    def create_approval(self, approval_id: str, task_id: str, action: ActionProposal, reason: str) -> None:
        now = utc_now_iso()
        with self._lock:
            state = self._read_state()
            state["approval_requests"][approval_id] = {
                "approval_id": approval_id,
                "task_id": task_id,
                "status": "pending",
                "risk": action.risk.value,
                "reason": reason,
                "action": action.to_dict(),
                "approved_by": None,
                "created_at": now,
                "updated_at": now,
            }
            self._write_state(state)

    def set_approval_status(self, approval_id: str, status: str, approved_by: str | None = None) -> None:
        with self._lock:
            state = self._read_state()
            approval = state["approval_requests"].get(approval_id)
            if approval:
                approval["status"] = status
                approval["approved_by"] = approved_by
                approval["updated_at"] = utc_now_iso()
                self._write_state(state)

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read_state()["approval_requests"].get(approval_id)

    def list_approvals(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            approvals = list(self._read_state()["approval_requests"].values())
        if status:
            approvals = [approval for approval in approvals if approval["status"] == status]
        approvals.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return approvals[:limit]

    def _empty_state(self) -> dict[str, Any]:
        return {
            "tasks": {},
            "audit_events": [],
            "approval_requests": {},
        }

    def _read_state(self) -> dict[str, Any]:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            state = self._empty_state()
        state.setdefault("tasks", {})
        state.setdefault("audit_events", [])
        state.setdefault("approval_requests", {})
        return state

    def _write_state(self, state: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")
