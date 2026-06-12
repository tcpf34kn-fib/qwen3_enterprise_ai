from __future__ import annotations

import ipaddress
from functools import wraps
from typing import Any, Callable

from flask import Response, g, jsonify, request

from .config import AppConfig


PUBLIC_PATHS = {"/healthz"}


def install_auth(app: Any, config: AppConfig) -> None:
    @app.before_request
    def authenticate_request() -> Response | None:
        if request.path in PUBLIC_PATHS or not request.path.startswith("/api/"):
            return None

        if not _ip_allowed(config):
            return jsonify({"error": "source IP is not allowed"}), 403

        if not config.auth_enabled:
            g.auth_role = "anonymous"
            return None

        api_key = _extract_api_key()
        if not api_key:
            return jsonify({"error": "missing API key"}), 401

        role = config.api_keys.get(api_key)
        if not role:
            return jsonify({"error": "invalid API key"}), 401

        g.auth_role = role
        return None


def require_permission(permission: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            config: AppConfig = current_app_config()
            if not config.auth_enabled:
                return func(*args, **kwargs)

            role = getattr(g, "auth_role", "")
            permissions = config.role_permissions.get(role, [])
            if "*" not in permissions and permission not in permissions:
                return jsonify({"error": "permission denied", "required": permission}), 403
            return func(*args, **kwargs)

        return wrapper

    return decorator


def current_app_config() -> AppConfig:
    return getattr(g, "app_config")


def attach_config(app: Any, config: AppConfig) -> None:
    @app.before_request
    def attach_runtime_config() -> None:
        g.app_config = config


def _extract_api_key() -> str | None:
    header_key = request.headers.get("X-API-Key")
    if header_key:
        return header_key.strip()

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def _ip_allowed(config: AppConfig) -> bool:
    if not config.ip_allowlist:
        return True

    raw_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    client_ip = raw_ip.split(",", 1)[0].strip()
    if not client_ip:
        return False

    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    for rule in config.ip_allowlist:
        try:
            if ip in ipaddress.ip_network(rule, strict=False):
                return True
        except ValueError:
            if client_ip == rule:
                return True
    return False
