# Architecture

Status: `active incubation baseline v0`.

## Product topology

```text
Business repository
  repository-specific skills and profiles
              |
              | repeated evidence
              v
Private control plane
  discovery, incubation, usage evidence, review
              |
              | approved ownership transfer
              v
stometa-skills
  stable public canonical source
```

The private control plane and its runtime data are intentionally absent from this repository. Public code receives only the extracted method, sanitized examples, provenance, and evidence summary required to evaluate the skill.

## Independent axes

Scope, visibility, and lifecycle are stored as independent facts:

| Axis | Examples | Invalid inference |
|---|---|---|
| Scope | repository, shared, public | Shared use does not prove public safety |
| Visibility | private, public | Public-safe content does not prove generality |
| Lifecycle | incubating, validated, stable, deprecated | Maturity does not decide who may read data |

## Canonical ownership

Promotion transfers ownership. After a skill enters this repository:

1. its public method is maintained here;
2. the private or repository source is deleted or reduced to a profile/pointer;
3. repository facts remain local;
4. adapters reference the public source without copying its body.

Long-running manual synchronization between public and private copies is prohibited because it creates silent drift and blocks outside contributions.

## Profiles and extensions

Use these relationships when a local repository needs more detail:

- `profile_of`: supplies paths, commands, thresholds, or local defaults;
- `extends`: adds a repository-only step or gate;
- `depends_on`: invokes another stable capability;
- `forked_from`: records an intentional incompatible branch and upstream commit;
- `replaces`: records a deprecation path.

The public skill remains authoritative for the common method.

## Distribution adapters

The source tree stays harness-neutral. Platform manifests, installer metadata, and Multica examples are generated or validated against `skills/`; they do not contain another skill implementation.

Adapter availability is documented only after a smoke test. See [Compatibility](compatibility.md).

## Known open loops

- No skill has completed the new promotion flow yet.
- Native plugin manifests will be added after the first stable skill exists.
- Production usage evidence remains private; public evidence files expose counts and methods, not raw task data.
- The first promotion will test whether the ownership-transfer checklist is strict enough without making small skills prohibitively expensive to maintain.

That first completed promotion is the review trigger for baseline v1. Until then, changes may refine the rules, but merged rules remain normative for every contribution.
