# Flow Diagram

File nay mo ta luong xu ly cua du an bang Mermaid. GitHub se render cac khoi `mermaid` thanh bieu do truc tiep.

## 1. Overall Architecture Flow

```mermaid
flowchart TD
    A["Input Adapters<br/>API / Telegram / Ticket / Webhook"] --> B["API Layer<br/>enterprise_ai/api.py"]
    B --> C["Auth Layer<br/>enterprise_ai/auth.py"]
    C --> D["Normalizer<br/>enterprise_ai/normalizer.py"]
    D --> E["Workflow Engine<br/>enterprise_ai/workflow.py"]

    E --> F["Task Classifier<br/>Qwen3 /no_think or fallback"]
    F --> G{"Confidence Gate<br/>type + confidence"}

    G -->|Low confidence / unknown| H["Human Escalation"]
    G -->|Information query| I["RAG Answer<br/>enterprise_ai/rag.py"]
    G -->|Incident / Report / Config change| J["RAG Search<br/>runbook / SOP / CMDB docs"]

    J --> K["Reasoning Planner<br/>Qwen3 /think or fallback"]
    K --> L["ActionProposal JSON<br/>tool + operation + risk + params"]
    L --> M["Policy Engine<br/>enterprise_ai/policy.py"]

    M -->|Block| N["Blocked Response"]
    M -->|Require approval| O["Approval Request<br/>storage.create_approval"]
    M -->|Allow| P["Tool Executor<br/>enterprise_ai/tools/base.py"]

    O --> Q{"Operator Decision"}
    Q -->|Reject| R["Rejected<br/>no action executed"]
    Q -->|Approve| P

    P --> S["Tool Adapters<br/>Grafana / Icinga2 / LibreNMS / ClickHouse / Ansible / Notify"]
    S --> T["ToolResult"]
    T --> U["Result Verifier<br/>enterprise_ai/verifier.py"]
    U --> V{"Verified?"}

    V -->|Failed| W["Failed Response"]
    V -->|Needs post-check| X["Needs Post-check"]
    V -->|Verified| Y["Final Response"]

    H --> Z["Audit Store<br/>enterprise_ai/storage.py"]
    I --> Z
    N --> Z
    R --> Z
    W --> Z
    X --> Z
    Y --> Z

    Z --> AA["Audit / Task / Approval History"]
```

## 2. Task Processing Sequence

```mermaid
sequenceDiagram
    autonumber
    participant Client as Input Adapter / Client
    participant API as API Layer
    participant Auth as Auth Middleware
    participant WF as WorkflowEngine
    participant Norm as Normalizer
    participant CLS as TaskClassifier
    participant RAG as LocalRagService
    participant Plan as ReasoningPlanner
    participant Policy as PolicyEngine
    participant Exec as ToolExecutor
    participant Verify as ResultVerifier
    participant Store as AuditStore

    Client->>API: POST /api/tasks
    API->>Auth: check API key / role / IP allowlist
    Auth-->>API: allow
    API->>WF: handle(payload)

    WF->>Norm: normalize(payload)
    Norm-->>WF: NormalizedTask
    WF->>Store: create_task + audit task_received

    WF->>CLS: classify(task)
    CLS-->>WF: Classification
    WF->>Store: audit task_classified

    alt unknown or low confidence
        WF->>Store: audit human_escalation
        WF-->>API: status=escalated
    else information_query
        WF->>RAG: answer_from_docs(task.text)
        RAG-->>WF: answer + sources
        WF->>Store: audit info_query_answered
        WF-->>API: status=completed
    else action workflow
        WF->>RAG: search(task.text)
        RAG-->>WF: RAG hits
        WF->>Plan: plan(task, classification, rag_hits)
        Plan-->>WF: summary + ActionProposal[]
        WF->>Store: audit actions_proposed

        WF->>Policy: evaluate(actions)
        Policy-->>WF: allow / require_approval / block
        WF->>Store: audit policy_evaluated

        alt block
            WF-->>API: status=blocked
        else require approval
            WF->>Store: create_approval
            WF-->>API: status=pending_approval
        else allow
            WF->>Exec: execute(action)
            Exec-->>WF: ToolResult[]
            WF->>Verify: verify(task, actions, results)
            Verify-->>WF: verified / failed / needs_post_check
            WF->>Store: audit actions_executed
            WF-->>API: final status + response
        end
    end

    API-->>Client: JSON response
```

## 3. Approval Flow

```mermaid
flowchart TD
    A["Config change or high-risk action"] --> B["ReasoningPlanner creates ActionProposal"]
    B --> C["PolicyEngine evaluates risk"]
    C --> D{"Decision"}

    D -->|allow| E["Execute immediately"]
    D -->|block| F["Return blocked response"]
    D -->|require_approval| G["Create approval request"]

    G --> H["GET /api/approvals"]
    H --> I{"Operator decision"}

    I -->|reject| J["POST /api/approvals/id/reject"]
    J --> K["status=rejected<br/>no tool execution"]

    I -->|approve| L["POST /api/approvals/id/approve"]
    L --> M["ToolExecutor executes approved action"]
    M --> N["ResultVerifier checks result"]
    N --> O{"Post-check"}

    O -->|missing or failed| P["status=needs_post_check or failed"]
    O -->|passed| Q["status=completed"]

    K --> R["Audit event"]
    P --> R
    Q --> R
```

## 4. Component To Source Map

```mermaid
flowchart LR
    A["API routes"] --> A1["enterprise_ai/api.py"]
    B["Auth / RBAC / IP allowlist"] --> B1["enterprise_ai/auth.py"]
    C["Runtime config"] --> C1["enterprise_ai/config.py"]
    D["Input normalization"] --> D1["enterprise_ai/normalizer.py"]
    E["Data contracts"] --> E1["enterprise_ai/domain.py"]
    F["Classification"] --> F1["enterprise_ai/classifier.py"]
    G["Qwen client"] --> G1["enterprise_ai/llm/qwen_client.py"]
    H["Prompts"] --> H1["enterprise_ai/llm/prompts.py"]
    I["Workflow orchestration"] --> I1["enterprise_ai/workflow.py"]
    J["RAG"] --> J1["enterprise_ai/rag.py"]
    K["Policy"] --> K1["enterprise_ai/policy.py"]
    L["Tool executor"] --> L1["enterprise_ai/tools/base.py"]
    M["Mock adapters"] --> M1["enterprise_ai/tools/mock_adapters.py"]
    N["Verification"] --> N1["enterprise_ai/verifier.py"]
    O["Storage / audit"] --> O1["enterprise_ai/storage.py"]
    P["Knowledge base"] --> P1["knowledge_base/*.md"]
```

## 5. Safety Gate View

```mermaid
flowchart TD
    A["LLM output"] --> B["Strict JSON parse"]
    B --> C["ActionProposal schema"]
    C --> D["Policy allow-list"]
    D --> E{"Risk level"}

    E -->|read / notify| F["Auto execute if policy allows"]
    E -->|write / high| G["Approval required"]

    G --> H["Human approval"]
    H --> I["Execute through adapter only"]
    F --> I

    I --> J["ToolResult"]
    J --> K{"Verifier"}

    K -->|read success| L["verified"]
    K -->|write without post_check| M["needs_post_check"]
    K -->|write post_check passed| L
    K -->|tool failure| N["failed"]

    L --> O["Audit + response"]
    M --> O
    N --> O
```

## 6. Production Extension Path

```mermaid
flowchart TD
    A["Current scaffold"] --> B["Real input adapters"]
    B --> C["Telegram / Zalo / Email / Ticket / Webhook"]

    A --> D["Real tool adapters"]
    D --> E["Grafana API"]
    D --> F["Icinga2 API"]
    D --> G["LibreNMS API"]
    D --> H["ClickHouse / Akvorado"]
    D --> I["Ansible / RouterOS / Netmiko"]

    A --> J["Production storage"]
    J --> K["PostgreSQL / EventStore / ClickHouse"]

    A --> L["Production RAG"]
    L --> M["Embeddings + Chroma / Qdrant / FAISS"]

    A --> N["Ops integration"]
    N --> O["Approval UI / Telegram approval"]
    N --> P["Metrics / traces / alerting"]
```

