# Autonomous Engineering Worker — Next Architecture Phase
## Coordinator, Event Inbox, Queues, Human Intervention UX, Adaptive Token Economy, Model Routing, and Agent Communication Protocol

**Status:** Implementation reference — see [completion and verification](coordinator-implementation.md#completion-boundary)  
**Date:** 2026-09-14  
**Primary constraint:** Preserve the current bounded engineering execution results. Do not replace FAST_PATCH with a new open-ended agent loop.

---

## 1. Executive decision

The project already has a working engineering execution core:

```text
task
→ bounded interpretation/localization
→ FAST_PATCH / STRUCTURED_MULTI_PATCH / BOUNDED_AGENTIC
→ deterministic developer checks
→ full validator
→ publication
→ review
→ guarded merge
```

That part should remain the foundation.

The next architecture phase should solve a different problem: the application should behave less like a collection of fixed provider automations and more like a durable AI engineering coordinator that understands ongoing work across Trello, Linear, GitHub, Slack, the dashboard, and the engineering engine.

The target is:

```text
Trello / Linear / GitHub / Slack / Dashboard
                    │
                    ▼
           Verified Event Gateway
                    │
                    ▼
             Durable Event Inbox
                    │
                    ▼
             Coordinator Agent
        understands meaning / context
                    │
          chooses semantic actions
                    │
                    ▼
           Policy Action Executor
      auth / current-state / idempotency
                    │
        ┌───────────┼────────────┐
        ▼           ▼            ▼
     Reply      Update task   Engineering request
                                 │
                                 ▼
                         Existing bounded engine
                                 │
                                 ▼
                    Validator → PR → review
                                 │
                                 └── event back to inbox
```

The Coordinator owns **meaning and communication**.

Deterministic code owns **authority, effects, spending, validation, and merge**.

The engineering engine owns **repository implementation**.

The token strategy should be **adaptive and progress-based**, not “two calls and stop.”

---

## 2. Non-negotiable preservation rules

### 2.1 Preserve FAST_PATCH as the default

Routine work should continue to use the current bounded pattern:

```text
deterministic project/repository evidence
→ small source packet
→ one Terra LOW patch request
→ apply patch
→ deterministic checks
→ at most bounded repair
→ full validation
```

Do not turn routine tasks back into:

```text
model → shell → model → read → model → edit → model → test → ...
```

### 2.2 Preserve bounded complex execution

Existing modes remain:

```text
FAST_PATCH
STRUCTURED_MULTI_PATCH
BOUNDED_AGENTIC
```

Complex work should scale through bounded work units and fresh contexts, not a single growing transcript.

### 2.3 Preserve deterministic authority

Models never directly authorize:

```text
merge
budget changes
credential scope
arbitrary Git operations
validator command changes
task eligibility
approval validity
repository permission
```

The model may express intent. Trusted code verifies and executes it.

### 2.4 Preserve durable state outside the LLM

Durable truth remains:

```text
PostgreSQL
Git/worktree
current SHA
validation results
PR/review state
provider delivery IDs
usage receipts
structured checkpoints
```

Raw model conversation history is not authoritative state.

### 2.5 Preserve zero-cost waiting

No paid model activity merely because a task is:

```text
queued
waiting for CI
waiting for PR review
waiting for a human
waiting for a Developer slot
waiting for mergeability
```

External changes wake the Coordinator.

---

# 3. Why a Coordinator is needed

The current implementation already has strong provider adapters and a bounded Supervisor, but the product still behaves mainly as deterministic workflow automation.

Typical current shape:

```text
provider event
→ fixed normalization/routing
→ fixed lifecycle action
→ occasional AI classification
```

The intended product experience is closer to:

```text
provider event
→ understand what the human meant
→ inspect relevant task/PR/discussion context
→ decide the next useful action
→ communicate back naturally
→ request engineering work when needed
→ wait
```

Example:

> A Trello user comments: “Wait, this also needs to work on mobile.”

Desired behavior:

```text
COMMENT_ADDED
→ Coordinator wakes
→ reads task requirement + recent discussion + current PR state
→ detects scope change
→ decides whether clarification is needed
→ replies in the original conversation
→ invalidates stale requirement/validation when appropriate
→ requests a bounded engineering change
→ later reports result
```

That behavior should not require a new hard-coded handler for each sentence type.

---

# 4. Coordinator Agent

## 4.1 Responsibilities

The Coordinator may:

```text
interpret task/review/message meaning
detect changed requirements
identify blockers
ask focused clarification
read relevant provider discussion
inspect current PR/check/review state
reply to humans
request implementation
request bounded repair
pause or cancel stale work
classify WAIT / CONTINUE / REPLAN / ASK_HUMAN
summarize status
decide whether additional reasoning is worth spending
```

## 4.2 Non-responsibilities

The Coordinator must not directly:

```text
run arbitrary shell
edit source code in normal operation
push arbitrary refs
merge PRs
change Team budget
change provider credentials
change validation configuration
grant itself new permissions
```

## 4.3 “Live” does not mean continuously running

A live Coordinator is:

```text
durable state
+ durable inbox
+ event-driven wakeup
+ bounded reasoning/action batch
+ sleep
```

This is critical for cost.

Do not keep an LLM session running while nothing changes.

---

# 5. Event Gateway

All providers should feed the same durable event architecture.

## 5.1 Webhook handler responsibilities

HTTP webhook handlers should perform only:

```text
verify provider authenticity
validate basic schema
extract delivery identity
persist event
enqueue processing
respond success quickly
```

Do **not** invoke the Coordinator inside the webhook request.

This matches current provider guidance:

- Slack requires an HTTP 2xx within three seconds and explicitly recommends not processing/reacting in the same request path; use a queue.
- GitHub recommends asynchronous processing when webhook handling may take time and notes that deliveries can arrive out of order.
- Linear provides a unique `Linear-Delivery`, `Linear-Signature`, event type, and timestamp and recommends HMAC/timestamp verification.

## 5.2 Canonical event envelope

```python
class ExternalEvent(BaseModel):
    event_id: UUID

    provider: Literal[
        "trello",
        "linear",
        "github",
        "slack",
        "dashboard",
        "engineering"
    ]

    provider_delivery_id: str
    provider_event_type: str
    provider_timestamp: datetime | None

    organization_id: UUID | None
    team_id: UUID | None
    repository_id: UUID | None
    task_id: UUID | None

    actor: ActorRef | None
    conversation_ref: ConversationRef | None

    kind: CanonicalEventKind

    payload_ref: str
    received_at: datetime
```

Suggested canonical event kinds:

```text
TASK_CREATED
TASK_UPDATED
TASK_CANCELLED
COMMENT_ADDED
MESSAGE_ADDED
HUMAN_RESPONSE

PR_CREATED
PR_UPDATED
PR_REVIEWED
PR_COMMENTED
CI_CHANGED

ENGINEERING_STARTED
ENGINEERING_PROGRESS
ENGINEERING_COMPLETED
ENGINEERING_FAILED

VALIDATION_COMPLETED
PUBLICATION_COMPLETED
MERGE_STATE_CHANGED
```

---

# 6. Idempotency and ordering

## 6.1 Delivery dedupe

Unique provider deliveries must not create duplicate decisions.

Store a unique key such as:

```text
(provider, provider_delivery_id)
```

## 6.2 Action idempotency

Every intended side effect gets an application idempotency key:

```text
task_id
decision_revision
semantic_action
target conversation/resource
```

Example:

```text
task=123|rev=7|action=reply_scope_change|thread=abc
```

If processing retries, the effect is reconciled instead of duplicated.

## 6.3 Never assume webhook order

GitHub documents that webhook deliveries may arrive out of order.

Therefore:

```text
incoming event
→ persist
→ reconcile authoritative state if action is sensitive
→ decide
```

For high-impact actions, current remote state wins over event arrival order.

---

# 7. Event coalescing

Human systems generate event bursts.

Example:

```text
comment
comment edit
second comment
status move
```

Waking an LLM for each event is unnecessary.

Add a task-scoped coalescer:

```text
normal debounce window: 2–5 seconds
```

Compatible events become one `CoordinatorSituation`.

Do not delay safety/control events such as:

```text
task cancelled
Team paused
requirement revision invalidated
credential/policy revoked
```

---

# 8. Coordinator memory

Do not replay the entire task conversation on every wake.

Use three layers.

## 8.1 Authoritative state

From PostgreSQL / Git / delivery state:

```text
original requirement
current requirement revision
current SHA
current PR
task stage/status
validation result
review status
current engineering generation
budget state
human wait state
```

## 8.2 Conversation store

Normalize provider messages:

```python
class ConversationMessage(BaseModel):
    id: UUID
    task_id: UUID

    provider: str
    provider_message_id: str

    actor_type: Literal["human", "coordinator", "system"]
    actor_ref: str | None

    text: str
    thread_ref: str | None

    created_at: datetime
```

Normal Coordinator context should receive:

```text
last relevant messages
+ unresolved questions
+ new messages since last decision
```

Older history is retrieved only when needed.

## 8.3 Coordinator checkpoint

Persist a tiny structured state:

```json
{
  "goal": "Add mobile support",
  "open_questions": [],
  "invariants": [
    "existing desktop behavior must remain unchanged"
  ],
  "last_human_decision": "mobile support is required",
  "pending_external": [
    "PR_REVIEW"
  ],
  "last_action": "ENGINEERING_REQUESTED"
}
```

Do not persist hidden chain-of-thought.

---

# 9. Semantic tools instead of raw APIs

The Coordinator should not receive unrestricted provider clients.

## 9.1 Tracker tools

```text
tracker.read_task
tracker.read_recent_discussion
tracker.reply
tracker.ask_clarification
tracker.update_summary_intent
tracker.set_status_intent
```

## 9.2 GitHub tools

```text
github.read_pr
github.read_reviews
github.read_review_delta
github.read_checks
github.reply
github.request_review
github.refresh_state
```

Do not expose:

```text
github.request(method, url, body)
```

to the LLM.

## 9.3 Slack tools

Add first-class outbound Slack capabilities:

```text
slack.read_thread
slack.reply_thread
slack.send_task_update
slack.ask_clarification
```

Inbound-only plumbing is not enough for the intended experience.

## 9.4 Engineering tools

```text
engineering.get_status
engineering.request_implementation
engineering.request_repair
engineering.pause_generation
engineering.cancel_stale_generation
engineering.request_validation
```

---

# 10. Action Executor

Coordinator output is an intent, not an effect.

```python
class CoordinatorAction(BaseModel):
    type: ActionType
    task_id: UUID

    requirement_revision: int
    expected_lifecycle_revision: int

    arguments: dict

    reason_code: str
    idempotency_key: str
```

The executor checks:

```text
current lifecycle revision
current requirement revision
actor permissions
Team policy
repository policy
provider scope
budget admission
duplicate action history
current provider state
```

Only then execute.

This is the central design:

```text
AI = meaning + choice
deterministic executor = permission + reliability
```

---

# 11. Preventing feedback loops

Your own provider updates can produce incoming webhooks.

Every outbound effect should record:

```text
action_id
origin_event_id
origin_agent
provider_effect_id
```

Inbound processing classifies echoes.

Examples:

```text
agent moved Trello status
→ Trello webhook comes back
→ persist as confirmation
→ do not wake Coordinator

agent posted Slack reply
→ same message event comes back
→ persist/dedupe
→ do not wake Coordinator

human replies to that message
→ wake Coordinator
```

---

# 12. Task queue model

Incoming work should create backlog entries, not instantly consume an AI slot.

## 12.1 Scheduling state is separate from lifecycle state

A task can be:

```text
ACTIVE / DEVELOPING logical lifecycle
```

while still:

```text
QUEUED_FOR_DEVELOPER
```

Do not overload lifecycle fields to represent scheduler ownership.

Suggested scheduling states:

```text
QUEUED
ELIGIBLE
LEASED
RUNNING
BLOCKED
DONE
```

## 12.2 Per-Team concurrency

Each Team configures:

```python
developer_concurrency: int
```

Recommended default:

```text
1
```

Ten new Trello cards:

```text
Team A

RUNNING
1 task

QUEUED
9 tasks
```

## 12.3 Global concurrency

Also configure:

```python
global_max_paid_developer_slots
```

Example:

```text
Team A max 1
Team B max 1
Team C max 1

global max 2

A = running
B = running
C = queued
```

## 12.4 Release Developer slots while waiting

A Developer slot is released when the task enters:

```text
WAITING_REVIEW
WAITING_CI
WAITING_HUMAN
WAITING_EXTERNAL
PAUSED
FAILED
CANCELLED
COMPLETE
```

Validation can have a separate concurrency pool.

## 12.5 Queue ordering

Initial deterministic ordering:

```text
priority DESC
created_at ASC
```

Later allow policy-approved factors:

```text
production incident
explicit human urgency
dependency unblocked
aging
```

Do not let AI silently reorder everything.

## 12.6 Fairness across Teams

Use fair scheduling when global capacity is lower than sum of Team capacities.

Simple first implementation:

```text
priority bucket
→ round-robin eligible Teams
→ oldest eligible task in selected Team
```

This prevents a noisy Team from starving another Team.

---

# 13. Human intervention as a normal workflow

`WAITING_HUMAN` is not merely failure.

It means:

```text
the system knows what it cannot safely decide
```

## 13.1 HumanRequest

```python
class HumanRequest(BaseModel):
    id: UUID
    task_id: UUID

    category: Literal[
        "CLARIFICATION",
        "PRODUCT_DECISION",
        "AUTHORIZATION",
        "CONFLICT",
        "TECHNICAL_RISK",
        "MANUAL_VERIFICATION"
    ]

    question: str
    why_needed: str

    choices: list[HumanChoice] | None

    requested_by: str
    evidence_refs: list[str]

    status: Literal["OPEN", "ANSWERED", "CANCELLED"]
```

## 13.2 Human response

```text
human answers in dashboard/Trello/Slack/GitHub
→ normalize HUMAN_RESPONSE
→ Coordinator wakes
→ update requirement/checkpoint if required
→ choose next action
→ resume safely
```

Normal clarification should not require an internal “resume task” ritual.

---

# 14. UI experience

The UI should feel like supervising a small AI engineering team.

## 14.1 Main dashboard

Top bar:

```text
Developer slots     2 / 2 busy
Queued              8
Needs You           2
Waiting Review      3
AI spend today      $X
```

Main lanes:

```text
ACTIVE
QUEUED
NEEDS YOU
WAITING EXTERNAL
RECENTLY COMPLETED
```

## 14.2 Team page

Example:

```text
Backend Team

Developer slot: 1 / 1 busy

RUNNING
TASK-143 — Fix transaction allocation

UP NEXT
1. TASK-144 — Export filtering
2. TASK-146 — Audit sorting
3. TASK-151 — Billing validation
```

## 14.3 Needs You

Example:

```text
⚠ Human input required

TASK-201
Live Execution resize

Coordinator:
"Should the window position persist after the app restarts?"

Why I need this:
"The ticket requests drag/resize but does not define persistence."

[ No, reset on restart                      ]

[ Send & Continue ]
```

## 14.4 Agent/system identity

Show icons/avatars consistently:

```text
Coordinator AI
Developer AI
Planner AI
Validator — deterministic
GitHub
Trello
Linear
Slack
Human
```

Do not visually imply the Validator or GitHub are AI agents.

## 14.5 Task timeline

Example:

```text
09:31  Trello       Task received
09:31  Coordinator  Requirement interpreted
09:32  Terra        Patch started
09:33  Validator    Checks passed
09:34  GitHub       PR created
10:02  Reviewer     Mobile support requested
10:02  Coordinator  Requirement change detected
10:03  Needs You    Clarification requested
10:07  You          "Mobile is required"
10:08  Terra        Bounded repair started
```

## 14.6 Default vs technical detail

Default UI should answer:

```text
What is happening?
Who is working?
What is next?
Does it need me?
How much has it cost?
```

Technical drawer can expose:

```text
model
provider
effort
execution mode
tokens
cost receipts
SHA
validation commands
runner resources
artifacts
```

## 14.7 Unified conversation panel

Task detail should show one logical conversation composed from:

```text
Trello
Linear
GitHub
Slack
Dashboard
Coordinator
```

Each message keeps its provider badge/source reference.

---

# 15. Token optimization philosophy

Do not make:

```text
max_calls = 2
```

the intelligence strategy.

Limits remain protection, but the real policy should answer:

```text
Is more spending producing useful engineering progress?
```

This better matches successful terminal-agent usage.

---

# 16. Budget hierarchy

Use multiple levels:

```text
account/month hard budget
Team/month budget
Team/day soft allowance
task estimated allowance
generation reservation
absolute task safety ceiling
```

A complex task may legitimately consume much more than a simple task.

Do not force every task into the same small budget.

Example economic shape:

```text
150 easy tasks  × very cheap
35 normal tasks × moderate
12 hard tasks   × larger
3 very hard     × expensive but justified
```

Optimize the portfolio, not every task independently.

---

# 17. Adaptive spending stages

## Stage A — cheap attempt

```text
FAST_PATCH
small context
Terra LOW
```

## Stage B — structured expansion

```text
STRUCTURED_MULTI_PATCH
one plan
bounded work units
fresh contexts
```

## Stage C — uncertainty resolution

```text
BOUNDED_AGENTIC
read-only investigation
possibly stronger model
structured findings
return to bounded patch execution
```

Escalation must come from evidence.

---

# 18. Useful progress

Useful progress examples:

```text
correct target localized
new root cause established
valid patch produced
failing tests reduced
check severity reduced
work unit completed
integration contract identified
validation advanced
review request resolved
```

Non-progress examples:

```text
same search repeated
same source reread without new reason
same failure repeated
same diagnosis repeated
unchanged diff
waiting/polling
```

---

# 19. Progress evidence

Do not begin with one opaque magic score.

Persist explicit measurements.

```python
class ProgressWindow(BaseModel):
    input_tokens: int
    uncached_input_tokens: int | None
    output_tokens: int
    cost_usd: Decimal | None
    elapsed_seconds: float

    new_localization: bool
    diagnosis_changed: bool
    diff_changed: bool
    checks_improved: bool
    milestone_advanced: bool

    repeated_commands: int
    repeated_failures: int
    repeated_reads: int
```

Policy classification:

```text
PRODUCTIVE
MARGINAL
STALLED
REGRESSING
```

Actions:

```text
PRODUCTIVE
→ continue if budget permits

MARGINAL
→ narrow context / restructure

STALLED
→ change mode / replan / ask Coordinator

REGRESSING
→ stop generation / escalate / ask human
```

---

# 20. Context strategy

## 20.1 Shared project context

Continue the current deterministic shared prefix:

```text
bounded AGENTS.md/README
package manifests
scripts/tool names
bounded directory/project facts
```

Recompute from checkout rather than storing an AI-generated project summary.

## 20.2 Keep operational data outside LLM context

OpenAI Agents SDK explicitly distinguishes local application context from LLM-visible context.

Keep things such as:

```text
task UUID
workspace path
policy objects
logger
budget tracker
credentials
provider clients
telemetry collectors
```

outside prompts unless the model actually needs them.

## 20.3 Prompt caching

For OpenAI GPT-5.6+ requests, current Responses API supports `prompt_cache_key`, explicit cache breakpoints, and a 30-minute TTL option.

Stable prefix:

```text
system contract
protocol definition
shared project evidence
```

Dynamic suffix:

```text
current task
current source
current error/review delta
```

Cache ratio is not the primary metric.

Primary metric:

```text
total AI cost/tokens per accepted delivery
```

## 20.4 Fresh contexts over transcript replay

For repairs/work units:

```text
original objective
current source/diff
structured handoff
new failure/review delta
```

Do not replay the previous Developer transcript.

Anthropic’s published long-running harness guidance specifically distinguishes context resets with structured handoffs from compaction and reports them as useful for long tasks.

## 20.5 Compaction

Keep compaction as a fallback for genuinely long active sessions.

Do not make compaction the normal memory system.

Preferred pattern:

```text
bounded generation
→ structured artifact
→ fresh generation
```

---

# 21. Agent-to-agent protocol

Agent communication should be typed, not primarily English prose.

Canonical packet:

```python
class AgentEnvelope(BaseModel):
    version: int
    type: str

    task_id: UUID
    requirement_revision: int
    current_sha: str | None

    payload: dict
    evidence_refs: list[str]
```

Example work request:

```json
{
  "v": 1,
  "t": "work",
  "task": "123",
  "req": 7,
  "sha": "a91f",
  "obj": "live_execution_window",
  "act": ["drag", "resize"],
  "inv": ["readonly", "viewport"],
  "f": ["LiveExecutionModal.svelte"]
}
```

Example result:

```json
{
  "v": 1,
  "t": "result",
  "task": "123",
  "status": "ready_validation",
  "f": ["LiveExecutionModal.svelte"],
  "checks": ["format:ok", "lint:ok", "typecheck:ok"]
}
```

Benefits:

```text
smaller prompts
less ambiguity
machine validation
provider-neutral handoffs
easy audit
easy compression
```

---

# 22. Experimental compact domain language (“alien language”)

Yes, test it.

Prompt-compression research shows that LLMs can sometimes preserve substantial task utility with highly compressed prompts that are difficult for humans to read.

Microsoft’s LLMLingua reported up to 20× compression in its evaluated workloads with little performance loss, and explicitly notes that token-level compressed prompts can be difficult for humans while still interpretable by models.

This does **not** prove that arbitrary symbolic syntax will help our models.

The correct implementation is a codec experiment.

## 22.1 Canonical state remains typed

Never store only the compressed string.

Store canonical structured objects.

Example:

```python
RepairRequest(...)
```

Serialize them using:

```text
JSON_VERBOSE
JSON_COMPACT
DSL_V1
COMPRESSED_V1
```

## 22.2 Example

Normal:

```json
{
  "type": "repair",
  "sha": "abc",
  "errors": [
    {
      "kind": "lint",
      "path": "Foo.svelte",
      "line": 88,
      "code": "unused_symbol"
    }
  ]
}
```

Compact:

```text
R|s=abc|e=L,Foo.svelte,88,U
```

Dictionary:

```text
R repair
L lint
U unused_symbol
W work
V validation
Q clarification
H human_required
```

## 22.3 What must remain verbatim

Do not aggressively compress:

```text
original human requirement
ambiguous review prose
exact compiler/test errors when exact wording matters
source code
security/authorization policy
```

## 22.4 Benchmark it per model

Compare:

```text
Luna
Terra
Sol
DeepSeek V4.1 Flash
```

Metrics:

```text
actual input tokens
schema/codec parse rate
semantic decision accuracy
patch acceptance rate
repair success rate
latency
cost
```

A Unicode-heavy “alien” format may visually look shorter but tokenize worse. Provider token usage is truth.

Enable a codec only when:

```text
token reduction is material
AND
quality does not materially decline
```

---

# 23. Model catalog and DeepSeek option

Add model selection as policy.

Architecture must not depend on one vendor/model.

Add **DeepSeek V4.1 Flash** as an experimental selectable model.

Do not replace Terra by default.

Suggested catalog:

```text
Coordinator
  Luna LOW — default
  DeepSeek V4.1 Flash — experimental
  Terra LOW — optional

FAST_PATCH
  Terra LOW — proven baseline
  DeepSeek V4.1 Flash — experimental

Planner
  Terra MEDIUM
  DeepSeek V4.1 Flash — experimental
  Sol MEDIUM — high risk

BOUNDED_AGENTIC
  Terra MEDIUM
  DeepSeek V4.1 Flash — experimental
  Sol MEDIUM — escalation
```

Policy model:

```python
class ModelPolicy(BaseModel):
    provider: str
    model: str

    role: str
    allowed_modes: list[str]

    default_effort: str | None
    max_effort: str | None

    experimental: bool
```

No silent cross-provider auto-escalation initially.

Benchmark first.

---

# 24. Clean integration boundaries

Separate these responsibilities.

## Provider Adapter

Owns:

```text
signatures
OAuth/provider credentials
pagination
provider API calls
provider IDs
rate limits
raw payload parsing
provider-specific retry semantics
```

## Event Gateway

Owns:

```text
dedupe
normalization
persistence
enqueue
```

## Coordinator

Owns:

```text
meaning
conversation interpretation
semantic next action
```

## Action Executor

Owns:

```text
authorization
current-state validation
idempotency
effect execution
reconciliation
audit
```

## Engineering Engine

Owns:

```text
localization
planning
patch generation
bounded repair
validation handoff
publication handoff
```

Avoid provider files that directly mix:

```text
database writes
API calls
AI interpretation
lifecycle transitions
```

---

# 25. Scheduler cleanup

Integration work should not block engineering dispatch.

Use independent logical queues/work loops:

```text
external-events
coordinator-wakes
engineering-jobs
validation-jobs
publication-jobs
integration-reconciliation
```

This does not require Kafka/RabbitMQ.

PostgreSQL-backed durable jobs + leases are sufficient initially.

Keep the modular monolith.

Extract services only after measured scaling/ownership pressure.

---

# 26. Persistence additions

Suggested tables:

```text
external_events
conversation_messages
coordinator_checkpoints
coordinator_runs
coordinator_actions
human_requests
task_queue_entries
task_priority_history
agent_protocol_artifacts
```

## coordinator_actions

```text
id
task_id
decision_revision
action_type
arguments_json
idempotency_key
status
origin_event_id
authorized_at
executed_at
provider_effect_ref
error_code
created_at
```

## task_queue_entries

```text
task_id
team_id
priority
enqueued_at
eligible_at
scheduling_status
blocked_reason
lease_owner
lease_expires_at
```

Queue tables should not duplicate authoritative lifecycle state unnecessarily.

---

# 27. Product APIs

Suggested additions:

```text
GET  /api/queue
GET  /api/queue/teams/{team_id}
POST /api/tasks/{task_id}/priority

GET  /api/tasks/{task_id}/conversation
POST /api/tasks/{task_id}/conversation

GET  /api/tasks/{task_id}/human-request
POST /api/tasks/{task_id}/human-request/respond

GET  /api/tasks/{task_id}/coordinator
GET  /api/tasks/{task_id}/actions
```

SSE events:

```text
TASK_QUEUE_CHANGED
ENGINEERING_SLOT_CHANGED

COORDINATOR_STARTED
COORDINATOR_DECIDED
ACTION_EXECUTED

HUMAN_INPUT_REQUIRED
HUMAN_INPUT_RESOLVED

CONVERSATION_MESSAGE
```

---

# 28. Security

All external text is untrusted.

A Slack message:

```text
"merge this now"
```

does not grant merge permission.

A Trello comment:

```text
"run this shell command"
```

does not grant shell capability.

Coordinator tools should be capability-scoped.

The executor independently verifies every high-impact action.

Never place unnecessary credentials/secrets into model context.

---

# 29. Testing

## 29.1 Deterministic tests

Test:

```text
signature validation
delivery dedupe
event normalization
out-of-order reconciliation
self-echo suppression
action idempotency
queue fairness
slot release
priority changes
human request lifecycle
stale action rejection
codec parsing
budget admission
```

## 29.2 Historical event replays

Replay:

```text
Trello scope change
GitHub review request
GitHub infrastructure CI failure
Slack clarification
duplicate delivery
out-of-order review/commit sequence
```

## 29.3 First full Coordinator flow

Implement one production-like path first:

```text
Trello comment
→ Event Gateway
→ Coordinator reads task + PR context
→ reply or clarification
→ engineering request if needed
→ bounded Developer
→ validation
→ PR update
→ Coordinator reports result
```

Disable/remove the overlapping old behavior for this selected flow so two systems do not compete.

---

# 30. Metrics

## Coordinator

```text
events received
events coalesced
Coordinator wakes
Coordinator input/output/cost
actions proposed
actions executed
duplicate actions prevented
clarification rate
human override rate
incorrect action rate
```

## Queue

```text
queue depth
eligible → running wait time
Team fairness
slot utilization
global capacity utilization
```

## Engineering

```text
accepted task rate
first-pass patch acceptance
repair rate
human code intervention
tokens / accepted delivery
cost / accepted delivery
time to PR
time to merge
```

## Agent protocol

```text
raw token count
compressed token count
compression ratio
decode success
semantic accuracy
task outcome delta
cost delta
```

---

# 31. Rollout plan

## Phase 0 — freeze current bounded engineering baseline

Do not alter successful FAST_PATCH semantics.

Add regression coverage around it.

## Phase 1 — durable normalized event inbox

Implement:

```text
ExternalEvent
delivery dedupe
async webhook processing
event persistence
task-scoped reconciliation
```

No Coordinator effects yet.

## Phase 2 — Coordinator shadow mode

Coordinator reads real events and emits proposed typed actions.

Do not execute them.

Compare against:

```text
existing fixed handler
human expectation
```

## Phase 3 — queue scheduling + dashboard

Implement:

```text
per-Team Developer concurrency
global Developer slots
fair queue
queue dashboard
```

## Phase 4 — human intervention UX

Implement:

```text
Needs You lane
HumanRequest
conversation response
safe automatic continuation
```

## Phase 5 — one end-to-end conversational flow

Enable:

```text
Trello comment → Coordinator → response/clarification → engineering
```

Remove overlapping fixed decision logic for this flow.

## Phase 6 — GitHub conversation ownership

Coordinator handles:

```text
review prose
questions
scope feedback
progress replies
```

Merge remains deterministic.

## Phase 7 — Slack outbound/thread support

Add:

```text
read thread
reply
ask clarification
send task updates
```

## Phase 8 — adaptive token economy

Introduce progress classification and evidence-backed budget escalation.

Existing hard budgets remain the final defense.

## Phase 9 — compact agent protocol experiment

Benchmark:

```text
verbose JSON
compact JSON
DSL
compression
```

## Phase 10 — DeepSeek benchmark

Add DeepSeek V4.1 Flash as experimental.

Replay identical historical cases and compare accepted outcomes.

---

# 32. What not to build

Do not build:

```text
always-running Coordinator LLM
AI call for every webhook
unrestricted GitHub/Slack/Trello API tool
default agent swarm
permanent Thinker/Reviewer/Tester chain
model-controlled merge
hard two-call rule for every task
huge transcript replay
RAG preload for every task
microservices only for architectural fashion
unbenchmarked symbolic language as default
```

---

# 33. Implementation priority

If implementing only the next five things:

```text
1. Durable Event Gateway + inbox + dedupe
2. Coordinator in shadow mode with typed semantic actions
3. Team/global execution queue and dashboard
4. Human intervention / Needs You conversation flow
5. One fully enabled conversational provider flow
```

Then:

```text
6. GitHub conversational coordination
7. Slack outbound/thread support
8. Adaptive progress-based token spending
9. Compact agent protocol benchmark
10. DeepSeek model benchmark
```

---

# 34. Final product behavior

The product should feel like this:

```text
Engineering

Developer slots      2 / 2
Queued               7
Waiting review       3
Needs you            1

ACTIVE
  Backend — Fix billing allocation       Terra
  Admin   — Add audit filters            Terra

QUEUED
  #1 Mobile — Fix login layout
  #2 Backend — Historical export

NEEDS YOU
  Live Execution
  Coordinator:
  "The reviewer added mobile support. Should mobile use the
   same minimum window size?"

  [ answer ... ] [ Send & Continue ]
```

Underneath:

```text
human/provider event
→ durable inbox
→ bounded Coordinator judgment
→ typed semantic action
→ deterministic authorization
→ bounded engineering execution
→ deterministic validation
→ provider effect
→ new event
```

The optimization goal is:

> **Maximize accepted engineering work per token/dollar while keeping the system reliable, understandable, and able to ask a human when judgment truly belongs to a human.**

Not:

> minimize model calls at all costs.

---

# 35. Research references

## Slack

Slack Events API documents that HTTP event requests should receive a 2xx within three seconds and recommends responding quickly, avoiding processing/reacting in the same request process, and using a queue.

- https://docs.slack.dev/apis/events-api/
- https://docs.slack.dev/apis/events-api/using-http-request-urls/

## GitHub

GitHub webhook troubleshooting/best-practice documentation recommends timely responses and asynchronous queue processing when needed. GitHub also documents that webhook deliveries may arrive out of order.

- https://docs.github.com/en/webhooks/testing-and-troubleshooting-webhooks/troubleshooting-webhooks
- https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks

## Linear

Linear webhooks include `Linear-Delivery`, `Linear-Event`, `Linear-Signature`, and `Linear-Timestamp`; Linear recommends HMAC signature verification and timestamp validation.

- https://linear.app/developers/webhooks

## OpenAI context

OpenAI Agents SDK distinguishes local application context from LLM-visible context. Local runtime/policy dependencies do not need to be placed in model prompts.

- https://openai.github.io/openai-agents-python/context/

## OpenAI tools

OpenAI Agents SDK supports Programmatic Tool Calling for coordinating multiple eligible tools with fewer model round trips. Keep it for bounded investigation where useful, not as a replacement for FAST_PATCH.

- https://openai.github.io/openai-agents-python/tools/

## OpenAI prompt caching

Current Responses API documents `prompt_cache_key` and prompt cache options for GPT-5.6+; explicit/implicit breakpoints are supported and the documented TTL option is currently 30 minutes.

- https://developers.openai.com/api/reference/

## Anthropic long-running agents

Anthropic’s long-running application harness guidance distinguishes context reset + structured handoff from compaction and describes context resets as useful when long tasks lose coherence.

- https://www.anthropic.com/engineering/harness-design-long-running-apps

## Prompt compression

Microsoft Research’s LLMLingua work demonstrates that prompts can be compressed substantially, including into representations that are difficult for humans to read, while retaining strong performance on evaluated tasks. These numbers are workload-specific and should not be assumed for this product without benchmarks.

- https://www.microsoft.com/en-us/research/project/llmlingua/llmlingua/
- https://www.microsoft.com/en-us/research/publication/llmlingua-compressing-prompts-for-accelerated-inference-of-large-language-models/
- https://www.microsoft.com/en-us/research/publication/longllmlingua-accelerating-and-enhancing-llms-in-long-context-scenarios-via-prompt-compression/

## DeepSeek V4.1 Flash

Keep DeepSeek V4.1 Flash as an experimental provider/model option and benchmark it against the current proven baseline rather than changing defaults based on public benchmarks alone.

- https://openrouter.ai/deepseek/deepseek-v4.1-flash
