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

The first implementation uses mock tool adapters. Replace those adapters with real Grafana, Icinga2, LibreNMS, ClickHouse, Ansible, email, ticket, or Telegram clients when ready.

## Folder layout

```text
qwen3_enterprise_ai/
  run.py
  smoke_test.py
  config.example.json
  requirements.txt
  enterprise_ai/
    api.py
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

## Local Qwen3

By default the scaffold is configured for Ollama:

```json
{
  "llm_provider": "ollama",
  "llm_endpoint": "http://127.0.0.1:11434/api/chat",
  "llm_model": "qwen3:8b"
}
```

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
5. result verifier
6. audit log

