from pathlib import Path

from enterprise_ai.api import create_app
from enterprise_ai.config import AppConfig


def main() -> None:
    root = Path(__file__).resolve().parent
    config = AppConfig(
        llm_provider="disabled",
        storage_path=str(root / "data" / "smoke_test.json"),
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
    print("smoke test passed")


if __name__ == "__main__":
    main()
