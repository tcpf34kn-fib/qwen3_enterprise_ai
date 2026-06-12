from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .config import AppConfig
from .domain import ActionProposal, NormalizedTask, utc_now_iso


class AuditStore:
    def create_task(self, task: NormalizedTask) -> None:
        raise NotImplementedError

    def update_task(self, task_id: str, status: str, result: dict[str, Any]) -> None:
        raise NotImplementedError

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        raise NotImplementedError

    def add_audit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    def list_audit(self, task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError

    def create_approval(self, approval_id: str, task_id: str, action: ActionProposal, reason: str) -> None:
        raise NotImplementedError

    def set_approval_status(self, approval_id: str, status: str, approved_by: str | None = None) -> None:
        raise NotImplementedError

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def list_approvals(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError


class JsonAuditStore(AuditStore):
    """File-backed audit store for local development and notebook demos."""

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
        return {"tasks": {}, "audit_events": [], "approval_requests": {}}

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


class SQLiteAuditStore(AuditStore):
    """SQLite audit store for single-node deployments and production-like labs."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._memory_conn: sqlite3.Connection | None = None
        if str(path) == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def create_task(self, task: NormalizedTask) -> None:
        now = utc_now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                insert into tasks (
                    task_id, status, source, text, payload_json, result_json, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    "received",
                    task.source,
                    task.text,
                    json.dumps(task.to_dict(), ensure_ascii=True),
                    None,
                    now,
                    now,
                ),
            )

    def update_task(self, task_id: str, status: str, result: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                update tasks
                set status = ?, result_json = ?, updated_at = ?
                where task_id = ?
                """,
                (status, json.dumps(result, ensure_ascii=True), utc_now_iso(), task_id),
            )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("select * from tasks where task_id = ?", (task_id,)).fetchone()
        return _sqlite_row_to_dict(row)

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "select * from tasks order by created_at desc limit ?",
                (limit,),
            ).fetchall()
        return [_sqlite_row_to_dict(row) for row in rows if row is not None]

    def add_audit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                insert into audit_events (task_id, event_type, payload_json, created_at)
                values (?, ?, ?, ?)
                """,
                (task_id, event_type, json.dumps(payload, ensure_ascii=True), utc_now_iso()),
            )

    def list_audit(self, task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            if task_id:
                rows = conn.execute(
                    """
                    select * from audit_events
                    where task_id = ?
                    order by id desc
                    limit ?
                    """,
                    (task_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "select * from audit_events order by id desc limit ?",
                    (limit,),
                ).fetchall()
        return [_sqlite_row_to_dict(row) for row in rows if row is not None]

    def create_approval(self, approval_id: str, task_id: str, action: ActionProposal, reason: str) -> None:
        now = utc_now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                insert into approval_requests (
                    approval_id, task_id, status, risk, reason, action_json, approved_by, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    task_id,
                    "pending",
                    action.risk.value,
                    reason,
                    json.dumps(action.to_dict(), ensure_ascii=True),
                    None,
                    now,
                    now,
                ),
            )

    def set_approval_status(self, approval_id: str, status: str, approved_by: str | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                update approval_requests
                set status = ?, approved_by = ?, updated_at = ?
                where approval_id = ?
                """,
                (status, approved_by, utc_now_iso(), approval_id),
            )

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "select * from approval_requests where approval_id = ?",
                (approval_id,),
            ).fetchone()
        return _sqlite_row_to_dict(row)

    def list_approvals(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    select * from approval_requests
                    where status = ?
                    order by created_at desc
                    limit ?
                    """,
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "select * from approval_requests order by created_at desc limit ?",
                    (limit,),
                ).fetchall()
        return [_sqlite_row_to_dict(row) for row in rows if row is not None]

    def _connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                create table if not exists tasks (
                    task_id text primary key,
                    status text not null,
                    source text not null,
                    text text not null,
                    payload_json text not null,
                    result_json text,
                    created_at text not null,
                    updated_at text not null
                );

                create table if not exists audit_events (
                    id integer primary key autoincrement,
                    task_id text not null,
                    event_type text not null,
                    payload_json text not null,
                    created_at text not null
                );

                create table if not exists approval_requests (
                    approval_id text primary key,
                    task_id text not null,
                    status text not null,
                    risk text not null,
                    reason text not null,
                    action_json text not null,
                    approved_by text,
                    created_at text not null,
                    updated_at text not null
                );

                create index if not exists idx_audit_events_task_id on audit_events(task_id);
                create index if not exists idx_approval_requests_status on approval_requests(status);
                """
            )


def build_audit_store(config: AppConfig) -> AuditStore:
    backend = config.storage_backend.lower()
    if backend == "json":
        return JsonAuditStore(config.resolved_storage_path)
    if backend == "sqlite":
        return SQLiteAuditStore(config.resolved_storage_path)
    raise ValueError(f"unsupported storage backend: {config.storage_backend}")


def _sqlite_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None

    data = dict(row)
    json_keys = {
        "payload_json": "payload",
        "result_json": "result",
        "action_json": "action",
    }
    for source_key, target_key in json_keys.items():
        if source_key in data:
            raw = data.pop(source_key)
            data[target_key] = json.loads(raw) if raw else None
    return data
