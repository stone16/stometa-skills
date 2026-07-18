---
name: sample-repo
version: 1.0
description: The helper.
---

# Sample Repo CLAUDE.md (deliberately defective)

This fixture exists to make doc_lint's deterministic checkers fire on KNOWN
defects so test_doc_lint can assert specific finding ids.

Known frontmatter defects in this file:

- FRONT-01: the description "The helper." is too short (<40 chars), is not
  verb-first (opens with the article "The"), and lacks both the "Use when"
  and "Not for" markers.
- FRONT-04: `version` is "1.0", which is not semver X.Y.Z.
