# Gated apply workflow

Use this workflow only after a read-only EVALUATE run identifies a concrete gap
and the user asks to change the target repository. The apply script writes files;
it never creates a branch, stages, commits, pushes, or opens a pull request.

## Preconditions

1. Save a fresh default `doc_lint.py --target <repo-root> --json` report as the
   plan **outside** the target worktree. Do not use `--history` for this handoff.
   The versioned report persists `schema_version`, `canonical_target`,
   `git_revision`, and `content_digest`; ENFORCE re-runs EVALUATE and requires
   the complete report (including catalog-owned finding fields) to match the
   target's current state exactly.
2. Check out a feature branch that is not detached and is not the repository's
   detected default/protected branch.
3. Require a completely clean target worktree, including untracked files.
4. Agree on the exact target, requested scaffolds, and allowed low-risk fixes.

## Preview

Run ENFORCE without `--apply` first:

```bash
python3 scripts/apply/enforce_apply.py \
  --target <repo-root> \
  --plan <evaluate-report.json> \
  --scaffold AGENTS.md=agents \
  --json
```

Omit `--scaffold` unless that exact absent file was requested. Review every
disposition. `ESCALATED` rows need human judgment and are never applied by the
script. A STRUCT-06 presence finding does not infer a scaffold. A dry run leaves
every file untouched.

LINK-01 never guesses from a matching basename. To preview a reviewed repoint,
pass the exact dead target and repository-relative replacement explicitly:

```bash
--link-map old/path.md=docs/new-path.md
```

The mapped file must exist inside the target, and the exact dead pointer must
occur once. Otherwise the row escalates.

## Apply

Ask for explicit approval of the previewed write set. Then repeat the same
command with `--apply`. The script refuses if the plan is forged, stale, bound
to another canonical target, incomplete, or catalog-invalid; if the branch is
the symbolic remote default, the repository-configured default, a conservative
`main`/`master`/`trunk` fallback, or detached; if the worktree is dirty; or if a
planned write escapes the target. Every refusal discovered before the write loop is fail-closed and
all-or-nothing: output is labeled `mode=REFUSED`, the exit is non-zero, and none
of the planned rows are applied. This is distinct from a dry run, which is an
exit-zero preview and also writes nothing.

Each file is written through a same-directory temporary file and atomic replace.
The multi-file batch is not a filesystem-wide transaction, so ENFORCE retains
every completed path's byte preimage. If a later replacement fails, it stops,
restores completed paths (or removes newly created files), verifies byte-identical
state, emits a complete disposition table plus a `rollback` receipt, and exits
non-zero. If `rollback.verified` is false, stop and inspect the target manually;
do not stage or continue.

Afterward:

1. Inspect `git status --short` and the complete diff.
2. Run repository-specific validation plus `git diff --check`.
3. If any check fails, restore only the files written by this run and report the
   failure; do not touch unrelated work.
4. Stage only the verified paths with `git add -- <path>...`. Never use a broad
   staging command.
5. Commit, push, or open a pull request only when the user has authorized those
   repository actions. Include the disposition table and validation evidence.

## LEARN is separate

Learning capture is never implied by ENFORCE. Invoke `learn_capture.py` only when
the user explicitly asks to retain a lesson, using the safe `noop` default or a
trusted adapter supplied with `--sink-module PATH`.
