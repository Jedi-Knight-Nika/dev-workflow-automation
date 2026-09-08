# First bounded native-agent task smoke test

Use one low-risk, narrowly scoped task to verify the native workflow on the deployment host. This is an operational smoke test, not a real-model benchmark; do not infer success rates or cost savings from it.

## Before you start

- Complete the Team admission checklist in [initial setup](initial-setup.md): configure a supported native Developer harness/provider/model, allow only the intended repository UUID, and use a prepared dependency image.
- Register current verified pricing, including its source and effective date, in the pricing UI. Do not use guessed rates.
- Set an explicit hard Developer allowance plus an explicit task budget and cumulative Team budget. All applicable task, Team, and role limits apply; raising a limit does not reset prior usage.
- Keep Thinker and Reviewer disabled for this routine task. They are optional and require their own limits if enabled.
- Keep auto-merge disabled. Configure validation commands first; validation runs separately in a no-network, credential-free container.
- Leave `V2_SCHEDULER_ENABLED=false` while you inspect configuration. A manually created task does not itself authorize or start automatic paid work.

## Run one task

1. Create one manual task with a clear, low-risk requirement for the allowed repository. Check its scope, task budget, and Team budget before starting it.
2. Explicitly enable execution/scheduling only when ready, then explicitly start that task. Do not treat task creation, model/harness changes, or enabling enrollment as a request to run a model.
3. Observe the ticket status, job state, metering, native-session artifact, and validation output. The Developer works in its persistent native session; the validator is a separate offline execution.
4. If source or review feedback needs work, supply the actionable delta. Compatible continuation resumes the existing native session and sends new feedback, rather than rebuilding a full transcript.

## Read the result

- A completed job means that execution unit finished; it does not by itself mean the delivery outcome is merged.
- Read the status history, latest job failure if any, validation output, and AI-run artifact. Check that the offline validation command ran against the intended change.
- If a PR is created, keep auto-merge off and wait for required CI and authorized human review. Review waiting and polling do not make AI calls.
- Treat a failed, paused, or budget-limited task as smoke-test evidence. Do not claim a successful real-model benchmark or numeric cost savings.

## Stop safely

- Use **Team Stop work** for a durable brake: the Team remains enabled, current tickets pause, and jobs lose leases.
- To wake the Team, enable execution. This clears the Team brake but does not automatically resume paused tickets; use explicit Resume work for each task you choose to continue.
- Stop/wake, pause/resume, and session changes do not reset historical usage. An already accepted provider request cannot be undone instantly, so confirm the task has paused before changing scope or ending the test.
