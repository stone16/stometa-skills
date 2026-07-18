# doc-steward Learning Sink — Capture Contract

Learning is explicit and disabled by default. An EVALUATE run never captures a
lesson. `scripts/apply/learn_capture.py` captures exactly one selected finding
only after the caller supplies explicit intent through `--sink` or an explicit
`--config` with `learn_enabled: true`.

## Stages

| Stage | What happens | Rule(s) |
|---|---|---|
| CAPTURE | Select one Issue-Ready finding and send it to an injected sink. | LEARN-01 |
| DISTILL | Apply the six-field candidate matrix and strip provenance. | LEARN-01, LEARN-02 |
| PROMOTE | Promote only after recurrence (at least 3 of the last 10) or a critical event. | LEARN-03 |
| WRITE-BACK | Add, change, or skip via the gated ENFORCE workflow. | LEARN-03, LEARN-04 |

## Candidate matrix

Before promotion, record whether the lesson is repeated, invariant, placed at
the right scope, machine-verifiable, at redaction risk, and stripped of incident
provenance. Prefer a deterministic check over prose whenever possible.

## Redaction

Distillation removes explicit-scheme URIs (including hierarchical and opaque
forms such as `http(s)://`, `file:/`, `mailto:`, `urn:`, and `ssh:`), public or
local-domain emails, absolute and home-relative paths, dates, ticket identifiers,
and line-number provenance. An explicit config may add `private_paths` and
`redaction_terms`; these are matched and removed before a record reaches a sink.
Do not put secrets in the config or finding text.

Structured fields copied to the sink are not prose and are never silently
scrubbed. `rule_id` must exist in the canonical catalog, `severity` must equal
that rule's catalog severity, and candidate `layer` must be one of `global`,
`repo`, `subtree`, or `shelf`. Invalid identifiers, URIs, path punctuation,
configured private terms, control characters, or free-form values reject the
entire record. A second recursive scan covers every string in the completed
record before the sink is called; the rejection receipt contains none of the
offending value.

## Sink seam

The default `noop` sink writes nothing. The public core deliberately ships no
personal or organization-specific sink. Python callers may inject any object
implementing `write(record)`. CLI users may pass `--sink-module PATH` only as an
explicit action; the module must expose a `Sink` class and is loaded as local
code. Use only a trusted, reviewed adapter, and pass `--sink-path` when that
adapter requires an output destination. No config file can load external code
implicitly.

Record tags remain scoped to documentation:

- `DOC-IMPL-DRIFT`
- `DOC-VERIFY-GAP`
- `DOC-CONTRACT-MISSING`

Write-back is a separate, human-approved ENFORCE run. Capturing a lesson never
silently changes repository documentation.
