# Changelog

## Unreleased

- Establish the public repository contract, catalog, promotion policy, documentation, and validation baseline.
- Promote `doc-steward` 1.0.0 as the first stable public Skill.
- Add public evidence, synthetic evaluations, deterministic tests, and a clean-copy package/CLI smoke test without claiming runtime discovery.
- Tighten `doc-steward` invocation routing and completion criteria, remove stale predecessor history from runtime reference, and record the unverified private-cutover state explicitly.
- Add `doc-steward` `exclude_paths` configuration so a repository can take a frozen or vendored documentation subtree out of the document corpus. Entries are target-relative paths, not directory names; absolute, drive-qualified, escaping, empty, non-string and non-list configurations are rejected. A narrowed report discloses `excluded_paths`, `corpus_scope` and the boundary of what exclusions affect. A NUL byte, which can match no filesystem path, is rejected rather than silently narrowing nothing.
- Stop `doc-steward` LINK-01 from auditing an `@path` or `@import` inside an inline-code span. Backticks are the documented way to mention a path without importing it, so a quoted pointer is a description, not routing. Pointer tokenization no longer swallows backticks or emphasis punctuation, and the span predicate is shared by all three extractors. Also fix an escaped backtick failing to close an open code span, which silently dropped a live pointer.
