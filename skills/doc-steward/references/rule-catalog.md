<!-- GENERATED FILE — do not edit by hand.
     Source of truth: scripts/lib/rules.py
     Regenerate: python3 scripts/gen_rule_catalog.py
     Drift check: python3 scripts/gen_rule_catalog.py --check -->

# doc-steward Rule Catalog

Generated from `scripts/lib/rules.py` (the canonical rule set). Tags:
**Sev** P0/P1/P2 · **Tier** min tier where required · **Auto** A\*=auto-when-preconditions-hold / E=escalate · **Src** S=spec-required / H=house-opinion · **Check** deterministic/inspector/manual (owner).


_48 rules across 11 categories._


## cross-tool

- **CROSS-01** [P0·Standard·E·S] — owner `inspector:inspector-taxonomy`

## structure/residency

- **CROSS-02** [P0·Standard·E·S] — owner `inspector:inspector-taxonomy`
- **STRUCT-01** [P1·Simple·E·S] — owner `inspector:inspector-structure`
- **STRUCT-02** [P0·Standard·E·S] — owner `inspector:inspector-structure` · self-ruler
- **STRUCT-03** [P2·Simple·E·H] — owner `inspector:inspector-structure`
- **STRUCT-04** [P1·Simple·E·S] — owner `inspector:inspector-structure`
- **STRUCT-05** [P1·Standard·E·S] — owner `inspector:inspector-structure`
- **STRUCT-06** [P1·Simple·E·S] — owner `deterministic:presence_check` · remedy: Create the missing required root document surface(s): Simple needs `<target>/AGENTS.md` or `<target>/CLAUDE.md`; Standard and Complex need both; Complex also needs `.claude/rules/<name>.md` and `docs/decisions/0001-<title>.md`. Scaffold only after an explicit request.
- **RESID-01** [P1·Simple·E·S] — owner `inspector:inspector-structure`
- **RESID-03** [P1·Simple·E·H] — owner `inspector:inspector-structure`

## staleness/volatility

- **RESID-02** [P1·Standard·E·H] — owner `inspector:inspector-structure`
- **VOL-01** [P1·Standard·E·S] — owner `inspector:inspector-staleness` · self-ruler
- **VOL-02** [P1·Standard·E·S] — owner `inspector:inspector-staleness`
- **STALE-01** [P1·Simple·E·S] — owner `inspector:inspector-staleness`
- **STALE-02** [P2·Standard·E·H] — owner `inspector:inspector-staleness`

## taxonomy/altitude

- **TAXO-01** [P1·Standard·E·S] — owner `inspector:inspector-taxonomy`
- **TAXO-02** [P2·Standard·E·H] — owner `inspector:inspector-taxonomy`
- **TAXO-03** [P1·Standard·E·S] — owner `inspector:inspector-taxonomy`
- **TAXO-04** [P1·Standard·E·H] — owner `inspector:inspector-taxonomy`

## links/routing

- **LINK-01** [P1·Simple·A*·S] — owner `deterministic:link_check` · autofix-when: explicit OLD=NEW mapping names one existing in-root replacement and the dead pointer occurs exactly once · remedy: Replace the cited pointer or Markdown-link target with a repository-relative path that exists, then rerun `python3 scripts/checks/doc_lint.py --target <repo-root> --json`.
- **LINK-02** [P0·Standard·E·S] — owner `deterministic:link_check` · remedy: Replace the cited `@import` edge with a direct pointer to the canonical document so the graph is acyclic and no chain exceeds five hops.
- **LINK-03** [P1·Standard·E·H] — owner `deterministic:link_check` · remedy: Rewrite the cited pointer as `When <recognizable situation>, read <relative-path>` and keep the target repository-relative.
- **LINK-04** [P2·Standard·E·H] — owner `deterministic:link_check` · remedy: Replace the nested pointer chain with one direct pointer from the cited document to the final target.

## frontmatter/discoverability

- **FRONT-01** [P1·Simple·E·H] — owner `deterministic:frontmatter_check` · remedy: Rewrite `description` to 40-500 English characters, start with an action verb, and include `Use when ...` plus `Not for ...`.
- **FRONT-02** [P2·Simple·E·H] — owner `deterministic:frontmatter_check` · remedy: Keep `description` English-only and move translated trigger text to a separate field or document.
- **FRONT-03** [P2·Standard·E·H] — owner `deterministic:frontmatter_check` · remedy: Differentiate the two `description` trigger clauses so each `Use when ...` names a distinct situation.
- **FRONT-04** [P1·Simple·A*·H] — owner `deterministic:frontmatter_check` · autofix-when: missing `version` insertable from the repo's known version; description already present · remedy: Add a leading `---` frontmatter block with the fields required for this document type; write `version` as `X.Y.Z` when present.
- **FRONT-05** [P2·Standard·E·H] — owner `deterministic:frontmatter_check` · remedy: Replace the cited value with glossary entries in `term: definition` form.

## verification

- **VERIFY-01** [P0·Simple·E·S] — owner `manual:manual`
- **VERIFY-02** [P0·Simple·E·S] — owner `manual:manual`
- **VERIFY-03** [P2·Standard·E·H] — owner `manual:manual`

## decisions/ADR

- **DECISION-01** [P1·Standard·E·S] — owner `manual:manual`
- **DECISION-02** [P1·Standard·E·S] — owner `manual:manual`
- **DECISION-03** [P2·Standard·E·H] — owner `manual:manual`

## learning

- **LEARN-01** [P1·Standard·E·S] — owner `manual:manual`
- **LEARN-02** [P1·Simple·E·S] — owner `manual:manual`
- **LEARN-03** [P2·Standard·E·H] — owner `manual:manual`
- **LEARN-04** [P2·Complex·E·H] — owner `manual:manual`

## safety-rails

- **SAFETY-01** [P0·Simple·E·S] — owner `manual:manual`

## design-system

- **DESIGN-01** [P0·Standard·E·S] — owner `inspector:inspector-design`
- **DESIGN-02** [P1·Standard·E·S] — owner `inspector:inspector-design`
- **DESIGN-03** [P1·Standard·E·S] — owner `inspector:inspector-design`
- **DESIGN-04** [P1·Standard·E·S] — owner `inspector:inspector-design`
- **DESIGN-05** [P2·Standard·E·S] — owner `inspector:inspector-design`
- **DESIGN-06** [P2·Standard·E·H] — owner `inspector:inspector-design`
- **DESIGN-07** [P2·Standard·E·H] — owner `inspector:inspector-design`
- **DESIGN-08** [P2·Standard·E·H] — owner `inspector:inspector-design`
- **DESIGN-09** [P2·Standard·E·H] — owner `inspector:inspector-design`
