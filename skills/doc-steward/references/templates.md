# doc-steward Templates — Skeletons by tier

Scaffolds ENFORCE writes for an ABSENT file (it never overwrites a present file).
This is the public, harness-neutral core. Placeholders are written as
`[Bracketed]`; no personal identity or response ritual is scaffolded.

---

## 1. AGENTS.md — canonical cross-tool source (Standard+)

`AGENTS.md` is the single canonical charter; `CLAUDE.md` is a symlink/bridge to it
(see §2). Codex reads this file directly.

```markdown
# [Project Name]

**Stack**: [Tech summary in one line]

## Architecture Map

\`\`\`
[project]/
├── src/              # [source]
├── tests/            # [tests]
├── docs/             # [docs + decisions/]
└── AGENTS.md         # this charter (CLAUDE.md is a symlink to it)
\`\`\`

## Commands

\`\`\`bash
[build]   # build
[test]    # run tests
[run]     # run locally
\`\`\`

## Verification Contract

Before claiming done, run [the verification command]; "the command is real" is
checked by [where]. Never fabricate output.

## Safety-Rails / Do Not

- Never blind-delete repo-specific content.
- [Forbidden pattern 1]
- [Forbidden pattern 2]

## Shelf routing (Progressive Disclosure)

| When you are… | Read first |
|---|---|
| [working on auth] | `docs/[auth].md` |
| [touching the UI] | `DESIGN.md` |

## Definition of Done

- [ ] [checkable completion criterion 1]
- [ ] Tests pass; verification command run with fresh evidence.
```

---

## 2. CLAUDE.md — thin bridge (Standard+)

Default form is a **symlink**: `ln -s AGENTS.md CLAUDE.md` (zero drift). Use the
`@import` overlay below ONLY when a genuine Claude-specific delta exists.

```markdown
@AGENTS.md

<!-- Claude-specific delta only — nothing duplicated from AGENTS.md. -->
```

For a Simple-tier repo, a single standalone `CLAUDE.md` (or `AGENTS.md`) suffices —
use the AGENTS.md skeleton's body directly:

```markdown
# [Project Name]

**Stack**: [one line]

## Architecture Map
[directory tree]

## Commands
[essential commands only]

## Verification Contract
[verification pointer]

## Definition of Done
[checkable criteria]
```

---

## 3. `.claude/rules/<name>.md` — `paths:`-scoped lazy rule (Complex / profile)

A true lazy-load rule (Claude Code): it fires only on a path match. Never `@import`
this — it is meant to load conditionally. `paths:` reliability is per-tool; keep the
body short and self-contained.

```markdown
---
paths: ["[glob/**/*.ext]"]
---

When touching [this area], read and conform to [the relevant shelf doc].
[One or two guardrails specific to this subtree.]
```

Frontend routing example (one rule per design-system subtree in a monorepo):

```markdown
---
paths: ["**/*.{tsx,jsx,vue,svelte}", "components/**", "src/components/**", "app/**/*.css"]
---

When touching UI, read and conform to DESIGN.md (this repo's design system). Reuse
the canonical component library and tokens; do not invent a second palette or
ad-hoc components.
```

---

## 4. MADR — Markdown Any Decision Record (`docs/decisions/NNNN-title.md`)

Canonical minimal template; sections are opt-in, not mandatory boilerplate
(DECISION-03). Every recommendation states Accepted → Rejected → Constraint
(DECISION-01).

```markdown
# [NNNN]. [Short decision title]

- Status: [proposed | accepted | superseded by [link]]
- Date: [YYYY-MM-DD]

## Context

[The forces at play; what makes this a decision.]

## Decision

We will [accepted choice].

## Considered Alternatives

- [Alternative A] — rejected because [constraint that ruled it out].
- [Alternative B] — rejected because [constraint].

## Consequences

[Trade-offs accepted. Record any open item as:]
TODO_DECISION: [question] | options: [list] | who resolves: [role]
```

---

## 5. DESIGN.md — frontend profile (uppercase filename)

Emitted only when the frontend profile fires (shadcn `components.json`, or a build
signal + a surface signal). An existing DESIGN.md is linted, not regenerated.
Color/spacing/typography point to the token source, never the sole hardcoded copy
(DESIGN-03).

```markdown
# [Project] Design System

## Technical Foundation / Stack            <!-- required -->
[UI framework + styling engine + component library + versions]

## Color System                            <!-- required -->
Defined in [token source, e.g. tokens.json / globals.css @theme]. Do NOT hardcode
hex values in components — reference the token source.

## Typography                              <!-- required -->
[Typeface + weights + scale + fallback stack]

## Component Patterns                       <!-- required -->
Canonical library: [name + config]. States covered: [hover/focus/disabled/...].

## Design Essence                          <!-- recommended -->
[The intended feel in a sentence or two.]

## Spacing / Layout / Radius / Motion      <!-- recommended -->
[Scales, pointing to the token source.]

## Anti-Patterns (do NOT)                   <!-- recommended -->
- Do not invent a second palette or ad-hoc components.

## Freshness / Verification                 <!-- recommended -->
Last verified [YYYY-MM-DD] against [tokens / Storybook]. Re-verify when [trigger].

## Accessibility                            <!-- optional -->
## Known Gaps                               <!-- optional -->
```
