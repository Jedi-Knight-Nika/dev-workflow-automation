# Resources UX MVP plan

The Integrations and Repositories domains remain separate. This work connects their user
experience without moving credentials into repository management or repository lifecycle into
integration management.

## Implementation sequence

1. Add shared user-facing resource status and detail-drawer components.
2. Extend compact backend read models with integration usage and repository health/usage.
3. Add safe resource actions: task-source sync request, repository archive/restore, dependency
   inspection, and batch repository import.
4. Group Integrations by category and move configuration into a detail drawer.
5. Replace the populated repository onboarding/card wall with a scalable responsive list and
   repository detail drawer.
6. Add cross-links between GitHub, task-source repository selection, and Repositories.
7. Verify migrations, backend contracts, frontend behavior, and production builds.

## Deliberately deferred

- A global multi-page onboarding wizard.
- Trello outbound list/state synchronization.
- Repository file browsing and detailed indexing history.
- Marketplace/search UX for integrations.
- Advanced per-file embedding controls.

These are separate product capabilities and are not required to make daily resource management
clear, scalable, and safe.
