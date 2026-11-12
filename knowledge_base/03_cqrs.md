# CQRS (Command Query Responsibility Segregation) Overview & Assessment Checklist

## Core Philosophy & Separation of Concerns
* **Command vs. Query Separation:** The system strictly separates operations that modify state (**Commands**) from operations that read state (**Queries**). No single method or model should both mutate data and return complex query results.
* **Commands (Write Side):** Represent user intent to change the state of the system (e.g., `PlaceOrder`, `UpdateShippingAddress`). Commands are named imperatively, are validated before execution, and typically return only an acknowledgement, an ID, or an error—not domain data.
* **Queries (Read Side):** Retrieve data without modifying any system state or causing side effects. Queries are idempotent and can be executed repeatedly without altering business data.
* **Independent Scaling & Optimization:** The read and write workloads are decoupled so they can use different data access strategies, schemas, or even separate databases tailored to their specific performance needs.

## Architectural & Implementation Patterns
* **Write Model (Domain-Centric):** Focuses on enforcing business rules, invariants, and transactional consistency. This side often pairs well with Domain-Driven Design (DDD) Aggregates, Entities, and Repositories.
* **Read Model (Query-Centric):** Bypasses complex domain logic to fetch data as fast and efficiently as possible. It often relies on flat, denormalized Data Transfer Objects (DTOs) or materialized views mapped directly to UI needs.
* **Command & Query Handlers:** Each Command and Query is routed to a dedicated, single-purpose handler (often via a Mediator pattern) rather than bloating large service classes with mixed read/write methods.
* **Task-Based UI Alignment:** Commands reflect specific business tasks rather than generic CRUD updates (e.g., using `ApproveInvoice` instead of `UpdateInvoiceStatus`), capturing clear business intent.

## Data Synchronization & Consistency
* **Shared Database vs. Separate Data Stores:** Check whether the solution uses a single database with separate read/write models (simpler CQRS) or completely separate read and write databases (advanced CQRS).
* **Eventual Consistency:** When separate read and write stores are used, evaluate how the read store is updated (e.g., via Domain Events or message brokers). Ensure the UI and user workflows gracefully handle the slight delay before read views reflect recent writes.
* **Event Sourcing Integration (Optional):** Verify whether state changes are stored as an immutable sequence of events rather than current-state snapshots. Keep in mind that CQRS does not require Event Sourcing, even though they are frequently paired together.

## Assessment & Trade-Off Checks
* **Pragmatic Adoption:** Confirm that CQRS is applied selectively to complex Bounded Contexts or systems with asymmetric read/write loads. Applying full CQRS with separate databases to simple CRUD features introduces unnecessary boilerplate and operational complexity.
* **Idempotency & Concurrency:** Check how the write side handles duplicate commands (idempotency keys) and simultaneous edits to the same record (optimistic concurrency control).
