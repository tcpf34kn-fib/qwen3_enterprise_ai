from __future__ import annotations

import json
import re
from typing import Any

from .domain import Classification, NormalizedTask, Severity, TaskType
from .llm.prompts import CLASSIFIER_SYSTEM_PROMPT
from .llm.qwen_client import QwenClient, QwenUnavailable


class TaskClassifier:
    def __init__(self, qwen: QwenClient) -> None:
        self.qwen = qwen

    def classify(self, task: NormalizedTask) -> Classification:
        try:
            raw = self.qwen.chat(
                [
                    {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": task.text},
                ],
                json_mode=True,
            )
            parsed = _extract_json(raw)
            classification = Classification.from_mapping(parsed)
            if classification.confidence > 0:
                return classification
        except (QwenUnavailable, ValueError, TypeError, json.JSONDecodeError):
            pass

        return self._fallback_classify(task)

    def _fallback_classify(self, task: NormalizedTask) -> Classification:
        text = task.text.lower()
        entities = _extract_entities(text)
        severity = _severity_from_text(text)

        if any(word in text for word in ("down", "failed", "critical", "alert", "incident", "offline", "packet loss", "cpu high")):
            return Classification(
                task_type=TaskType.INCIDENT,
                confidence=0.76,
                severity=severity,
                entities=entities,
                reason="keyword fallback matched incident language",
            )

        if any(word in text for word in ("report", "summary", "generate", "export", "traffic", "capacity")):
            return Classification(
                task_type=TaskType.REPORT,
                confidence=0.72,
                severity=Severity.LOW,
                entities=entities,
                reason="keyword fallback matched report language",
            )

        if any(word in text for word in ("change", "configure", "config", "apply", "vlan", "route", "acl", "firewall")):
            return Classification(
                task_type=TaskType.CONFIG_CHANGE,
                confidence=0.74,
                severity=Severity.MEDIUM,
                entities=entities,
                reason="keyword fallback matched config-change language",
            )

        if any(word in text for word in ("what", "how", "why", "status", "explain", "lookup", "show")):
            return Classification(
                task_type=TaskType.INFO_QUERY,
                confidence=0.66,
                severity=Severity.LOW,
                entities=entities,
                reason="keyword fallback matched information-query language",
            )

        return Classification(
            task_type=TaskType.UNKNOWN,
            confidence=0.25,
            severity=Severity.LOW,
            entities=entities,
            reason="no confident fallback match",
        )


def _extract_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(raw[start : end + 1])


def _extract_entities(text: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    if ip_match:
        entities["ip"] = ip_match.group(0)

    host_match = re.search(r"\b(?:host|device|router|switch|server)\s*[:=]?\s*([a-z0-9._-]+)", text)
    if host_match:
        entities["host"] = host_match.group(1)
    elif ip_match:
        entities["host"] = ip_match.group(0)

    vlan_match = re.search(r"\bvlan\s*([0-9]{1,4})\b", text)
    if vlan_match:
        entities["vlan"] = vlan_match.group(1)

    return entities


def _severity_from_text(text: str) -> Severity:
    if any(word in text for word in ("critical", "sev1", "p1", "outage", "down")):
        return Severity.CRITICAL
    if any(word in text for word in ("high", "sev2", "p2", "failed", "loss")):
        return Severity.HIGH
    if any(word in text for word in ("warning", "degraded", "slow")):
        return Severity.MEDIUM
    return Severity.LOW

