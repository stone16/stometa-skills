# doc-steward ownership transfer

Status: public version 1.0.0 is stable. The public record does not yet verify that
the paired private cutover completed, so the ownership transfer remains an open
baseline-v1 governance item.

## Ownership

- Public canonical source: `skills/doc-steward/`
- Extracted from: an anonymized private control-plane implementation
- Source revision: `98bec7e18d7924cfd66373168fdc301006d4738a`
- Public version: `1.0.0`
- Intended private remainder: profile, runtime configuration, raw evidence, and provider-specific adapters only

The source repository name, private runtime data, raw prompts, and usage receipts are intentionally absent from this record.

## Public extraction

The public package owns the generic documentation standard, deterministic audit engine, sanitized templates, scoring rules, synthetic evaluations, tests, and dry-run-first apply engine. It removes personal identity behavior, private paths, private learning sinks, source-repository cutover tests, and provider-specific command policy.

## Recorded cutover state

- Public promotion commit: `37f31b78cb1faca736bd8426ff12ef0e5210bd2f`
- Public paired-cutover governance commit: `568b7ec8dbc33af9926c631748a3f7a1d9984116`
- Prepared private cutover revision recorded during review:
  `61f6f8e9008ef67b6d9f489ec3062abfc59dd322`

The intended sequence required governance to merge before promotion. Public Git
history records the promotion before the governance commit; this ordering is a
baseline-review finding, not evidence that the private cutover failed. Because
the private repository identity and merge record are intentionally absent, this
repository must not claim that side completed until the maintainer records a
sanitized verification result.

## Remaining confirmation

The maintainer must update this record and `evidence/doc-steward.yaml` with a
sanitized completion date and verification result showing that:

1. the old reusable private implementation was deleted or replaced by an explicit
   profile/pointer plus private adapters;
2. local runtime links resolve to the released public canonical source;
3. no independently editable duplicate remains; and
4. the exact released public revision passes the applicable runtime discovery and
   audit smoke tests before any adapter is marked verified.

## Rollback

Restore functionality by pinning the last known-good public revision; do not
recreate a second editable private implementation. If the private cutover is
found incomplete, resolve it in the private control plane or revert the public
promotion through a reviewed public PR.
