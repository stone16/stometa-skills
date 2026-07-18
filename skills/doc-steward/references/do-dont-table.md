# doc-steward ENFORCE — Disposition table & LOW-RISK-AUTO allowlist

What `scripts/apply/enforce_apply.py` is allowed to do with each EVALUATE
finding. This is the public, harness-neutral core.

The audit skill itself is structurally read-only; ENFORCE runs on a non-default
feature branch + a clean worktree, and **all writes go through
`scripts/apply/enforce_apply.py`** (dry-run by default; refuses `--apply` unless
HEAD is outside the detected default/protected branch set, the worktree is
clean, and a fresh versioned EVALUATE report is bound to the canonical target,
current revision, and current content digest).

Iron rule: **never blind-delete repo-specific content.** Repair the smallest useful
surface (SAFETY-01).

---

## 1. The disposition table

Every finding becomes one row. The report groups rows under four dispositions.

Row columns: `Finding | rule-id | Disposition | Action | Rationale`.

| Disposition | When | What ENFORCE does |
|---|---|---|
| **ADDED** | A required file/section is ABSENT for the repo's tier/profile. | Scaffold it from `templates.md` (never overwrite a present file). |
| **CHANGED** | A finding is **LOW-RISK-AUTO** AND its `autofix_preconditions` hold at runtime. | Apply the single-line mechanical fix automatically. |
| **LEFT-UNTOUCHED** | A finding's remedy is satisfied, disabled by config, or out of the supplied plan's scope. | Nothing; recorded for transparency. |
| **ESCALATED** | Anything ambiguous, destructive, judgment-bearing, or private-path-touching. | Emit a human checklist item; do NOT auto-apply. |

### Classifier (deterministic, from each rule's `auto:` field)
- **LOW-RISK-AUTO** ⇔ a single-line mechanical substitution **with a known target
  value** AND **no private-path involvement** AND **deletes nothing** AND
  the rule's `autofix_preconditions` hold at runtime.
- Everything else → **ESCALATE**.
- Bootstrap of an ABSENT file → **ADDED**. Overwrite of a PRESENT file → always
  **ESCALATE** (never silently overwrite). Bootstrap is never inferred from a
  STRUCT-06 finding: the caller must explicitly pass `--scaffold REL=kind`.
- A LOW-RISK-AUTO rule whose `autofix_preconditions` do NOT hold at runtime
  **degrades to ESCALATE**.

---

## 2. The LOW-RISK-AUTO allowlist

Per `scripts/lib/rules.py`, **exactly two** rules carry `auto: LOW-RISK-AUTO`.
Every other rule is `ESCALATE`. (Semantic rules — no-op, altitude, single-source,
stale-fact — are `check: inspector` and never auto-fix.)

| rule-id | Owner (check) | Auto-fix is allowed ONLY when (`autofix_preconditions`) |
|---|---|---|
| **LINK-01** | `deterministic:link_check` | caller supplies an explicit exact old→new mapping to one existing in-root target, and the dead pointer occurs exactly once |
| **FRONT-04** | `deterministic:frontmatter_check` | missing `version` insertable from the repo's known version; description already present |

LINK-01 never infers rename evidence from a matching basename; absent or invalid
`--link-map OLD=NEW` input degrades to ESCALATE. If FRONT-04 finds a missing/weak **description** (not just a
missing version), it degrades to ESCALATE — rewriting a description is judgment.

> Note the deliberately-tight bound: LINK-01 and FRONT-01 also concern
> links/frontmatter, but **FRONT-01** (description quality) is `ESCALATE` —
> rewriting a description is judgment, so it is NOT on the allowlist. Only the two
> rules above auto-fix.

---

## 3. Worked disposition rows (illustrative)

Placeholders, not a real repo — anchors are not real file:line refs.

| Finding | rule-id | Disposition | Action | Rationale |
|---|---|---|---|---|
| `AGENTS.md` absent on a Standard-tier repo | STRUCT-06 | ESCALATED | report the exact missing root surface | deterministic presence finding never infers a write |
| Caller explicitly requests `--scaffold AGENTS.md=agents` while the file is absent | STRUCT-01 | ADDED | scaffold from `templates.md` (AGENTS.md skeleton) | explicit bootstrap request; never overwrite a present file |
| Dangling pointer with an explicit reviewed `--link-map` | LINK-01 | CHANGED | rewrite the exact pointer to the mapped in-root path | LOW-RISK-AUTO; explicit mapping + one-occurrence preconditions hold |
| Missing `version`, description already present | FRONT-04 | CHANGED | insert `version` from the repo's known version | LOW-RISK-AUTO; precondition holds |
| Vague description (no "Use when…"/"Not for…") | FRONT-01 | ESCALATED | human rewrites the description | rewriting a description is judgment (ESCALATE) |
| Repo name baked into a global behavioral rule | TAXO-03 | ESCALATED | human relocates the fact to the right altitude | altitude judgment + private-content risk |
| Resident no-op line restating the default | RESID-01 | ESCALATED | human confirms + deletes the no-op | semantic (inspector-owned); never auto-deletes content |
| Already-thin CLAUDE.md bridge, no issue | CROSS-01 | LEFT-UNTOUCHED | none | satisfied; recorded for transparency |

---

## 4. Hard guarantees

- **Structural read-only audit:** EVALUATE cannot mutate any audited doc — it has
  no Edit/Write, no `gh`, and no raw git tool. ENFORCE is a separate write surface.
- **No blind delete:** repo-specific content is never deleted automatically;
  extract the invariant first, then ESCALATE the removal (SAFETY-01, STALE-01).
- **Target boundary:** any finding or scaffold resolving outside the canonical
  target (including through a symlink) is a run-level refusal. ENFORCE writes
  only explicit, contained target paths.
- **Plan-gated writes:** `--apply` refuses without a non-default feature branch,
  a clean worktree, and a complete versioned EVALUATE report whose canonical
  target, Git revision, content digest, report body, and finding catalog fields
  reproduce against the target's current state.
- **Fail-closed preflight:** if any run-level refusal is known before writing —
  including a planned/scaffold path escaping `--target` — ENFORCE applies none
  of the planned rows. Ordinary row-local ESCALATED findings remain reports and
  do not become run-level refusals.
- **Late-I/O boundary:** each file uses a same-directory atomic replacement, but
  the batch is not a filesystem transaction across all paths. A later failure stops the run,
  restores completed byte preimages/removes new files, and emits the tested
  rollback verification receipt defined in `apply-workflow.md`.
