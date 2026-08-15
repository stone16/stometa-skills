# Changelog

## Unreleased

- Establish the public repository contract, catalog, promotion policy, documentation, and validation baseline.
- Promote `doc-steward` 1.0.0 as the first stable public Skill.
- Add public evidence, synthetic evaluations, deterministic tests, and a clean-copy package/CLI smoke test without claiming runtime discovery.
- Tighten `doc-steward` invocation routing and completion criteria, remove stale predecessor history from runtime reference, and record the unverified private-cutover state explicitly.
- Add `doc-steward` `exclude_paths` configuration so a repository can take a frozen or vendored documentation subtree out of audit scope. Entries are target-relative paths, not directory names; an absolute or escaping entry raises.
