# Shared project context

Bounded Developer requests reuse a small, deterministic project-facts prefix.
No additional model call builds it, and previous ticket conversations are not replayed.

## Current behavior

- Read root AGENTS.md/README excerpts and root/immediate-child package manifests.
- Include bounded directory layout, declared package scripts and tool names.
- Limit the combined evidence to 6,000 UTF-8 bytes; label excerpts as incomplete.
- Treat repository material as untrusted evidence, not permission to execute commands.
- Put this material before the original requirement, current source and failure evidence.
- Use a cache key derived from model, contract and actual shared text. Changes to included
  facts invalidate reuse; task IDs, worktree paths and unrelated code changes do not.
- On supported GPT-5.6/6 requests, place an explicit cache breakpoint after shared evidence
  with 30-minute TTL. Do not pay cache-write overhead for the changing task suffix.
- Apply this layout to fast patches, unit repairs, planning and bounded investigation.
- Save the key in request artifacts; existing receipts record cached and uncached usage.

Repository files remain the durable project memory. Facts are recomputed cheaply from
the current checkout rather than loading a potentially stale AI summary from another task.
This is not a semantic index, cross-task chat history or an automatic lessons-learning system.
Nested package details and scoped instructions still require task-specific retrieval.

## Verification and measurement

Tests cover identical prefixes across different task worktrees, refreshing changed conventions,
symlink exclusion, bounded multilingual text, dynamic-suffix separation and unchanged audit packets.
Live savings are unmeasured until deployed. Cache reuse depends on provider eligibility, prefix
length, matching model/schema/effort and lifetime; a cache key is not a guaranteed hit.
Cached tokens remain part of total input. Compare cost per validated delivery, not cache ratio alone.

Reference: [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
