# CleanOne — Solution Architecture Review

CleanOne reviews **solution architecture documentation against modern architecture
standards**, with a primary focus on **event-driven microservice solutions**. It
helps architects and delivery teams assess whether a proposed design is coherent,
communicates its decisions and trade-offs, and addresses relevant technical
concerns.

Event-driven architecture is a key focus, not a requirement for every design. The
review first determines which architectural lenses are relevant; it will not
recommend microservices, CQRS, or event-driven patterns simply because they are
available.

CleanOne provides architectural feedback; it does not implement, deploy, or
certify a solution.

## What it reviews

The application accepts a written prompt and optionally a solution document. It
supports Word (`.docx`), PDF (`.pdf`), Markdown (`.md`), and image (`.png`, `.jpg`,
`.jpeg`) uploads. Embedded diagrams and standalone images are described and added
to the document search index so their architecture can be considered alongside
the text.

There are two review modes:

- **Smart Panel** classifies the submission, selects relevant specialists, runs
  their reviews, reconciles technical feedback, assesses the documentation, and
  produces a final implementation decision.
- **Single Specialist Review** runs one selected specialist for a focused review.

The Smart Panel rejects material only when it is clearly unrelated to software or
a digital solution. It runs at most four selected specialists. This cap applies
to specialist reviews; the internal reconciliation, document-review, and final
review stages run afterward.

The final review distinguishes implementation readiness from document quality:

- **Implementation decision:** Pass or Needs Revision. A design can pass when it
  is likely to work and meet its stated functional requirements, provided the
  reviews identify no architectural anti-pattern or severe direct violation.
  Ordinary recommendations alone do not block a pass.
- **Documentation presentation rating:** Good, Fair, or Bad, with Unable to assess
  used when there is no document to review. This rating is reported separately
  and does not by itself determine the implementation decision.

## Review agents

### Solution Architect Triage

Before a Smart Panel run, this reviewer considers the prompt, uploaded-document
evidence, and knowledge-base guidance for DDD, Clean Architecture, CQRS,
Event-Driven Architecture, and NFRs. It classifies the solution and explains which
of those specialist lenses should run. Domains that are not useful are reported
with a reason rather than treated as design defects.

### Architectural and operational specialists

- **Domain-Driven Design (DDD) Specialist** — Reviews domain boundaries,
  aggregates, entities, value objects, and ubiquitous language.
- **Clean Architecture Reviewer** — Assesses layer boundaries, dependency
  direction, and separation of domain logic from frameworks and infrastructure.
- **CQRS & Data Flow Architect** — Reviews command/query separation, handlers,
  read models, and consistency between reads and writes.
- **Event-Driven Architecture Specialist** — Assesses asynchronous communication,
  domain and integration events, messaging, idempotency, eventual consistency,
  outbox patterns, and saga workflows.
- **Non-Functional Requirements (NFR) Architect** — Reviews scalability,
  performance, security, observability, resilience, availability, and fault
  tolerance.
- **Testing & Verification Strategist** — Assesses testability, testing
  boundaries, and unit, integration, and contract-testing approaches.
- **AWS Cloud Infrastructure Architect** — Reviews AWS services, IAM, networking,
  and managed infrastructure when AWS is present.
- **Azure Cloud Infrastructure Architect** — Reviews Azure services, identity,
  networking, and platform patterns when Azure is present.
- **GCP Cloud Infrastructure Architect** — Reviews Google Cloud services, IAM,
  data pipelines, and container or serverless topologies when GCP is present.

The triage agent selects the five core lenses (DDD, Clean Architecture, CQRS, EDA,
and NFR) according to solution context. Testing and cloud specialists use the
existing prompt/document keyword-routing rules. All specialists are instructed to
treat “As Is”, current-process, and current-state examples as context, not as the
target design.

### Internal review stages

- **Technical Feedback Reconciliation Reviewer** — Resolves conflicts among
  specialist recommendations and returns a coherent technical change set while
  preserving changed original feedback for traceability.
- **Solution Document Architecture Peer Reviewer** — Assesses the write-up against
  general architecture-documentation standards, checks evidence for twelve
  business and technical attributes, and identifies evidenced gaps, risks,
  contradictions, and alignment changes.
- **Overall Solution Review Judge** — Combines the reconciled technical review and
  document-review findings into the final implementation decision, documentation
  assessment, and business-level summary. The document reviewer’s raw report is
  used as input and is not shown as a separate final-output section.

## How a Smart Panel review works

1. **Prepare the submission.** The application extracts document text and
   describes embedded diagrams or uploaded images.
2. **Classify and select.** The Solution Architect Triage assesses whether the
   material is software-solution related and chooses relevant core specialists
   using their knowledge-base guidance.
3. **Run bounded specialist reviews.** Selected specialists review the target
   design. Results are collected sequentially, subject to the four-specialist
   cap.
4. **Reconcile technical feedback.** The reconciliation reviewer resolves
   conflicting recommendations and identifies substantive changes.
5. **Assess documentation.** The document reviewer checks the proposal and its
   alignment with technical recommendations.
6. **Produce the final review.** The final judge reports implementation
   readiness, documentation presentation quality, a technical summary, and
   business understanding.

## Solution structure

```text
main.py                         Application startup
config/
  agents.yaml                   Agent roles, goals, knowledge sources, routing
  tasks.yaml                    Review and output instructions
  kb_hash.txt                   Knowledge-base index fingerprint
knowledge_base/
  00_general.md                 General solution-documentation standards
  01_ddd.md                     Domain-Driven Design guidance
  02_ca.md                      Clean Architecture guidance
  03_cqrs.md                    CQRS guidance
  04_ed.md                      Event-driven architecture guidance
  05_nfr.md                     Non-functional requirements guidance
  06_testing.md                 Testing guidance
  07_cloud_aws.md               AWS guidance
  08_cloud_azure.md             Azure guidance
  09_cloud_gcp.md               GCP guidance
src/
  ui.py                         Gradio interface and request handling
  agent_factory.py              Agent construction and Smart Panel orchestration
  solution_architect_triage.py  Pre-review classification and specialist selection
  proposal_processor.py         Document/image extraction and proposal indexing
  rag_engine.py                 Local knowledge-base indexing and retrieval
  llm_router.py                 Local and AWS Bedrock model configuration
  output_cleanup.py             Cleanup of conditional specialist output
  logging_config.py             Rotating application logs and request IDs
tests/                          Unit and regression tests
```

### Request and knowledge flow

`main.py` configures logging, initializes the local knowledge base, and launches
the Gradio interface. The UI sends a request to `AgentFactory`. For Smart Panel
reviews, `SmartPanelRunner` invokes the triage agent, runs the selected reviewers,
and then runs the internal reconciliation, document-review, and final-review
stages.

The knowledge-base files are split into searchable chunks and stored in a local
Chroma database. The knowledge base is rebuilt on application startup when its
source files change. Uploaded proposals are indexed separately for the current
review so the agents can retrieve relevant sections without passing an entire
large document to every stage.

Agent definitions and task prompts are kept in YAML to separate review policy
from orchestration code. The local knowledge documents provide the criteria used
by the specialists and triage agent.

## Running locally

Install the Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start the selected model backend, then launch the application from the repository
root:

```bash
python main.py
```

The Gradio interface binds to `127.0.0.1:7860`. The local backend uses Ollama with
`llama3.2:3b` at `http://localhost:11434`. The AWS Bedrock backend requires
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_DEFAULT_REGION` to be
configured in the environment.

Application logs are written to `logs/cleanone.log` with request IDs and timing
information. `CLEANONE_LOG_LEVEL` and `CLEANONE_LOG_FILE` can be used to configure
the log level and output path.

## Privacy, security, and operational notes

CleanOne is intended to run inside an organization's controlled environment,
locally or in a controlled cloud, without depending on public consumer AI
services. The model backend determines where prompts, extracted document text,
and diagram descriptions are processed. **The application alone cannot guarantee
that private domain knowledge will not leave your environment.**

- **Local inference:** The built-in Ollama option points to
  `http://localhost:11434`. When the model server is running on the same machine,
  inference requests are sent to that local service. Confirm the Ollama
  configuration and network policy before treating this as an isolated
  deployment.
- **Managed cloud inference:** The other built-in option uses AWS Bedrock. It is
  a managed AWS endpoint, not a public consumer chatbot, but review content is
  sent to AWS for processing. Confirm your organization's AWS, contractual,
  retention, and data-handling requirements before using it with sensitive
  material.
- **Private-cloud inference:** The architecture can be adapted to a model hosted
  within a business-controlled cloud environment without using a public model
  API. The current backend selector only includes local Ollama and AWS Bedrock;
  using another private endpoint requires configuring or extending
  `src/llm_router.py`. Verify the endpoint and network route before claiming
  private inference.
- **Local data and logs:** Knowledge and proposal indexes are persisted under
  `config/chroma_db/` and `config/session_proposal_db/`; application logs are
  written under `logs/`. Restrict access to these locations, define retention and
  cleanup policies, and use appropriate disk encryption and backups.
- **Network exposure:** The UI binds to loopback by default and does not
  configure authentication. Do not expose it directly to a network as-is. A
  cloud or shared deployment needs an intentional bind/proxy configuration,
  authentication and authorization, TLS, network controls, and an operational
  data-retention policy.
- **Review limitations:** Outputs are AI-generated guidance, not a security
  certification, compliance determination, or substitute for qualified
  architecture and security review. Verify recommendations against the source
  documents, organizational standards, and the actual implementation before
  making delivery decisions.
