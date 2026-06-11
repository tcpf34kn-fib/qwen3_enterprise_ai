from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS

from .classifier import TaskClassifier
from .config import AppConfig, load_config
from .event_bus import InMemoryEventBus
from .llm.qwen_client import QwenClient
from .normalizer import Normalizer
from .policy import PolicyEngine
from .rag import LocalRagService
from .storage import AuditStore
from .tools.mock_adapters import build_mock_executor
from .verifier import ResultVerifier
from .workflow import ReasoningPlanner, WorkflowEngine


def create_app(config: AppConfig | None = None) -> Flask:
    config = config or load_config()
    app = Flask(__name__)
    CORS(app)

    engine, storage = _build_runtime(config)

    @app.route("/healthz", methods=["GET"])
    def healthz() -> Any:
        return jsonify(
            {
                "status": "ok",
                "llm_provider": config.llm_provider,
                "llm_model": config.llm_model,
            }
        )

    @app.route("/api/tasks", methods=["POST"])
    def submit_task() -> Any:
        payload = request.get_json(silent=True) or {}
        result = engine.handle(payload)
        status_code = 202 if result["status"] == "pending_approval" else 200
        return jsonify(result), status_code

    @app.route("/api/tasks", methods=["GET"])
    def list_tasks() -> Any:
        limit = int(request.args.get("limit", "50"))
        return jsonify({"tasks": storage.list_tasks(limit=limit)})

    @app.route("/api/tasks/<task_id>", methods=["GET"])
    def get_task(task_id: str) -> Any:
        task = storage.get_task(task_id)
        if not task:
            return jsonify({"error": "task not found"}), 404
        return jsonify(task)

    @app.route("/api/audit", methods=["GET"])
    def list_audit() -> Any:
        task_id = request.args.get("task_id")
        limit = int(request.args.get("limit", "100"))
        return jsonify({"events": storage.list_audit(task_id=task_id, limit=limit)})

    @app.route("/api/approvals", methods=["GET"])
    def list_approvals() -> Any:
        status = request.args.get("status")
        limit = int(request.args.get("limit", "100"))
        return jsonify({"approvals": storage.list_approvals(status=status, limit=limit)})

    @app.route("/api/approvals/<approval_id>/approve", methods=["POST"])
    def approve(approval_id: str) -> Any:
        payload = request.get_json(silent=True) or {}
        approved_by = str(payload.get("approved_by") or "api")
        return jsonify(engine.approve_and_execute(approval_id, approved_by=approved_by))

    @app.route("/api/approvals/<approval_id>/reject", methods=["POST"])
    def reject(approval_id: str) -> Any:
        payload = request.get_json(silent=True) or {}
        rejected_by = str(payload.get("rejected_by") or "api")
        return jsonify(engine.reject_approval(approval_id, rejected_by=rejected_by))

    @app.errorhandler(ValueError)
    def handle_value_error(exc: ValueError) -> Any:
        return jsonify({"error": str(exc)}), 400

    return app


def _build_runtime(config: AppConfig) -> tuple[WorkflowEngine, AuditStore]:
    qwen = QwenClient(config)
    storage = AuditStore(config.resolved_storage_path)
    engine = WorkflowEngine(
        config=config,
        normalizer=Normalizer(),
        classifier=TaskClassifier(qwen),
        planner=ReasoningPlanner(qwen),
        rag=LocalRagService(config.resolved_knowledge_base_path),
        policy=PolicyEngine(config),
        executor=build_mock_executor(),
        verifier=ResultVerifier(),
        storage=storage,
        event_bus=InMemoryEventBus(),
    )
    return engine, storage

