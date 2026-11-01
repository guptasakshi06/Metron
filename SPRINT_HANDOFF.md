# Data Optimizer sprint handoff

This is the canonical implementation plan and progress record for Data Optimizer. A new chat can execute the next unfinished sprint using this file and the repository, without reading previous chats or accessing the original Page.

## Start here

**Project root:** `/home/ubuntu/Documents/ChatGPT/Data Optimizer`  
**Canonical handoff:** `/home/ubuntu/Documents/ChatGPT/Data Optimizer/SPRINT_HANDOFF.md`  
**Repository instructions:** `AGENTS.md`  
**Architecture reference:** `docs/ARCHITECTURE.md`  
**Plan created:** 2026-11-01, Asia/Kolkata  
**Last updated:** 2026-11-02, Asia/Kolkata  
**Current sprint:** S02  
**Next sprint:** S02  
**MVP status:** S01 complete; MVP implementation in progress  
**Verified repository state at planning:** No application files and no Git commits. Do not assume this remains true in later chats.

User operating model: one sprint per new chat. When the user supplies this handoff for execution without naming a sprint, resume an in-progress sprint; otherwise execute the first eligible unfinished MVP sprint in dependency order. Do the implementation, run appropriate verification and update this same file before ending. Do not merely produce another plan. Stop after that sprint unless the user explicitly requests more.

Copy this into a new chat in the same project:

> Read `/home/ubuntu/Documents/ChatGPT/Data Optimizer/SPRINT_HANDOFF.md`, execute the next unfinished sprint, verify it, and update the handoff before finishing.

If the user supplies just the path as an implementation request, apply the same behavior. If the user explicitly asks for review, explanation or a planning change, honor that narrower request. If this repository moves, derive the project root from this file's actual location and update the stored absolute paths; never recreate the old directory solely because it is recorded here.

## Mandatory execution and continuity protocol

### At the beginning of every implementation chat

1. Read applicable repository instructions, this entire handoff and the local architecture reference. Read later decision notes or sprint reports linked here before altering their affected areas. Existing session instructions and the user's latest directions take precedence.
2. Inspect the actual worktree, Git status, dependency manifests and current files. Preserve unrelated user changes. A checked task or a chat summary is not proof that code still exists or works.
3. Reconcile the Current sprint, Next sprint, ledger and per-task checklists. Resume incomplete work first. If completed work is missing or regressed, record the discrepancy and repair prerequisites before claiming further completion.
4. Select one sprint. Ensure its required dependencies are complete. Mark it `in_progress` in the ledger, set Current sprint and write a concrete Resume from note before substantial implementation.
5. Briefly tell the user which sprint is being executed and its expected working outcome. Resolve ordinary engineering decisions using the recorded defaults and actual repository evidence.
6. Read relevant skills and official current documentation when required by the active environment or version-dependent integration. This plan does not override tool permissions or required approvals.

### While working

- Implement the selected sprint's required scope, including integration and relevant checks. Add only prerequisite changes needed for that sprint; record scope adjustments.
- Update its task checkboxes and Resume from note at useful checkpoints, especially before a context limit, interruption or tool limitation. Never wait until the very end to save all continuity.
- Reuse working components from earlier sprints. Avoid gratuitous rewrites and changes to the selected stack.
- Implement the real data path. Synthetic fixtures are valid for reproducible evaluation; synthetic measurements must never masquerade as uploaded-data results or live prices.
- Make no unsupported claims about performance, model quality, interviews, cloud integrations or savings. Distinguish mocked tests, actual local execution and actual external-service execution.
- A missing optional API key must not prevent building and testing the deterministic local path. A genuinely required missing dependency remains a recorded blocker, not a silent skip.
- Ask a focused question only when an unresolved choice actually blocks required work. Continue independent tasks in the selected sprint while waiting. Do not mark dependent work complete.
- Use local reversible development actions within the user's authorized sprint. Do not publicly deploy, provision paid resources, send messages, migrate production data or delete source data without appropriate authorization.
- Do not introduce autonomous subagents solely because the plan has several tasks. Follow the active conversation's delegation rules.
- Do not commit, push, reset, discard unrelated changes or rewrite Git history unless requested or separately authorized. Record the branch and commit when available, but do not require a commit to finish a sprint.

### Before ending every implementation chat

1. Run the checks needed to establish the sprint's acceptance gates. Fix failures caused by the sprint. Record exact commands and outcomes; use `not_run` or `blocked` for checks that were not executed.
2. Update every affected task checkbox. Only check a task when its actual deliverable and verification are present.
3. Update the ledger, Current sprint, Next sprint, MVP status and Last updated date/time. Recalculate the next action from actual completion, not a guessed calendar date.
4. Fill the selected sprint's Execution record with changed files, behavior delivered, exact setup/run/test commands, environment, results, limitations and a precise resume instruction.
5. Append an entry to the Session history. Link any new decision notes, runbooks and evidence locations using repository-relative paths so the handoff survives moving the repository.
6. Mark a sprint `completed` only when all required tasks and acceptance gates pass. If incomplete, leave it `in_progress` or `blocked`, keep the next pointer on it and explain the exact remaining work.
7. Read back the updated status and ensure it agrees with the implementation. End with a short result, verification summary, material gap and the next sprint ID.

**These status updates are mandatory after every sprint and after partial attempts.** Do not instruct the user to update the handoff manually. Chat memory is not the progress database.

### Status rules

| Status | Meaning |
| --- | --- |
| not_started | No implementation claimed |
| in_progress | Some work exists but required tasks or verification remain |
| blocked | A concrete external requirement prevents remaining required work; record what unblocks it |
| completed | Required tasks and acceptance checks passed with recorded evidence |
| deferred | Only for work explicitly removed from scope by the user; record the decision and downstream impact |

The ledger and task checklists must agree. A cancelled test is not passed. An unavailable live-provider smoke test may stay unverified if that sprint explicitly allows offline completion; a required local integrity, security or integration gate may not.

No sprint is automatically completed by this planning document. S01 through S14 all start as not_started.

## Product and scope

Data Optimizer helps technical founders and engineers choose how to represent and store analytical datasets using requirements, data profiles, workload experiments and transparent costs.

The core promise is: **recommend the best tested feasible configuration for the user's dataset and workload, explain the evidence and provide a reproducible implementation handoff.**

### MVP scope

- CSV, NDJSON and Parquet analytical datasets; lossless transformations within explicitly supported semantics.
- Startup context and structured requirements; user-supplied queries expressed as a constrained workload specification.
- Local profiling, optional metadata-only import and bounded server-side upload analysis.
- Baseline plus compressed NDJSON and Parquet codec/layout alternatives.
- Integrity checks, reproducible sandboxed benchmarks, itemized cost modeling and empirical ranking.
- Adaptive sequential experiment selection for larger spaces; direct enumeration for tiny spaces.
- Browser assessment flow, optional structured AI assistance, report/migration exports and manual savings observations.
- A fully working local development/demo environment and a documented production-readiness boundary.

### Out of the initial implementation

Automatic production migrations/deletion, broad transactional database replacement, media/video optimization, vector storage advice, automatic cross-cloud moves, enterprise billing connectors, scheduled external notifications, custom supervised-model training and paid/public deployment.

These are explicit post-MVP options, not hidden requirements. Real customer interviews and invoice validation require real participants/data; agents must not fabricate them. Build a usable local MVP while recording pending pilot validation.

### User experience and evidence rules

- A startup description alone yields requirement clarification and scenario guidance, not historical savings.
- Unknown volume, usage or price inputs remain unknown; return useful next questions.
- Preserve the baseline as a candidate and support change, keep_current and insufficient_evidence.
- Distinguish sample measurements, larger-workload projections and observations after deployment.
- Never infer transactional database replacement from a file-format benchmark.
- Preserve decimal precision, IDs, null/missing distinctions, time semantics and record multiplicity. Duplicate-looking events are not disposable.
- Local disk measurements do not prove cloud concurrency or latency.
- Smaller physical bytes do not automatically mean a lower fixed/provisioned bill.
- No arbitrary model confidence scores; explain coverage, variance and assumptions.

## Architecture and defaults

```text
React dashboard -> FastAPI -> PostgreSQL assessment metadata
                        |
                        +-> object storage for uploaded/transformed artifacts
                        |
                        +-> Redis/RQ -> isolated profiling/conversion/benchmark worker
                                           |
                                  integrity + cost + constrained ranking
                                           |
                                  versioned report and migration export

Optional LLM -> proposed requirements / clarification / grounded explanation
Local profiler -> reviewable metadata report -> optional import
```

Use a modular backend codebase with separate API and worker processes. This is a product with an optimization engine, not an unrestricted tool-using agent.

| Area | Default decision |
| --- | --- |
| Frontend | React, TypeScript and Vite; no framework switch without a recorded concrete need |
| API and core | Python, FastAPI, typed models, DuckDB and PyArrow |
| State | PostgreSQL and versioned migrations |
| Queue | Redis with RQ; durable business state in PostgreSQL |
| Artifacts | S3-compatible storage, MinIO locally |
| Local runtime | Containers/Compose for infrastructure and benchmark boundary; documented direct developer commands |
| Python tooling | uv and locked dependencies; Ruff, pytest and a type checker |
| Frontend tooling | npm with a lockfile; lint, type check, production build and targeted flow tests |
| Authentication | Maintained integration, verified identity for external use, explicit local-only development mode |
| Optimization | Experiment-driven ranking with bounded adaptive search; no custom training prerequisite |
| Reports | JSON plus readable Markdown/HTML; no mandatory PDF or spreadsheet dependencies |
| Prices | Versioned offline fixture labeled synthetic; verified provider snapshots when actually configured |
| AI | Optional structured provider adapter, no raw-record prompts by default, offline fallback |

Choose actual supported runtime/library versions during S01; record them rather than relying on versions from old chat context. This document defines desired interfaces, not claims about packages already installed.

Starting policy targets, to calibrate against the actual hardware: 256 MiB raw upload cap, a separate explicit decompressed-byte cap, up to 12 candidate configurations, up to 5 timed repeats per workload and bounded per-query/assessment time. Expose these as configuration. Budget, runtime and memory limits must be set before processing untrusted input. Do not advertise these values as proven capacity; S06/S14 measure and revise them.

### Intended repository layout

```text
AGENTS.md
SPRINT_HANDOFF.md
README.md
Makefile
.env.example
backend/
  pyproject.toml
  uv.lock
  migrations/
  src/data_optimizer/
    api/ auth/ db/ storage/ domain/ cli/
    readers/ profiling/ workloads/ integrity/
    candidates/ conversion/ benchmarking/ sandbox/
    pricing/ economics/ optimization/ recommendations/
    jobs/ workers/ intake/ llm/ explanations/
    reports/ migration/ observations/
  tests/
frontend/
  package.json
  package-lock.json
  src/
  tests/
infra/
  compose.yaml
  worker/
evaluation/
examples/
docs/
  ARCHITECTURE.md
  decisions/
  runbooks/
```

Create folders when their sprint introduces real code; do not create empty implementation placeholders or pretend all modules exist. Adapt paths to working code when justified and update this plan's references.

### Required command contract

S01 creates working developer entry points. Later sprints extend them without breaking the basic contract.

| Command | Intended behavior |
| --- | --- |
| make setup | Install locked dependencies and explain required local tooling |
| make infra-up | Start local infrastructure; run explicitly as needed |
| make infra-down | Stop local infrastructure without deleting data volumes by default |
| make dev | Start documented development processes |
| make check | Lint and type-check implemented backend and frontend code |
| make test | Run applicable meaningful tests, separating service-dependent suites clearly |
| make build | Build distributable application artifacts |
| make demo | Run the deterministic full demonstration once implemented; label fixture pricing |

Do not run a long-lived dev process as if it were a completing test. Record actual commands and any prerequisites in the sprint Execution record. A command that only prints success is not verification.

## Core contracts and state

Versioned entities: Project, Dataset, Requirements, Assessment, Profile, Workload, Candidate, Experiment, PriceSnapshot, Recommendation, MigrationPlan, Observation and AuditEvent. Ownership and immutable input/result references must be traceable throughout.

Assessment states: draft, needs_input, queued, profiling, benchmarking, scoring, completed, failed, cancelled. Add explicit stop/budget reasons for partial coverage. Recommendation outcomes: change, keep_current, insufficient_evidence.

Proposed API surface to refine through checked contracts:

```text
POST /v1/projects
POST /v1/projects/{project_id}/datasets
POST /v1/assessments
GET  /v1/assessments/{assessment_id}
GET  /v1/assessments/{assessment_id}/recommendations
GET  /v1/assessments/{assessment_id}/handoff
POST /v1/assessments/{assessment_id}/cancel
POST /v1/migration-plans/{plan_id}/observations
```

Authentication and upload subroutes may be added as needed; preserve a documented versioned API. Explicitly distinguish user-supplied evidence from server-measured evidence.

Cost objective: minimize expected total cost over the selected horizon including migration, subject to required semantics, capability, retention, freshness, latency, throughput and analysis budgets. Explain which constraints were actually tested.

```text
physical_space_saved = baseline_physical_bytes - candidate_physical_bytes
monthly_savings = baseline_monthly_total - candidate_monthly_total
horizon_net_savings = sum(monthly_savings_over_horizon) - migration_cost
payback_months = migration_cost / monthly_savings  # only for positive steady savings
```

Count required retained copies and overhead; compare equivalent logical data and requirements. Store price/date/region/currency/units. Unknowns remain null. Actual invoices, modeled counterfactuals and projections are different evidence categories.

## Sprint ledger

Sprints are execution units, not promises that a whole unit fits a single model turn. The user intends one new chat per sprint; resume within that chat or a replacement chat if needed. The earlier eight-week outline is replaced by this dependency-based sequence. Calendar estimates depend on scope and environment.

| ID | Sprint | Depends on | Status | Evidence |
| --- | --- | --- | --- | --- |
| S01 | Project foundation and executable contracts | None | completed | Locked setup, integrated checks/build, Compose service health, API readiness, direct HTTP and browser connectivity verified; see execution record below |
| S02 | Tenant data model and secure dataset ingestion | S01 | in_progress | Implementation session 2026-11-02; see S02 execution record |
| S03 | Typed profiling and the local privacy workflow | S02 | not_started | None |
| S04 | Workload specifications and semantic integrity checks | S03 | not_started | None |
| S05 | Candidate generation and lossless conversion | S04 | not_started | None |
| S06 | Bounded benchmark execution and evidence capture | S05 | not_started | None |
| S07 | Versioned pricing and total cost calculations | S06 | not_started | None |
| S08 | Evidence based ranking and adaptive experiment selection | S07 | not_started | None |
| S09 | Asynchronous assessments and complete API integration | S08 | not_started | None |
| S10 | Complete assessment dashboard | S09 | not_started | None |
| S11 | Structured AI intake and grounded explanations | S10 | not_started | None |
| S12 | Reproducible reports and migration handoff exports | S11 | not_started | None |
| S13 | Savings observations and manual reassessment | S12 | not_started | None |
| S14 | Integrated evaluation and local release readiness | S13 | not_started | None |

**Selection now:** S02 is the next unfinished sprint. S01 is complete. After S14 is verified, set Next sprint to `COMPLETE_MVP` and stop. Do not start the post-MVP backlog without a new request.

## Detailed sprint instructions
### S01 Project foundation and executable contracts

**Status:** completed  
**Dependencies:** None  
**Outcome:** Create a runnable repository skeleton and explicit contracts that later sprints can extend without guessing.  
**Expected code and document areas:** backend/pyproject.toml; backend/src/data_optimizer/{api,domain,cli}; frontend/; infra/compose.yaml; Makefile; .env.example; docs/decisions/

#### Tasks

- [x] S01.01 Inspect available runtimes and choose compatible supported Python, Node and package-manager versions. Verify official documentation when version-dependent; record versions and rationale. Create Python and frontend lockfiles without embedding credentials.
- [x] S01.02 Scaffold FastAPI and a React TypeScript application using Vite. Keep one backend package shared by API, CLI and workers. Establish Ruff, a Python type checker, pytest, frontend lint/type checks and production build commands.
- [x] S01.03 Define typed, versioned contracts for requirements, dataset descriptors, workload specifications, profiles, candidates, experiment measurements, price snapshots, decisions and evidence provenance. Treat unknown values as null or explicit unknown, never zero.
- [x] S01.04 Define assessment states and allowed transitions separately from recommendation outcomes. Specify stable IDs, timestamps, error envelopes, units and configuration fingerprints.
- [x] S01.05 Add /health and /ready endpoints with honest dependency behavior; implement only real readiness checks available in this sprint. Add a CLI version/help command and a frontend shell that shows backend connectivity.
- [x] S01.06 Create local Compose configuration for PostgreSQL, Redis and MinIO with development-only configuration. The API can start before business tables exist; readiness must explain missing dependencies.
- [x] S01.07 Create Make targets for setup, infra-up, infra-down, dev, check, test, build and demo. Targets for later capabilities must explain unavailability and fail clearly rather than returning fake success.
- [x] S01.08 Document setup in README.md and record architectural decisions. Set initial dataset limits, supported semantics and provisional benchmark thresholds as explicit configurable values.

#### Acceptance gates

1. A clean checkout can install from lockfiles, start the API and frontend, and display honest health information using documented commands.
2. Typed contracts reject invalid units, missing required fields and impossible state transitions; optional unknowns survive round-trip serialization.
3. make check, make test and make build run meaningful checks for implemented code; no product screen displays invented assessment results.

#### Verification to perform

Run setup and relevant checks; request /health; exercise CLI help and the frontend against the actual API. Capture exact commands, versions and outcomes.

#### Required handoff update

Record runtime versions, installed tooling, service ports, setup commands, contract locations and any environment limitations. Point next work to S02.

#### Execution record

- Started: 2026-11-02, Asia/Kolkata
- Updated: 2026-11-02, Asia/Kolkata
- Completed: 2026-11-02, Asia/Kolkata
- Branch and commit if available: `master`; no commits exist yet
- Delivered behavior: Installable Python/FastAPI foundation, strict versioned Pydantic contracts and lifecycle transition rules; React/TypeScript/Vite shell that reads actual API health and readiness; local tool bootstrap and process-clean `make dev`; local PostgreSQL/Redis/MinIO Compose stack; documented limits, setup and architectural decisions.
- Files changed: `.gitignore`, `.tool-versions`, `.env.example`, `Makefile`, `README.md`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/src/data_optimizer/`, `backend/tests/`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/index.html`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/eslint.config.js`, `frontend/src/`, `infra/compose.yaml`, `infra/minio/Dockerfile`, `scripts/bootstrap-tools.sh`, `scripts/dev.sh`, `scripts/check-local-runtime.sh`, `docs/decisions/0001-s01-foundation.md`, and this handoff.
- Setup and run commands: `bash scripts/bootstrap-tools.sh`; `make setup`; `make infra-up`; `make dev`; `make infra-down`. Use project-local Node 24/uv from `.tools/` as configured by the scripts and Make targets. `.env.example` documents defaults; Compose runs under `data-optimizer-local` on loopback ports 55432/56379/59000/59001.
- Verification commands and outcomes: Node archive checksum verified with `sha256sum -c`; Python 3.12.3, Node v24.22.2, npm 11.19.1, uv 0.13.6. `make setup` passed from the project root using both lockfiles (uv resolved/checked 45 packages; npm installed 270 locked packages). `make check` passed (Ruff; mypy on 9 source files; ESLint; TypeScript). `make test` passed (13 backend tests, 3 frontend tests). `make build` passed after final configuration changes (Python sdist+wheel and Vite 7.3.7 production build). Installed CLI `data-optimizer --help` and `--version` passed; version is 0.1.0. `make demo` exited 2 with its truthful not-yet-implemented message. `docker-compose -p data-optimizer-local -f infra/compose.yaml config` passed. Source-built MinIO image `f3a63730af43` was created from pinned commit `9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`; all three project services reached `(healthy)` at PostgreSQL 55432, Redis 56379, and MinIO 59000/59001. With `make dev` running, direct `GET /health` and `GET /ready` returned HTTP 200; Vite proxy `/api/health` and `/api/ready` also returned HTTP 200. The runtime check stopped the make process group and confirmed ports 8000/5173 closed with no Uvicorn/Vite child match. Its exit cleanup invoked `make infra-down` without `-v`; the command's output was suppressed by the runtime script version used for this run, and no separate post-down container listing was captured. The `infra-down` command preserves named volumes by default. Chrome 155 CDP browser verification displayed actual connected/degraded readiness, then disconnected after API stop, then recovered after restart; screenshots: `/tmp/data-optimizer-headless/connected-degraded.png`, `/tmp/data-optimizer-headless/disconnected.png`, `/tmp/data-optimizer-headless/recovered-degraded.png`. A final `bash -n scripts/bootstrap-tools.sh scripts/dev.sh scripts/check-local-runtime.sh` passed. Readiness probes use real PostgreSQL `SELECT 1`, Redis `PING`, and MinIO readiness HTTP checks; there are no S01 database tables.
- Evidence and report paths: command output recorded in this session; `backend/tests/`, `frontend/src/App.test.tsx`, `backend/uv.lock`, `frontend/package-lock.json`.
- Decisions and deviations: Python 3.12.3 with isolated Node 24.22.2 and uv 0.13.6. Node 18/npm 9 were below current Vite requirements, so setup pins and installs the supported tools project-locally. A MinIO source build is used because no usable published image tag was verified. Existing unrelated PostgreSQL and Redis containers occupied conventional ports, so the app uses Compose project `data-optimizer-local` and loopback ports 55432/56379/59000/59001. The first default-port attempt was cancelled before container start; only its partial network was removed, and named volumes were preserved.
- Blockers or unverified checks: None for S01. Compose v2 plugin is absent, so installed Compose 1.29.2 is used. The MinIO source build and local services were verified. The local policy limits remain provisional and are not measured capacity claims. Customer, production and external price validation remain future work outside S01.
- Resume from: Start S02.01, tenant schema and secure dataset-ingestion design, after reading this handoff and inspecting the actual worktree. Do not start later sprints in this execution.

### S02 Tenant data model and secure dataset ingestion

**Status:** in_progress  
**Dependencies:** S01  
**Outcome:** Persist projects and dataset versions and accept bounded uploads with ownership enforced.  
**Expected code and document areas:** backend/src/data_optimizer/{api,db,storage,auth}; backend/migrations/; infra/; backend/tests/integration/

#### Tasks

- [ ] S02.01 Implement PostgreSQL migrations for tenants, principals, projects, datasets, artifact references, requirements snapshots and audit events. Add version columns and ownership constraints where appropriate.
- [ ] S02.02 Introduce a maintained authentication integration and an explicit local-development identity adapter. Production mode must reject unverified identity. Keep the local adapter limited to explicit loopback development; do not accept an arbitrary tenant header as production authentication.
- [ ] S02.03 Enforce tenant-scoped access in service and repository methods for projects, datasets and artifact downloads. Verify the same rules for listing, fetching and deleting resources.
- [ ] S02.04 Implement project creation, dataset upload initiation, bounded transfer and upload finalization. Use scoped artifact keys and short-lived signed links, or a bounded streaming endpoint for the local MVP.
- [ ] S02.05 Validate actual file structure rather than trusting names or MIME headers. Limit uploaded and decompressed bytes; reject unsupported archives, path traversal and malformed upload state.
- [ ] S02.06 Calculate input fingerprints, retain immutable dataset versions and record original physical bytes, detected representation and declared semantics. Avoid reading entire large files into API memory.
- [ ] S02.07 Implement configurable retention and deletion of the user's uploaded assessment copies, including signed-link access and failure recovery. Explain deletion scope; never touch external source systems.
- [ ] S02.08 Add local seed/demo identities with no real customer records. Document mode switching and the requirements for an externally accessible environment.

#### Acceptance gates

1. Create a project, upload each supported input kind and retrieve its metadata and owned artifact.
2. A second tenant cannot list or retrieve another tenant's project, dataset or artifact; expired upload references and oversized files are rejected.
3. Migrations work on an empty development database and interrupted uploads do not become usable datasets.

#### Verification to perform

Run database/storage integration tests against local services; exercise two tenants, malformed input, quotas, expiration and upload finalization.

#### Required handoff update

Record migration commands, authentication mode, upload limits, storage layout, retention defaults and working API examples. Advance to S03.

#### Execution record

- Started: 2026-11-02 (Asia/Kolkata)
- Updated: 2026-11-02 (Asia/Kolkata)
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: S02.01: implement PostgreSQL tenant schema and migration wiring. S01 is recorded complete; infrastructure defaults are loopback PostgreSQL 127.0.0.1:55432, Redis 56379 and MinIO 59000/59001. Await Sol's detailed implementation plan before substantive code changes.

### S03 Typed profiling and the local privacy workflow

**Status:** not_started  
**Dependencies:** S02  
**Outcome:** Produce reproducible profiles from CSV, NDJSON and Parquet, including a local-only profiling option.  
**Expected code and document areas:** backend/src/data_optimizer/{profiling,readers,cli}; backend/tests/fixtures/; docs/dataset-semantics.md

#### Tasks

- [ ] S03.01 Build streaming or bounded readers using DuckDB/PyArrow. Define how CSV nulls, mixed types, decimals, identifiers, timestamps, JSON missing fields and nested values are interpreted. Ask for schema overrides when inference could change meaning.
- [ ] S03.02 Create deterministic small fixtures and generators for categorical events, high-cardinality text, legitimate duplicates, null/missing distinctions, decimal precision, time zones, nested records, schema drift and already compressed data.
- [ ] S03.03 Measure rows, columns, physical bytes, type distributions, null density, cardinality estimates, width distributions, temporal spread and file-size distributions. Label estimates and exact statistics separately.
- [ ] S03.04 Implement reproducible sampling across relevant time/source strata with a seed and coverage record. Support bounded full scans where feasible; explain unsupported sampling layouts.
- [ ] S03.05 Persist profile versions with input/schema fingerprints, engine versions, sample fraction and warnings. Reuse cached profiles only when fingerprints and relevant settings match.
- [ ] S03.06 Add CLI commands to profile locally and export a reviewable, versioned metadata-only report. Raw values and example records must be excluded by default.
- [ ] S03.07 Import valid local profiler reports without pretending the server inspected the raw dataset. Validate report schema and mark measurements as locally supplied evidence.
- [ ] S03.08 Define sensitive-field redaction for reports and logs. Add a user-review step before an optional metadata upload; profiling locally requires no external API key.

#### Acceptance gates

1. Equivalent supported fixtures yield stable profiles across repeated seeded runs, with explicit coverage and schema interpretation.
2. The profiler handles files above memory size within configured limits or returns a clear quota failure.
3. Local-only profiling works without network calls and the exported default report contains no raw customer rows.

#### Verification to perform

Run semantic fixture and reproducibility tests, a bounded larger generated dataset and a local CLI profile/export/import exercise.

#### Required handoff update

Record supported reader semantics, remaining unsupported cases, sample settings, exact CLI commands and resource observations. Advance to S04.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S03.01 after its dependencies are verified.

### S04 Workload specifications and semantic integrity checks

**Status:** not_started  
**Dependencies:** S03  
**Outcome:** Define comparable analytical operations and prove transformations preserve the agreed dataset meaning.  
**Expected code and document areas:** backend/src/data_optimizer/{workloads,integrity,domain}; backend/tests/{unit,integration}/

#### Tasks

- [ ] S04.01 Define a validated workload DSL for projections, predicates, time ranges, grouped aggregates and full scans. Include frequencies, freshness needs and concurrency scope. Unknown workload parameters remain explicit.
- [ ] S04.02 Compile the DSL into parameterized analytical queries against a fixed assessment dataset. Validate identifiers and allowlisted operations; do not expose arbitrary SQL, shell execution, external readers or extensions.
- [ ] S04.03 Create canonical baselines for row counts, schema, null/missing behavior, decimal precision, timestamp semantics and duplicate multiplicity.
- [ ] S04.04 Implement streaming canonical-content comparison or equivalent strong verification with counts and semantic checks. File byte hashes identify artifacts but cannot establish cross-format equality.
- [ ] S04.05 Compare workload outputs against the baseline with deterministic ordering where order is irrelevant, multiplicity preserved and explicitly configured numeric tolerances.
- [ ] S04.06 Handle nested and mixed inputs by preserving meaning or rejecting the specific conversion capability. Define cases requiring original-byte retention.
- [ ] S04.07 Create mutation fixtures that intentionally lose records, change precision, collapse duplicates, shift timestamps or coerce identifiers. Ensure integrity checks detect these changes.
- [ ] S04.08 Persist per-check evidence and a capability matrix that later candidate eligibility uses. A failed or incomplete check must never be marked passed.

#### Acceptance gates

1. Valid equivalent representations pass and intentionally corrupted transformations fail with useful reasons.
2. Workload compilation cannot query another dataset or access host files/network paths.
3. Missing workload evidence is distinguishable from a measured performance pass.

#### Verification to perform

Run golden workload comparisons, semantic mutation tests and DSL boundary tests. Demonstrate one successful and one rejected comparison.

#### Required handoff update

Record the workload schema, supported operations, numerical tolerance policy, canonical comparison method and capability exclusions. Advance to S05.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S04.01 after its dependencies are verified.

### S05 Candidate generation and lossless conversion

**Status:** not_started  
**Dependencies:** S04  
**Outcome:** Generate reproducible eligible alternatives while retaining the original setup.  
**Expected code and document areas:** backend/src/data_optimizer/{candidates,conversion}; backend/tests/integration/; docs/candidate-support.md

#### Tasks

- [ ] S05.01 Define a typed candidate configuration and stable hash covering format, codec/level, file-size target, row-group size, partitioning, sorting and fixed execution context.
- [ ] S05.02 Always include the current representation. Add compressed NDJSON, Parquet Snappy and Parquet Zstandard where the reader and semantics permit; record exclusion reasons instead of silently omitting options.
- [ ] S05.03 Implement conversion into new assessment-owned artifact prefixes. Preserve originals and make output publication atomic so interrupted conversions cannot appear complete.
- [ ] S05.04 Generate a bounded set of row-group and layout alternatives guided by available workload columns. Include an unpartitioned candidate and cap partition counts and small-file amplification.
- [ ] S05.05 Use the S04 integrity checks after conversion. Record conversion time, bytes, file counts, peak resources where available and validation status.
- [ ] S05.06 Represent unsupported codecs, nested semantics and reader incompatibilities as explicit candidate outcomes. Do not silently cast or drop fields to make conversion succeed.
- [ ] S05.07 Support idempotent conversion reuse for matching input and candidate fingerprints. Clean temporary partial outputs after failure or cancellation.
- [ ] S05.08 Add CLI conversion and candidate-list commands with output manifests and reproducibility metadata.

#### Acceptance gates

1. The baseline and at least three supported alternatives are materialized and validated on the primary event fixture.
2. Unsupported inputs yield explicit exclusions; originals are unchanged after successful and failed conversions.
3. Repeated conversion requests reuse only compatible verified outputs and do not double-count artifacts.

#### Verification to perform

Run conversion round-trips on fixtures, interrupted-output recovery and already-optimized inputs. Inspect manifests and physical output byte totals.

#### Required handoff update

Record candidate defaults, codec versions, artifact conventions, compatibility restrictions and conversion CLI examples. Advance to S06.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S05.01 after its dependencies are verified.

### S06 Bounded benchmark execution and evidence capture

**Status:** not_started  
**Dependencies:** S05  
**Outcome:** Measure candidate performance fairly inside a constrained execution environment.  
**Expected code and document areas:** backend/src/data_optimizer/{benchmarking,sandbox}; infra/worker/; backend/tests/integration/; docs/benchmark-method.md

#### Tasks

- [ ] S06.01 Implement a benchmark runner in isolated containers or an equivalent enforceable process boundary with CPU, memory, disk, wall-clock and output limits. Document the actual boundary and unsupported isolation controls.
- [ ] S06.02 Disable unnecessary network access, engine extensions, arbitrary paths and executable input. Limit query compilation to S04 workload operations and allowlisted assessment artifacts.
- [ ] S06.03 Run baseline and candidates under the same environment and limits. Randomize/interleave order where useful to reduce drift; record repeat counts and warm-up behavior.
- [ ] S06.04 Measure query timings, conversion cost, CPU, peak memory, physical bytes and scanned bytes only where actually available. Keep missing metrics null with a reason.
- [ ] S06.05 Distinguish warm runs, fresh-process runs and genuine cold-cache runs. Never label OS-cache-cold measurements unless the cache procedure actually controls that cache.
- [ ] S06.06 Record raw timings and compute suitable summaries. Define minimum observations for tail latency; show unvalidated tail behavior when observations are insufficient.
- [ ] S06.07 Make timeouts, memory failures, integrity failures, cancellation and experiment-budget exhaustion explicit results. Never rank failed trials as fast or free.
- [ ] S06.08 Persist environment and workload fingerprints, engine versions, parameters, raw measurements and artifact references. Add a CLI benchmark report suitable for reproduction.

#### Acceptance gates

1. A fixed dataset/workload produces repeatable comparable experiments with honest cache labels and resource provenance.
2. A hanging or excessive-memory workload terminates within configured limits without harming the API or another assessment.
3. Every usable performance result links to passed integrity evidence and raw observations.

#### Verification to perform

Run the baseline/candidate matrix, resource-limit failure cases and repeated measurements. Capture observed variance without hardcoding machine-specific performance expectations.

#### Required handoff update

Record hardware/environment, limits, cache procedure, metric coverage, benchmark commands and any unresolved reliability issue. Advance to S07.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S06.01 after its dependencies are verified.

### S07 Versioned pricing and total cost calculations

**Status:** not_started  
**Dependencies:** S06  
**Outcome:** Calculate auditable costs, space changes and migration economics with explicit assumptions.  
**Expected code and document areas:** backend/src/data_optimizer/{pricing,economics}; backend/tests/unit/; docs/pricing-method.md; examples/

#### Tasks

- [ ] S07.01 Define immutable price snapshots with provider, region, currency, effective date, billing units, source references, minimum sizes/durations and discount assumptions.
- [ ] S07.02 Ship a clearly synthetic offline price fixture for deterministic demos. If adding a real catalog, verify its rates and terms against official provider sources and record retrieval/effective dates; do not relabel fixture rates as live prices.
- [ ] S07.03 Implement itemized storage, query/transform compute, requests, retrieval, network transfer, backups/replicas, maintenance and recurring service costs. Scope shared fixed charges and achievable capacity reductions explicitly.
- [ ] S07.04 Calculate physical bytes for equivalent logical content and retention, including metadata and required copies. Report temporary migration peak space separately.
- [ ] S07.05 Calculate recurring savings, percentage changes, horizon net savings and payback. Handle zero baselines, negative savings, nonpositive payback denominators and unknown inputs without misleading numbers.
- [ ] S07.06 Include migration labor estimates, conversion, temporary copies, transfer and rollback preparation exactly once. Keep forecast assumptions and actual costs in different fields.
- [ ] S07.07 Support scenario ranges for uncertain workload, growth or prices. Show missing inputs and line-item provenance instead of false precision or invented confidence.
- [ ] S07.08 Reproduce the documented synthetic example: $300 vs $180 monthly cost, $300 migration, 2.5 month payback and $1,140 twelve-month net savings.

#### Acceptance gates

1. Every total reconciles to itemized calculations with units and a price snapshot or labeled assumption.
2. Unchanged provisioned capacity does not become cash savings simply because used bytes fall.
3. Known, unknown, zero and negative scenarios return correct outcomes and no fabricated payback.

#### Verification to perform

Run arithmetic/property boundary tests, minimum billing cases, discount scenarios and the synthetic reconciliation example.

#### Required handoff update

Record supported cost components, catalog provenance, unsupported tariffs, rounding rules and example commands. Advance to S08.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S07.01 after its dependencies are verified.

### S08 Evidence based ranking and adaptive experiment selection

**Status:** not_started  
**Dependencies:** S07  
**Outcome:** Produce useful recommendations from measured outcomes and adapt experiment selection to a bounded search budget.  
**Expected code and document areas:** backend/src/data_optimizer/{optimization,recommendations,cli}; backend/tests/; docs/decision-method.md

#### Tasks

- [ ] S08.01 Filter candidates using semantic, compatibility, retention, freshness and measured workload constraints. Explain exclusions and distinguish untested requirements from violated requirements.
- [ ] S08.02 Rank verified feasible options by total cost over the selected horizon including migration; retain the baseline. Compute a compact cost/latency tradeoff set where appropriate.
- [ ] S08.03 Implement outcomes change, keep_current and insufficient_evidence. Define and document a configurable materiality threshold rather than forcing marginal migrations.
- [ ] S08.04 Build a sequential search interface: propose configuration, execute experiment, ingest measurement and propose the next configuration. Use bounded enumeration for tiny spaces and an adaptive optimizer such as Optuna for larger spaces after checking its official current API.
- [ ] S08.05 Persist search seed, history, tested coverage, feasibility and stopping reason. Resume without rerunning successful identical trials; do not infer global optimality.
- [ ] S08.06 Choose promising experiments from accumulated results and uncertainty where supported. Every recommended candidate still requires actual validation; predictions must remain labeled predictions.
- [ ] S08.07 Return machine-readable decisions with evidence IDs, costs, limitations and requirement coverage. Explanation text must reflect these fields rather than edit them.
- [ ] S08.08 Add a single CLI assess command that runs the real profile-to-decision pipeline. Metadata-only/new-startup cases return scenario guidance without historical savings claims.

#### Acceptance gates

1. The pipeline can recommend a beneficial tested change, retain an already-efficient baseline and abstain on missing evidence.
2. Adaptive search responds to trial results and respects trial/time budgets; a test of selection logic does not depend on noisy wall-clock timing.
3. A recommendation identifies the best tested feasible option and never claims unsupported full-cloud performance.

#### Verification to perform

Run three decision-path fixtures, deterministic optimizer logic tests and a real end-to-end CLI assessment with raw evidence.

#### Required handoff update

Record objective settings, materiality defaults, optimizer strategy/version, supported decision paths and a reproducible demo. Advance to S09.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S08.01 after its dependencies are verified.

### S09 Asynchronous assessments and complete API integration

**Status:** not_started  
**Dependencies:** S08  
**Outcome:** Expose the working core through durable asynchronous jobs with correct retries and cancellation.  
**Expected code and document areas:** backend/src/data_optimizer/{api,jobs,db,workers}; backend/migrations/; infra/compose.yaml; backend/tests/integration/

#### Tasks

- [ ] S09.01 Extend migrations for assessments, profiles, candidates, experiments, price snapshots and recommendations with immutable input/requirements references.
- [ ] S09.02 Implement assessment creation returning 202, status/progress reads, recommendation retrieval and cancellation. Define request validation, idempotency keys and conflict responses.
- [ ] S09.03 Run the existing core via Redis/RQ workers using PostgreSQL as the durable business-state record. Use a transactional dispatch/outbox or documented equivalent recovery mechanism to avoid lost jobs.
- [ ] S09.04 Implement stage checkpoints, bounded retries, leases/heartbeats or equivalent stale-job detection. Retrying a stage must not duplicate valid trials or billed work.
- [ ] S09.05 Propagate cancellation to active sandbox processes and prevent queued follow-up stages. Retain trustworthy partial evidence with an explicit stopped status.
- [ ] S09.06 Make progress reflect actual completed work and stage state. Handle needs_input, quota failures, temporary dependency outages and budget-limited partial results.
- [ ] S09.07 Apply tenant ownership to all assessment endpoints and artifacts. Introduce per-tenant active-job quotas and fair worker admission.
- [ ] S09.08 Add structured operational logs/metrics without raw records or credentials. Provide restart/recovery and expired-artifact cleanup commands.

#### Acceptance gates

1. An uploaded dataset can complete a real assessment entirely through the API and worker.
2. Duplicate creation, worker restart and transient retry preserve one logical assessment and reuse verified evidence.
3. Cancellation terminates outstanding work; cross-tenant status/result access is denied.

#### Verification to perform

Run service integration tests plus actual API-to-worker-to-storage flow, restart recovery, idempotency and cancellation exercises.

#### Required handoff update

Record endpoints, worker startup, queue/recovery semantics, quotas, migrations and verified curl examples without secrets. Advance to S10.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S09.01 after its dependencies are verified.

### S10 Complete assessment dashboard

**Status:** not_started  
**Dependencies:** S09  
**Outcome:** Let a user run and understand the real assessment from the browser.  
**Expected code and document areas:** frontend/src/; frontend/tests/; backend/src/data_optimizer/api/; docs/user-flow.md

#### Tasks

- [ ] S10.01 Build project/context intake with progressive requirements and explicit unknown values. Use backend-generated types or a checked contract-sharing approach.
- [ ] S10.02 Build bounded file upload with progress, validation feedback, schema clarification and a metadata-only report option. Explain raw-data retention before transfer.
- [ ] S10.03 Provide workload-template editing and performance/cost assumptions. Validate errors inline and preserve entered inputs when requests fail.
- [ ] S10.04 Implement assessment creation, honest stage progress, cancellation and recovery after page refresh. Use polling initially; add streaming only if justified.
- [ ] S10.05 Build comparison views showing baseline, tested candidates, feasibility reasons, physical bytes, observed performance, itemized costs and migration economics.
- [ ] S10.06 Visually distinguish sample measurements, projections, synthetic pricing and observed production outcomes. Missing values must not render as zero.
- [ ] S10.07 Show keep_current and insufficient_evidence as first-class result flows with useful next actions. Include links to raw evidence summaries and reproducibility metadata.
- [ ] S10.08 Verify keyboard access, readable labels, responsive layout, loading/empty/error states and session/ownership behavior. Test against actual backend services, not only mocked responses.

#### Acceptance gates

1. A browser user can create a project, upload supported data, describe a workload, run an assessment and inspect its measured result.
2. Refresh and cancellation work; server errors and incomplete requirements remain actionable.
3. Display totals match the API and no mock result is presented as a real calculation.

#### Verification to perform

Run frontend checks/build and browser end-to-end flows against local services, including keep_current, missing input and a failed upload. Inspect desktop and narrow layouts.

#### Required handoff update

Record browser verification, routes, accessibility issues, screenshots only if useful and remaining product gaps. Advance to S11.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S10.01 after its dependencies are verified.

### S11 Structured AI intake and grounded explanations

**Status:** not_started  
**Dependencies:** S10  
**Outcome:** Use a language model to reduce user effort while preserving deterministic evidence and a usable offline path.  
**Expected code and document areas:** backend/src/data_optimizer/{intake,llm,explanations}; frontend/src/; backend/tests/; docs/ai-boundaries.md

#### Tasks

- [ ] S11.01 Define a provider-neutral structured interface for extracting proposed requirements and generating questions/explanations. Keep provider credentials server-side and optional for local deterministic workflows.
- [ ] S11.02 Check official provider API documentation at implementation time. Select a supported structured-output API and configure model, timeout, token limits and per-assessment usage budgets.
- [ ] S11.03 Extract proposed fields from the startup description, mark assumptions and ask only consequential missing questions. Let the user confirm inferred requirements before benchmarking.
- [ ] S11.04 Ground recommendation explanations in immutable result/evidence IDs. Render authoritative numbers from calculated fields so generated prose cannot introduce competing financial values.
- [ ] S11.05 Send approved summaries instead of raw customer records. Treat uploaded text and query comments as untrusted data; do not grant tool execution or unrestricted data access.
- [ ] S11.06 Validate responses against typed schemas and allowed candidate/requirement references. Handle invalid output, missing keys, timeout, budget exhaustion and provider unavailability with an honest fallback.
- [ ] S11.07 Expose edit/confirm controls in the dashboard and explain evidence limitations in plain language. Preserve the original user input and accepted requirements version.
- [ ] S11.08 Evaluate extraction, question relevance, fabricated-claim rejection and instruction-like file content with deterministic fixtures; use optional live smoke tests only when credentials are available.

#### Acceptance gates

1. Users can complete the product without an LLM key, and configured AI improves clarification without changing authoritative metrics.
2. Generated unsupported configurations, invented numbers and arbitrary execution requests are rejected or excluded.
3. No raw data or provider secrets appear in prompts by default, browser bundles or logs.

#### Verification to perform

Run schema/failure/grounding tests and an optional budget-limited live API exercise. Record live integration as unverified when credentials are unavailable.

#### Required handoff update

Record provider setup, model configuration, budgets, prompt/schema versions, fallback behavior and actual live verification status. Advance to S12.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S11.01 after its dependencies are verified.

### S12 Reproducible reports and migration handoff exports

**Status:** not_started  
**Dependencies:** S11  
**Outcome:** Export a recommendation that another engineer can inspect, reproduce and apply deliberately.  
**Expected code and document areas:** backend/src/data_optimizer/{reports,migration}; frontend/src/; backend/tests/; docs/templates/

#### Tasks

- [ ] S12.01 Implement a versioned assessment bundle containing requirements, profile coverage, candidate configurations, environment/workload fingerprints, raw result references and price snapshot details.
- [ ] S12.02 Generate readable Markdown/HTML and machine-readable JSON reports from the same calculation data. Avoid adding a PDF dependency unless an actual user requirement justifies it.
- [ ] S12.03 Generate conversion/configuration scripts from validated templates and typed parameters. Quote paths safely and avoid executable interpolation of dataset contents or LLM output.
- [ ] S12.04 Include prerequisites, required reader support, one-time and recurring costs, peak migration space, integrity checks and a canary workload.
- [ ] S12.05 Include rollback triggers and a concrete rollback procedure that retains the source and prior reader configuration. No automatic production changes or deletion.
- [ ] S12.06 Implement tenant-scoped expiring download endpoints and report links in the dashboard. Redact secrets and unnecessary sensitive summaries from export contents.
- [ ] S12.07 Provide a local reproduction command that consumes the bundle and a supplied fixture or user-local source path. Match fingerprints and surface mismatches rather than rerunning incompatible evidence silently.
- [ ] S12.08 Document limitations for sampled benchmarks, missing concurrency evidence, unsupported tariff components and scenario-only recommendations within the relevant report sections.

#### Acceptance gates

1. An engineer can reproduce the core recommendation on a supplied fixture using the exported instructions.
2. JSON and human-readable reports reconcile, and scripts preserve originals and pass integrity checks.
3. Download access respects tenant ownership and bundles contain no credentials or automatic production mutation.

#### Verification to perform

Generate, inspect and reproduce an export; test path quoting and tenant download boundaries. Verify a deliberately mismatched input is rejected.

#### Required handoff update

Record report schemas, download APIs, tested reproduction steps and any user actions required for real migration. Advance to S13.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S12.01 after its dependencies are verified.

### S13 Savings observations and manual reassessment

**Status:** not_started  
**Dependencies:** S12  
**Outcome:** Track adoption and observed outcomes without confusing lower usage with optimization savings.  
**Expected code and document areas:** backend/src/data_optimizer/{observations,economics,api}; backend/migrations/; frontend/src/; backend/tests/

#### Tasks

- [ ] S13.01 Persist versioned migration plans with proposed/planned/deployed/reverted states, adopted configuration, deployment date and original evidence references.
- [ ] S13.02 Accept validated manual observation uploads or entry for retained bytes, logical volume, query mix, access rates, itemized costs, currency and measurement period. Record source and coverage.
- [ ] S13.03 Compute workload-adjusted baseline estimates using the original representation/cost assumptions under comparable observed usage. Label the counterfactual baseline as modeled.
- [ ] S13.04 Show actual costs, projected costs, modeled savings and cumulative migration-adjusted benefit separately. Handle missing bills, currency mismatch, negative outcomes and partial periods.
- [ ] S13.05 Provide a savings history view with clear units, dates and attribution assumptions. Manual input must remain identified as user supplied rather than provider verified.
- [ ] S13.06 Add a deliberate reassess action that creates a new immutable assessment when data/workload/prices change and compares versions without modifying old evidence.
- [ ] S13.07 Calculate drift signals from supported metadata and explain when prior recommendations may be stale. Do not create scheduled external notifications in this sprint.
- [ ] S13.08 Document how to reconcile observations with bills and how to mark a change reverted. Keep input/edit audit history.

#### Acceptance gates

1. Observed cost reductions caused solely by lower usage are not presented as verified optimization savings.
2. Historical evidence remains immutable when assumptions or deployment status change.
3. The dashboard distinguishes projections, user-supplied observations and modeled adjusted savings, including negative outcomes.

#### Verification to perform

Run synthetic growth, lower-usage, missing-bill, negative-savings and revert scenarios; verify the browser totals against API calculations.

#### Required handoff update

Record observation provenance, normalization assumptions, history APIs, supported drift checks and known attribution limits. Advance to S14.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S13.01 after its dependencies are verified.

### S14 Integrated evaluation and local release readiness

**Status:** not_started  
**Dependencies:** S13  
**Outcome:** Deliver a verified local MVP, reproducible demonstration and explicit release limitations.  
**Expected code and document areas:** backend/tests/; frontend/tests/; evaluation/; infra/; README.md; docs/runbooks/; docs/release-readiness.md

#### Tasks

- [ ] S14.01 Create a held-out evaluation matrix spanning categorical, high-cardinality, nested, schema-drift, tiny-file, already-optimized and malformed inputs. Keep dataset-level separation from any tuning data.
- [ ] S14.02 Evaluate recommendation validity, integrity, workload constraint violations, cost reconciliation, search coverage, runtime and resource consumption. Compare against exhaustive testing within a bounded supported candidate space.
- [ ] S14.03 Run complete browser-to-API-to-worker-to-storage-to-report flows, including local profiler import, no-change, insufficient evidence, cancellation and restart recovery.
- [ ] S14.04 Verify authentication mode boundaries, tenant isolation, signed links, worker network/file restrictions, quotas, log redaction, raw-artifact expiration and cleanup recovery.
- [ ] S14.05 Exercise backup/restore for assessment metadata and document storage lifecycle/rollback operations. Complete meaningful CI checks using clean ephemeral dependencies where supported.
- [ ] S14.06 Measure supported upload and workload limits on the recorded hardware. Publish honest operational ceilings and flag unverified tail latency, cloud performance and live-provider gaps.
- [ ] S14.07 Write a clean-start demo, administrator runbook, user guide and release checklist. Document authenticated deployment prerequisites and environment configuration without buying services or publicly deploying.
- [ ] S14.08 Fix issues necessary for the agreed MVP acceptance gates. Record concrete remaining pilot validation and external-service dependencies separately; never invent interviews, customer results or live bill savings.
- [ ] S14.09 Prepare a release summary and final handoff. Mark the MVP implemented only when required local gates pass, and distinguish local release readiness from production/pilot validation.

#### Acceptance gates

1. A fresh environment can run the documented demo and reproduce a complete measured recommendation and report.
2. All required local correctness, isolation and integration gates pass with evidence; unresolved production credentials or pilot checks are explicit.
3. The sprint ledger, task checklists, commands, decisions and continuation state match the repository; the next pointer is COMPLETE_MVP or the actual unfinished gate.

#### Verification to perform

Run make check, make test, make build and make demo plus the integrated/evaluation checks. Record exact commands, results, dataset fingerprints and verified environment.

#### Required handoff update

Write the MVP completion report, actual capabilities, operational ceilings and open external validations. Stop before post-MVP work unless the user selects it.

#### Execution record

- Started:
- Updated:
- Completed:
- Branch and commit if available:
- Delivered behavior:
- Files changed:
- Setup and run commands:
- Verification commands and outcomes:
- Evidence and report paths:
- Decisions and deviations:
- Blockers or unverified checks:
- Resume from: Start S14.01 after its dependencies are verified.

## Completion checklist for every sprint

Before marking the active sprint completed:

- [ ] All required task checkboxes reflect actual delivered behavior.
- [ ] Every acceptance gate has concrete verification evidence.
- [ ] Related integration paths work, not just isolated helpers.
- [ ] Known failures and skipped checks are recorded honestly.
- [ ] Existing data and unrelated user changes are preserved.
- [ ] Runtime/setup instructions match the actual repository.
- [ ] Any changed decisions and interfaces are recorded.
- [ ] The sprint Execution record contains exact commands and outcomes.
- [ ] Ledger, section status, current/next pointers and date agree.
- [ ] A Session history entry records completion or the precise resume point.

This checklist is a reusable template. Copy its result into the active Execution record or a linked sprint report; do not check it globally once and imply it applies forever.

## Decision log

| ID | Date | Decision | Reason and revisit condition |
| --- | --- | --- | --- |
| D001 | 2026-11-01 | Local SPRINT_HANDOFF.md is canonical for progress | The user wants execution from a file path in independent chats |
| D002 | 2026-11-01 | One unfinished MVP sprint per implementation chat | Keeps each result reviewable and continuation explicit |
| D003 | 2026-11-01 | Start with analytical files and measured experiments | Establish a tractable, useful decision pipeline |
| D004 | 2026-11-01 | Keep the language model optional and evidence-grounded | Measurements and calculations must work without provider credentials |
| D005 | 2026-11-01 | React/FastAPI/PostgreSQL/RQ/object storage default stack | Matches web, asynchronous analysis and reproducibility needs |
| D006 | 2026-11-01 | No public deployment or paid provisioning in the MVP execution plan | Local functionality can be verified without customer production access |
| D007 | 2026-11-01 | Distinguish baseline, sample measurements, projections and observations | Prevent unsupported performance and savings claims |
| D008 | 2026-11-01 | Preserve the original architecture as a local reference | Future chats must not depend on the Pages connector |
| D009 | 2026-11-01 | Fourteen dependency-based sprints supersede the earlier calendar outline | Makes individual new-chat assignments concrete |
| D010 | 2026-11-01 | No automatic implementation from this planning session | All implementation starts in a later chat at S01 |
| D011 | 2026-11-02 | Pin Node 24.22.2 and uv 0.13.6 in project-local `.tools` bootstrap | Current Vite requires a supported Node release; local tooling avoids global system changes and makes clean setup reproducible |
| D012 | 2026-11-02 | Build MinIO from the verified source commit in a pinned multi-stage image | No usable published image tag was verified for the selected release; revisit when a supported published image is available |
| D013 | 2026-11-02 | Use `data-optimizer-local` with loopback ports 55432/56379/59000/59001 | Existing unrelated PostgreSQL and Redis containers occupy conventional ports; alternate defaults prevent collision |

Append significant decisions with the affected sprint and a concrete reason. When superseding a decision, preserve its history and link the replacement.

## Current blockers and open questions

No known blocker prevents S02. S01 completed with a local service startup and API readiness check.

| Item | Treatment |
| --- | --- |
| Runtime availability, Docker and local service support | Verified in S01: Python 3.12.3; Node 24.22.2/npm 11.19.1 and uv 0.13.6 installed under `.tools`; Docker 29.1.3 plus legacy Compose 1.29.2; S01 containers healthy on alternate loopback ports. Compose v2 plugin is absent, so Make auto-selects legacy Compose where needed. |
| Exact workload limits and benchmark reliability | Establish configured bounds, then calibrate in S06/S14 |
| LLM provider credentials | Optional for the local MVP; configure a real adapter when available and record unverified live tests |
| Real cloud pricing or customer discounts | Use explicitly synthetic offline fixtures until official rates or customer inputs are verified |
| Customer interviews, representative private data and bills | Pending external pilot validation; never fabricate completion |
| Public hosting, domain and external identity provider | Outside current execution scope; document prerequisites rather than provisioning |

If a new blocker appears, record the affected sprint, exact failing action, evidence, independent work still possible and the smallest action needed to unblock. Do not repeatedly ask already answered questions.

## Session history

### Planning session on 2026-11-01

- User requested detailed sprints runnable in separate chats from a handoff path, with automatic status updates after each sprint.
- Read the original architecture Page and inspected the repository.
- Repository contained no application code and no Git commits at planning time.
- Created this sprint plan, AGENTS.md continuity instructions and docs/ARCHITECTURE.md reference.
- No implementation, runtime installation, application test or production integration was performed.
- Planning verification: Python 3 structural checks passed for 14 sequential sprint sections, 113 unique ordered tasks, dependency order, required acceptance/execution sections, initial statuses and local reference files. These checks validate the plan, not application functionality.
- Next action: execute S01 in a new implementation chat.

### Implementation session on 2026-11-02

- Selected S01 after reading the repository instructions, full handoff, and architecture reference. Confirmed there is no application code or commit history; the only files are the existing planning documents.
- Recorded S01 as `in_progress` before implementation, with a concrete S01.01 resume point.
- Environment inspection: Python 3.12.3, Node 18.19.1, npm 9.2.0, Docker CLI 29.1.3, legacy Docker Compose 1.29.2 and Make 4.3 available; `uv` and Compose plugin absent. Current Vite's runtime requirements exceed system Node. Docker daemon socket access is denied; package installation/network availability is not yet verified. Planned isolated Node 24 LTS and `uv` setup under project `.tools` or `/tmp`, with no global system changes.
- No application implementation or tests have been performed at this checkpoint.
- Resume at S01.01: verify current official tooling guidance and runtime support, then establish locked package environments and scaffold the application.

### S01 completion on 2026-11-02

- User requested GPT-6.1 Sol for planning and GPT-6 Luna for implementation, tests and execution; root coordinated/reviewed the work.
- Completed S01.01–S01.08. The S01 ledger and checkboxes now agree, Current sprint is None and Next sprint is S02.
- Delivered locked Python/npm environments, FastAPI/React foundation, contracts and lifecycle rules, real health/readiness checks, local source-built MinIO Compose service, Make commands and setup/architecture documentation.
- `make setup`, `make check`, `make test` (13 backend, 3 frontend), `make build`, CLI help/version, Compose configuration, actual service health, API `/ready` HTTP 200, Vite proxy HTTP 200 and Chrome 155 browser connectivity/disconnect/recovery checks passed.
- `make demo` returned its expected nonzero not-implemented result; it did not produce placeholder results. The runtime check invoked `make infra-down` without `-v`; that script version suppressed its output, so post-down container absence was not separately inspected. The command preserves named volumes by default.
- No customer, cloud price or production claims were made. Provisional limits remain unmeasured and S02 is the only next sprint.

### Template for subsequent session entries

Copy and fill this template; do not overwrite earlier history.

```text
Date and timezone:
Sprint and session outcome:
Repository/branch:
Delivered behavior and changed paths:
Verification commands and results:
Remaining failures or unverified checks:
Decisions:
Exact resume action or next sprint:
Handoff status reconciled:
```

## Post MVP backlog requiring a new request

These items are not automatically selected by the Next sprint pointer.

| ID | Capability | Prerequisite and scope decision |
| --- | --- | --- |
| P01 | Read-only cloud/database/billing connectors | Select actual providers, scopes, credentials and supported evidence |
| P02 | Access-history-based storage lifecycle advice | Obtain representative access logs; include restore times, retrieval charges and minimum billing |
| P03 | Continuous scheduled reassessment and notifications | Define hosting, user consent, schedules and meaningful-change notification policy |
| P04 | Learned size/latency/cost prediction models | Accumulate diverse consented experiments; evaluate on held-out datasets and verify final choices |
| P05 | Broader database and physical-design comparisons | Add transaction, update, concurrency, durability and operational cost evidence |
| P06 | Assisted copy/canary migration automation | Define production authorization, credentials, safeguards and rollback gates |
| P07 | Paid pilot and savings attribution agreement | Validate willingness to pay using real customers and agreed cost baselines |

## Future chat response contract

After working, give the user a concise message containing the sprint ID, delivered outcome, verification result, any real limitation and the next sprint. Link this handoff. Do not ask the user to reconstruct context or maintain the status themselves.

The canonical next-chat instruction remains:

> Read this handoff, execute the next unfinished sprint, verify it and update this file before finishing.

