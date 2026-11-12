# Azure Architecture & Well-Architected Framework Assessment Checklist

## The Five Pillars of the Azure Well-Architected Framework

### 1. Reliability
* **Availability Zones & Paired Regions:** Verify that stateful services (Azure SQL, Cosmos DB, Storage Accounts) and compute (AKS, App Service, Container Apps) are deployed across multiple Availability Zones (Zone-Redundant), with Paired Region failover configured if strict RTO/RPO targets require it.
* **Asynchronous Decoupling & Messaging:** Look for event-driven decoupling using Azure Service Bus (for enterprise messaging, transactions, and sessions), Event Grid (for reactive event routing), or Event Hubs (for high-throughput telemetry streaming).
* **Self-Healing & Resiliency Patterns:** Confirm code and infrastructure handle transient cloud faults using retry policies with exponential backoff, circuit breakers, and Dead-Letter Queues (DLQs) on Service Bus topics and queues.
* **Automated Backups & Disaster Recovery:** Verify geo-redundant storage (GRS/GZRS), point-in-time restore (PITR) on databases, and automated failover testing via Azure Chaos Studio or scheduled DR drills.

### 2. Security
* **Identity-First Security (Microsoft Entra ID):** Ensure all user and service authentication relies on Microsoft Entra ID (formerly Azure AD) with Conditional Access, Privileged Identity Management (PIM), and Managed Identities—eliminating connection strings and stored credentials.
* **Subscription & Management Group Governance:** Verify workloads are separated across dedicated Azure Subscriptions (Prod, Non-Prod, Connectivity, Identity, Management) governed by Management Groups and Azure Policy guardrails.
* **Network Segmentation & Zero Trust:** Confirm databases and internal compute run inside Virtual Networks (VNets) using Private Endpoints (Azure Private Link) with public network access disabled, protected by Network Security Groups (NSGs), Azure Firewall, and Azure Web Application Firewall (WAF).
* **Data Encryption & Secrets Management:** Check that data is encrypted at rest (Microsoft-managed or Customer-Managed Keys in Azure Key Vault) and in transit (TLS 1.2+), and that all certificates and secrets live exclusively in Azure Key Vault.

### 3. Cost Optimization
* **Consumption & Elastic Scaling:** Verify auto-scaling rules (Azure Container Apps KEDA scaling, AKS cluster autoscaler, Azure Functions Consumption/Flex Consumption plans) scale down to zero or minimum baseline during off-peak periods.
* **Azure Reservations & Savings Plans:** Check for Azure Reservations or Azure Savings Plans for Compute on predictable baseline workloads, alongside Azure Hybrid Benefit if bringing existing Windows Server or SQL Server licenses.
* **Storage Tiers & Data Egress:** Confirm Azure Blob Storage lifecycle management policies move aging data from Hot to Cool, Cold, or Archive tiers, and check that traffic patterns minimize cross-region bandwidth charges.
* **Tagging & Cost Management:** Verify strict Azure Policy enforcement of resource tags (`Environment`, `CostCenter`, `BoundedContext`) paired with Azure Cost Management budgets and anomaly alerts.

### 4. Operational Excellence
* **Infrastructure as Code (IaC):** Confirm that 100% of Azure infrastructure is defined declaratively using Bicep, Terraform, or ARM templates—preventing manual configuration drift in the Azure Portal.
* **CI/CD & Safe Release Pipelines:** Look for automated GitHub Actions or Azure DevOps pipelines using Deployment Slots (App Service), Blue/Green, or Canary rollouts with automated health-check gates.
* **Unified Observability:** Verify end-to-end telemetry using Azure Monitor, Log Analytics workspaces, Application Insights (distributed tracing and dependency mapping), and actionable alert rules.
* **Cloud Adoption Framework (CAF) Landing Zones:** Check whether the environment follows Azure Landing Zone principles for standardized networking, identity, and governance.

### 5. Performance Efficiency
* **Right-Sized Compute Selection:** Evaluate whether compute fits the workload—Azure Container Apps or AKS for microservices, Azure Functions for event-driven tasks, or Azure App Service for standard web apps and APIs.
* **Purpose-Built Data Stores:** Verify data stores align with access patterns—Azure SQL Database or PostgreSQL Flexible Server for relational ACID workloads, Azure Cosmos DB for globally distributed low-latency NoSQL, and Azure Cache for Redis for high-speed caching.
* **Global Routing & Edge Caching:** Confirm global applications leverage Azure Front Door (with integrated WAF and CDN) for global load balancing, SSL offloading, and edge caching.

## Azure-Specific Architectural Red Flags
* **Connection Strings Instead of Managed Identities:** Storing database passwords or storage account keys in App Settings or Key Vault when native Entra ID Managed Identity authentication is supported.
* **Public Endpoints Left Enabled on PaaS Services:** Leaving Azure SQL, Storage Accounts, or Key Vault exposed to the public internet instead of locking them down via Private Endpoints.
* **Using Event Grid When Service Bus Is Needed:** Relying on Event Grid for ordered, transactional enterprise commands where Service Bus queues, FIFO sessions, and duplicate detection are required.
* **Single-Region Deployment for Mission-Critical Apps:** Deploying stateful workloads without Zone Redundancy (ZRS) or geo-replication when high availability SLAs are required.
