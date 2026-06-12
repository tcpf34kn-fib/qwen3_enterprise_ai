---
domain: network
doc_type: sop
roles: admin,operator
---

# Configuration Change SOP

Configuration changes must follow policy:

1. Identify target device and service owner.
2. Confirm change window and business impact.
3. Produce a dry-run diff when possible.
4. Require approval for write actions.
5. Execute through approved automation only.
6. Verify post-change health checks.
7. Store rollback ID and audit trail.

Never allow an LLM to execute shell commands or device commands directly.
