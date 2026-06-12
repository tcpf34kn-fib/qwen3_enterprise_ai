# Qwen3 Enterprise AI Automation Scaffold

This folder is a standalone starter service for an enterprise AI system that can:

- receive tasks from webhook/API/chat/ticket systems
- normalize and classify tasks with local Qwen3 or a rule-based fallback
- route tasks into info, incident, report, config-change, or escalation workflows
- retrieve local runbook/SOP/CMDB-style knowledge
- generate action proposals as typed JSON
- enforce policy and approval gates before execution
- execute only through deterministic tool adapters
- verify results and write audit trails

The default implementation still uses mock tool adapters so the whole flow can be tested without Grafana, Icinga2, LibreNMS, ClickHouse, or Ansible. Replace those adapters with real clients when the surrounding systems are ready.

This is a hardened scaffold, not a complete production platform. It now includes API key auth, role checks, IP allowlist support, configurable CORS, chunked RAG with metadata/citations, JSON or SQLite audit storage, approval gates, and post-action verification hooks. Production deployments should still add real tool adapters, real vector search for large runbooks, secret management, backups, monitoring, and organization-specific approval workflows.

## Folder layout

```text
qwen3_enterprise_ai/
  run.py
  smoke_test.py
  config.example.json
  config.production.example.json
  Dockerfile
  docker-compose.yml
  requirements.txt
  enterprise_ai/
    api.py
    auth.py
    classifier.py
    config.py
    domain.py
    event_bus.py
    normalizer.py
    policy.py
    rag.py
    storage.py
    verifier.py
    workflow.py
    llm/
      prompts.py
      qwen_client.py
    tools/
      base.py
      mock_adapters.py
  knowledge_base/
    runbook_network_incident.md
    sop_config_change.md
```

## Quick start

```powershell
cd D:\webappquicktest\qwen3_enterprise_ai
pip install -r requirements.txt
python smoke_test.py
python run.py
```

The service starts on `http://127.0.0.1:8088` by default.

Submit a task:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8088/api/tasks `
  -ContentType 'application/json' `
  -Body '{"source":"telegram","text":"Router edge-01 is down, check status and suggest next action"}'
```

View audit records:

```powershell
Invoke-RestMethod http://127.0.0.1:8088/api/audit
```

## API auth

Auth is disabled in `config.example.json` so local demos and Kaggle notebooks run without friction. For internal deployment, start from `config.production.example.json` and set:

```json
{
  "auth_enabled": true,
  "api_keys": {
    "replace-with-long-random-admin-key": "admin",
    "replace-with-long-random-operator-key": "operator"
  },
  "ip_allowlist": ["10.0.0.0/8", "192.168.0.0/16"],
  "cors_origins": ["https://ops.example.internal"]
}
```

Authenticated requests can use either `X-API-Key` or `Authorization: Bearer <key>`:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8088/api/tasks `
  -Headers @{"X-API-Key"="replace-with-long-random-operator-key"} `
  -ContentType 'application/json' `
  -Body '{"source":"api","text":"Router edge-01 is down"}'
```

Roles are mapped through `role_permissions`. The built-in permissions are:

- `tasks:read`
- `tasks:write`
- `audit:read`
- `approvals:read`
- `approvals:write`

## Local Qwen3

By default the scaffold is configured for Ollama:

```json
{
  "llm_provider": "ollama",
  "llm_endpoint": "http://127.0.0.1:11434/api/chat",
  "llm_model": "qwen3:8b"
}
```

## RAG

`LocalRagService` loads Markdown files from `knowledge_base/`, splits them into chunks, stores metadata from front matter, and returns line citations such as `runbook_network_incident.md:L10-L18`.

Example document metadata:

```markdown
---
domain: network
doc_type: runbook
roles: admin,operator,viewer
---
```

For a large production knowledge base, keep the `LocalRagService` interface but replace the implementation with local embeddings plus Chroma, Qdrant, FAISS, or another vector store.

## Storage

The storage backend is configurable:

```json
{
  "storage_backend": "json",
  "storage_path": "data/audit.json"
}
```

Use `json` for demos and notebooks. Use `sqlite` for single-node internal deployments:

```json
{
  "storage_backend": "sqlite",
  "storage_path": "data/audit.sqlite3"
}
```

For production with multiple replicas, replace the storage implementation with PostgreSQL, ClickHouse, or an event store.

## Docker Compose

```powershell
docker compose up --build
```

The compose file uses `config.production.example.json`, so replace its API keys before using it outside a private lab.

If Qwen3 is not running, the classifier and planner fall back to deterministic rules. This keeps the workflow testable even before the model is deployed.

To disable LLM calls explicitly, set:

```json
{
  "llm_provider": "disabled"
}
```

## Enterprise control rule

Qwen3 is used for classification, reasoning, and proposing actions. It does not execute commands. Every action must pass through:

1. typed JSON action schema
2. policy engine
3. approval gate for write/high-risk actions
4. deterministic tool executor
5. result verifier with post-action checks for write/high-risk actions
6. audit log

Write actions are not considered verified only because the tool returned success. Tool adapters should include a `post_check` result after real changes, for example:

```json
{
  "post_check": {
    "status": "passed",
    "checks": ["device reachable", "alert cleared", "config converged"]
  }
}
```
