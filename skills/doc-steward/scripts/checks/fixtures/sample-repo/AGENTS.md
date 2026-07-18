# Sample Repo AGENTS.md (deliberately defective)

This file carries a KNOWN dead reference pointer so doc_lint's link_check fires
LINK-01 deterministically.

Live pointer (resolves fine): @./CLAUDE.md

Dead pointer (MUST be flagged LINK-01): @./missing-charter.md

The following dead pointer is inside a fenced block and MUST be skipped by the
link_check failure-mode guard:

```
@./guarded-dead.md
```
