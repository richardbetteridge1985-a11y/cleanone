# Google Cloud Well-Architected Framework: Practical Review Guide

Use the framework as a source of design guidance, not a checklist that every
workload must satisfy in full. Tailor recommendations to purpose, data
sensitivity, regulatory obligations, business impact, expected scale and
availability, lifecycle stage, team capacity, and budget. A fintech or other
regulated, high-impact system may need stringent security, audit, resilience, and
recovery controls. A small low-sensitivity B2C service or personal project can
use simpler controls when the consequences and requirements justify them. Do not
infer regulatory status, traffic, or criticality that the proposal does not state.

For each recommendation, explain the risk it addresses, its expected benefit, and
its cost or operational trade-off. Prefer a small viable Google Cloud-native
improvement over an enterprise-scale redesign when it adequately addresses the
evidenced need. Label changes as Blocking, Recommended, or Optional. Multi-region
deployment, centralized enterprise governance, GKE, 24/7 operations, and other
heavyweight practices are conditional on workload risk and organizational
requirements, not universal prerequisites. Never treat a stated legal or
regulatory obligation as optional.

## Well-Architected considerations

### Operational excellence

- Use repeatable deployment and configuration practices appropriate to the
  service's maturity. Infrastructure as code and automated delivery reduce drift
  for production systems, but a small prototype does not automatically need a
  large platform engineering setup.
- Use Cloud Logging, Cloud Monitoring, and tracing where they provide actionable
  visibility. Define useful service-level indicators, alerts, and runbooks in
  proportion to the service's availability and support needs.

### Security, privacy, and compliance

- Apply least-privilege IAM to users, service accounts, and workloads. Avoid
  broad primitive roles and long-lived keys; prefer workload identity or other
  short-lived credentials where supported.
- Protect sensitive data with appropriate access controls, encryption in transit,
  and encryption at rest. Use Secret Manager for credentials and consider
  customer-managed encryption keys when regulatory or business requirements call
  for them.
- Restrict public access and use VPC Service Controls, private connectivity, or
  organization policies when the threat model and data sensitivity justify the
  added complexity.

### Reliability

- Set availability, recovery time (RTO), and recovery point (RPO) goals from
  business needs. Use regional, multi-zone, or multi-region designs only when
  those goals justify their cost and operational complexity.
- Design asynchronous consumers for at-least-once delivery: make handlers
  idempotent, bound retries, and use dead-letter handling for messages that
  cannot be processed.
- Choose Pub/Sub, Eventarc, or another messaging service based on delivery,
  ordering, retention, throughput, and integration needs. Version event schemas
  and avoid synchronous service chains where they create fragile dependencies.

### Performance and cost optimization

- Select a runtime and datastore that fit the workload. Cloud Run or Cloud
  Functions may suit smaller event-driven services; GKE is appropriate when
  Kubernetes capabilities justify its operational overhead.
- Use autoscaling and right-sized resources. Consider database, storage, network
  egress, and cross-region costs as part of the end-to-end design.
- Set budgets, labels, and cost alerts appropriate to the team's ability to
  monitor spend; avoid complex cost governance where a simple budget is enough.

### Sustainability

- Prefer efficient resource sizing and scale-to-zero or scale-down behavior when
  workloads are intermittent and the operational trade-offs are acceptable.
- Treat sustainability improvements as workload-specific opportunities, not a
  reason to compromise required availability, privacy, or performance.

## Common risks to evaluate

- Broad project-level IAM roles or exposed service credentials.
- Publicly reachable services or data stores without a stated need and suitable
  protections.
- Event consumers without idempotency, bounded retries, or failed-message
  handling.
- Shared writable databases across independent services where this creates
  coupling or undermines ownership boundaries.
- Multi-region, GKE, or enterprise landing-zone complexity without a business,
  risk, scale, or regulatory justification.