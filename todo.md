1. need intake and deliver to be combines, to be like someone who views what takss are asigned and does job of github stuff commit mpusg see ther emessages of reviewers merge and so on, every gfucking action inside oproject to have access to github, need this shit to that top level ai agent which must not be high capabilities ai, simple and fast. in permission of github actions i mean all, i have an dalso i dont have buthtere exist for github. 
2. orchestrator must be like getting essage from that top layer ai agent and must doing like orchestrate between ai gaents give thinker take from thinker start executor and so on. hmsel must not be sontnest ai, fast and easy. 
3. thinker must think abotuthask, have all access all over the project must be like techincally accumulate and predict thinks what must be done in what projects and so on andf give that info to reviewer and tester and the executor
4. executor must execute 
5. rester must test 
6. reviewer must reviewers
7. if in menitoned ai agents stuff theres any flaw or not tsomehtinggood or super token burner or unoptimised tell me and lets discuss. 
8. i must be able from canwa besides menitoned directions to swire messaging directions wire up, it must be working now but check and if not fic, and that must do like set up able ai agents to takin each other. 
9. something btw burns too much tokens so thinabout this too what does and lets discuss. 

## Agreed implementation — 7 September 2026

One backend Deliverer replaces Intake and Delivery; the Orchestrator is the deterministic dispatcher, not another paid relay. Preserve existing tasks, history, graph wiring, and credentials. No authentication project or GitHub CI changes.

- [x] Consolidate active roles, migrate existing workflows, and expose one Deliverer.
- [x] Add bounded current-repository inspection for the configured OpenAI agents; retain useful context.
- [x] Add persisted, directed consultations distinct from workflow handoffs; no broadcast loops.
- [x] Complete authorized PR approval → merge → tracker Done, including revision freshness and multi-repository scope.
- [x] Configure starter models in the Default team database (Luna coordination, Sol planning/implementation/review, Terra test interpretation).
- [x] Run unit, PostgreSQL, frontend/browser checks and rebuild the local Docker deployment.

Completion means verified running behavior, not only UI controls or prompt instructions.

### Delivered behavior

- One active **Deliverer** handles task/message interpretation and GitHub delivery actions. The former Intake node becomes this agent; existing incoming/outgoing connections are redirected. Previous role/job history is retained, the redundant agent is disabled, and inherited knowledge remains available. Workflow migration publishes a new revision rather than rewriting historical snapshots.
- **Orchestrator runs as ordinary code**, not another model call. `Start next work` connections route typed outcomes. `Ask / reply` connections authorize focused questions; a controller may relay them without invoking AI itself.
- A question completes and checkpoints the current reasoning job, queues a read-only specialist reply, then queues a continuation with that answer. Question and reply appear as durable internal task messages. The task's business state and current plan are preserved. At most three consultations per continuation chain; stale/disallowed routes block once with an explanation.
- OpenAI engineering jobs can list, search and batch-read current tracked source within their task workspaces. Tool calls, returned source bytes, model turns and spending remain bounded; credentials and unsafe paths are excluded. File changes still use structured proposals and the existing Tool Gateway. The exact workflow node selects the runtime, even when multiple agents share a role.
- Clear PR approval comments/reviews from authorized collaborators trigger deterministic merge checks. Approval and evidence are repository/SHA-specific, metadata actions target the originating PR, and a task reaches Done only after every changed repository scope is merged. Tester → Deliverer is supported as well as Reviewer → Deliverer.

### Verification and scope

- Backend lint, formatting and type checking passed; **375 unit tests** passed, including preserving already-paid usage when a later tool-loop request fails.
- **15 PostgreSQL integration tests** passed, including consultation persistence/replay, exact-node selection, multi-repository merge state, and upgrade → downgrade → upgrade.
- Frontend lint, formatting, type checking and production build passed; **32 unit tests and 3 browser regressions** passed.
- Docker backend, worker and frontend rebuilt; database at **0056**, Default workflow at **23**. Starter runtime configuration validated without starting real tasks.
- Native tool calls and question initiation currently use the OpenAI adapter. Anthropic/Google retain their existing bounded context path and can answer consultation jobs; native tool adapters for them are a follow-up, not claimed complete here.
- GitHub actions remain an explicit typed set (PR title/body, commit-message update and gated merge), not arbitrary access to every GitHub API operation. Merge tests use controlled fixtures; no real PR was merged as part of this verification.
- No authentication rollout or GitHub workflow changes. Migration rollback restores the pre-change configuration snapshot and refuses to erase completed work on the new revision; use a forward migration after new work completes.
