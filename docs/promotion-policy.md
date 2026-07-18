# Promotion policy

Status: `active incubation baseline v0`, human approval required.

## Roles

| Role | Authority |
|---|---|
| Skill Steward | Finds candidates and assembles evidence; cannot publish |
| Repository owner | Confirms task history and local constraints |
| Promotion Reviewer | Challenges generality, safety, provenance, and overlap |
| Public maintainer | Approves, delays, or rejects promotion |
| CI | Enforces structural and packaging gates; cannot approve judgment calls |

The author of a skill cannot be its only evaluator.

## Nomination signals

A candidate may be nominated when at least one signal exists:

- the same job appears in three or more repositories;
- the skill has at least five accepted or edited executions across two distinct repositories;
- the same correction recurs in three independent tasks;
- a maintainer explicitly nominates it with a written reason.

Nomination starts evaluation. It does not authorize publication.

## Scope transitions

Promotion begins before a public PR:

| Observation | Decision | Ownership change |
|---|---|---|
| duplicate behavior inside one repository | consolidate locally | none |
| similar names but different jobs | keep separate and clarify triggers | none |
| repeated job across repositories, still personal or context-bound | nominate for shared-private consolidation | repository owners transfer the common method to the private control plane |
| common method passes every public gate | nominate for public promotion | the public repository takes canonical ownership after approval |
| public method needs local paths, thresholds, or business rules | add `profile_of` or `extends` locally | no copy of the public workflow body |
| public behavior loses support or has a replacement | deprecate with a migration window | history stays public; default distribution moves to the replacement |

Cross-repository reuse can move a skill upward for evaluation. It cannot skip privacy, portability, or maintenance review. Local specialization moves downward as a profile or extension, never as a silent editable copy.

## Public gates

Every promotion must pass all six gates:

1. **Generative** — handles a class of problems rather than replaying one case.
2. **Distinctive** — an existing public skill cannot absorb the behavior cleanly.
3. **Separable** — the common method can be extracted from private facts and configuration.
4. **Portable** — evidence covers at least two distinct contexts.
5. **Legal and safe** — privacy, secret, permission, and provenance reviews pass.
6. **Maintainable** — an owner, tests, evaluation cadence, and rollback path exist.

Automated checks may block promotion. They cannot waive a gate.

## Required evidence

`evidence/<skill-name>.yaml` records:

- evidence level and sample counts;
- repositories or contexts as anonymized identifiers;
- trigger, non-trigger, execution, and installation results;
- reviewer and review date;
- provenance and license status;
- known limitations and the next review trigger.

Raw prompts, outputs, customer data, private repository names, and usage receipts stay private.

## State machine

```text
incubating
  -> promotion-candidate
  -> evaluation
  -> awaiting-human-approval
  -> promotion-pr
  -> promoted
```

`blocked`, `deferred`, and `rejected` are explicit outcomes. A failed gate returns the candidate to private incubation with the blocker recorded.

## Ownership transfer checklist

Before merge:

- sanitize the extracted source;
- add catalog, collection, evidence, evaluation, and notices;
- validate installation adapters that claim support;
- replace the previous implementation with a profile/pointer or delete it. When a
  cross-repository dependency makes public-first merge order unavoidable, the
  cutover PR must already contain that deletion/pointer, pass review, and be
  blocked only on public dependency availability. Link it when public; otherwise
  record an anonymized revision receipt and an access-controlled maintainer
  attestation without exposing the private repository;
- record `extracted_from`, prior commit, and migration notes;
- run an independent review of the public contract.

A paired cutover is not `promoted` when only the public PR merges. The public
maintainer who merges the Promotion owns the cutover and must merge the
already-reviewed pointer/deletion PR within 30 minutes. If that second merge
cannot complete inside the window, that maintainer must revert the exact public
Promotion merge commit on `main` instead of keeping two editable canonical
copies. Record both the cutover revision and either the dependent merge or public
revert revision in the access-controlled review record.

## Deprecation and private extensions

Published history cannot become private again.

- Personalization creates a private profile or extension.
- A public behavior change follows normal review and version history.
- An obsolete skill is marked deprecated with a replacement and migration window. Its source remains under `skills/` for that window, while catalogs and default adapters exclude it.
- A security issue may remove current distribution artifacts, but history and disclosure follow the security policy.
