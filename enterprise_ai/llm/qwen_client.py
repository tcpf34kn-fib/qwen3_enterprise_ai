from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..config import AppConfig


class QwenUnavailable(RuntimeError):
    pass


class QwenClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return self.config.llm_provider.lower() not in ("", "disabled", "none", "off")

    def chat(self, messages: list[dict[str, str]], json_mode: bool = False) -> str:
        if not self.enabled:
            raise QwenUnavailable("LLM provider is disabled")

        provider = self.config.llm_provider.lower()
        if provider == "ollama":
            return self._ollama_chat(messages, json_mode=json_mode)
        if provider in ("openai_compatible", "openai-compatible", "vllm", "lmstudio"):
            return self._openai_compatible_chat(messages)

        raise QwenUnavailable(f"unsupported LLM provider: {self.config.llm_provider}")

    def _ollama_chat(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        payload: dict[str, Any] = {
            "model": self.config.llm_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        if json_mode:
            payload["format"] = "json"

        data = self._post_json(self.config.llm_endpoint, payload)
        message = data.get("message") or {}
        content = message.get("content")
        if not content:
            raise QwenUnavailable("empty Ollama response")
        return str(content)

    def _openai_compatible_chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.config.llm_model,
            "messages": messages,
            "temperature": 0.1,
        }
        data = self._post_json(self.config.llm_endpoint, payload)
        choices = data.get("choices") or []
        if not choices:
            raise QwenUnavailable("empty OpenAI-compatible response")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise QwenUnavailable("empty OpenAI-compatible message")
        return str(content)

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.llm_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QwenUnavailable(str(exc)) from exc

