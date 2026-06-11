# Network Incident Runbook

Use this runbook for alerts such as host down, link down, high packet loss, high CPU, weak optical power, or unstable routing.

Recommended first checks:

1. Confirm alert state in monitoring.
2. Check device reachability and last successful check.
3. Review interface carrier state, error counters, CPU, memory, and temperature.
4. Compare Grafana metrics over the last 15 minutes and 24 hours.
5. Check recent changes in ticket history and CMDB.
6. Escalate if the impact is production-wide, customer-facing, or unclear.

Read-only actions should be performed before any remediation. Write actions require approval.

