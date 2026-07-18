# Compatibility

Compatibility is evidence, not an aspiration. The catalog uses three states:

- `verified`: the current revision passed an installation and discovery smoke test;
- `expected`: the structure follows the platform contract but has not passed the current smoke test;
- `unsupported`: the adapter is intentionally unavailable.

## Current repository state

| Adapter | State | Notes |
|---|---|---|
| Agent Skills directory format | expected | `doc-steward` passes a clean-copy structure and CLI execution smoke; actual Agent runtime discovery remains unverified |
| skills.sh editable install | expected | Verify the exact public Git revision after release |
| Claude Code plugin | unsupported | No native plugin manifest ships in this promotion |
| Codex plugin | unsupported | No native plugin manifest ships in this promotion |
| Multica Workspace GitHub import | expected | Import a released skill from its GitHub tree URL, then attach it to an agent |
| Multica repository-scoped discovery | expected | Repo-specific skills remain in the checkout and depend on the underlying tool's native discovery |

## Adapter rule

Every adapter points at the canonical `skills/` tree. Generated packages may select or decorate files, but they must be reproducible from the canonical source and must not accept direct edits.

When an adapter is introduced, add a pinned smoke test and update both language versions of the README. Do not mark the adapter `verified` from schema validation alone.

Multica-specific behavior and the release checklist are documented in [multica.md](multica.md).
