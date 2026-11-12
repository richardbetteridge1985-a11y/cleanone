# Solution Architecture Proposal Standards (TOGAF, arc42, C4 & ATAM)

## Business & Executive Assessment Checklist

* **Architecture Vision & Strategic Alignment (TOGAF Phase A)**
  * Clearly states the business problem, strategic drivers, and measurable objectives (KPIs/OKRs).
  * Defines explicit boundaries distinguishing what is In Scope versus Out of Scope.
* **Stakeholder & Concern Mapping (TOGAF Stakeholder Management)**
  * Identifies key business personas, end users, and operational owners alongside workflow impacts.
  * Includes a plain-English Executive Summary free of unexplained technical jargon.
* **Business Capability & Process Impact (TOGAF Phase B)**
  * Illustrates high-level "As-Is" vs. "To-Be" business process flows showing how value moves across teams.
  * Articulates operational handoffs, manual steps, and user journey touchpoints clearly.
* **Options Analysis & Architecture Decision Records (ADRs / ATAM)**
  * Compares at least two viable architectural options (including a simpler or "do nothing" baseline).
  * Justifies business trade-offs such as speed-to-market versus long-term flexibility.
* **Cost, Commercials & Resource Viability (FinOps / TOGAF Phase E)**
  * Provides a Total Cost of Ownership (TCO) estimate covering build effort, licensing, and monthly cloud run costs.
  * Highlights team skill requirements, vendor lock-in risks, and third-party dependencies.
* **Delivery Roadmap, Risks & Governance (TOGAF Phases E–G)**
  * Breaks implementation into incremental, value-delivering phases or MVPs rather than a single "big bang" release.
  * Documents key business, compliance, and delivery risks with clear owners and mitigation plans.

---

## Technical & Engineering Assessment Checklist

* **Multi-Level Visual Clarity & Diagram Consistency (C4 Model & arc42)**
  * Progresses logically from System Context (actors and external systems) down to Containers and Components.
  * Includes legends and labelled arrows (protocol and direction) that match the surrounding prose without contradictions.
* **Data Architecture & Lifecycle Governance (TOGAF Phase C - Data)**
  * Defines core domain entities, data ownership boundaries, and single sources of truth.
  * Addresses data retention, encryption at rest and in transit, PII/GDPR compliance, and schema evolution.
* **Integration Contracts & Interface Specifications (arc42 Runtime & Interfaces)**
  * Specifies synchronous APIs (REST/gRPC/GraphQL) and asynchronous events (topics/queues) with schemas and versioning.
  * Defines failure handling including timeouts, retries, dead-letter queues, and idempotency.
* **Quantified Non-Functional Requirements (arc42 & ATAM)**
  * Backs quality attributes with concrete targets (e.g., 99.95% availability, <200ms p95 latency, 500 TPS peak) rather than vague claims.
  * Defines Recovery Time Objectives (RTO) and Recovery Point Objectives (RPO) for disaster recovery.
* **Security, Identity & Trust Boundaries (Zero Trust / TOGAF Security)**
  * Maps authentication (OIDC/OAuth2), authorisation (RBAC/ABAC), secrets management, and network trust zones.
  * Documents external ingress points, service-to-service permissions, and tenant/data isolation boundaries.
* **Deployment Topology, Operability & Verification (arc42 Deployment & Crosscutting)**
  * Specifies the runtime environment including cloud regions, availability zones, compute topology, and CI/CD pipelines.
  * Defines observability standards (structured logging, distributed tracing, alerting) and end-to-end verification strategies.
