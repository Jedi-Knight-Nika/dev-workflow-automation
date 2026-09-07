# Executor workspace editing and validation

Executor now receives direct workspace tools when its provider supports native tools
and its workflow action is `IMPLEMENT_PLAN`. These operate in the existing task checkout;
there is no new checkout, interactive editor, or container created for each edit.
Read-only consultations and other roles do not receive these mutation tools.

## Same-run correction

1. Inspect current source with list/search/batched reads or `read_workspace_file`.
2. Apply a small exact-text replacement with `edit_workspace_file`. For a new file,
   supply empty `old_text` and the complete new content. An existing file requires
   exactly one match. A missing or ambiguous match returns an error without a write.
3. Run `run_workspace_checks` in the relevant directory, such as `backend` or
   `frontend`. Where `RUN_COMMANDS` is granted, `run_workspace_command` accepts a
   non-interactive argument array for focused tests and other permitted commands.
4. Read the returned exit code and bounded diagnostics, correct the edit or command,
   and retry within the same provider conversation and job budget.
5. Return a structured outcome with empty `files`, `patches`, and `delete_files`.
   Edits have already been applied; final proposals cannot apply them twice.

`delete_workspace_file` supports explicit deletion with the existing delete permission.
Every workspace operation requires an exact key from `executor_workspaces` (`.` for
a single repository). The new-file reader also sees files not yet tracked by Git.

The runtime still inspects actual Git changes and performs final validation before
normal workflow routing. It re-runs detected checks in directories used by the
interactive command/check tools, as well as the repository root. Test/check failures do not
mean that code has been delivered. No commit, PR, or merge tool was added here.
Providers without native tool support retain the previous proposal-based path.

## Permissions and limits

- Existing Role permissions and Team execution policy remain authoritative. No
  permissions or task budgets are increased by this change.
- File reads/writes/deletes and commands pass through `ToolGateway`. Paths resolve
  inside the assigned workspace. Secret paths, including symlink aliases, are
  excluded from direct file tools.
- Arbitrary commands require `RUN_COMMANDS`; detected checks use existing validation
  and dependency-install capabilities. Only dependency setup receives the existing
  package-registry environment. Arbitrary commands do not receive that environment.
- Interactive commands have a maximum requested timeout of 120 seconds, further
  restricted by Team policy. Command tool output retains at most 6,000 characters
  per stdout/stderr stream. Check results retain their existing bounded diagnostics.
- Stop/takeover is checked before tool operations and while they run. Cancelling a
  running command terminates its process tree. Completed edits remain in the task
  workspace for inspection or continuation; cancellation is not a rollback.
- Explicit policy approvals stop the model loop immediately instead of spending
  additional calls asking the model to bypass the approval.
- Source-byte, tool-call, model-call, token, and spending limits still apply. Edits
  invalidate source-read tracking without resetting those allowances. Model history
  retains tool errors and results, so it is useful context but still consumes tokens.

The gateway confines file-tool paths and command working directories; it is **not**
an OS filesystem sandbox for arbitrary programs. Commands run with the worker
container's existing mounts, process identity, and network access. This change does
not grant access to the host terminal or provide a new security isolation boundary.

## Verification and rollout

`tests/infrastructure/test_executor_tools.py` covers an actual temporary-file and
subprocess edit/error/test/fix/pass sequence using a scripted provider (no paid calls),
new-file reads, preserved limits, secret aliases/traversal, command permissions and
working directories, subdirectory checks, approval suspension, cancellation, invalid
patch classification, and rejection of duplicate final edits.

Rebuild and recreate the backend and worker images to load these tools. No database
migration or editor installation is required. This does not resume paused tasks or
erase historical usage. Tasks already over their lifetime budget remain blocked by
that budget; choose a deliberate budget adjustment or a new scoped test rather than
repeatedly reopening them. A successful local loop test is not proof that every
feature will complete within the configured model allowance.
