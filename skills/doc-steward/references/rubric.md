# doc-steward Rubric — Scoring & Finding format

How an EVALUATE run turns deterministic linter findings into a 0–10 composite
and a verdict. Explicitly requested deep-inspector findings stay in a separate,
unscored judgment appendix. This is the PUBLIC core: it contains no private
identifiers.

The scorer is `scripts/lib/score.py` (pure, DI-seam: callers may pass their own
weight table). This file documents the **dimensions**, their **10/7/4/0 anchors**,
the **weights**, the **severity / confidence taxonomy**, and the **Finding format**
that every report line must follow.

---

## 1. Dimensions and weights

The composite is a tier-weighted average over the dimensions graded at the repo's
tier. The base weights below are `score.py`'s `DEFAULT_WEIGHTS` (they sum to 1.0).
A dimension **not required at the current tier is dropped, and its weight is
redistributed proportionally** across the dimensions that ARE required — a skipped
dimension can never drag the composite down.

The default `doc_lint.py` composite includes only required-document `structure`,
`links`, and `frontmatter`. Its report therefore carries
`structure_scope: required-document-presence`: a deterministic `structure=10`
means the required surfaces exist, **not** that their resident content passes
Ruler 1. Semantic structure, taxonomy, staleness, verification, and decisions
remain deep-inspector/manual reference dimensions and do not alter that score.

| Dimension | Base weight | Graded by |
|---|---|---|
| `structure` | 0.25 | `presence_check` (deterministic required-document presence slice); `inspector-structure` evaluates semantic residency only in the unscored appendix |
| `taxonomy` | 0.20 | `inspector-taxonomy` (altitude + cross-tool) + TAXO-* / CROSS-* |
| `staleness` | 0.15 | `inspector-staleness` (volatility) + VOL-* / STALE-* |
| `links` | 0.15 | `link_check` (deterministic) + LINK-* |
| `frontmatter` | 0.10 | `frontmatter_check` (deterministic) + FRONT-* |
| `verification` | 0.10 | manual + VERIFY-* |
| `decisions` | 0.05 | manual + DECISION-* |

> **Dimension ↔ rule-category mapping is intentional, not 1:1 with the §5 catalog
> headings.** A dimension aggregates the rule families that bear on it: `structure`
> covers the structure/residency family (STRUCT-01..06, RESID-01, RESID-03);
> `staleness` covers the staleness/volatility family (RESID-02, VOL-01, VOL-02,
> STALE-01, STALE-02); `taxonomy` covers altitude + cross-tool (TAXO-01..04,
> CROSS-01, CROSS-02); `links` = LINK-01..04; `frontmatter` = FRONT-01..05;
> `verification` = VERIFY-01..03; `decisions` = DECISION-01..03. The learning,
> safety-rails, and design-system families are scored as policy/profile overlays,
> not as one of these seven weighted dimensions.

A profile (e.g. frontend) does not add a new weighted dimension at the core; its
rules (DESIGN-01..09) gate the profile's required docs and surface as findings, but
the seven-dimension weighting stays profile-agnostic (design §4.5).

---

## 2. Per-dimension 10 / 7 / 4 / 0 anchors

Each dimension is scored 0–10 by anchoring to the nearest band below.

### structure (required-document presence slice; semantic Ruler 1 is unscored)

The deterministic slice uses three bands (10/4/0); it never claims the semantic
7-point band:

- **10** — Every tier/target-profile-required resident surface exists.
- **4** — At least one required Standard/Complex surface is absent while a root
  charter is still present.
- **0** — A repository target has no exact-root resident charter at all. An
  exact-root portable `SKILL.md` is instead the resident entrypoint for a
  `skill-package` target.

For the optional deep-inspector appendix, semantic Ruler-1 quality is judged
separately: clean executable navigation hub; no-op/procedure sediment;
force-loaded shelf content; and single-source-of-truth violations. Those
judgments do not change the deterministic presence score or composite.

### taxonomy (altitude + cross-tool — Ruler 2)
- **10** — Every fact at the highest layer where universally true and no higher.
  One canonical cross-tool source (AGENTS.md), CLAUDE.md a thin bridge, zero
  duplication; nested subtrees correctly wired; fewest seams.
- **7** — Altitude correct overall; one fact slightly too high/low, or a tolerable
  near-duplication between AGENTS.md and CLAUDE.md.
- **4** — Repo-specific content in a shared/global rule, OR a globally-true rule
  duplicated into per-leaf copies, OR ad-hoc seams without behavior variance.
- **0** — Two hand-edited fat copies (CROSS-01 violated), or pervasive
  altitude/duplication errors; nested guidance invisible to a tool.

### staleness (volatility — Ruler 3)
- **10** — Only invariants resident; every volatile value points to one live
  source. Durable facts re-verifiable against current state; no stale paths.
- **7** — Largely invariant-only; one volatile value duplicated instead of
  pointed-to, but not yet drifted.
- **4** — A durable "fact" contradicts current code/CI, or a one-off
  report/scorecard lives in a durable doc, or a cited verifier path is stale.
- **0** — Charter asserts multiple stale values (actively misleads); dated dumps
  treated as durable source of truth.

### links (routing integrity — deterministic)
- **10** — Every pointer / `@import` / relative link resolves; no cycles, no
  >5-hop chains; `@import` used only for a true charter; one registry entry per doc.
- **7** — All links resolve; one questionable `@import` of borderline-shelf content.
- **4** — A dangling pointer or two, or a shelf doc force-loaded via `@import`, or
  an orphaned doc.
- **0** — Multiple dead links / import cycles / force-loaded shelf docs; routing
  unreliable.

### frontmatter (discoverability — deterministic)
- **10** — Required frontmatter matches the document-type policy: exact
  `SKILL.md` has portable `name` + `description`; `.claude/rules/*.md` has
  non-empty `paths`; optional AGENTS/CLAUDE/DESIGN/ADR docs may omit frontmatter,
  but a block they elect to carry has `name` + semver `version` + `description`.
  Every present description is 40–500 chars, verb-first, has "Use when…" +
  "Not for…", is English-only, and does not collide with another trigger.
- **7** — Frontmatter complete; description slightly weak (missing "Not for…" or
  marginally long) but discoverable.
- **4** — A strict optional-frontmatter block is missing `version`, a rule file
  is missing `paths`, or a description is vague/over-long/multilingual.
- **0** — An exact `SKILL.md` is missing portable `name` or `description`, or
  ≥50% trigger overlap collisions across docs.

### verification (groundedness — manual)
- **10** — Every factual/code claim cites file:line or URL; no fabricated command
  output; ungroundable claims labelled `(hypothesis)`; done-conditions are
  checkable.
- **7** — Claims grounded overall; one or two unground­able claims unlabeled.
- **4** — Several uncited claims, or quoted output not clearly verbatim.
- **0** — Fabricated/uncited output presented as fact.

### decisions (ADR discipline — manual)
- **10** — Recommendations state Accepted → Rejected alternatives → Constraint;
  unresolved questions recorded as `TODO_DECISION`; ADRs use a canonical minimal
  template.
- **7** — Decisions captured; one recommendation missing its ruling constraint.
- **4** — Decisions asserted without alternatives/constraints; silent defaults.
- **0** — No decision trail; choices undocumented and unreproducible.

A required dimension absent from the findings counts as **0** (a gap is a finding,
not a free pass).

---

## 3. Verdict thresholds

On the clamped 0–10 composite (`score.py`):

| Composite | Verdict |
|---|---|
| ≥ 8.0 | **PASS** |
| 5.0 – 7.9 | **PASS_WITH_CONCERNS** |
| < 5.0 | **FAIL** |

---

## 4. Severity taxonomy

| Severity | Meaning |
|---|---|
| **P0** | Standard-violating AND breaks discoverability/safety (e.g. CROSS-01, STRUCT-02, LINK-02, VERIFY-01/02, SAFETY-01). |
| **P1** | Required-for-tier missing, or drift/stale. |
| **P2** | House-opinion / polish. |

Each rule's canonical severity is carried in `scripts/lib/rules.py` and mirrored in
`rule-catalog.md`.

---

## 5. Confidence quote-gate

Each finding carries a confidence `N/10`. A finding that cannot quote the offending
text (an un-quotable / inference-only finding) is **forced to low confidence** and
moved to a report appendix — it never drives the headline composite. This keeps the
score anchored to verifiable evidence (Ruler-aligned with VERIFY-01).

---

## 6. Finding format (identical in JSON and prose)

```
[SEVERITY] (confidence: N/10) <rule-id> file:line — <description> → <remedy>
```

- `<rule-id>` MUST be a real id from `rule-catalog.md` / `scripts/lib/rules.py`.
- `file:line` is the evidence anchor (or a URL for VERIFY-01).
- `<remedy>` is a copy-pasteable Action (SAFETY-01): the smallest useful repair,
  never a bare "too long".

Example shape (illustrative — anchors are placeholders, not a real repo):

```
[P1] (confidence: 9/10) RESID-01 CLAUDE.md:42 — resident line restates the model's
default behavior (no-op) → delete the line (it changes nothing vs default).
```

Every finding lands in the ENFORCE disposition table (`do-dont-table.md`) with its
ADDED / CHANGED / LEFT-UNTOUCHED / ESCALATED disposition.
