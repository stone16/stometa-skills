# doc-steward ownership transfer

Status: promotion candidate; independent review approved. [Paired-cutover governance PR #4](https://github.com/stone16/stometa-skills/pull/4), Promotion CI, and the paired private cutover are still required before completion.

## Ownership

- Public canonical source: `skills/doc-steward/`
- Extracted from: an anonymized private control-plane implementation
- Source revision: `98bec7e18d7924cfd66373168fdc301006d4738a`
- Public version: `1.0.0`
- Private remainder: profile, runtime configuration, raw evidence, and provider-specific adapters only

The source repository name, private runtime data, raw prompts, and usage receipts are intentionally absent from this record.

## Public extraction

The public package owns the generic documentation standard, deterministic audit engine, sanitized templates, scoring rules, synthetic evaluations, tests, and dry-run-first apply engine. It removes personal identity behavior, private paths, private learning sinks, source-repository cutover tests, and provider-specific command policy.

## Pre-merge ownership gate

The public Promotion PR is blocked until governance PR #4 merges. The candidate
does not amend its own admission rule.

The public PR must not merge until a dependent private cutover PR is open, reviewed,
and verified to delete the prior reusable implementation while retaining only an
explicit profile/pointer and private adapters. Because its repository identity is
private, public evidence records the anonymized cutover revision
`61f6f8e9008ef67b6d9f489ec3062abfc59dd322`; the maintainer keeps the PR link in
the access-controlled review record. A plan or promise to delete the duplicate
later is insufficient.

Cross-repository merges are not atomic, so the prepared private PR remains
unmerged only until the public dependency is available. The old implementation
is frozen during that interval. Promotion is not complete until both PRs merge.

## Cutover order

1. Review and merge public governance PR #4.
2. Prepare, review, and validate the private pointer/deletion PR; keep it blocked on the public dependency.
3. Complete independent public review and CI, recording the private revision without publishing its repository identity.
4. Merge the public Promotion PR.
5. The public maintainer who performed step 4 merges the already-reviewed private cutover within 30 minutes.
6. Install the exact released public revision and run runtime discovery plus audit smoke tests before marking an adapter verified.
7. Repoint local runtime links to the public canonical directory and verify no independently editable copy remains.

## Rollback

Before the Promotion or cutover PR merges, rollback means closing both. If the
public merge succeeds but the prepared private cutover cannot merge within 30
minutes, the same public maintainer reverts the exact Promotion merge commit on
`main`. After both sides transfer, restore functionality by pinning the last
known-good public revision; do not recreate a second editable private
implementation.
