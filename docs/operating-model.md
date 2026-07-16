# Operating model

This model solves one recurring problem: a useful prompt starts inside one repository, gets copied into several places, and eventually nobody knows which copy owns the behavior.

The remedy is not to publish everything. Give each skill the smallest scope that matches its evidence, then move canonical ownership only when the evidence changes.

## The three layers

| Layer | Typical content | Canonical owner | Promotion signal |
|---|---|---|---|
| Repository | local workflows, paths, domain rules, project profiles | the repository that needs the behavior | the same job recurs elsewhere |
| Shared private | personal or organizational methods, runtime evidence, candidates under review | a private control plane | the common method is portable and safe to expose |
| Public | stable skills, sanitized examples, tests, provenance, and public evidence summaries | a public skill repository | normal versioning and maintenance |

You do not need all three layers on day one. Start with repository skills. Add a private shared layer when copying becomes a maintenance problem. Add a public layer when outside reuse and contribution justify the long-term obligation.

## Placement decision

Ask these questions in order:

1. Does the skill require this repository's paths, vocabulary, data, credentials, or release process? Keep it repository-scoped.
2. Has the same job been observed in distinct contexts? If no, keep collecting evidence where it started.
3. Can the common method be separated from personal, customer, and operational facts? If no, consolidate privately.
4. Can another maintainer understand its trigger, permissions, failure behavior, and tests without private context? If no, continue incubation.
5. Is somebody willing to own compatibility, review, deprecation, and security reports? If yes, open a promotion case.

Reuse is a nomination signal, not an automatic promotion. Three copies of the same customer-specific workflow are still customer-specific.

## Raise-bar and sink-down flow

```text
observe locally
  -> nominate
  -> consolidate privately
  -> evaluate and sanitize
  -> approve ownership transfer
  -> publish and maintain

public regression or lost portability
  -> deprecate the public behavior
  -> keep local specialization as a profile or extension
```

The flow changes ownership, not just location. After promotion, local repositories reference or extend the public source. They do not retain an independently edited copy.

## Copyable prompts

These prompts are intentionally tool-neutral. Replace bracketed values and keep the first pass read-only.

### 1. Audit one repository

```text
Inspect the agent skills in [repository path]. Do not modify files.

For each skill, report:
- its trigger and intended job;
- repository-specific paths, vocabulary, data, and permissions;
- overlap with other skills in this repository;
- missing tests, provenance, or failure behavior;
- recommended scope: repository, shared-private candidate, or public candidate.

Treat reuse as a nomination signal only. Cite file:line for every claim and end with the three highest-value maintenance actions.
```

### 2. Nominate across repositories

```text
Compare skills that perform [job] across [repository list]. Do not copy raw prompts or private data into the report.

Determine:
- whether they share one generative method or only similar names;
- the common trigger, workflow, permissions, and completion criteria;
- which facts must remain local profiles or extensions;
- observed usage across distinct contexts;
- blockers for consolidation or public promotion.

Return one decision: keep-local, consolidate-private, nominate-public, or merge-with-existing. Include evidence and uncertainty.
```

### 3. Review a public promotion

```text
Act as an independent promotion reviewer for [candidate path]. The author cannot be the only evaluator.

Test six gates: generative, distinctive, separable, portable, legal-and-safe, and maintainable. Inspect SKILL.md, bundled files, tests, evidence, provenance, and installation claims.

Look specifically for personal paths, customer facts, credentials, raw prompts, hidden tool assumptions, duplicated canonical sources, unsafe side effects, and unsupported compatibility claims.

Return approve, defer, or reject. List blocking findings first with file:line citations. Do not waive a judgment gate because CI passes.
```

### 4. Design a repository profile

```text
The public skill [skill name] owns the common method. Design the smallest repository-local profile for [repository].

Keep only local paths, commands, thresholds, vocabulary, permissions, and overrides. Reference the public skill explicitly. Do not duplicate its workflow body. State whether the relationship is profile_of, extends, depends_on, forked_from, or replaces, and explain why.
```

## Minimum governance

- One canonical source per behavior.
- One named maintainer per public skill.
- An independent reviewer for promotion.
- Evidence labels that distinguish fixtures, model runs, human review, and production observation.
- Explicit `deferred`, `rejected`, and `deprecated` states.
- A private boundary that excludes raw task data and secrets from public evidence.

If those rules feel expensive, keep the skill local longer. Public release creates a maintenance promise; it is not a reward for writing a clever prompt.
