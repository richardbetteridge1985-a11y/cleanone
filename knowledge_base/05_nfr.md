# Non-Functional Requirements (NFRs) Assessment by Project Type

## Core NFR Evaluation Principles
* **Context-Driven Priorities:** Never apply a one-size-fits-all NFR baseline. Every architectural decision involves trade-offs (such as latency vs. consistency, or security vs. usability), so NFRs must reflect the actual business risk of the domain.
* **Measurable & Testable Targets:** Avoid vague goals like "the system must be fast" or "highly available." Define concrete metrics such as Service Level Objectives (SLOs), p99 latency thresholds, Recovery Time Objectives (RTO), and Recovery Point Objectives (RPO).
* **Architecture Alignment:** Verify that the chosen architectural style supports the top NFRs (e.g., using CQRS for high-read scalability, or strict DDD Aggregates and ACID transactions for financial integrity).

## NFR Priorities by Project Archetype

### 1. Financial, Banking & FinTech Systems
* **Security & Compliance:** Strict adherence to standards like PCI-DSS, SOC2, or PSD2. Require end-to-end encryption (at rest and in transit), Hardware Security Modules (HSM) for key management, zero-trust networking, and multi-factor authentication (MFA).
* **Data Integrity & Consistency:** Strong transactional consistency (ACID) is non-negotiable to prevent double-spending or lost funds. Idempotency keys must be enforced on all payment and ledger commands.
* **Auditability & Traceability:** Immutable, tamper-evident audit logs (or Event Sourcing) recording who changed what, when, and why for regulatory inspections.
* **Availability & Resilience:** Active-active multi-region failover with near-zero RPO (zero data loss) and strict RTO targets.

### 2. Healthcare & Medical Systems
* **Privacy & Regulatory Compliance:** Strict compliance with HIPAA, GDPR, or local health data laws. Enforce granular Role-Based or Attribute-Based Access Control (RBAC/ABAC) and comprehensive patient consent tracking.
* **Data Confidentiality:** Strict separation of Personally Identifiable Information (PII) and Protected Health Information (PHI), utilizing field-level encryption and data anonymization for analytics.
* **Reliability & Safety:** High availability for clinical workflows where system downtime directly impacts patient care, paired with offline-first fallbacks for critical hospital tools.
* **Interoperability:** Support for industry data exchange standards (such as HL7 and FHIR) via dedicated Anti-Corruption Layers.

### 3. High-Traffic E-Commerce & Consumer Platforms
* **Scalability & Elasticity:** Ability to handle massive, sudden traffic spikes (e.g., Black Friday or flash sales) through horizontal auto-scaling, CDNs, and distributed caching.
* **Performance & Low Latency:** Sub-second page loads and fast search responses (p95/p99 latency budgets) to prevent cart abandonment.
* **Graceful Degradation:** Use circuit breakers, bulkheads, and asynchronous queues so non-critical failures (like product recommendations or reviews) do not block checkout.
* **Eventual Consistency Tolerance:** Accept eventual consistency for product catalogs, inventory counts, and user reviews while keeping payment processing strongly consistent.

### 4. Real-Time IoT, Telemetry & Streaming Systems
* **High Throughput & Ingestion Rate:** Ability to ingest millions of concurrent messages per second using event brokers (such as Kafka or MQTT) without backpressure crashes.
* **Low End-to-End Latency:** Deterministic processing times for real-time alerting, industrial control, or live tracking.
* **Data Retention & Storage Tiering:** Automated lifecycle policies to move hot telemetry data into cold, cost-effective storage over time.
* **Device Security & Resilience:** Mutual TLS (mTLS) for device authentication and local buffering on edge devices to handle intermittent network drops.

### 5. Internal Enterprise Tools & B2B Back-Office Apps
* **Maintainability & Evolvability:** Clean codebases, comprehensive automated test suites, and clear documentation so rotating teams can easily update business rules over many years.
* **Integration & Extensibility:** Well-defined APIs, webhooks, and Single Sign-On (SSO via OAuth2/OIDC/SAML) to connect smoothly with existing corporate identity providers and ERPs.
* **Cost Efficiency:** Right-sized infrastructure with predictable operational costs rather than over-engineered multi-region active-active setups.
* **Usability & Accessibility:** Compliance with WCAG accessibility standards and intuitive workflows to minimize employee training time.

## Assessment Checklist for Any Proposal
* **Single Points of Failure (SPOF):** Identify any database, queue, or third-party service that would take down the entire system if it failed.
* **Observability:** Confirm built-in support for structured logging, distributed tracing, and real-time metrics/alerting from day one.
* **Disaster Recovery & Backup Testing:** Check not just whether backups exist, but how frequently restoration is automated and tested.
* **Rate Limiting & Abuse Protection:** Verify protections against DDoS attacks, credential stuffing, and noisy-neighbor API consumption.
