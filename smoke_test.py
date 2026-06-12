from pathlib import Path
from uuid import uuid4

from enterprise_ai.api import create_app
from enterprise_ai.config import AppConfig


def main() -> None:
    root = Path(__file__).resolve().parent
    config = AppConfig(
        llm_provider="disabled",
        storage_path=str(root / "data" / f"smoke_test_{uuid4().hex}.json"),
        knowledge_base_path=str(root / "knowledge_base"),
        debug=False,
    )
    app = create_app(config)
    client = app.test_client()

    payloads = [
        {
            "source": "telegram",
            "text": "Router edge-01 is down, check status and suggest next action",
        },
        {
            "source": "ticket",
            "text": "Generate a 24h traffic report for core link",
        },
        {
            "source": "api",
            "text": "Change VLAN config on switch access-02",
        },
    ]

    for payload in payloads:
        response = client.post("/api/tasks", json=payload)
        assert response.status_code in (200, 202), response.get_data(as_text=True)
        body = response.get_json()
        assert body["task_id"]
        assert body["status"] in ("completed", "pending_approval", "escalated")
        print(f"{body['task_id']} {body['classification']['task_type']} {body['status']}")

    health = client.get("/healthz")
    assert health.status_code == 200

    auth_config = AppConfig(
        auth_enabled=True,
        api_keys={"test-admin-key": "admin"},
        llm_provider="disabled",
        storage_path=str(root / "data" / f"smoke_test_auth_{uuid4().hex}.json"),
        knowledge_base_path=str(root / "knowledge_base"),
        debug=False,
    )
    auth_client = create_app(auth_config).test_client()
    unauthorized = auth_client.post("/api/tasks", json=payloads[0])
    assert unauthorized.status_code == 401

    authorized = auth_client.post(
        "/api/tasks",
        json=payloads[0],
        headers={"X-API-Key": "test-admin-key"},
    )
    assert authorized.status_code == 200, authorized.get_data(as_text=True)

    print("smoke test passed")


if __name__ == "__main__":
    main()
