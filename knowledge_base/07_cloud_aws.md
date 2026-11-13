# Applying the AWS Well-Architected Framework Proportionately

Use the six pillars below as prompts to find material risks and trade-offs, not as
a scorecard that every solution must satisfy in full. Tailor advice to the system's
purpose, data sensitivity, regulatory obligations, business impact, expected scale
and availability, lifecycle stage, team capacity, and budget. A fintech or other
regulated, high-impact service may need stringent security, audit, resilience, and
recovery controls. A small low-sensitivity B2C service or personal project can use
simpler controls when the consequences and requirements justify them. Do not infer
regulatory status, traffic, or criticality that the proposal does not state.

For each recommendation, explain the risk it addresses, its expected benefit, and
its cost or operational trade-off. Prioritize a small, viable AWS-native change
over an enterprise-scale redesign when both address the evidenced need. Label
changes as Blocking, Recommended, or Optional. Practices such as multi-account
governance, multi-region failover, 100% IaC, extensive game days, and 24/7
operations are conditional on workload risk and organizational requirements, not
universal prerequisites. Never treat a stated legal or regulatory obligation as
optional.

# AWS Architecture & Well-Architected Framework Assessment Checklist

## The Six Pillars of the AWS Well-Architected Framework

### 1. Operational Excellence
* **Infrastructure as Code (IaC):** Confirm that 100% of AWS resources are provisioned via declarative IaC (Terraform, AWS CDK, or CloudFormation) with zero manual "ClickOps" in production.
* **CI/CD & Safe Deployments:** Look for automated pipelines using progressive delivery strategies (Blue/Green, Canary, or rolling deployments) with automated rollback triggers on CloudWatch alarms.
* **Observability & Telemetry:** Verify centralized structured logging (CloudWatch Logs), metrics, and distributed tracing (AWS X-Ray or OpenTelemetry) across all microservices and serverless functions.
* **Runbooks & Game Days:** Check that operational runbooks exist for common failure modes and that teams regularly run chaos engineering or Game Day exercises.

### 2. Security
* **Identity & Least Privilege (IAM):** Ensure IAM roles use strict least-privilege permissions, temporary credentials (IAM Roles for Service Accounts / Lambda execution roles), and zero long-lived static access keys.
* **Multi-Account Isolation:** Verify workloads are separated across dedicated AWS accounts (Production, Staging, Shared Services, Security/Log Archive) managed via AWS Organizations and Service Control Policies (SCPs).
* **Network Segmentation:** Confirm databases and internal compute run in private subnets with no direct internet ingress, protected by Security Groups, NACLs, AWS WAF, and VPC Endpoints (PrivateLink).
* **Data Protection & Secrets Management:** Check that data is encrypted at rest (AWS KMS) and in transit (TLS 1.2+), and that secrets are stored in AWS Secrets Manager or Parameter Store—never hardcoded in environment variables or source control.

### 3. Reliability
* **Multi-AZ & Multi-Region Resilience:** Verify that stateful services (RDS, ElastiCache) and compute (ECS, EKS, EC2) span multiple Availability Zones (Multi-AZ), with Multi-Region failover defined if strict RTO/RPO targets require it.
* **Decoupling & Asynchronous Buffering:** Look for event-driven decoupling using Amazon SQS, SNS, or EventBridge so downstream spikes or outages do not cascade upstream.
* **Quotas, Throttling & Retries:** Confirm service quotas have been reviewed and that code implements exponential backoff with jitter and Dead Letter Queues (DLQs) for failed messages.
* **Automated Backups & DR Testing:** Verify automated backups (AWS Backup, RDS snapshots, S3 versioning) paired with regular, automated restoration tests.

### 4. Performance Efficiency
* **Right-Sized Compute Selection:** Evaluate whether the compute choice matches the workload profile—Serverless (AWS Lambda, Fargate) for spiky or event-driven workloads, Containers (EKS/ECS) for steady microservices, or EC2 for specialized hardware needs.
* **Purpose-Built Databases:** Check that data stores match access patterns rather than forcing everything into one database (e.g., RDS/Aurora for relational transactions, DynamoDB for predictable single-digit millisecond key-value scale, OpenSearch for search, ElastiCache for caching).
* **Edge & Content Delivery:** Confirm static assets and API caching leverage Amazon CloudFront to reduce latency and offload origin servers.

### 5. Cost Optimization
* **Consumption & Scaling Alignment:** Verify auto-scaling policies (horizontal scaling, Lambda concurrency limits, Aurora Serverless v2) scale down during off-peak hours so you only pay for active demand.
* **Pricing Models & Commitments:** Check for use of Savings Plans or Reserved Instances for predictable baseline compute, and Spot Instances for fault-tolerant batch or background workers.
* **Storage Lifecycle & Data Transfer:** Confirm S3 Intelligent-Tiering or Lifecycle policies move aging objects to Glacier, and check that architecture minimizes expensive cross-AZ or NAT Gateway data transfer fees.
* **Cost Allocation & Budgets:** Verify consistent resource tagging strategies (`Environment`, `Team`, `BoundedContext`) and AWS Budgets alerts to catch spend anomalies early.

### 6. Sustainability
* **Managed & Serverless Adoption:** Favor serverless and managed services over idle, always-on virtual machines to maximize hardware utilization.
* **Efficient Compute & Storage:** Look for modern, energy-efficient processor architectures (such as AWS Graviton ARM-based instances) and automated deletion of unused EBS snapshots, unattached volumes, and stale logs.

## AWS-Specific Architectural Red Flags
* **Shared Monolithic Database Across Services:** Multiple bounded contexts or microservices reading and writing directly to the same RDS instance instead of communicating via APIs or events.
* **Lambda Monoliths or Distributed Monoliths:** Overly complex synchronous chains of Lambda functions calling each other directly, creating high latency and tight coupling.
* **Missing Dead Letter Queues (DLQs):** Asynchronous SQS queues, EventBridge rules, or SNS topics configured without a DLQ to capture and inspect failed events.
* **Unbounded NAT Gateway Costs:** High-volume internal traffic routing to S3 or DynamoDB through NAT Gateways instead of free Gateway VPC Endpoints.
