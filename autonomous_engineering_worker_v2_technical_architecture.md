# Autonomous Engineering Worker V2
## Technical Architecture, Token-Efficiency, Docker Runtime, Metrics, and Migration Plan

**Status:** Proposed target architecture for review before implementation  
**Prepared:** 2026-09-08  
**Basis:** Current project architecture/lifecycle at checkout `b306a04`, plus the redesign decisions made during review.  
**Primary optimization target:** **cost and time per correctly merged engineering task**, while preserving safety, traceability, and recoverability.

---

# 1. Executive decisions

This document proposes a substantial simplification of the current system without throwing away the useful infrastructure already built.

The product should be treated as an **autonomous engineering delivery worker**, not as a generic simulation of an AI company and not as a user-programmable multi-agent graph engine.

The fixed high-level lifecycle is:

```text
Trello / Linear / Slack / Manual / GitHub events
                    |
                    v
           deterministic intake/router
                    |
          ambiguous natural language?
             |                  |
            no                 yes
             |                  v
             |         cheap Event Interpreter
             |       local Qwen -> cheap fallbacks
             |                  |
             +------------------+
                    |
                    v
             Engineering Task
                    |
                    v
             Developer Harness
          Codex SDK or Claude Agent SDK
                    |
              real worktree
                    |
          edit / test / correct
                    |
                    v
        deterministic validation gates
                    |
                    v
      commit -> push -> create/update PR
                    |
                    v
              WAITING_REVIEW
               no AI running
                    |
             GitHub webhook
                    |
            interpret feedback
          /          |           \
      code fix   architecture    approval
         |          change          |
         v             v            v
   same Developer   Thinker     merge policy
      session       optional        |
         |             |            v
         +------> Developer       MERGED
```

The most important architectural decisions are:

1. **Keep multiple Teams** for parallel execution.
2. **Keep the frontend canvas**, but make it a read-only/live visualization of a fixed lifecycle rather than a workflow-authoring engine.
3. Replace generic Role CRUD with **fixed system role kinds**:
   - `INTERPRETER`
   - `DEVELOPER`
   - `THINKER` (optional)
   - `REVIEWER` (optional)
4. The displayed agent name/avatar remains customizable for fun and usability, e.g. Developer can be displayed as `Sani`.
5. The expensive coding loop should be delegated to a mature coding harness:
   - Codex Python SDK
   - Claude Agent SDK
6. Do not make RAG/repository embeddings part of the normal Developer path. The live task worktree is authoritative.
7. Tests, validation, Git, PR creation, merge gates, status synchronization, retries, and scheduling remain deterministic application code.
8. Local Qwen through Ollama is used for cheap event/message interpretation only, not as the default coding model.
9. Every normal engineering ticket should aim to produce a validated PR.
10. GitHub review feedback should continue the **same logical Developer task/session**, not restart Deliverer -> Thinker -> Executor -> Reviewer.
11. Every AI/local-model invocation and every task phase must produce normalized usage/timing metrics.
12. Budgets must be **cost-aware and cache-aware**, not only raw-token ceilings.

---

# 2. Product scope

## 2.1 Core product promise

The application should automate the operator's real software-development glue work:

- notice eligible work from Trello/Linear/Slack;
- turn it into a durable engineering task;
- let a coding harness inspect the repository and implement the task;
- run project checks;
- commit and push the task branch;
- create/update a GitHub PR;
- wait without consuming AI tokens;
- read PR comments/reviews/check results;
- send actionable code feedback back to the same Developer task;
- repeat until approval/LGTM and all merge gates are satisfied;
- merge automatically when policy authorizes it;
- synchronize the external task tracker;
- preserve complete execution, cost, timing, and audit evidence.

## 2.2 Supported external sources

Keep these as first-class adapters:

- **Trello** — dogfooding/product-development tasks.
- **Linear** — 9-5/company tasks.
- **Slack** — unstructured messages/mentions and requirement updates.
- **GitHub** — repository discovery, branches, PRs, checks, reviews, comments, merge state.
- **Manual** — tasks created from the application UI.

Do not couple the core domain to any tracker-specific field names.

## 2.3 Explicitly not the core MVP

These may remain behind feature flags or legacy routes while migration occurs, but they are not reasons to complicate the core execution architecture:

- arbitrary user-created workflow graphs;
- arbitrary Role creation/deletion;
- mandatory AI Tester stage;
- mandatory internal AI Reviewer stage;
- repository RAG as a required dependency;
- generic agent-to-agent chat;
- Telegram as a core dependency;
- a large incident-management product;
- a full browser terminal product;
- social-style internal task conversations with reactions/thread complexity;
- Kubernetes/distributed brokers before a single-host design is proven;
- multi-tenant public SaaS security in the first dogfood milestone.

---

# 3. What to keep, simplify, disable, and eventually remove

## 3.1 Keep

Keep and strengthen the following existing capabilities:

- PostgreSQL durable state.
- Durable Jobs and scheduler leases.
- Task-specific Git worktrees.
- Repository cache.
- GitHub integration/webhooks.
- Trello integration.
- Linear integration.
- execution policy/tool gateway.
- credential encryption.
- Docker isolation.
- pause/cancel/takeover.
- provider/integration wait states.
- retries with backoff.
- deterministic validation.
- PR publication and merge evidence.
- task event timeline.
- usage records.
- dashboard/task detail UI.
- frontend workflow/canvas rendering technology.

## 3.2 Simplify

Simplify these concepts:

### Roles and Agents

Replace generic Role CRUD + legacy AgentConfig + arbitrary AIAgent configuration with one fixed `TeamAgentProfile` per role kind.

Each profile can contain:

- display name;
- avatar/icon;
- enabled flag where applicable;
- harness/provider;
- model;
- effort/reasoning policy;
- fallback policy;
- budget policy;
- team/repository supplemental instructions.

Core system prompts and permissions are versioned application assets, not fully editable user text.

### Workflow

Replace generic workflow authoring with a fixed domain state machine.

The canvas remains visually useful but reads state from the domain instead of defining execution semantics.

### Task conversation

Keep only what affects execution:

- operator instruction;
- clarification request/answer;
- requirement update;
- pause/takeover note.

Reactions and social-style behaviors are not part of the execution contract.

## 3.3 Disable from the critical path

### Repository RAG

Set repository knowledge retrieval to off for Developer runs by default.

Keep existing indexing code/table migrations temporarily to avoid risky deletion during the harness migration, but:

- stop automatic RAG injection into Developer prompts;
- stop blocking task execution when index is stale/unavailable;
- optionally stop automatic reindexing after merge while feature flag is disabled;
- measure whether any real task is measurably improved by RAG before deciding to reintroduce it.

After a successful dogfood period, pgvector and repository knowledge tables can be removed if unused.

### AI Tester

Normal testing is deterministic command execution. Do not pay an AI to decide whether `pytest`, `npm test`, `npm run check`, build, lint, etc. passed.

A future semantic Tester may exist for tasks that cannot be checked mechanically, but is not default lifecycle infrastructure.

### Internal AI Reviewer

Off by default because GitHub/company review already supplies independent feedback.

Allow enabling it only for high-risk teams/tasks.

## 3.4 Defer or hide

- Telegram notification UI.
- large incident-management UI.
- browser PTY/terminal UI unless actively used.
- CSV export beyond simple metrics export.
- detailed CPU/load dashboards beyond useful worker/model health.
- perfect localization coverage.

Do not immediately delete working code. Hide/feature-flag it first, remove only after the new lifecycle is stable.

---

# 4. Target DDD architecture

The current global `domain/application/infrastructure` folder split should evolve toward **vertical bounded contexts**, so engineering business rules do not spread across role-specific completion handlers and persistence helpers.

Recommended target:

```text
backend/app/
    intake/
        domain/
        application/
        infrastructure/

    engineering/
        domain/
        application/
        infrastructure/

    delivery/
        domain/
        application/
        infrastructure/

    teams/
        domain/
        application/
        infrastructure/

    repositories/
        domain/
        application/
        infrastructure/

    agent_runtime/
        domain/
        application/
        infrastructure/
            codex/
            claude/
            ollama/
            cloud_fallbacks/

    platform/
        persistence/
        scheduling/
        security/
        execution/
        telemetry/
        configuration/
        crypto/

    interfaces/
        http/
        webhooks/
        sse/

    bootstrap/
    main.py
    scheduler_runner.py
```

This can be migrated gradually. Do not perform a giant folder move before behavior is covered by tests.

---

# 5. Bounded contexts and ownership

## 5.1 Intake context

Owns the conversion of external input into semantic commands.

### Domain concepts

- `ExternalEvent`
- `EventSource`
- `EventInterpretation`
- `TaskCandidate`
- `TaskReference`
- `RequirementUpdate`

### Source types

```text
TRELLO
LINEAR
SLACK
GITHUB
MANUAL
```

### Core rule

Structured events are interpreted deterministically whenever possible.

Examples requiring no AI:

- Linear issue assigned to configured user/team and moved into configured AI-ready status.
- Trello card enters configured Ready-for-AI list.
- GitHub check suite passes/fails.
- GitHub formal review state is `APPROVED` or `CHANGES_REQUESTED`.
- PR head SHA changed.
- task explicitly paused/cancelled from UI.

Only ambiguous natural-language content goes to the Event Interpreter.

## 5.2 Engineering context

This is the core business context.

### Aggregate: `EngineeringTask`

Owns:

- task goal;
- source identity;
- Team assignment;
- repository scopes;
- lifecycle status;
- execution stage;
- current Developer session reference;
- budgets;
- latest requirement version;
- current workspace revision;
- current validated revision;
- current delivery/PR state reference;
- blocking reason;
- cumulative metrics summary.

### Related entities/value objects

- `TaskRequirement`
- `TaskRepositoryScope`
- `DeveloperSessionRef`
- `DeveloperCheckpoint`
- `ExecutionBudget`
- `ValidationEvidence`
- `TaskBlocker`
- `TaskMetricsSnapshot`

### Application commands

- `CreateEngineeringTask`
- `AssignTaskToTeam`
- `StartDevelopment`
- `ContinueDevelopment`
- `ApplyRequirementChange`
- `FixReviewFeedback`
- `RunValidation`
- `PauseTask`
- `ResumeTask`
- `CancelTask`
- `TakeOverTask`
- `ReleaseTakeover`

## 5.3 Delivery context

Owns GitHub delivery semantics, not coding.

### Concepts

- `PullRequestRef`
- `PullRequestRevision`
- `ReviewFeedback`
- `ApprovalEvidence`
- `CheckEvidence`
- `MergePolicy`
- `MergeDecision`

### Commands

- `PublishTaskChanges`
- `RefreshPullRequestState`
- `RecordCheckResult`
- `RecordReviewFeedback`
- `EvaluateMergeEligibility`
- `MergePullRequest`
- `SynchronizeTrackerAfterMerge`

## 5.4 Teams context

A Team is a parallel execution lane plus configuration boundary.

### Team owns

- name;
- repository scope;
- enabled state;
- maximum active engineering tasks;
- fixed role profiles;
- execution budgets/defaults;
- auto-merge policy;
- authorized GitHub approval actors/teams;
- source integration mappings.

A Team is not a security tenant in the MVP.

## 5.5 Agent Runtime context

Owns model/harness interaction and normalized telemetry.

The Engineering domain must not know Claude/Codex-specific classes.

Main interfaces:

```python
class DeveloperHarness(Protocol):
    async def start_session(...): ...
    async def resume_session(...): ...
    async def run_turn(...): ...
    async def compact(...): ...
    async def interrupt(...): ...
    async def inspect_session(...): ...

class EventInterpreter(Protocol):
    async def interpret(...): ...
```

Adapters:

```text
CodexDeveloperHarness
ClaudeDeveloperHarness
OllamaEventInterpreter
DeepSeekEventInterpreter
OpenAIEventInterpreter
```

---

# 6. Task lifecycle model

Avoid adding one enum value for every tiny operational condition. Separate **status** from **stage**.

## 6.1 Task status

```text
NEW
ACTIVE
WAITING_EXTERNAL
WAITING_HUMAN
PAUSED
FAILED
CANCELLED
MERGED
```

## 6.2 Execution stage

```text
INTAKE
PLANNING
DEVELOPING
VALIDATING
PUBLISHING
REVIEWING
FIXING
MERGING
COMPLETE
```

The frontend can derive friendly labels such as:

```text
ACTIVE + DEVELOPING       -> Developing
ACTIVE + VALIDATING       -> Validating
WAITING_EXTERNAL + REVIEWING -> Waiting for PR review
WAITING_HUMAN + FIXING    -> Needs human during review fix
```

This is cleaner than maintaining dozens of state values that mix business progress with wait reasons.

## 6.3 Wait reason

Store a separate normalized value:

```text
NONE
GITHUB_REVIEW
GITHUB_CHECKS
PROVIDER_RATE_LIMIT
PROVIDER_OUTAGE
INTEGRATION_FAILURE
MISSING_CONFIGURATION
BUDGET_EXHAUSTED
MISSING_REQUIREMENT
APPROVAL_REQUIRED
MERGE_CONFLICT
MANUAL_TAKEOVER
```

## 6.4 Normal transition

```text
NEW
 -> ACTIVE/INTAKE
 -> ACTIVE/DEVELOPING
 -> ACTIVE/VALIDATING
 -> ACTIVE/PUBLISHING
 -> WAITING_EXTERNAL/REVIEWING
 -> ACTIVE/FIXING            (when actionable feedback arrives)
 -> ACTIVE/VALIDATING
 -> ACTIVE/PUBLISHING        (push same PR branch)
 -> WAITING_EXTERNAL/REVIEWING
 -> ACTIVE/MERGING
 -> MERGED/COMPLETE
```

## 6.5 Thinker branch

Thinker is not a mandatory stage.

Invoke only when:

- high architecture uncertainty;
- cross-service/multi-repository design decision;
- migration/data-safety work;
- Developer explicitly returns `NEEDS_PLAN`;
- review feedback materially invalidates architecture;
- high-risk strategy forces planning.

Then:

```text
ACTIVE/PLANNING
 -> plan artifact
 -> ACTIVE/DEVELOPING or ACTIVE/FIXING
```

---

# 7. Fixed Team role model

Every Team has the same logical role slots.

```text
INTERPRETER  required configuration, but often bypassed by deterministic routing
DEVELOPER    required
THINKER      optional
REVIEWER     optional
```

The role type cannot be added/deleted by users.

## 7.1 Customizable per Team

Allow:

- display name;
- avatar/icon;
- model/harness selection from supported catalog;
- reasoning/effort level within allowed range;
- fallback chain;
- soft/hard budget;
- supplemental instructions;
- enable/disable Thinker/Reviewer.

Do not allow:

- replacing the fixed role's security contract;
- granting arbitrary system capabilities;
- arbitrary workflow edges;
- user-defined result contracts that control merge authority.

## 7.2 Prompt ownership

Use three instruction layers:

```text
1. System role prompt         owned/versioned by product
2. Team engineering rules    configurable, bounded
3. Repository instructions   e.g. AGENTS.md/CLAUDE.md/project docs
```

Version the product role prompt. Store `prompt_version` on every run for auditability.

---

# 8. Model and harness strategy

Model IDs and prices change. Do not permanently hard-code catalogs into business logic. Store current defaults in configuration, refresh supported model catalogs where APIs allow it, and persist the exact model actually used on every run.

The recommendations below are the starting defaults verified on 2026-09-08.

## 8.1 Developer default: Codex

### Harness

Use the **OpenAI Codex Python SDK** (`openai-codex`) as the first production Developer adapter.

Why:

- Python SDK is stable and matches the existing Python backend.
- It supports persistent Threads and `thread_resume`.
- It exposes a workspace-write sandbox mode.
- It returns per-turn usage and duration.
- Threads support explicit `compact()`.
- The Codex harness is specifically optimized for repeated coding/tool work and context/cache efficiency.

### Default model preset

For normal engineering tasks:

```text
model: gpt-5.6-terra
effort: medium or high
multi-agent/ultra: disabled
```

Use `medium` for small/normal tasks and `high` for uncertain normal tasks.

### Escalation model

For genuinely complex tasks:

```text
model: gpt-5.6-sol
effort: high
```

`max` should be exceptional, not the default.

Do not default to GPT-6 Astra merely because it exists; it is substantially more expensive and the system should first prove that Terra/Sol fail the task class.

### Why Terra rather than Luna for Developer

Luna is excellent for cost-sensitive general workloads but the Developer is the one place where capability can reduce total cost by avoiding rework. Do not optimize the most important engineering role down to the cheapest model by default.

## 8.2 Claude Developer preset

Implement a second Developer adapter using **Claude Agent SDK**.

Default:

```text
model: claude-sonnet-5
effort: medium/high according to task strategy
```

Escalation:

```text
model: claude-opus-5
effort: high
```

Sonnet 5 is the cost/capability choice for everyday coding. Opus 5 is for complex long-horizon agentic coding.

The Team configuration may choose Claude as its primary Developer instead of Codex.

## 8.3 Developer fallback policy

Do not silently switch harnesses in the middle of a task without state reconstruction.

### Provider/model fallback levels

1. Retry transient failure inside the same harness with bounded backoff.
2. Escalate model inside the same harness if policy allows.
3. If provider is unavailable long enough, move task to `WAITING_EXTERNAL` with provider reason.
4. Optional cross-harness failover may be performed only by creating a new session from a compact `DeveloperCheckpoint` and the existing worktree/diff.

Cross-harness state is not portable conversation state.

Never pretend a Claude session can be resumed as a Codex thread or vice versa.

## 8.4 Interpreter default: Ollama + Qwen

Run Ollama as a separate Docker Compose service.

Recommended first model:

```text
qwen3:4b
```

The Ollama model artifact is currently about 2.5 GB. For classification/routing, this is a better fit than loading a 19 GB coding model.

Use non-thinking mode for ordinary interpretation.

Interpreter jobs should be tiny and structured:

- maximum app-provided input approximately 2-4K tokens;
- expected output under 300-500 tokens;
- strict JSON schema;
- no repository source;
- no RAG;
- no full task history;
- no shell/file tools.

If host resources are comfortable and evals show a meaningful quality improvement, allow `qwen3:8b` as an optional interpreter model.

## 8.5 Interpreter cloud fallbacks

Recommended chain:

```text
1. Ollama / qwen3:4b / non-thinking
2. DeepSeek V4 Flash / non-thinking
3. GPT-5.6 Luna / none or low reasoning
4. NEEDS_HUMAN if classification remains unsafe/ambiguous
```

Do not make a large Developer model the routine fallback for simple message classification.

## 8.6 Thinker

Only invoked when justified.

Recommended presets:

```text
Codex:  gpt-5.6-sol / high
Claude: claude-opus-5 / high
```

Thinker produces a compact durable plan/decision artifact. It does not edit source by default.

## 8.7 Reviewer

Default: disabled.

If enabled for high-risk teams, use a model no stronger than needed:

```text
gpt-5.6-terra high
or
claude-sonnet-5 high
```

Reviewer is read-only and evaluates current diff + acceptance criteria + validation evidence.

---

# 9. Event Interpreter contract

The Interpreter is a classifier/router, not an orchestrator with broad authority.

## 9.1 Input envelope

```json
{
  "event_id": "...",
  "source": "GITHUB|SLACK|TRELLO|LINEAR",
  "event_type": "...",
  "actor": {
    "id": "...",
    "display_name": "...",
    "is_authorized_reviewer": true
  },
  "message": "raw natural language text",
  "task": {
    "id": "...",
    "title": "...",
    "status": "...",
    "stage": "..."
  },
  "pull_request": {
    "number": 123,
    "head_sha": "..."
  },
  "recent_related_messages": []
}
```

Omit fields that are irrelevant.

## 9.2 Output schema

```json
{
  "classification": "CODE_CHANGE_REQUEST",
  "confidence": 0.96,
  "task_relation": "EXISTING_TASK",
  "requires_developer": true,
  "requires_thinker": false,
  "approval_intent": false,
  "summary": "Reviewer requests reuse of existing helper.",
  "reason": "Short explanation for audit, not chain-of-thought."
}
```

Allowed classifications should be fixed, e.g.:

```text
ENGINEERING_TASK
REQUIREMENT_CHANGE
CODE_CHANGE_REQUEST
ARCHITECTURAL_CHANGE
QUESTION
INFORMATIONAL
APPROVAL
MERGE_REQUEST
METADATA_REQUEST
NOT_RELEVANT
NEEDS_HUMAN
```

## 9.3 Deterministic parser before model

Examples of deterministic handling:

- formal GitHub `APPROVED` review event -> approval evidence;
- GitHub `CHANGES_REQUESTED` -> code/review attention;
- check suite status -> check evidence;
- `/merge` exact command from authorized actor -> merge request;
- configured Trello list transition -> task eligibility;
- configured Linear state/assignment -> task eligibility.

Do not use a naive substring `"lgtm" in text` rule.

A message such as `"I don't think this is LGTM"` must not approve a PR.

For free-text approval phrases, require either:

- exact bounded parser patterns with negation checks; or
- Interpreter classification with high confidence;

and always verify actor authorization and current PR SHA before merge.

---

# 10. Developer harness abstraction

The application should no longer implement a large custom model/file/tool conversation loop as the primary coding runtime.

The harness owns:

- source discovery;
- file reads;
- edits;
- shell commands;
- test iteration;
- model/tool turns;
- harness-specific context handling;
- harness-specific compaction.

The platform owns:

- lifecycle;
- workspace creation;
- credentials;
- security boundary;
- task budgets;
- orchestration;
- PR delivery;
- merge authority;
- persistent normalized metrics;
- wait/recovery states.

## 10.1 Normalized harness interface

Example target interface:

```python
@dataclass(frozen=True)
class DeveloperSessionSpec:
    task_id: UUID
    team_id: UUID
    repository_paths: list[str]
    primary_repository_path: str
    system_prompt_version: str
    team_instructions: str | None
    model: str
    effort: str
    max_budget_usd: Decimal | None

@dataclass(frozen=True)
class DeveloperSessionRef:
    harness: Literal["codex", "claude"]
    external_session_id: str
    state_location: str | None

@dataclass(frozen=True)
class DeveloperTurnRequest:
    session: DeveloperSessionRef
    objective: str
    mode: Literal["IMPLEMENT", "FIX_REVIEW", "REQUIREMENT_CHANGE", "RECOVER"]
    review_feedback: list[ReviewFeedback] = field(default_factory=list)
    checkpoint: DeveloperCheckpoint | None = None

class DeveloperHarness(Protocol):
    async def start_session(self, spec: DeveloperSessionSpec) -> DeveloperSessionRef: ...
    async def run_turn(self, request: DeveloperTurnRequest) -> DeveloperTurnResult: ...
    async def resume_session(self, ref: DeveloperSessionRef) -> None: ...
    async def compact(self, ref: DeveloperSessionRef) -> CompactionResult: ...
    async def interrupt(self, ref: DeveloperSessionRef) -> None: ...
```

## 10.2 Normalized events

Both adapters should emit a small common event stream:

```text
SESSION_STARTED
MODEL_TURN_STARTED
MODEL_TURN_COMPLETED
TOOL_STARTED
TOOL_COMPLETED
FILE_CHANGED
VALIDATION_COMMAND_OBSERVED
COMPACTION_STARTED
COMPACTION_COMPLETED
CHECKPOINT_CREATED
SESSION_BLOCKED
SESSION_COMPLETED
```

Store metadata, not unlimited source bodies.

## 10.3 Developer result contract

```json
{
  "status": "IMPLEMENTED",
  "summary": "Implemented ...",
  "files_changed": ["..."],
  "tests_run": ["..."],
  "known_issues": [],
  "needs_human": false,
  "needs_thinker": false
}
```

Do not trust this result alone. The application verifies actual Git diff and validation results.

---

# 11. Session persistence and review continuation

This is essential for token efficiency.

## 11.1 One logical Developer session per task/harness

Persist:

```text
task_id
harness
external_session_id
model
model_provider
created_at
last_resumed_at
last_completed_at
workspace_revision
last_compaction_at
status
```

When GitHub feedback arrives:

```text
review comment
 -> classify
 -> actionable code fix
 -> locate DeveloperSessionRef
 -> resume same harness session
 -> send only the new feedback + small execution envelope
```

Do not regenerate the full original role briefing and repository context.

## 11.2 Harness state in Docker

Developer runner containers should be disposable while their state is durable.

Persist:

- task worktree in shared workspace volume;
- Codex state under a mounted `CODEX_HOME` path;
- Claude session state under a mounted Claude config/session path or supported session-store mechanism;
- platform-level DeveloperCheckpoint in PostgreSQL.

The runner exits while waiting for GitHub.

On feedback, a new runner container mounts the same task worktree and harness state, then resumes the session.

## 11.3 Platform checkpoint

Always keep a provider-neutral fallback checkpoint even when harness resume works.

Example:

```json
{
  "goal": "...",
  "requirement_version": 4,
  "important_decisions": ["..."],
  "important_files": ["..."],
  "workspace_head": "...",
  "diff_summary": "...",
  "last_validation": {
    "status": "PASS",
    "commands": ["..."]
  },
  "unresolved_issue": null
}
```

This is used when:

- provider session cannot resume;
- switching harnesses;
- old session is intentionally retired;
- recovery after corruption;
- context is deliberately reset.

It must remain compact. It is not a copy of the conversation transcript.

---

# 12. Docker architecture

The product already runs through Docker Compose. Keep that operating model.

## 12.1 Long-running services

Recommended local/production logical services:

```text
caddy            production only
frontend
backend
scheduler
postgres
ollama
```

Developer execution is not a permanently running AI container. The scheduler/runner transport launches short-lived **developer-runner containers** when work is active.

## 12.2 Recommended Compose topology

```text
Browser
  |
Caddy (production)
  |
  +--> frontend
  +--> backend
         |
         +--> postgres
         +--> ollama
         +--> external APIs

scheduler
  |
  +--> postgres
  +--> Docker execution transport
          |
          +--> developer-runner(task A)
          +--> developer-runner(task B)
```

## 12.3 Volumes

Recommended persistent volumes:

```text
postgres_data
repository_cache
task_workspaces
harness_state
ollama_models
backup_data (optional)
```

Suggested mount semantics:

```text
backend:
  task_workspaces: controlled access if task detail/workspace operations require it

scheduler:
  task_workspaces
  repository_cache
  harness_state

ollama:
  ollama_models -> /root/.ollama

developer-runner:
  task-specific worktree only
  task-specific harness-state subdirectory only
```

Do not mount the entire host filesystem into Developer runners.

## 12.4 Ollama service

Conceptual Compose configuration:

```yaml
ollama:
  image: ollama/ollama:<PINNED_VERSION>
  restart: unless-stopped
  volumes:
    - ollama_models:/root/.ollama
  expose:
    - "11434"
  networks:
    - app_private
```

Do not expose port 11434 publicly.

Backend/scheduler access it by Docker DNS:

```text
http://ollama:11434/api
```

Initial model bootstrap:

```bash
docker compose exec ollama ollama pull qwen3:4b
```

Pin the Ollama image version after validation. Do not rely forever on `latest` in production.

## 12.5 Ollama resource policy

Interpreter traffic is low and short.

Starting policy:

- one local model loaded;
- low request concurrency;
- app-level input cap;
- no repository context;
- non-thinking mode;
- strict timeouts;
- health check based on API/version/model list rather than an AI generation.

For a small CPU-only Hetzner host, `qwen3:4b` is the intended starting model. Measure latency before considering 8B.

## 12.6 Developer runner image

Build a dedicated image containing:

- Python runtime;
- `openai-codex` pinned version;
- `claude-agent-sdk` pinned version;
- matching required CLI/runtime dependencies;
- git;
- common build tools required by permitted project types;
- platform runner entrypoint;
- no long-lived app database credentials where avoidable.

Project-specific package dependencies remain in the project/workspace and are installed only according to execution policy.

Pin harness versions. Record them in every Developer run.

## 12.7 Docker socket authority

Only the scheduler/execution transport receives Docker socket access.

- backend API does not receive the Docker socket;
- frontend never receives it;
- Ollama never receives it;
- Developer runner never receives it.

The scheduler is trusted infrastructure.

## 12.8 Future scale abstraction

Keep a port:

```python
class ExecutionTransport(Protocol):
    async def launch(run_spec: RunSpec) -> RunHandle: ...
    async def cancel(run_id: UUID) -> None: ...
```

Implement today:

```text
DockerExecutionTransport
```

Future:

```text
RemoteWorkerTransport
KubernetesTransport
NomadTransport
```

Do not introduce them until required.

---

# 13. Repository/workspace behavior

## 13.1 Worktree is authoritative

The task worktree is the source of truth for coding.

Never let:

- stale RAG index;
- old task memory;
- old plan;
- old PR diff;

silently override current files.

## 13.2 Workspace lifecycle

```text
Task created
 -> resolve repository
 -> ensure shared cache fetched
 -> create task worktree + branch
 -> Developer operates only in that worktree
 -> validation operates on same worktree
 -> deterministic publisher commits/pushes
 -> PR references task branch
 -> review fixes reuse same worktree
 -> after merge and retention period, archive/remove worktree
```

## 13.3 Parallel tasks

Separate tasks get separate worktrees/branches.

Multiple Teams may work in parallel.

Global/repository locks are used only for shared Git cache operations and sensitive publication operations, not for all Developer execution.

## 13.4 Default branch movement

Do not silently rebase dirty task worktrees whenever `main/master` moves.

Before publication/update, fetch remote and detect divergence.

If conflict resolution is required:

- route to Developer with explicit conflict context if policy permits; or
- `WAITING_HUMAN` for unsafe/confusing conflicts.

---

# 14. Trello, Linear, Slack, and GitHub flows

## 14.1 Trello

Configured board/list mapping remains supported.

Example:

```text
Backlog
Ready for AI
In Progress
In Review
Done
Blocked
```

When card enters `Ready for AI`:

1. deduplicate card/event;
2. create/update durable task snapshot;
3. resolve Team/repository mapping;
4. queue normal engineering task;
5. move external card according to configured semantic status changes.

Trello is not just temporary test infrastructure; it remains a supported task source.

## 14.2 Linear

Use structured webhook fields first.

If issue is assigned to configured operator/team and status is eligible:

```text
webhook -> deterministic eligibility -> task
```

No LLM call is needed to decide whether an explicit Linear assignment is work.

Natural-language descriptions are passed to Developer as the requirement, not pre-explained by another premium model.

## 14.3 Slack

Add a Slack adapter with event deduplication.

Possible interpretation results:

```text
ENGINEERING_TASK
REQUIREMENT_CHANGE
QUESTION
INFORMATIONAL
NOT_RELEVANT
NEEDS_HUMAN
```

Task relation should use explicit references first:

- issue key;
- PR link/number;
- Trello/Linear link;
- known task ID;
- Slack thread relation stored by the app.

Do not guess a relation to an existing task at low confidence.

## 14.4 GitHub

Treat GitHub as authoritative for:

- PR number/head SHA;
- review states;
- check states;
- remote merge result.

Persist every webhook delivery ID for deduplication.

---

# 15. Development -> validation -> PR flow

## 15.1 Start development

The scheduler creates one `DEVELOPER_TURN` job.

It launches a Developer runner with:

- task ID;
- Team configuration snapshot;
- task worktree path;
- requirement version;
- harness adapter;
- model/effort;
- budget;
- scoped credentials;
- execution policy.

## 15.2 Developer prompt

Keep the initial platform prompt compact:

- exact ticket title/description;
- acceptance criteria if explicitly present;
- repository path;
- team/repository instructions;
- requirement version;
- instruction to inspect source and implement/test;
- no bulk repository RAG chunks;
- no giant historical task event list.

The harness discovers code on demand.

## 15.3 Developer completion

Application inspects:

- actual Git status;
- actual changed files;
- workspace revision/fingerprint;
- harness result;
- observed test commands.

If no useful change and task requires change, do not treat a cheerful model response as success.

## 15.4 Deterministic validation

Validation profiles are repository configuration, e.g.:

```yaml
validation:
  quick:
    - npm run check
  full:
    - make check
    - npm run test:e2e
```

The Team/task strategy chooses a profile.

Validation output policy:

- store exit code;
- store duration;
- store bounded stdout/stderr tails;
- store artifact references if needed;
- do not repeatedly feed full successful logs to models.

If validation fails:

```text
VALIDATION_FAILED
 -> resume same Developer session
 -> send command + concise failure tail + relevant structured metadata
```

Do not start a new Thinker by default.

## 15.5 Publication

Once required validation passes:

1. verify current workspace fingerprint is the validated fingerprint;
2. generate deterministic commit metadata;
3. commit;
4. push task branch;
5. find existing PR or create one;
6. set task `WAITING_EXTERNAL/REVIEWING`;
7. release runner capacity.

PR description may be generated from task + diff through deterministic template and, if desired, a cheap summarization call. It should not require a full Developer role cycle.

---

# 16. PR review loop and automatic merge

## 16.1 Waiting is free

While waiting for GitHub:

- no Developer container remains active;
- no model polling;
- no periodic AI review;
- scheduler job slot is free.

GitHub webhook/reconciliation wakes the task.

## 16.2 Review feedback

For each new review/comment:

1. deduplicate event;
2. record actor, PR, head SHA, comment/review identity;
3. deterministic parse if formal GitHub state or exact command;
4. otherwise Event Interpreter;
5. route only the required work.

### Code change

```text
CODE_CHANGE_REQUEST
 -> ACTIVE/FIXING
 -> resume same Developer session
 -> provide new feedback
 -> validate
 -> push same branch
 -> WAITING_REVIEW
```

### Architecture change

```text
ARCHITECTURAL_CHANGE
 -> optional Thinker
 -> compact revised plan
 -> resume Developer
```

### Question/information

Do not automatically start a coding lifecycle.

## 16.3 Approval/LGTM evidence

Store approval evidence with:

```text
source
actor_id
actor_name
review/comment id
PR number
approved_head_sha
timestamp
interpretation method
confidence if model-derived
```

## 16.4 Merge gate

Auto-merge only if all applicable rules pass:

```text
PR exists
current GitHub HEAD == expected task PR HEAD
current HEAD == validated revision/commit
required CI checks pass
no active CHANGES_REQUESTED/blocking review
approval/LGTM applies to current HEAD
approval actor is authorized
no merge conflict
Task is not paused/taken over/cancelled
Team auto-merge policy enabled
repository policy permits auto-merge
```

A new Developer push invalidates approval evidence tied to an older SHA unless repository policy explicitly says otherwise.

Merge is performed by deterministic Delivery code, never directly because an LLM emitted `MERGE`.

---

# 17. Token and cost optimization architecture

This section is mandatory, not optional tuning.

## 17.1 Primary rules

1. One expensive Developer harness session per task.
2. Resume instead of rebuilding context.
3. Use harness-native compaction.
4. No default repository RAG injection.
5. No mandatory Thinker/Tester/Reviewer pipeline.
6. Cheap/local Interpreter gets tiny context.
7. Deterministic operations use zero model tokens.
8. Successful tool/log output is aggressively bounded.
9. Waiting states consume zero model tokens.
10. Provider/harness subagents are disabled by default.
11. Cache tokens are tracked separately from uncached input.
12. Budgets are cost-aware.

## 17.2 Never send to Interpreter

- repository file bodies;
- source map;
- RAG chunks;
- full task event history;
- complete PR diff unless the message cannot be understood otherwise;
- validation logs;
- Developer transcript.

## 17.3 Developer context

The app sends only stable task instructions and new external information.

The harness handles source discovery.

On review continuation send:

```text
new review feedback
current task requirement version
any requirement change
current workspace/PR identity
```

Do not resend all old feedback that has already been resolved.

## 17.4 Log compaction

Command result storage and model feedback should distinguish:

```text
PASS:
  command
  exit_code
  duration
  short final summary

FAIL:
  command
  exit_code
  bounded failure tail
  optionally extracted error lines
  full log saved as artifact/reference if needed
```

A 10 MB build log must never become retained model context.

## 17.5 Harness compaction

### Codex

Use thread-native compaction based on normalized policy/telemetry.

Do not force an enormous 1M active context simply because the model supports it. Larger active context increases cost and can reduce focus.

Suggested starting rule:

- let Codex native auto-compaction operate;
- additionally compact before a review-fix continuation if the previous implementation turn was very long;
- compact when platform-observed context/usage anomaly thresholds are exceeded;
- record compaction count/time.

### Claude

Use Claude Agent SDK/Claude Code session context management and platform-supported compaction behavior.

Do not repeatedly call expensive context-inspection APIs merely to draw dashboard gauges. Track usage from normal execution events/results.

## 17.6 Prompt caching

Preserve stable prefixes:

- system role prompt;
- team rules;
- repository static instructions;

Avoid adding timestamps/random IDs to the beginning of prompts if that destroys provider cache locality.

Store cache read/write token counts separately when available.

## 17.7 Raw tokens vs billable cost

Do not make the old mistake of treating all input tokens as economically equal.

Persist separately:

```text
input_tokens
output_tokens
reasoning_tokens
cache_read_input_tokens
cache_write_input_tokens
uncached_input_tokens
```

Budget decisions should prefer estimated/known USD cost while still using token anomalies as safety signals.

## 17.8 Starting budget policy

These are **dogfood starting guardrails**, not universal truth. Tune them from real task data.

### Interpreter

```text
max app input: ~4K tokens
max output: 500 tokens
max local attempts: 1
max cloud fallbacks: 2
timeout: short
```

### FAST engineering task

```text
soft cost alert: $0.50
hard task budget: $2.00
expected: one implementation turn + bounded fixes
```

### STANDARD task

```text
soft cost alert: $2.00
hard task budget: $5.00
```

### HIGH_ASSURANCE/COMPLEX

```text
soft cost alert: $5.00
hard task budget: $15.00
Thinker/Reviewer may be enabled
```

A user may explicitly grant a one-time extension.

Do not silently reset lifetime usage on reopen.

For Claude, use SDK/provider budget support when reliable **in addition to** app-side accounting. For every provider, application budget remains authoritative.

## 17.9 Anomaly rules

Alert/stop for investigation when, for example:

- small task reaches 100K+ non-cached-equivalent tokens before first useful edit;
- repeated identical reads/logs occur;
- more than 3 consecutive Developer turns make no workspace progress;
- review-fix cycle consumes more than original implementation without meaningful diff;
- a single Interpreter request exceeds configured context envelope;
- task cost exceeds strategy budget;
- provider call count grows unexpectedly.

---

# 18. Usage, cost, and timing persistence

Metrics must be based on durable raw events plus derived aggregates.

Do not store only a task-level total because it prevents diagnosing where money/time disappeared.

## 18.1 `ai_runs`

One normalized row per harness/local/cloud model execution unit.

Suggested fields:

```text
id UUID PK
task_id UUID nullable
job_id UUID nullable
team_id UUID
role_kind enum
harness enum nullable
provider enum
model text
model_version/snapshot text nullable
session_id text nullable
turn_id text nullable
purpose enum
started_at timestamptz
completed_at timestamptz
duration_ms bigint
provider_duration_ms bigint nullable
status enum
error_class text nullable
retry_index int
prompt_version text nullable
input_tokens bigint nullable
output_tokens bigint nullable
reasoning_tokens bigint nullable
cache_read_input_tokens bigint nullable
cache_write_input_tokens bigint nullable
provider_reported_cost_usd numeric nullable
calculated_cost_usd numeric nullable
pricing_version_id UUID nullable
usage_complete boolean
metadata jsonb bounded
```

Purposes:

```text
INTERPRET_EVENT
DEVELOP_TASK
FIX_REVIEW
FIX_VALIDATION
THINK
REVIEW
SUMMARIZE_PR
OTHER
```

## 18.2 `local_model_runs`

Can use the same `ai_runs` table with `provider=OLLAMA`, but preserve Ollama-specific metrics in a child/JSON structure:

```text
prompt_eval_count
prompt_eval_duration_ns
eval_count
eval_duration_ns
load_duration_ns
total_duration_ns
```

Ollama exposes these usage/performance counts, so local inference is still measurable even though API dollar cost is zero.

## 18.3 `developer_sessions`

```text
id UUID PK
task_id UUID
team_id UUID
harness enum
external_session_id text
provider text
initial_model text
current_model text
state_path text nullable
status enum
created_at
last_resumed_at
completed_at
compaction_count int
turn_count int
cumulative_input_tokens bigint
cumulative_output_tokens bigint
cumulative_cost_usd numeric
last_workspace_revision text
prompt_version text
harness_version text
```

## 18.4 `task_phase_runs`

Track stage timing explicitly.

```text
id
task_id
stage
started_at
ended_at
duration_ms
end_reason
job_id nullable
```

This makes it possible to split total elapsed time into actual work vs waiting.

## 18.5 `validation_runs`

```text
id
task_id
workspace_revision
profile
command
started_at
completed_at
duration_ms
exit_code
status
stdout_tail
stderr_tail
full_log_ref nullable
```

## 18.6 `review_cycles`

```text
id
task_id
pr_number
cycle_number
head_sha
started_at
feedback_received_at
fix_started_at
fix_pushed_at
approval_at
feedback_count
code_change_count
architecture_change_count
status
```

## 18.7 `pricing_catalog`

Do not hard-code price calculations in scattered code.

```text
id
provider
model
valid_from
valid_to nullable
input_per_million
cached_input_per_million nullable
cache_write_per_million nullable
output_per_million
notes
source
```

Store the pricing version used for every calculated cost.

Provider-reported cost and app-calculated cost are separate fields because SDK/provider cost reporting can be incomplete or buggy.

## 18.8 Task aggregate metrics

Maintain a query/read model; do not update dozens of counters manually in domain logic if they can be derived.

Useful task metrics:

```text
wall_clock_ms
automation_active_ms
queue_wait_ms
developer_active_ms
provider_ms
interpreter_ms
validation_ms
github_wait_ms
human_wait_ms
time_to_first_edit_ms
time_to_first_validation_ms
time_to_first_pr_ms
time_to_merge_ms
input_tokens
output_tokens
cache_read_tokens
cache_write_tokens
calculated_cost_usd
provider_reported_cost_usd
developer_turns
interpreter_calls
compactions
validation_runs
review_cycles
retries
human_interventions
files_changed
lines_added
lines_deleted
final_result
```

---

# 19. Dashboard and frontend

## 19.1 Preserve the canvas

The visual Team canvas remains a major product feature.

Change its semantics:

```text
OLD: canvas defines arbitrary workflow behavior
NEW: canvas visualizes fixed workflow behavior
```

Suggested nodes:

```text
Intake
Interpreter
Thinker (optional, faded when inactive/disabled)
Developer
Validation
Reviewer (optional)
PR / GitHub Review
Merge
```

The UI may visually preserve the existing style/layout.

## 19.2 Agent display

Each active role node can show:

```text
Display name: Sani
Role: Developer
Harness: Codex
Model: GPT-5.6 Terra
Current task: TRELLO-123
Stage: Developing
Elapsed active time: 04:32
Task cost: $0.18
Tokens: 18.2K input / 2.1K output
```

Renaming `Developer` to `Sani` changes display identity only; it does not change the system role contract.

## 19.3 Team overview

Per Team show:

- active tasks;
- queued tasks;
- waiting PRs;
- ready-to-merge tasks;
- needs-human count;
- current Developer utilization;
- today's cost;
- 7-day cost;
- completion/merge rate.

## 19.4 Global dashboard KPIs

Primary cards:

```text
Active engineering tasks
Waiting for GitHub
Needs human
Ready to merge
Merged today / 7d / 30d
AI cost today / 7d / 30d
Tokens today
Autonomy rate
Median time to PR
Median time to merge
```

Useful charts/tables:

- cost by Team;
- cost by role;
- cost by provider/model;
- successful merged tasks by source;
- tokens per merged task distribution;
- cost per merged task distribution;
- review cycles per task;
- top expensive tasks;
- blocked tasks;
- provider failures/rate limits.

## 19.5 Task detail metrics

Task detail must clearly show:

```text
Total elapsed
Active automation time
Waiting GitHub time
Human wait time
Developer time
Validation time
Total cost
Developer cost
Interpreter cost
Input/output/cache tokens
Developer turns
Compactions
Review cycles
Validation history
PR/head SHA
Current approval SHA
```

Timeline should answer:

> Where did this task spend time and money?

## 19.6 Cost visibility rules

Never display missing cost as `$0.00`.

Use:

```text
$0.34 calculated
provider cost unavailable
usage incomplete
```

when appropriate.

---

# 20. Job scheduler redesign

Keep Jobs, but make them **execution units**, not simulated employees.

Recommended job kinds:

```text
INTERPRET_EVENT
DEVELOPER_TURN
RUN_VALIDATION
PUBLISH_PR
PROCESS_GITHUB_EVENT
MERGE_PR
SYNC_TRACKER
RECONCILE_TASK
CLEANUP_WORKSPACE
```

Thinker/Reviewer can be specialized AI run purposes invoked from a generic AI job or explicit job kinds if operationally useful, but the domain does not require one job class per Role result.

## 20.1 One Developer Job != one model API call

`DEVELOPER_TURN` launches the harness and lets it perform its internal coding/tool loop.

Do not store every harness model turn as a separately scheduled Job.

Store each internal model turn in `ai_runs`/telemetry instead.

## 20.2 Concurrency

Two levels:

```text
Team.max_active_tasks
Global provider concurrency governor
```

Default:

- Team concurrency = 1 during initial dogfood;
- multiple Teams provide parallel work;
- increase per-Team concurrency only after rate/cost behavior is measured.

Provider governor considers:

- active expensive Developer turns;
- estimated prompt size;
- TPM/RPM limits;
- provider health;
- current spend rate.

Local Qwen classification should not consume an expensive-provider slot.

---

# 21. Failure, retry, and recovery

## 21.1 Retry classification

Retry only transient failures:

```text
provider overload
network timeout
temporary GitHub failure
temporary tracker failure
runner infrastructure failure
```

Do not automatically retry:

```text
invalid model configuration
permission denied
missing requirement
hard budget reached
merge conflict requiring decision
repeated no-progress coding loop
schema/programming bug
```

## 21.2 Provider outage

```text
Developer provider unavailable
 -> preserve worktree
 -> preserve harness session reference
 -> WAITING_EXTERNAL / PROVIDER_OUTAGE
 -> retry according to backoff/circuit policy
```

Do not start another planning cycle.

## 21.3 Runner crash

The workspace and harness state are persistent.

On expired lease:

1. mark run interrupted;
2. inspect whether subprocess/container still exists;
3. preserve partial workspace changes;
4. resume same Developer session if safe;
5. otherwise restore from platform checkpoint.

## 21.4 No progress

Fingerprint workspace after each Developer turn.

If multiple turns produce:

- same workspace fingerprint;
- same failure classification;
- same validation failure;

stop automatic looping and request human/Thinker intervention.

---

# 22. Security model

Preserve the existing core principle:

> Give the coding agent everything needed to finish the task, not everything needed to control the host.

## 22.1 Developer runner

- non-root;
- task worktree only;
- no Docker socket;
- no production credentials;
- no direct default-branch push;
- no force push unless a separately reviewed policy explicitly requires it;
- bounded network access;
- package installs controlled by policy;
- CPU/memory/pid/time limits;
- secrets passed only for the current task/provider and not written to normal logs.

## 22.2 Merge authority

Model/harness cannot merge directly.

Only Delivery application code can invoke merge after `MergePolicy` passes.

## 22.3 Local Ollama

Keep Ollama API private on the Compose network. Local Ollama has no local API authentication by default, so it must not be exposed to untrusted networks.

## 22.4 Webhooks

Continue signature/secret validation and durable delivery deduplication.

---

# 23. RAG/indexing decision

## 23.1 Immediate target

```text
repository_rag_enabled = false
```

for Developer/Thinker default path.

The Developer harness searches the live worktree directly.

## 23.2 Why

RAG currently adds:

- embedding cost;
- stale-index risk;
- merge/reindex synchronization complexity;
- context injection risk;
- another source-of-truth concept.

A coding harness already has grep/file discovery/read tools.

## 23.3 Migration approach

Do not delete pgvector/index code on day one.

Phase:

1. disable automatic retrieval;
2. stop using index freshness as task readiness;
3. collect 20-50 task benchmark data;
4. if no measurable benefit, remove repository indexing UI/routes/tables and pgvector extension;
5. if retained, redefine it only as an optional repository discovery accelerator whose results must be verified against live files.

---

# 24. API surface changes

The exact route naming may follow current conventions, but conceptually move toward:

```text
/api/v1/tasks
/api/v1/tasks/{id}
/api/v1/tasks/{id}/pause
/api/v1/tasks/{id}/resume
/api/v1/tasks/{id}/takeover
/api/v1/tasks/{id}/metrics
/api/v1/tasks/{id}/timeline
/api/v1/tasks/{id}/developer-session
/api/v1/tasks/{id}/validations
/api/v1/tasks/{id}/pull-request

/api/v1/teams
/api/v1/teams/{id}/agent-profiles
/api/v1/teams/{id}/activity
/api/v1/teams/{id}/canvas
/api/v1/teams/{id}/budgets

/api/v1/repositories
/api/v1/integrations

/api/v1/dashboard/summary
/api/v1/dashboard/cost
/api/v1/dashboard/performance

/webhooks/github
/webhooks/linear
/webhooks/slack
```

Deprecate:

- generic Role CRUD APIs;
- generic workflow graph mutation APIs;
- legacy role-keyed AgentConfig APIs;
- repository search/index APIs if RAG is ultimately removed.

Do not break the frontend all at once. Add new read models/routes, migrate UI, then remove old APIs.

---

# 25. Frontend route target

Recommended product navigation:

```text
Dashboard
Tasks
Teams
Repositories
Integrations
Settings
```

## Teams page

Team detail contains:

- live fixed canvas;
- agent cards/configuration;
- queue;
- repository scope;
- budget/policy;
- activity.

The old separate generic `/roles` page should disappear.

The old generic `/agents` workflow editor can become Team Canvas/Agent configuration, retaining visual styling but removing edge editing.

---

# 26. Configuration model

## 26.1 Team agent profile

Suggested shape:

```text
team_id
role_kind
label/display_name
avatar
is_enabled
harness
provider
model
effort
fallback_policy
soft_budget_usd
hard_budget_usd
max_turns_optional
supplemental_instructions
prompt_version
overrides_json bounded
```

Enforce uniqueness:

```text
UNIQUE(team_id, role_kind)
```

## 26.2 Team policies

```text
max_active_tasks
auto_merge_enabled
required_validation_profile
require_formal_github_approval
allow_text_lgtm_approval
authorized_reviewer_ids/teams
reviewer_enabled
thinker_strategy
repository_scope
```

## 26.3 Model catalog

Maintain a runtime capability registry for:

```text
provider
model
supports_tools
supports_resume/harness compatibility
supports_reasoning_effort
supports_usage
supports_cache_usage
supports_budget
context_window
max_output
active/deprecated
```

But do not expose every provider knob to end users.

---

# 27. Current model cost baseline (2026-09-08)

These values are informational defaults and must be kept in a versioned pricing catalog rather than compiled into business logic.

## Claude

```text
Claude Sonnet 5: $2 / MTok input, $10 / MTok output
Claude Opus 5:   $5 / MTok input, $25 / MTok output
```

Prompt cache pricing differs and must be stored separately.

## OpenAI

Current API model catalog shows approximately:

```text
GPT-5.6 Luna:  $0.20 / MTok input, $1.20 / MTok output
GPT-5.6 Terra: $2.00 / MTok input, $12.00 / MTok output
GPT-5.6 Sol:   $4.00 / MTok input, $20.00 / MTok output
```

Cached input pricing is lower and must be recorded separately.

## DeepSeek

DeepSeek V4 Flash has very low API pricing with peak/off-peak differences and supports JSON/tool use. Use it as a cheap Interpreter fallback, not as the initial default Developer until it is benchmarked against real tickets.

Never assume a current price is permanent.

---

# 28. Metrics quality and reconciliation

## 28.1 Do not trust one SDK field as invoice truth

Store:

- raw usage fields returned by harness/provider;
- provider-reported cost if present;
- app-calculated cost using a versioned pricing catalog;
- `usage_complete` flag.

Known SDK/provider gaps can exist, so the dashboard must distinguish exact vs estimated values.

## 28.2 Do not poll context APIs just for pretty charts

Avoid instrumentation that itself causes AI/token usage.

Metrics should come from normal run events/results whenever possible.

## 28.3 Reconciliation job

Optional daily/periodic background task:

```text
aggregate ai_runs
 -> compare provider usage/billing data when an API is available
 -> mark discrepancies
 -> never rewrite raw historical usage
```

---

# 29. Dashboard success metrics

The redesign is successful only if real task-level outcomes improve.

Primary engineering/product KPIs:

```text
% tasks reaching PR
% tasks merged
% tasks merged without human coding
median cost per merged task
P90 cost per merged task
median tokens per merged task
P90 tokens per merged task
median time to first edit
median time to PR
median active automation time
median GitHub wait time
review fix cycles per merged task
human intervention rate
budget-exhaustion rate
provider failure rate
```

A simple ticket consuming hundreds of thousands of tokens should show as an obvious anomaly.

---

# 30. Migration from the current project

Do this incrementally. The project already contains valuable infrastructure; do not rewrite everything.

## Phase 0 — Freeze architecture expansion

Before migration:

- stop adding new generic Roles/workflow features;
- stop adding new RAG behavior;
- stop polishing legacy paths unless needed for stability;
- preserve current end-to-end test fixtures;
- create feature flags for new execution path.

Flags:

```text
NEW_FIXED_LIFECYCLE
DEVELOPER_HARNESS_CODEX
DEVELOPER_HARNESS_CLAUDE
LOCAL_EVENT_INTERPRETER
REPOSITORY_RAG_ENABLED
LEGACY_WORKFLOW_ROUTING
LEGACY_EXECUTOR
```

## Phase 1 — Introduce DDD domain services without deleting legacy

Create new vertical modules for:

- Intake;
- Engineering;
- Delivery;
- Agent Runtime;
- Teams.

Wrap current persistence/GitHub/worktree logic behind ports first.

Do not move every file merely for aesthetics.

## Phase 2 — Fixed Team role profiles

Add new `team_agent_profiles` table.

Migrate current effective settings:

```text
Deliverer -> Interpreter profile where useful
Executor  -> Developer profile
Thinker   -> Thinker profile
Reviewer  -> Reviewer profile
```

Do not migrate Historical Intake as a new role.

Create default fixed profiles for every Team.

Frontend:

- reuse agent cards;
- remove add/delete role controls;
- allow rename/avatar/model/harness/budget.

## Phase 3 — Read-only fixed canvas

Keep existing `@xyflow/svelte` rendering.

Replace workflow definition data with a fixed graph DTO generated by Team activity read model.

Remove:

- add node;
- delete node;
- add edge;
- arbitrary outcome routing configuration;
- workflow version editing UI.

Keep:

- pan/zoom;
- fullscreen;
- live node state;
- selected agent details;
- current task/activity;
- queue counts.

## Phase 4 — Codex Developer adapter

Add `CodexDeveloperHarness`.

Requirements:

- start thread in task worktree;
- use workspace-write sandbox;
- persist thread ID;
- persist Codex home/state on volume;
- stream normalized events;
- record `TurnResult.usage`, duration, model, errors;
- explicit compaction support;
- interrupt/cancel support;
- no Codex multi-agent mode by default.

Run shadow benchmark against existing Executor before replacing it.

## Phase 5 — Claude Developer adapter

Add `ClaudeDeveloperHarness`.

Requirements:

- session ID persistence;
- persistent session state volume/store;
- bounded tools/permissions;
- result usage/cost capture;
- budget support;
- resume after runner restart;
- context/compaction behavior;
- no subagent spawning by default.

Use as second supported Developer option and benchmark.

## Phase 6 — Local Interpreter

Add Ollama service and health adapter.

Bootstrap `qwen3:4b`.

Implement strict JSON interpretation contract.

Add fallback chain.

Migrate Deliverer's classification responsibilities into:

```text
deterministic EventRouter
+
EventInterpreter only when needed
```

Do not migrate Deliverer's repository-context behavior.

## Phase 7 — New lifecycle routing

Implement fixed lifecycle behind feature flag.

New normal route:

```text
Task -> Developer -> Validation -> Publish -> Wait GitHub -> Fix/Approve -> Merge
```

Thinker/Reviewer branches only on policy/classification.

Stop normal `reopen` from enqueueing a complete interpretation/planning lifecycle.

## Phase 8 — Metrics schema

Add normalized:

- `ai_runs`;
- `developer_sessions`;
- `task_phase_runs`;
- `review_cycles`;
- pricing catalog or equivalent normalized persistence.

Backfill old WorkerRun history where mapping is possible, but mark incomplete historical data instead of fabricating fields.

## Phase 9 — Dashboard refresh

Build new read models first, then UI.

Priority:

1. task cost/time breakdown;
2. Team canvas live state;
3. cost per merged task;
4. expensive-task anomalies;
5. provider/model breakdown;
6. review-cycle metrics.

## Phase 10 — Disable RAG default

Turn off repository indexing/retrieval for new Teams.

Measure.

If no useful benefit, remove after migration stability.

## Phase 11 — Remove legacy architecture

Only after new lifecycle has successfully merged representative real tickets:

- delete legacy AgentConfig APIs;
- delete generic Role CRUD;
- delete legacy Executor proposal path;
- delete compatibility workflow routing;
- delete arbitrary workflow mutation APIs;
- delete unused workflow version tables after data migration/retention decision;
- remove unused RAG/pgvector subsystem if decision is final;
- hide/remove deferred Telegram/incident/terminal surfaces if not actively used.

---

# 31. Database migration guidance

Do not drop old tables in the same migration that introduces the new path.

Recommended pattern:

```text
Release A: add new schema + dual/read compatibility
Release B: new writes use new schema, old schema read-only
Release C: migration verification + backup
Release D: drop obsolete tables/routes
```

Old workflow tables can remain as historical audit data until a deliberate cleanup migration.

Preserve old token usage records exactly.

Never "fix" old cost data by silently recomputing it with today's prices.

---

# 32. Testing strategy

## 32.1 Unit tests

Domain tests should cover:

- task transitions;
- wait/status/stage combinations;
- merge eligibility;
- approval SHA invalidation;
- requirement versioning;
- Team role invariants;
- budget decisions;
- event classification routing;
- no-progress detection.

## 32.2 Adapter contract tests

A common DeveloperHarness contract test suite runs against Codex and Claude adapters using mocks/offline modes where possible.

Verify:

- start session;
- resume session;
- persist external ID;
- normalized telemetry;
- cancellation;
- interrupted runner recovery;
- compaction;
- workspace writes remain scoped.

## 32.3 Ollama Interpreter eval

Build a fixed corpus of real-ish messages:

```text
"lgtm"
"I don't think this is lgtm"
"looks good, merge after CI"
"please rename this variable"
"this architecture should move to the backend"
"can you explain why this failed?"
"@Nika make integration cards show teams"
```

Score:

- classification accuracy;
- unsafe false approvals;
- false task creation;
- latency;
- input/output tokens.

Approval false positives must be treated as severe failures.

## 32.4 End-to-end dogfood suite

Use at least 10 real representative tasks:

- tiny frontend style change;
- normal frontend feature;
- backend bug fix;
- test fix;
- database/query change;
- cross-file refactor;
- requirement update after first implementation;
- PR review code fix;
- architecture-change review;
- task requiring human clarification.

For each compare current Executor vs new harness path where practical.

---

# 33. Acceptance criteria for the redesign

The new architecture should not be declared successful merely because the services start.

Minimum acceptance:

1. Trello card can create a task and reach PR.
2. Linear issue can create a task and reach PR without unnecessary interpretation AI calls.
3. Slack engineering mention can be classified and create/modify the right task.
4. Developer can implement, test, and preserve changes.
5. Validation failure returns to the same Developer session.
6. PR is created deterministically.
7. Waiting on GitHub consumes no model calls.
8. PR code-change feedback resumes the same Developer session.
9. New push invalidates stale approval evidence.
10. authorized LGTM/approval + green CI can auto-merge.
11. merge updates Trello/Linear semantic status.
12. task detail shows complete cost/token/time breakdown.
13. Team canvas visually shows current stage/agent/task.
14. restart of scheduler/runner does not lose worktree or session reference.
15. small representative tasks do not repeatedly approach old 400K/1M-token behavior.

---

# 34. Benchmark and rollout gate

Do not switch all work to the new architecture after one demo.

## Benchmark cohort

Run 10-20 dogfood tickets.

Capture:

```text
success/PR/merge
human intervention
Developer model/harness
input/output/cache tokens
calculated cost
provider cost if available
time to first edit
time to validation
time to PR
active automation time
GitHub wait time
review cycles
compactions
retries
```

## Rollout decision

Choose default Developer preset based on:

```text
cost per correctly merged task
not
cost per token
```

Compare at least:

```text
Codex + GPT-5.6 Terra
Codex + GPT-5.6 Sol on hard tasks
Claude Agent SDK + Sonnet 5
Claude Agent SDK + Opus 5 on hard tasks
```

The winner can differ by task class.

---

# 35. Initial recommended production defaults

These are intentionally conservative.

## Team

```text
max_active_tasks: 1
auto_merge_enabled: true only for configured trusted repositories
Thinker: enabled-on-demand
Reviewer: disabled
```

## Interpreter

```text
primary: ollama/qwen3:4b
thinking: disabled
input envelope: <= ~4K tokens
strict JSON schema: yes
fallback 1: deepseek-v4-flash non-thinking
fallback 2: gpt-5.6-luna none/low
```

## Developer

```text
primary preset: Codex / gpt-5.6-terra / medium
normal uncertain task: Terra / high
complex escalation: gpt-5.6-sol / high
multi-agent/ultra: disabled
```

## Claude alternative

```text
normal: claude-sonnet-5
complex escalation: claude-opus-5
subagents: disabled unless explicit experiment
```

## RAG

```text
enabled for Developer: false
auto retrieval: false
index required for task: false
```

## Validation

```text
deterministic: yes
AI Tester: off
```

## Internal reviewer

```text
off by default
```

---

# 36. Operational notes

## 36.1 Model version pinning

Pin SDK/harness package versions in the runner image.

Do not necessarily pin floating model aliases forever. Store:

- configured alias;
- actual model/snapshot returned when available;
- date/time;
- capability snapshot.

When changing a default model, run the dogfood eval suite first.

## 36.2 Credentials

For self-hosted dogfood, SDK login methods may support personal account flows, but the target product architecture should support API-key/BYOK credentials cleanly and should not depend on an interactive browser login inside a headless server.

Keep provider credentials outside task worktrees.

## 36.3 Backups

Back up together:

- PostgreSQL;
- task workspaces with unfinished changes;
- harness state/session store;
- encrypted integration credential state/configuration.

A DB backup without unfinished workspaces can lose uncommitted engineering work. A workspace backup without DB state loses ownership/routing/session references.

---

# 37. Things deliberately not solved in this redesign

Do not mix these into the token-efficiency migration:

- public multi-tenant auth/tenant isolation;
- horizontal scheduler clustering;
- Kubernetes;
- enterprise RBAC;
- arbitrary marketplace role plugins;
- universal project management system support;
- custom user-programmed workflow graphs;
- full autonomous deployment to production environments.

Design ports so they can be added later, but do not build them now.

---

# 38. Final target architecture

```text
                         +----------------+
                         |    Frontend    |
                         | Dashboard/Tasks|
                         | Team Canvas    |
                         +-------+--------+
                                 |
                                 v
                         +----------------+
                         |    Backend     |
                         | API/Webhooks   |
                         +-------+--------+
                                 |
          +----------------------+-----------------------+
          |                      |                       |
          v                      v                       v
 +----------------+     +----------------+      +----------------+
 | Intake Context |     | Delivery       |      | Teams/Config   |
 | Trello/Linear  |     | GitHub/PR      |      | Fixed profiles |
 | Slack/GitHub   |     | Merge policy   |      | Budgets        |
 +-------+--------+     +--------+-------+      +----------------+
         |                       ^
         v                       |
 +----------------+              |
 | Engineering    |--------------+
 | Task aggregate |
 | State machine  |
 +-------+--------+
         |
         v
 +--------------------+
 | Agent Runtime      |
 | DeveloperHarness   |
 +----+-----------+---+
      |           |
      v           v
 +---------+   +---------+
 | Codex   |   | Claude  |
 | SDK     |   | SDK     |
 +----+----+   +----+----+
      |             |
      +------+------+ 
             |
             v
      task worktree + shell
             |
             v
      deterministic validation

Ambiguous external message path:

Backend/EventRouter
      |
      v
Ollama / Qwen3 4B
      |
cloud fallback only if needed
```

Persistent platform services:

```text
PostgreSQL
repository cache
task workspaces
harness session state
Ollama model volume
```

The core simplification is:

> **The application orchestrates engineering. The coding harness performs coding. The cheap Interpreter understands ambiguous messages. Deterministic code performs authority-sensitive actions.**

---

# 39. Implementation priority order

If only one ordered TODO list is followed, use this:

1. Freeze new legacy workflow/role/RAG feature development.
2. Add feature flags for V2 path.
3. Introduce fixed `TeamAgentProfile` model.
4. Build fixed lifecycle/state-machine domain service.
5. Convert canvas to read-only fixed lifecycle visualization.
6. Add normalized AI usage/phase metrics schema.
7. Implement Codex DeveloperHarness + persistent thread state.
8. Benchmark Codex path on a few Trello tasks.
9. Add deterministic validation -> same-session fix loop.
10. Add deterministic PR publication -> WAITING_REVIEW.
11. Add GitHub feedback router -> same-session Developer continuation.
12. Add current-SHA approval/merge gate.
13. Add Ollama service + Qwen Interpreter.
14. Add DeepSeek/Luna Interpreter fallbacks.
15. Add Slack integration.
16. Implement Claude DeveloperHarness.
17. Run 10-20 task comparative benchmark.
18. Update dashboard with cost/time/token/task KPIs.
19. Disable repository RAG by default and measure.
20. Remove legacy routing/Role CRUD/workflow mutation only after V2 proves reliable.

---

# 40. External implementation references verified on 2026-09-08

These are reference sources for implementation details; they are not a substitute for pinning and testing the exact SDK versions used in the project.

## OpenAI Codex

- Codex Python SDK getting started: https://github.com/openai/codex/blob/main/sdk/python/docs/getting-started.md
- Codex Python SDK API reference: https://github.com/openai/codex/blob/main/sdk/python/docs/api-reference.md
- GPT-5.6 efficiency/harness discussion: https://openai.com/index/gpt-5-6-frontier-intelligence-efficiency/
- Current OpenAI model catalog: https://developers.openai.com/api/docs/models

## Claude

- Claude model overview: https://platform.claude.com/docs/en/models/overview
- Claude model selection: https://platform.claude.com/docs/en/about-claude/models/choosing-a-model
- Claude pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Claude server-side compaction: https://platform.claude.com/docs/en/build-with-claude/compaction
- Claude Agent SDK Python repository: https://github.com/anthropics/claude-agent-sdk-python

## Ollama / Qwen

- Ollama Docker: https://docs.ollama.com/docker
- Ollama API: https://docs.ollama.com/api/introduction
- Ollama usage metrics: https://docs.ollama.com/api/usage
- Ollama Qwen3 model library: https://ollama.com/library/qwen3
- Qwen3 thinking/non-thinking behavior: https://qwenlm.github.io/blog/qwen3/

## DeepSeek

- Models/pricing: https://api-docs.deepseek.com/quick_start/pricing/
- Responses API: https://api-docs.deepseek.com/guides/responses_api/

---

# 41. Final architectural rule set

When implementation decisions become confusing, use these rules:

1. **Does this require intelligence?** If no, use deterministic code.
2. **Does it require repository engineering?** If yes, use the Developer harness.
3. **Is it just ambiguous human language?** Use local/cheap Interpreter.
4. **Is it architecture-level uncertainty?** Optionally invoke Thinker.
5. **Is it mechanical validation?** Run commands, not AI.
6. **Is it merge/push/permission authority?** Application policy owns it, never the model.
7. **Is the task waiting on an external event?** Stop all AI and wait for webhook/reconciliation.
8. **Did review feedback arrive?** Continue the same task/session unless architecture truly changed.
9. **Is context old?** Compact or reconstruct from checkpoint; do not keep resending everything.
10. **Can we measure its token/cost/time impact?** If not, add telemetry before scaling it.

