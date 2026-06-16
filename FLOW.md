# Flow cua tung thanh phan trong du an

Tai lieu nay mo ta cach cac thanh phan trong `qwen3_enterprise_ai` phoi hop voi nhau. Nhin tong the, du an nay la **core AI automation engine**:

```text
Input Adapter
  -> API/Auth
  -> Normalizer
  -> Classifier
  -> Router/Workflow
  -> RAG
  -> Reasoning Planner
  -> Policy/Approval
  -> Tool Executor
  -> Verifier
  -> Storage/Audit
  -> Final Response
```

## 1. API layer

File chinh:

```text
enterprise_ai/api.py
```

Vai tro:

- tao Flask app
- gan CORS
- gan auth middleware
- khoi tao runtime dependencies
- expose endpoint cho task, audit va approval

Endpoint chinh:

```text
GET  /healthz
POST /api/tasks
GET  /api/tasks
GET  /api/tasks/<task_id>
GET  /api/audit
GET  /api/approvals
POST /api/approvals/<approval_id>/approve
POST /api/approvals/<approval_id>/reject
```

Flow:

```text
HTTP request
  -> Flask route
  -> auth middleware
  -> WorkflowEngine
  -> JSON response
```

## 2. Auth layer

File chinh:

```text
enterprise_ai/auth.py
```

Vai tro:

- kiem tra API key
- map API key sang role
- kiem tra permission theo role
- kiem tra IP allowlist
- cho phep public endpoint `/healthz`

Header ho tro:

```text
X-API-Key: <key>
Authorization: Bearer <key>
```

Flow:

```text
Request vao /api/*
  -> check IP allowlist
  -> neu auth_enabled=false: cho qua
  -> neu auth_enabled=true: check API key
  -> gan role vao request
  -> route check permission
```

Permission hien co:

```text
tasks:read
tasks:write
audit:read
approvals:read
approvals:write
```

## 3. Config layer

File chinh:

```text
enterprise_ai/config.py
config.example.json
config.production.example.json
```

Vai tro:

- doc config tu JSON file
- override bang environment variable
- resolve duong dan storage va knowledge base

Flow:

```text
run.py
  -> load_config()
  -> AppConfig
  -> create_app(config)
```

Config quan trong:

```text
auth_enabled
api_keys
role_permissions
ip_allowlist
cors_origins
llm_provider
llm_endpoint
llm_model
storage_backend
storage_path
knowledge_base_path
```

## 4. Normalizer

File chinh:

```text
enterprise_ai/normalizer.py
```

Vai tro:

- chuan hoa input tu nhieu nguon
- lay noi dung task tu `text`, `message`, `description`, hoac `body`
- tao `task_id`
- gom metadata

Input vi du:

```json
{
  "source": "telegram",
  "text": "Router edge-01 is down"
}
```

Output logic:

```text
NormalizedTask(
  task_id=<uuid>,
  source=telegram,
  text="Router edge-01 is down",
  metadata={...}
)
```

Flow:

```text
raw payload
  -> Normalizer.normalize()
  -> NormalizedTask
  -> storage.create_task()
  -> audit task_received
```

## 5. Domain models

File chinh:

```text
enterprise_ai/domain.py
```

Vai tro:

- dinh nghia data contract noi bo
- chuan hoa enum cho task, severity, risk, policy decision

Model quan trong:

```text
NormalizedTask
Classification
ActionProposal
PolicyResult
ToolResult
```

Day la lop giup LLM, policy, executor va verifier noi chuyen voi nhau bang object ro rang thay vi string tu do.

## 6. Classifier

File chinh:

```text
enterprise_ai/classifier.py
enterprise_ai/llm/prompts.py
enterprise_ai/llm/qwen_client.py
```

Vai tro:

- dung Qwen3 `/no_think` de phan loai task neu LLM kha dung
- fallback bang rule-based keyword neu Qwen3 chua chay
- tra ve task type, confidence, severity va entities

Task type:

```text
information_query
incident
report_request
config_change
unknown
```

Flow:

```text
NormalizedTask
  -> TaskClassifier.classify()
  -> QwenClient.chat(json_mode=True)
  -> neu fail: keyword fallback
  -> Classification
  -> audit task_classified
```

Output vi du:

```json
{
  "task_type": "incident",
  "confidence": 0.76,
  "severity": "critical",
  "entities": {
    "host": "edge-01"
  },
  "reason": "keyword fallback matched incident language"
}
```

## 7. Workflow engine

File chinh:

```text
enterprise_ai/workflow.py
```

Vai tro:

- dieu phoi flow tong
- goi normalizer, classifier, RAG, planner, policy, executor, verifier, storage
- quyet dinh task nao duoc xu ly tu dong, task nao can approval, task nao can human escalation

Flow tong:

```text
WorkflowEngine.handle(payload)
  -> normalize
  -> create task in storage
  -> classify
  -> confidence gate
  -> route by task_type
```

Route:

```text
information_query
  -> RAG answer
  -> final response

incident/report_request/config_change
  -> RAG search
  -> ReasoningPlanner
  -> ActionProposal
  -> PolicyEngine
  -> allow/block/approval
```

Neu confidence thap:

```text
Classification unknown/low confidence
  -> human escalation
  -> status=escalated
```

## 8. RAG service

File chinh:

```text
enterprise_ai/rag.py
knowledge_base/*.md
```

Vai tro:

- load Markdown trong `knowledge_base`
- doc metadata front matter
- chia document thanh chunk
- search theo token/score
- tra snippet va citation theo dong

Metadata vi du:

```markdown
---
domain: network
doc_type: runbook
roles: admin,operator,viewer
---
```

Flow:

```text
query/task text
  -> LocalRagService.search()
  -> filter by role metadata
  -> score document chunks
  -> return SearchHit
```

SearchHit gom:

```text
title
path
score
snippet
citation
chunk_id
metadata
```

Vi du citation:

```text
runbook_network_incident.md:L10-L18
```

Ghi chu production:

```text
LocalRagService hien la retrieval nhe cho demo/lab.
Neu knowledge base lon, thay implementation bang Chroma/Qdrant/FAISS + local embeddings.
```

## 9. Reasoning planner

File chinh:

```text
enterprise_ai/workflow.py
enterprise_ai/llm/prompts.py
```

Vai tro:

- dung Qwen3 `/think` de suy luan va tao action plan
- neu Qwen3 khong kha dung, dung fallback planner
- chi tao action proposal, khong execute truc tiep

Flow:

```text
Classification + RAG hits
  -> ReasoningPlanner.plan()
  -> QwenClient.chat(json_mode=True)
  -> neu fail: fallback plan
  -> summary + actions + response
```

ActionProposal vi du:

```json
{
  "tool": "icinga2",
  "operation": "get_host_status",
  "risk": "read",
  "parameters": {
    "host": "edge-01"
  },
  "reason": "check monitoring state before proposing remediation",
  "requires_approval": false
}
```

## 10. Policy engine

File chinh:

```text
enterprise_ai/policy.py
```

Vai tro:

- allow-list tool va operation
- gan risk thuc te cho operation
- chan operation la
- yeu cau approval cho write/high-risk action

Flow:

```text
ActionProposal[]
  -> PolicyEngine.evaluate()
  -> allow | require_approval | block
  -> audit policy_evaluated
```

Risk level:

```text
read
notify
write
high
```

Vi du:

```text
icinga2.get_host_status       -> read
grafana.get_dashboard_snapshot -> read
ansible.apply_config_change   -> write
```

## 11. Approval flow

File chinh:

```text
enterprise_ai/workflow.py
enterprise_ai/storage.py
enterprise_ai/api.py
```

Vai tro:

- giu write/high-risk action o trang thai pending
- chi execute sau khi co approval
- cho phep reject action

Flow khi can approval:

```text
PolicyDecision.REQUIRE_APPROVAL
  -> storage.create_approval()
  -> response status=pending_approval
  -> operator approve/reject qua API
```

Approve:

```text
POST /api/approvals/<approval_id>/approve
  -> approve_and_execute()
  -> executor.execute()
  -> verifier.verify()
  -> audit approval_executed
```

Reject:

```text
POST /api/approvals/<approval_id>/reject
  -> reject_approval()
  -> status=rejected
  -> audit approval_rejected
```

## 12. Tool executor va adapters

File chinh:

```text
enterprise_ai/tools/base.py
enterprise_ai/tools/mock_adapters.py
```

Vai tro:

- executor nhan action da qua policy
- tim adapter theo `tool`
- goi operation cua adapter
- tra ve ToolResult

Flow:

```text
ActionProposal
  -> ToolExecutor.execute()
  -> adapter.run(operation, parameters)
  -> ToolResult
```

Adapter hien co la mock:

```text
grafana
icinga2
librenms
clickhouse
ansible
ticket
email
telegram
```

Huong mo rong:

```text
mock GrafanaAdapter
  -> GrafanaHttpAdapter

mock Icinga2Adapter
  -> Icinga2ApiAdapter

mock AnsibleAdapter
  -> AnsibleRunnerAdapter
```

Nguyen tac:

```text
LLM khong duoc goi API/device truc tiep.
LLM chi tao ActionProposal.
Executor moi la noi goi adapter.
```

## 13. Verifier

File chinh:

```text
enterprise_ai/verifier.py
```

Vai tro:

- kiem tra tool call thanh cong hay that bai
- voi read-only action: success la du cho verified co ban
- voi write/high-risk action: can post-check pass

Flow:

```text
actions + tool_results
  -> ResultVerifier.verify()
  -> verified | failed | needs_post_check
```

Write action can co:

```json
{
  "post_check": {
    "status": "passed",
    "checks": ["device reachable", "alert cleared", "config converged"]
  }
}
```

Neu write action khong co post-check:

```text
status=needs_post_check
```

## 14. Storage va audit

File chinh:

```text
enterprise_ai/storage.py
```

Vai tro:

- luu task
- luu result
- luu audit event
- luu approval request

Backend hien co:

```text
json
sqlite
```

JSON backend:

```text
phu hop demo, notebook, dev local
```

SQLite backend:

```text
phu hop single-node lab hoac noi bo nho
```

Production multi-node nen thay bang:

```text
PostgreSQL
ClickHouse/EventStore
managed database
```

Audit event quan trong:

```text
task_received
task_classified
actions_proposed
policy_evaluated
actions_executed
info_query_answered
human_escalation
approval_executed
approval_rejected
```

## 15. LLM client

File chinh:

```text
enterprise_ai/llm/qwen_client.py
enterprise_ai/llm/prompts.py
```

Vai tro:

- goi Qwen3 local qua Ollama hoac OpenAI-compatible endpoint
- ho tro JSON output mode
- bao loi ro khi LLM khong kha dung

Provider hien co:

```text
ollama
openai_compatible
vllm
lmstudio
disabled
```

Flow classifier:

```text
Task text
  -> Qwen3 /no_think
  -> JSON classification
```

Flow planner:

```text
Task + classification + RAG hits
  -> Qwen3 /think
  -> JSON action plan
```

Neu provider la `disabled` hoac Qwen3 loi:

```text
classifier fallback
planner fallback
```

## 16. End-to-end examples

### Incident

Input:

```json
{
  "source": "telegram",
  "text": "Router edge-01 is down, check status and suggest next action"
}
```

Flow:

```text
API
  -> Auth
  -> Normalizer
  -> Classifier: incident
  -> RAG: network incident runbook
  -> Planner: propose read-only checks
  -> Policy: allow
  -> Executor: icinga2/librenms/grafana mock
  -> Verifier: verified
  -> Audit
  -> status=completed
```

### Report

Input:

```json
{
  "source": "ticket",
  "text": "Generate a 24h traffic report for core link"
}
```

Flow:

```text
Classifier: report_request
  -> Planner: clickhouse.query_netflow_summary
  -> Policy: allow
  -> Executor: clickhouse mock
  -> Verifier: verified
  -> status=completed
```

### Config change

Input:

```json
{
  "source": "api",
  "text": "Change VLAN config on switch access-02"
}
```

Flow:

```text
Classifier: config_change
  -> Planner: ansible.apply_config_change
  -> Policy: require_approval
  -> storage.create_approval()
  -> status=pending_approval
```

Sau approve:

```text
approve endpoint
  -> executor: ansible mock
  -> verifier: check post_check
  -> status=completed
```

## 17. Nguyen tac an toan

```text
Qwen3 phan loai va suy luan.
Qwen3 khong duoc execute truc tiep.
Moi action phai co schema.
Moi action phai qua policy.
Write/high-risk action phai qua approval.
Write/high-risk action phai co post-check.
Moi buoc phai duoc audit.
```

## 18. Nhung phan con can lam de production that

```text
1. Thay mock adapters bang adapter API that.
2. Dung secret manager thay vi hard-code API key trong file config.
3. Doi storage sang PostgreSQL/EventStore neu chay multi-node.
4. Doi RAG sang vector DB neu knowledge base lon.
5. Them UI hoac Telegram approval flow.
6. Them metrics/trace/log tap trung.
7. Them test suite cho policy, auth, adapter va verifier.
8. Them backup/retention cho audit log.
```

