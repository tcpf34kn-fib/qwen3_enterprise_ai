from __future__ import annotations

import uuid
from typing import Any

from .domain import NormalizedTask


class Normalizer:
    def normalize(self, payload: dict[str, Any]) -> NormalizedTask:
        text = (
            payload.get("text")
            or payload.get("message")
            or payload.get("description")
            or payload.get("body")
            or ""
        )
        text = str(text).strip()
        if not text:
            raise ValueError("task text is required")

        source = str(payload.get("source") or "api").strip() or "api"
        metadata = dict(payload.get("metadata") or {})
        for key, value in payload.items():
            if key not in {"text", "message", "description", "body", "source", "metadata"}:
                metadata[key] = value

        return NormalizedTask(
            task_id=str(uuid.uuid4()),
            source=source,
            text=text,
            metadata=metadata,
        )

