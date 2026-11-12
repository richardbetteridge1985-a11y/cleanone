# Domain-Driven Design (DDD) Assessment Checklist

## Strategic Design & Boundaries
* **Core, Supporting, and Generic Subdomains:** Check if the solution separates the unique business advantage (Core) from necessary custom software (Supporting) and off-the-shelf problems (Generic). Ensure engineering effort focuses heavily on the Core subdomain.
* **Bounded Contexts:** Verify that the system is divided into clear boundaries where a specific domain model applies. Each context should have its own data ownership, team autonomy, and clear responsibilities.
* **Ubiquitous Language:** Look at the code, database schemas, APIs, and documentation to see if developers and business experts use the exact same terminology. Flag any generic technical names like "Manager," "Processor," or "Data" that hide real business concepts.
* **Context Maps:** Review how different Bounded Contexts interact and depend on one another. The architecture should explicitly define relationships such as Shared Kernel, Customer-Supplier, Conformist, or Published Language.
* **Anti-Corruption Layers (ACL):** Check if there is a translation layer sitting between your Core domain and external systems or legacy databases. This prevents outside models and messy data structures from polluting your clean domain logic.

## Tactical Design & Building Blocks
* **Entities:** Confirm that objects defined by their continuity and unique identity (such as a User, Order, or Account) are modeled as Entities. Their identity must remain constant even as their attributes change over time.
* **Value Objects:** Look for concepts defined purely by their attributes (such as Money, DateRange, or Address) and verify they have no unique ID. Ensure they are immutable and enforce their own validation rules upon creation.
* **Aggregates and Aggregate Roots:** Check that closely related Entities and Value Objects are grouped into consistency boundaries. External objects should only hold references to the Aggregate Root, and all state changes must pass through that root to enforce business invariants.
* **Domain Events:** Look for explicit representations of meaningful business occurrences written in the past tense (such as `OrderPlaced` or `PaymentFailed`). These should trigger side effects across different Aggregates or Bounded Contexts without tight coupling.
* **Repositories:** Verify that data persistence logic is abstracted behind interfaces that mimic in-memory collections. Repositories should only exist for Aggregate Roots, not for every individual database table.
* **Domain Services:** Check that stateless operations involving multiple Aggregates or complex calculations that do not naturally belong to a single Entity are placed in Domain Services.

## Model Behavior & Architecture
* **Rich vs. Anemic Domain Models:** Inspect the domain classes to see if they contain both data and business behavior. If Entities are just getters and setters while all business rules live in external "Service" classes, the design suffers from an Anemic Domain Model anti-pattern.
* **Domain Isolation:** Ensure the core domain layer has zero dependencies on infrastructure, databases, UI frameworks, or third-party libraries. Dependencies should always point inward toward the domain, following patterns like Hexagonal, Onion, or Clean Architecture.
* **Application Services:** Check that the application layer remains thin and acts only as a coordinator. It should fetch Aggregates from Repositories, execute domain methods, save changes, and publish events without containing business rules itself.
* **Pragmatic Application:** Evaluate whether DDD is actually appropriate for the problem's complexity. Applying heavy tactical DDD patterns to simple CRUD (Create, Read, Update, Delete) subdomains adds unnecessary overhead.