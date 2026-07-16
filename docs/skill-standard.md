# Skill standard

## Required layout

```text
skills/<skill-name>/
  SKILL.md
  agents/openai.yaml       # recommended
  references/              # optional
  scripts/                 # optional
  assets/                  # optional
```

`skills/` is flat. Drafts, personal skills, fixtures, and deprecated experiments are developed outside this public tree. A previously promoted skill may remain here with lifecycle `deprecated` so existing users have a migration source; it must not remain in default collections.

## SKILL.md

Frontmatter requires:

```yaml
---
name: skill-name
description: Use when the concrete triggering conditions apply.
---
```

- Keep `name` identical to the directory and catalog key.
- Describe triggering conditions precisely enough to distinguish near neighbors.
- Keep the core workflow concise; move heavy reference material into directly linked files.
- State permissions, mutation boundaries, completion criteria, and failure behavior.
- Prefer deterministic scripts for mechanical validation and fragile state transitions.

## Tests and evaluations

- Scripts require deterministic tests.
- Stable skills require trigger and non-trigger cases under `evals/<skill-name>/`.
- High-risk side effects require adversarial cases, preview behavior, approval boundaries, and rollback verification.
- Fixtures, real model runs, human review, and production observation must be labeled as different evidence levels.

## Portability and safety

- Do not hard-code home directories, customer identifiers, private repositories, credentials, or tool-specific global paths.
- Declare required and optional dependencies and the behavior when they are absent.
- External mutations follow: inspect, preview, show exact mutation, obtain approval, execute, verify, report.
- Adapted work records the upstream repository, pinned commit, original license, and modification summary.
