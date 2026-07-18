---
name: doc-steward
description: >
  Audits and standardizes agent-facing docs (CLAUDE.md, AGENTS.md, SKILL.md, .claude/rules,
  docs/decisions, DESIGN.md) against a tiered house standard, then scaffolds gaps and applies
  low-risk fixes via a feature-branch PR. Use when auditing, grading, or linting docs; checking
  doc health, drift, or stale docs; reviewing frontmatter or broken doc links; or bootstrapping
  CLAUDE.md/AGENTS.md. Not for prose copy-editing, application code review, or generic
  linting/formatting.
---

# doc-steward

An opinionated, business-agnostic **standard** for how a repository organizes its
**agent-facing documentation** — CLAUDE.md / AGENTS.md / SKILL.md / `.claude/rules` /
`docs/decisions` / DESIGN.md — plus the machinery to **evaluate** a repo against that
standard and **apply** fixes toward it. This entrypoint is the **read-only audit
surface**: it defines the standard and grades a repo, but never edits a doc. Writing
fixes and capturing learnings use the explicit scripts under `scripts/apply/`
(see Modes).

> **Run scripts from this skill's own directory.** Every path below
> (`scripts/…`, `references/…`, `agents/…`) is relative to where this `SKILL.md`
> lives.

## The standard in one breath

A fact belongs in always-resident context (CLAUDE.md/AGENTS.md, loaded every turn,
before the agent sees the task) only if it passes **all three rulers**:

1. **Residency / form** — carry guardrails + invariants; shelve procedures + detail.
   The no-op test: would removing this line cause a mistake on a turn you did not
   think to look? If not, cut it.
2. **Altitude / scope** — place each fact at the highest layer where it is
   universally true, and no higher (global → repo → subtree).
3. **Volatility / freshness** — only invariants are resident; volatile values
   (IP, VM, dates, versions) point to a single live source, never get copied.

Meta-principle: **make the correct state hold structurally, not by discipline.** The
standard turns "you must remember" into "it checks for you." Full text:
`references/standard-core.md`.

## Modes

**EVALUATE is the default** and is read-only. DEFINE is an optional, explicitly
requested preface that may run before EVALUATE. Explicit commands under
`scripts/apply/` own **ENFORCE + LEARN**; never cross from a read-only mode into
a write mode silently.

| Mode | Surface | Writes? | What it does |
|------|---------|---------|--------------|
| **DEFINE** | this skill (optional preface) | no | Classify tier + profile; present the tiered standard + taxonomy; tag each rule spec-required vs house-opinion. |
| **EVALUATE** | this skill (default) | no* | Inventory docs → deterministic lint → optional deep inspectors → score + grade → fenced `DOC-STEWARD REPORT`. |
| **ENFORCE** | `scripts/apply/enforce_apply.py` | yes | Require a fresh versioned EVALUATE bound to the current canonical target → non-default feature branch + clean worktree → apply low-risk fixes and explicitly requested absent-file scaffolds. Any preflight refusal applies zero planned writes. Never blind-delete. |
| **LEARN** | `scripts/apply/learn_capture.py` | yes | Explicit trigger only: distill one EVALUATE finding and send it to an explicitly configured sink. |

\* EVALUATE does not modify, create, or delete audited docs. History is disabled
by default; `--history` explicitly opts in to `.doc-steward/history.jsonl`.

Do not silently switch from DEFINE or EVALUATE to a write mode. Require explicit
write intent, then run the relevant apply script explicitly.

## Workflow

### DEFINE — optionally present the standard first

1. Classify the repo deterministically. The tier (Simple / Standard / Complex) and
   the frontend profile come from `scripts/checks/tier_assess.py`:

   ```bash
   python3 scripts/checks/tier_assess.py <repo-root> --json
   ```

   Precedence: `--tier` flag > explicit `--config` > auto-detect; when a signal
   is not inferable offline, auto-detect rounds **down** to the lower tier.
2. Present the tiered standard + taxonomy from `references/standard-core.md`,
   tagging each rule **spec-required (S)** vs **house-opinion (H)** using the
   human mirror `references/rule-catalog.md` (generated from the canonical
   `scripts/lib/rules.py`; never hand-edit the catalog).
3. Show the per-tier required-doc checklist and the skeletons in
   `references/templates.md`. DEFINE proposes nothing and writes nothing. Stop
   unless the user explicitly requested EVALUATE after DEFINE.

### EVALUATE — grade this repo (default mode, read-only)

1. **Inventory + deterministic lint.** Run the top-level runner over the repo (or a
   single `--target` dir). It globs the doc taxonomy, classifies the tier, dispatches
   the deterministic checkers, and aggregates one scored report:

   ```bash
   python3 scripts/checks/doc_lint.py --target <repo-root> --json
   ```

   - The runner preserves
     `{"passed", "tier", "composite", "grade", "findings", "skipped"}` and
     also emits `scope: "deterministic"`, `target_profile` (`repository` or
     `skill-package`), `structure_scope: "required-document-presence"`,
     per-dimension scores in `dimensions`, and
     `severity_counts` for P0/P1/P2. Every finding includes catalog-owned
     `severity`, `confidence: 10`, and a concrete `remedy`.
   - `--fail-on P0|P1|P2` gates the exit code on severity; otherwise exit is
     non-zero iff `passed` is false.
   - `--tier Simple|Standard|Complex` forces the tier; `--history` opts in to a
     run-log self-write; `--config PATH` loads generic config explicitly.
   - Deterministic checkers under the hood:
     `scripts/checks/presence_check.py` (STRUCT-06 — exact-root tier/profile
     required-document presence),
     `scripts/checks/frontmatter_check.py` (FRONT-* — name/version format,
     description quality) and `scripts/checks/link_check.py` (LINK-* — dead
     pointers/relative Markdown links plus cyclic, over-long, or over-nested
     routing). Each is wrapped in a failure-mode
     guard: a checker that is unavailable or raises is recorded in `skipped` and
     its weight redistributes — the run never crashes mid-way.

   **Optional config dependency:** explicit `--config PATH` parsing uses PyYAML
   from [requirements.txt](requirements.txt). Without PyYAML, no-config EVALUATE
   and LEARN still work with safe defaults; an explicit config request fails
   clearly before evaluation or capture. Install it with
   `python3 -m pip install -r requirements.txt` when YAML config is needed.

2. **Deep inspectors (explicit request only).** When the user explicitly asks for
   deep inspection, run the read-only inspector checklists as parallel subagents
   where the harness supports them (soft-degrade to inline sequential execution
   of the same checklists otherwise). This is an agent/checklist step, not a
   `doc_lint.py` CLI flag. Each inspector owns one ruler:
   - `agents/inspector-structure.md` — ruler 1 (residency): procedure-as-fact,
     force-load, bloat, no-op lines.
   - `agents/inspector-taxonomy.md` — ruler 2 (altitude) + cross-tool wiring,
     duplication, ADR coverage.
   - `agents/inspector-staleness.md` — ruler 3 (volatility): IP/VM/date/version
     drift, docs-vs-code drift.
   - `agents/inspector-design.md` — frontend profile: DESIGN.md completeness vs
     the rubric.

   Findings carry a fingerprint for dedupe and are run through the **confidence
   quote-gate**. They go in a clearly labeled **unscored judgment appendix** and
   never alter the deterministic composite.
3. **Score + grade.** The deterministic composite covers **required-document
   structure + frontmatter + links** and comes from `scripts/lib/score.py` via
   the runner. A normal repository with no resident root charter floors all
   three dimensions to 0; an exact-root `SKILL.md` instead selects the portable
   `skill-package` contract and serves as its resident entrypoint. The
   deterministic `structure=10` certifies presence only; semantic Ruler-1 quality
   remains in the explicitly requested, unscored deep-inspector appendix.
   Dimensions not
   required at the detected tier drop out and their weight redistributes (a
   skipped/irrelevant dimension never drags the score down). Verdict: **PASS** (≥8.0) /
   **PASS_WITH_CONCERNS** (≥5.0) / **FAIL**. Anchors, weights, severity taxonomy,
   and the Finding format live in `references/rubric.md`.
4. **Report.** Emit a fenced `DOC-STEWARD REPORT` block from the runner's
   self-sufficient deterministic output: scope/dimensions, composite, P0/P1/P2
   counts, verdict, and each finding as `[SEVERITY] (confidence: N/10) <rule-id>
   file:line — <description> → <remedy>`. If deep inspection was explicitly
   requested, follow it with the separate unscored judgment appendix.
5. **History (optional).** Pass `--history` to append a trend row to
   `.doc-steward/history.jsonl`. The default audit writes nothing.

### ENFORCE / LEARN — hand off to the apply command

These are outside the default read-only audit surface. When EVALUATE finds
fixable gaps, follow `references/apply-workflow.md` and invoke
**`scripts/apply/enforce_apply.py`**, which classifies findings
LOW-RISK-AUTO vs ESCALATE (from each rule's `auto:` field — see
`references/do-dont-table.md`), applies only low-risk auto fixes on a feature
branch, scaffolds ABSENT files from `references/templates.md` only when the caller
explicitly passes `--scaffold` (never inferring or overwriting),
and prints a disposition table. The script never stages, commits, pushes, or opens
a PR. LEARN writes one distilled finding to an explicitly selected sink (contract
in `references/learning-sink.md`). Keep the default `noop` sink unless a reviewed
adapter is supplied explicitly.

## Read on demand (progressive disclosure)

Open a reference only when the workflow step above calls for it.

| Need | Open |
|------|------|
| The full tiered standard + document taxonomy (public core) | `references/standard-core.md` |
| Score anchors (10/7/4/0), weights, severity taxonomy, Finding format | `references/rubric.md` |
| Human mirror of every rule (S vs H, severity, tier, owner) | `references/rule-catalog.md` |
| Per-tier AGENTS.md / CLAUDE.md / .claude-rules / MADR / DESIGN.md skeletons | `references/templates.md` |
| ENFORCE disposition table + the LOW-RISK-AUTO allowlist | `references/do-dont-table.md` |
| Approval, dry-run, verification, exact staging, and rollback steps | `references/apply-workflow.md` |
| The LEARN sink contract (safe `noop` default) | `references/learning-sink.md` |
| Tier + frontend-profile detection | `scripts/checks/tier_assess.py` |
| The top-level read-only audit runner | `scripts/checks/doc_lint.py` |
| STRUCT-06 required-document presence checker | `scripts/checks/presence_check.py` |
| FRONT-* frontmatter checker | `scripts/checks/frontmatter_check.py` |
| LINK-* reference / routing checker | `scripts/checks/link_check.py` |
| Run-log + trend-delta helper | `scripts/checks/history.py` |
| Canonical rule catalog AS DATA (single source of truth) | `scripts/lib/rules.py` |
| Optional PyYAML dependency for explicit `--config` | `requirements.txt` |
| Tiered weighted-composite scorer | `scripts/lib/score.py` |
| Regenerate the human rule-catalog from `scripts/lib/rules.py` (`--check` for drift) | `scripts/gen_rule_catalog.py` |
| Residency inspector (ruler 1) | `agents/inspector-structure.md` |
| Altitude + cross-tool inspector (ruler 2) | `agents/inspector-taxonomy.md` |
| Volatility / staleness inspector (ruler 3) | `agents/inspector-staleness.md` |
| Frontend DESIGN.md inspector | `agents/inspector-design.md` |

## Guardrails

- **Read-only by default.** Require explicit approval before invoking an apply
  script. `enforce_apply.py` is dry-run unless `--apply` is passed.
- **Mode boundary.** EVALUATE is the default; DEFINE may explicitly precede it.
  Never silently slide from either read-only mode into a write.
- **Cite evidence.** Every finding quotes `file:line`; un-quotable findings are
  low-confidence and appendixed (rubric quote-gate).
- **Dogfood.** This skill is the standard's reference implementation and must pass
  its own audit (`scripts/checks/test_dogfood.py`): `doc_lint --target` this
  skill's root is PASS, SKILL.md is ≤500 lines, and every pointer above resolves
  on disk.
