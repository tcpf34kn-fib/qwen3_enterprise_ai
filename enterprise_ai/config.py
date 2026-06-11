from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class AppConfig:
    app_host: str = "127.0.0.1"
    app_port: int = 8088
    debug: bool = True
    llm_provider: str = "ollama"
    llm_endpoint: str = "http://127.0.0.1:11434/api/chat"
    llm_model: str = "qwen3:8b"
    llm_timeout_seconds: int = 20
    classifier_min_confidence: float = 0.62
    auto_approve_read_only: bool = True
    require_approval_for_write: bool = True
    storage_path: str = "data/audit.db"
    knowledge_base_path: str = "knowledge_base"

    def resolve_path(self, value: str) -> str:
        path = Path(value)
        if path.is_absolute():
            return str(path)
        return str(PROJECT_ROOT / path)

    @property
    def resolved_storage_path(self) -> str:
        return self.resolve_path(self.storage_path)

    @property
    def resolved_knowledge_base_path(self) -> str:
        return self.resolve_path(self.knowledge_base_path)


def _coerce_env_value(raw: str, current: Any) -> Any:
    if isinstance(current, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(current, int) and not isinstance(current, bool):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    return raw


def load_config(path: str | None = None) -> AppConfig:
    config_path = path or os.getenv("ENTERPRISE_AI_CONFIG")
    data: dict[str, Any] = {}

    if config_path:
        config_file = Path(config_path)
    else:
        config_file = PROJECT_ROOT / "config.example.json"

    if config_file.exists():
        data.update(json.loads(config_file.read_text(encoding="utf-8")))

    config = AppConfig(**{key: value for key, value in data.items() if key in _field_names()})

    for field in fields(AppConfig):
        env_name = f"ENTERPRISE_AI_{field.name.upper()}"
        if env_name in os.environ:
            setattr(config, field.name, _coerce_env_value(os.environ[env_name], getattr(config, field.name)))

    return config


def _field_names() -> set[str]:
    return {field.name for field in fields(AppConfig)}

