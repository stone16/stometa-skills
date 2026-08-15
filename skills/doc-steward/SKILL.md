---
name: doc-steward
description: >
  Steward agent-facing repository documentation against a tiered house standard. Use when
  auditing or grading AGENTS.md, CLAUDE.md, SKILL.md, .claude/rules, ADRs, or DESIGN.md for
  structure, drift, frontmatter, or broken routing; explicitly previewing or applying gated
  low-risk fixes after an audit; or explicitly capturing one documentation lesson. Not for
  prose copy-editing, application-code review, product-interface design, or generic formatting.
---

# doc-steward

Keep agent-facing repository documentation predictable: put each fact at the
right residency, altitude, and volatility level; evaluate it deterministically
where possible; and gate every write.

Run commands from this skill directory. Every `scripts/`, `references/`, and
`agents/` path below is relative to this file.

## Route the request

Choose exactly one starting mode. Never cross from a read-only mode into a write
mode without explicit user intent.

| Mode | Trigger | Writes? | Surface |
|---|---|---:|---|
| **DEFINE** | The user asks to explain or classify against the standard. | No | This skill + references |
| **EVALUATE** | Default for audits, grading, drift, frontmatter, or routing checks. | No* | `scripts/checks/doc_lint.py` |
| **ENFORCE** | The user explicitly asks to preview or apply fixes after an audit. | Yes, only with `--apply` | `scripts/apply/enforce_apply.py` |
| **LEARN** | The user explicitly asks to retain one documentation lesson. | Sink-dependent | `scripts/apply/learn_capture.py` |

\* EVALUATE changes no audited document. Pass `--history` only when the user
explicitly wants `.doc-steward/history.jsonl` updated.

## DEFINE

1. Classify the target:

   ```bash
   python3 scripts/checks/tier_assess.py <repo-root> --json
   ```

   Precedence is `--tier` > explicit `--config` > auto-detection. Unknown offline
   signals round down. An explicit `--config` may also set `exclude_paths` to
   take target-relative subtrees out of audit scope — frozen archives and
   vendored doc trees, where every finding is unfixable because the material is
   not editable. Report what was excluded; a narrowed scope that goes unstated
   reads as a clean audit.
2. Read `references/standard-core.md` for the three rulers, tier, profile, and
   taxonomy. Use `references/rule-catalog.md` to distinguish spec-required rules
   from house opinion.
3. Open `references/templates.md` only when the user requests required-document
   checklists or skeletons.

DEFINE is complete when the requested standard, classification, and rule status
have been presented with no mutation. Stop unless the user also requested an
audit.

## EVALUATE

1. Run the deterministic audit for the exact target:

   ```bash
   python3 scripts/checks/doc_lint.py --target <repo-root> --json
   ```

   Use `--tier`, `--config`, `--fail-on`, or `--history` only when the request
   calls for them. Explicit YAML config needs PyYAML from `requirements.txt`;
   no-config evaluation remains stdlib-only.
2. Run deep inspectors only when explicitly requested. Dispatch the applicable
   read-only checklists in parallel when the harness supports it, otherwise apply
   the same checklists sequentially:
   - `agents/inspector-structure.md` — residency, structure, duplication, no-ops.
   - `agents/inspector-taxonomy.md` — altitude and cross-tool wiring.
   - `agents/inspector-staleness.md` — volatility and implementation drift.
   - `agents/inspector-design.md` — DESIGN rules when the frontend profile fires.
3. Render the deterministic result as a fenced `DOC-STEWARD REPORT`. Follow
   `references/rubric.md` for verdicts and finding format. Put deep-inspector
   findings in a separate, unscored judgment appendix; never alter the
   deterministic composite with them.

EVALUATE is complete only when:

- the report was freshly generated for the exact canonical target;
- every unavailable or failed checker appears under `skipped`;
- every deterministic finding includes its catalog severity and remedy;
- every judgment finding cites `file:line` and passes the quote-gate;
- the final output states target, tier/profile, dimensions, grade, findings,
  skipped checks, and whether history was enabled; and
- no audited document changed.

## ENFORCE

Open `references/apply-workflow.md` and follow it completely. The essential
sequence is:

1. Save a fresh default EVALUATE report outside the target worktree.
2. Confirm the target is on an existing non-default feature branch with a fully
   clean worktree. The script does not create or switch branches.
3. Preview the exact dispositions without `--apply`. Use `--scaffold` and
   `--link-map` only for exact user-requested paths or mappings.
4. Show the previewed write set and obtain explicit approval.
5. Repeat the same command with `--apply`.
6. Inspect the complete diff and run target validation plus `git diff --check`.

The classifier and LOW-RISK-AUTO allowlist live in
`references/do-dont-table.md`. ENFORCE never blind-deletes or overwrites a
present scaffold target. The script never stages, commits, pushes, or opens a
pull request; perform those repository actions only under separate user
authorization.

ENFORCE is complete only when every finding has a disposition, preflight and
verification succeeded, and the exact changed paths and remaining escalations
have been reported. If rollback verification fails, stop and report the target
for manual inspection.

## LEARN

Open `references/learning-sink.md` and capture exactly one selected finding.
Learning is never implied by EVALUATE or ENFORCE. Keep the `noop` sink unless the
user explicitly supplies a trusted, reviewed adapter; capturing a lesson never
changes repository documentation.

LEARN is complete when the sink returns a success or safe rejection receipt and
no unapproved write-back occurred.

## Read on demand

| Need | Open |
|---|---|
| Three rulers, taxonomy, tiers, and profiles | `references/standard-core.md` |
| Canonical rule ids and ownership | `references/rule-catalog.md` |
| Score anchors, severity, quote-gate, and finding format | `references/rubric.md` |
| Required-document skeletons | `references/templates.md` |
| Preview, approval, apply, verification, and rollback | `references/apply-workflow.md` |
| ENFORCE dispositions and auto-fix allowlist | `references/do-dont-table.md` |
| LEARN redaction and sink contract | `references/learning-sink.md` |

## Invariants

- Read-only by default; writes require explicit mode and intent.
- `scripts/lib/rules.py` is the rule catalog's single source of truth; regenerate
  `references/rule-catalog.md` with `scripts/gen_rule_catalog.py`.
- Quote every judgment finding at `file:line`; hypotheses are not findings.
- This package must pass its own deterministic audit, resolve every pointer, and
  keep this entrypoint within the dogfood line budget.
