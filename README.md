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
`.jpeg`) uploads. Embedded diagrams and standalone images receive AI-generated
descriptions that are added to the document search index so their architecture
can be considered alongside the text. These descriptions are not verified OCR;
vision models can misread or omit labels, so confirm exact image text before
treating it as a fact.

There are two review modes:

- **Smart Panel** classifies the submission, selects relevant specialists, runs
  their reviews, reconciles technical feedback, assesses the documentation, and
  produces a final implementation decision.
- **Single Specialist Review** runs only the selected specialist and limits its
  response to that specialist's domain. Testing coverage is included only when
  the Testing & Verification Strategist is selected; an overall implementation
  decision is produced by the Smart Panel.

The Smart Panel rejects material only when it is clearly unrelated to software or
a digital solution. It runs every specialist selected as relevant to the
solution; there is no specialist-count cap. The internal reconciliation,
document-review, and final-review stages run after the specialist reviews.

The final review distinguishes implementation readiness from document quality:

- **Implementation decision:** Pass or Fail. A design can pass when it
  is likely to work and meet its stated functional requirements, provided the
  reviews identify no architectural anti-pattern or severe direct violation.
  Ordinary recommendations alone do not block a pass.
- **Changes required for Pass:** If revision is needed, the final review lists
  only blocking changes, ordered by importance and tied to the responsible
  specialist and design-document area. Test-plan gaps are not approval blockers.
- **Testing plan coverage:** The final review summarizes how well the documented
  plan covers the solution and names key scenarios to test. This is advisory and
  does not affect the implementation decision.
- **Solution document rating:** Good when most important areas are covered with
  only minor flaws; Fair when key areas are missing but the concept remains clear
  to business and technical readers; Bad when vital information is missing for
  implementation or business understanding. Fair/Bad reports list areas to rework.

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
- **Testing & Verification Strategist** — Runs in every Smart Panel review to
  assess test-plan coverage and identify key scenarios and suitable test levels,
  such as unit, integration, and contract tests. Its findings are advisory.
- **AWS Cloud Infrastructure Architect** — Reviews AWS services, IAM, networking,
  and managed infrastructure against the AWS Well-Architected Framework when AWS
  is present.
- **Azure Cloud Infrastructure Architect** — Reviews Azure services, identity,
  networking, and platform patterns against Azure's Well-Architected guidance.
- **GCP Cloud Infrastructure Architect** — Reviews Google Cloud services, IAM,
  data pipelines, and container or serverless topologies against Google's
  Well-Architected guidance when GCP is present.

The triage agent selects the five core lenses (DDD, Clean Architecture, CQRS, EDA,
and NFR) according to solution context. The testing specialist always runs in the
Smart Panel. AWS, Azure, and Google Cloud specialists run only when the solution
prompt or uploaded document clearly indicates use of that cloud, such as a
deployment statement, a cloud architecture label, or cloud-specific services.
Comparisons, options, and incidental mentions do not trigger them. Cloud
framework practices are treated as guidance, not a universal checklist:
recommendations are scaled to the proposal's sensitivity, regulation, business
impact, expected workload, operational capacity, and budget. A fintech system may
warrant stringent controls; a personal or small low-risk service may need simpler
safeguards. All specialists are instructed to
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

The Gradio interface binds to `127.0.0.1:7860`. Local text inference offers
`llama3.2:3b` and `qwen3.5:9b` through Ollama at `http://localhost:11434`. The AWS
Bedrock backend uses the standard AWS SDK credential chain (for example,
environment credentials, shared profiles/SSO, or an attached role) and requires
an AWS region from the environment or shared configuration.

Uploads are limited to 25 MB. The image pipeline prioritizes images near
architecture-related headings, checks at most 20 images, ignores photos,
decorative images, logos, and unrelated charts, and analyses at most five
solution-architecture diagrams. Images not checked within those limits are
reported as skipped. Vision analysis has a three-minute budget per upload, with
a 60-second timeout per image. The local text backend uses `llama3.2:3b`; diagram analysis
uses the vision-capable Ollama model `qwen3.5:9b` by default. It classifies
diagram type, identifies technologies with visible evidence, summarizes the
diagram's goal, and maps its components and flows. Install that model locally
before reviewing diagrams, or set
`CLEANONE_OLLAMA_VISION_MODEL` to another already-installed vision-capable model.
CleanOne checks that the configured model is installed and will not download it
automatically. If vision analysis is unavailable, the text review continues and
the proposal-processing status reports that the diagrams could not be analysed.
Local Qwen vision calls disable reasoning mode and allow up to 1,024 output
tokens for the structured analysis. Review agents receive the generated
description rather than the original image; the description is not verified OCR.
Exact labels should be confirmed from proposal text or manually checked against
the image before treating them as facts. All classified architecture diagrams
are included in specialist proposal searches, even when they are not the closest
semantic search match.

### Local model sizing and token safeguards

The output-token safeguards are **local-only**: Ollama text calls are limited by
`_LOCAL_MAX_OUTPUT_TOKENS` in `src/llm_router.py`. The Overall Solution Review
Judge has a local-only override, `local_max_output_tokens`, in
`config/agents.yaml` (currently 2,048 tokens) to give its synthesized response
more room. Qwen Smart Panel triage has its own `_QWEN_TRIAGE_MAX_OUTPUT_TOKENS`
in `src/solution_architect_triage.py`, and Ollama diagram analysis uses
`_LOCAL_VISION_MAX_OUTPUT_TOKENS` in `src/proposal_processor.py`. These caps are
intended to limit local inference work. AWS Bedrock requests do not receive these
application token caps; the provider's own limits apply. Request timeouts and
upload/diagram limits still apply to both backends.

To use a higher-capability local model, install it in Ollama yourself, then
update or add its `ollama/<model>:<tag>` entry in `_BACKEND_MAP` in
`src/llm_router.py`. Adjust `_LOCAL_MAX_OUTPUT_TOKENS` for its normal agent
responses. If using Qwen for Smart Panel, adjust
`_QWEN_TRIAGE_MAX_OUTPUT_TOKENS` separately; if the replacement model has
different reasoning controls, update `_prepare_triage_llm` in
`src/solution_architect_triage.py` to match. For diagram analysis, set
`CLEANONE_OLLAMA_VISION_MODEL` to an installed vision-capable Ollama model and,
if needed, adjust `_LOCAL_VISION_MAX_OUTPUT_TOKENS`. The application does not
install models automatically.

Application logs are written to `logs/cleanone.log` with request IDs and timing
information. `CLEANONE_LOG_LEVEL` and `CLEANONE_LOG_FILE` can be used to configure
the log level and output path.

The built-in local Qwen configuration disables its internal reasoning mode so
the local output-token budget is available for review content. If changing the
Qwen model, keep or revise the `reasoning_effort` setting in `_BACKEND_MAP` to
match that model's supported reasoning controls.

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
  written under `logs/`. These generated proposal files are excluded from Git.
  Restrict access to these locations, define retention and cleanup policies, and
  use appropriate disk encryption and backups.
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
