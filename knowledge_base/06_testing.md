# Test Strategy & Test Plan Assessment by Project Type

## Core Test Plan Evaluation Principles
* **Risk-Based Testing:** Testing effort must concentrate on the highest business and technical risks rather than chasing arbitrary code coverage percentages.
* **Test Pyramid & Trophy Alignment:** Verify a healthy balance between fast, isolated Unit Tests (domain logic), Integration Tests (databases, queues, external adapters), and lean End-to-End (E2E) tests (critical user journeys).
* **Shift-Left & CI/CD Automation:** Confirm that unit, contract, security, and static analysis checks run automatically on every pull request rather than relying on manual QA bottlenecks before release.
* **Test Data & Environment Parity:** Check how test data is generated, masked, and reset, and ensure staging environments mirror production configurations closely enough to catch real issues.

## Test Plan Priorities by Project Archetype

### 1. Financial, Banking & FinTech Systems
* **Deterministic Domain & Ledger Unit Tests:** Exhaustive unit testing of complex calculations, rounding rules, currency conversions, and DDD Aggregate invariants with 100% deterministic outcomes.
* **Idempotency & Concurrency Testing:** Automated tests verifying that duplicate payment requests, network retries, and simultaneous race conditions never cause double-charges or negative balances.
* **Security & Penetration Testing:** Automated SAST/DAST scanning in CI/CD, dependency vulnerability checks, and scheduled third-party penetration tests.
* **Reconciliation & Audit Verification:** End-to-end tests proving that every state transition produces an accurate, immutable audit trail and balances match across ledgers.

### 2. Healthcare & Medical Systems
* **Privacy & Access Control Verification:** Automated tests validating RBAC/ABAC boundaries (proving unauthorized roles cannot access patient records) and verifying PII/PHI masking in logs.
* **Compliance & Traceability Matrix:** Explicit mapping between regulatory requirements, test cases, and execution evidence for clinical safety audits.
* **Interoperability & Contract Testing:** Schema validation and Consumer-Driven Contract Tests (e.g., Pact) for external integrations using HL7, FHIR, or legacy hospital systems.
* **Offline & Failover Testing:** Chaos and network-partition tests confirming clinical workflows degrade safely when connectivity drops.

### 3. High-Traffic E-Commerce & Consumer Platforms
* **Load, Stress & Spike Testing:** Automated performance testing (e.g., k6, JMeter, Gatling) simulating flash-sale traffic surges to validate auto-scaling and identify database bottlenecks before launch.
* **Cross-Browser & Mobile E2E Journeys:** Automated E2E tests (e.g., Playwright, Cypress) covering high-value conversion funnels (search, cart, promo codes, checkout) across key devices.
* **Chaos & Resilience Testing:** Fault-injection tests proving that failures in non-critical services (recommendations, reviews, loyalty points) do not block checkout.
* **Canary & Synthetic Monitoring:** Post-deployment synthetic user checks running continuously in production to catch payment or checkout regressions immediately.

### 4. Real-Time IoT, Telemetry & Streaming Systems
* **High-Throughput & Backpressure Testing:** Sustained soak tests pumping millions of synthetic messages per second to verify queue durability, consumer lag recovery, and memory stability.
* **Out-of-Order & Duplicate Event Testing:** Tests verifying that event consumers handle delayed, out-of-sequence, or duplicate telemetry packets gracefully.
* **Edge & Network Drop Simulation:** Hardware-in-the-loop or emulator tests simulating packet loss, high latency, and device reconnections.
* **Schema Evolution Compatibility:** Automated checks ensuring updates to message schemas (Avro, Protobuf, JSON) do not break downstream consumers.

### 5. Internal Enterprise Tools & B2B Back-Office Apps
* **Workflow & Integration Testing:** Focus on integration tests validating business workflows across internal databases, ERPs, webhooks, and SSO/identity providers.
* **Role & Permission Matrix Testing:** Automated API tests verifying that different employee roles see and modify only their permitted data subsets.
* **Accessibility (WCAG) & Usability Checks:** Automated accessibility linting (e.g., axe-core) paired with structured User Acceptance Testing (UAT) by actual business stakeholders.
* **Data Migration & Upgrade Testing:** Dry-run migration tests verifying data integrity when upgrading schemas or importing records from legacy systems.

## Assessment Checklist for Any Proposed Test Plan
* **Clear Exit Criteria:** Does the plan define objective "Definition of Done" gates (e.g., zero critical bugs, p95 latency under threshold, passing contract tests) required before releasing?
* **Mocking Boundaries:** Are mocks limited strictly to external boundaries (third-party APIs, payment gateways) while real databases (via Testcontainers) are used for repository integration tests?
* **Flakiness Management:** Does the plan address how flaky E2E tests are quarantined, fixed, and prevented from eroding developer trust in the CI pipeline?
* **Production Readiness & Rollback Verification:** Are rollback procedures, feature flags, and database backward-compatibility tested before deployment?
