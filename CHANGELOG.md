# Changelog

## Unreleased

- Establish the public repository contract, catalog, promotion policy, documentation, and validation baseline.
- Promote `doc-steward` 1.0.0 as the first stable public Skill.
- Add public evidence, synthetic evaluations, deterministic tests, and a clean-copy package/CLI smoke test without claiming runtime discovery.
- Tighten `doc-steward` invocation routing and completion criteria, remove stale predecessor history from runtime reference, and record the unverified private-cutover state explicitly.
- Stop `doc-steward` LINK-01 from auditing an `@path` inside an inline-code span. Backticks are the documented way to mention a path without importing it, so a quoted pointer is a description, not routing.
