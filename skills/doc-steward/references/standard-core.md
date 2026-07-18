# doc-steward Standard — Core

The business-agnostic standard for how a repository organizes its **agent-facing
documentation** (CLAUDE.md / AGENTS.md / SKILL.md / `.claude/rules` / `agent_docs`
/ `docs/decisions` / DESIGN.md). This is the public, harness-neutral core and
contains no personal identity conventions.

This file is the read-on-demand DEFINE reference. The canonical rule list lives in
`rule-catalog.md` (generated from `scripts/lib/rules.py`); scoring anchors live in
`rubric.md`; ENFORCE dispositions live in `do-dont-table.md`; skeletons live in
`templates.md`.

---

## 1. The physical fact this standard is built on

CLAUDE.md / AGENTS.md is **loaded into context on every turn, before the agent
sees the task.** It is working memory you pay a token tax on every turn — not
"documentation you fetch when needed."

Metaphor: a few things **tattooed on the back of the hand** (always glanceable,
costs you to carry) vs. the **handbook on the shelf** (fetched when relevant).

---

## 2. The Three Rulers

A piece of knowledge belongs in always-resident context only if it passes **all
three** rulers.

### Ruler 1 — Residency / form
*Is this a guardrail/invariant (carry), or a procedure/detail (shelf)?*

- **Carry** what you must know **before you know the task**: invariants and
  guardrails.
- **Shelve** what you **go fetch once you've committed to a task**: procedures,
  topic detail.

The classic failure (the 947-line CLAUDE.md) dumps a whole *topic* (guardrail
**and** procedure) onto the hand.

**No-op test**: would removing this line cause a mistake on a turn you didn't
think to look? If not, cut it — don't reword it.

### Ruler 2 — Altitude / scope
*Place each fact at the highest layer where it is universally true — and no higher.*

| Scope | Lives at |
|---|---|
| True for all repos | global `~/.claude/CLAUDE.md` (+ optional `dotfiles/PRINCIPLES.md` / `RULES.md`) |
| True for this repo | repo `AGENTS.md` / `CLAUDE.md` |
| True for one service/subtree | that subtree (nested `AGENTS.md` + sibling `CLAUDE.md`, or `.claude/rules` `paths:`-scoped) |

A service fact at repo root is "too high" (noise for sibling services); a universal
rule buried in one leaf is lost everywhere else.

### Ruler 3 — Volatility / freshness
*Only invariants are resident.*

A volatile value (IP, VM name, current goals, dates, versions) — even when
frequently needed — must not live in a durable charter, because a charter
asserting a stale value is **worse than silent: it actively misleads.** Volatile
facts point to a **single live source** (`terraform output`, a tokens file, a
Makefile target). Write the *method of getting the value*, not the value.

### Meta-principle (load-bearing)
**Make the correct state hold structurally, not by discipline.** A symlink makes
cross-tool consistency a physical fact (one inode); a `paths:` rule makes
conditional loading an engine behavior; a verification contract makes "the command
is real" a deterministic check. Whatever a machine can guarantee, don't leave to
human memory. This is doc-steward's entire reason to exist: it turns *"you must
remember"* into *"it checks for you."*

---

## 3. The Document Taxonomy (placement map)

| Altitude (highest layer where universally true) | Physical location | What goes here (residency-filtered: guardrails/invariants only; procedures shelved) |
|---|---|---|
| All repos | the tool's global instruction layer | Cross-repo behavioral rules (honesty / verification / git discipline). Nothing repo-specific. |
| This repo | `AGENTS.md` (canonical, cross-tool source) + `CLAUDE.md` (thin bridge) | Repo guardrails, build/test commands, Architecture Map, verification-contract pointer |
| One service/subtree | nested `AGENTS.md` (Codex concatenates root→leaf, sibling-isolated, **not** lazy) **or** `.claude/rules/*.md` (`paths:`-scoped, **true lazy load**, Claude Code only) | Service-level guardrails, module boundaries |
| Any altitude — procedures / detail | `docs/` (runbooks), `docs/decisions/` (MADR ADRs), skills, `agent_docs/`, `DESIGN.md` | Multi-step procedures, ADR bodies, topic detail. Resident files keep only a one-line pointer. |

### Cross-tool wiring (Codex + Claude)
Claude reads `CLAUDE.md`; Codex reads `AGENTS.md`. **One canonical source =
`AGENTS.md`.** `CLAUDE.md` is a **symlink** by default (`ln -s AGENTS.md CLAUDE.md`,
zero drift) or a thin **`@import` overlay** (importing `AGENTS.md` plus a tool-specific delta)
only when genuine tool-specific content exists. **Zero duplication universally** —
no exemption for self-contained-per-agent models.

**Nested subtrees:** because Claude Code reads only `CLAUDE.md` (never
`AGENTS.md`), every subtree shipping a nested `AGENTS.md` must also carry a sibling
nested `CLAUDE.md` symlink, or Claude Code silently won't see the subtree guidance.
`@import` is not a substitute (it loads fully every turn).

### Routing (how a shelf doc is read at the right moment)
Priority: **nearest-file > `paths:`-rule > skill > pointer-table.** Use the most
automatic mechanism the content's scope allows. **Never `@import` a shelf doc** —
`@import` loads fully every turn (it does not save context), so it is only correct
for a charter that *deserves* residency. Pointer-table wording must name the
situation the agent will recognize itself to be in ("when working against the
staging env"), and every pointer target must resolve on disk.

### Frontmatter scope (matches the templates)

FRONT-* rules validate any taxonomy document that already begins with a `---`
frontmatter block. The block is required only for an exact `SKILL.md` and for
`.claude/rules/*.md`; a similarly named fixture such as `SKILL.fixture.md` is not
a Skill entrypoint. Plain `AGENTS.md`, `CLAUDE.md`, `DESIGN.md`, and
`docs/decisions/*.md` are valid without frontmatter and must not receive a
missing-frontmatter finding. If one of those optional documents does carry a
leading block, its metadata is still validated.

`SKILL.md` uses the portable Skill schema: `name` + `description`. Optional
frontmatter-bearing documents use `name`, semver `version`, and `description`.
Claude rule files follow their template instead: they require a non-empty
`paths` field; `name`, `version`, and `description` are optional there, though
any present version must still be valid semver.

### Audit target shape (exact-root contract)

`doc_lint.py` reports one of two deterministic `target_profile` values:

- **`skill-package`** — an exact `<target>/SKILL.md` exists. That portable Skill
  entrypoint is the resident surface, so repository-specific AGENTS/CLAUDE,
  `.claude/rules`, and ADR presence requirements do not apply. Its portable
  `name` + `description` frontmatter still does.
- **`repository`** — no exact-root `SKILL.md` exists. The tiered resident-document
  requirements below apply using exact-root paths.

A nested `skills/<name>/SKILL.md` does not convert the repository root into a
skill package. Likewise, nested AGENTS.md / CLAUDE.md files do not satisfy the
root charter requirement. This exact-root distinction prevents a large repo
that merely contains skills or service charters from receiving a false clean
presence score.

---

## 4. The Tiers

Tier is detected deterministically by `tier_assess.py` (source-file count excludes
`.git/`, `node_modules/`, `dist`/`build`/`vendor`, and lockfiles). Final-tier
precedence: `--tier` flag > explicit `--config` > auto-detect; when a signal is
not inferable offline, auto-detect rounds **down**.

### Simple (single-lang, <50 source files, internal)
**Required:** project identity/stack · Architecture Map ·
Commands · verification-contract pointer · Definition-of-Done.

**Canonical resident file:** a single standalone `CLAUDE.md` **or** `AGENTS.md`
suffices. The `AGENTS.md`-canonical + `CLAUDE.md`-bridge split is **not** required
at this tier.

### Standard (normal app / multi-contributor, 50–5000 source files)
**Adds:** `AGENTS.md` canonical + `CLAUDE.md` thin bridge · Safety-Rails / Do-Not ·
link integrity · AGENTS↔CLAUDE wiring.

### Complex (monorepo / multi-lang / public / OSS, >5000 source files or a workspaces marker)
**Adds:** full Project Contract (NEVER/ALWAYS, Coding-Conventions,
Architecture-Boundaries, Compact-Instructions) · nested nearest-file precedence
(per-subtree `AGENTS.md` **+** sibling `CLAUDE.md` symlink) · `.claude/rules`
(`paths:`-scoped) · `docs/decisions/` MADR · all inspectors.

Public/OSS is inferred from **local deterministic signals only** (an
OSI-recognized `LICENSE` file + a public-host git remote); when unknown it defaults
to the lower (private/non-OSS) tier.

The deterministic `STRUCT-06` preflight enforces these presence surfaces before
content scoring: Simple repository targets need root `AGENTS.md` **or**
`CLAUDE.md`; Standard/Complex need both; Complex also needs at least one
`.claude/rules/*.md` and one `docs/decisions/*.md`. A repository with neither root
charter receives structure/frontmatter/links = 0 and FAIL, not a vacuous PASS.
One missing Standard/Complex surface is a P1 structure=4 concern. Presence
findings never create files: ENFORCE scaffolds an absent surface only when the
caller explicitly supplies the matching `--scaffold` request.

---

## 5. The repo-profile axis (orthogonal to tier)

A profile activates extra required doc types by **capability**, not size. A profile
is a 4-part contract: (1) deterministic detection checklist; (2) conditionally
required doc types; (3) per-doc rubric; (4) `XXX-NN` rules. The three rulers stay
profile-agnostic at the core; a profile only adds *"which extra docs are required."*

**Frontend is the first and only profile implemented now** (DESIGN.md; see
`rule-catalog.md` DESIGN-01..09 and `inspector-design`). Backend-API / data /
library / CLI follow the same template later — the seam is built, not over-built.

---

## 6. Standard sections of a resident charter

A resident root charter (CLAUDE.md / AGENTS.md) carries only these, in roughly this
order; everything else is shelved with a one-line pointer.

| Section | Required at tier | Notes |
|---|---|---|
| Project identity / Stack | Simple+ | One line |
| Architecture Map | Simple+ | Directory tree with terse comments |
| Commands | Simple+ | Essential build/test/run only — actual, runnable |
| Verification-contract pointer | Simple+ | Points to where "the command is real" is checked |
| Definition-of-Done | Simple+ | Checkable completion criteria |
| Safety-Rails / Do-Not | Standard+ | Forbidden patterns; never blind-delete |
| Pointer table (shelf routing) | Standard+ | Each target must resolve on disk |
| Project Contract (NEVER/ALWAYS, conventions, boundaries) | Complex | Full charter |

Sizing guidance (house-opinion): a resident charter stays machine-actionable —
prefer a navigation hub over an essay, and split deep topics into shelved
`agent_docs/` / `docs/` files reached by the pointer table.

---

## 7. Absorbed from the predecessor CLAUDE.md skill

doc-steward supersedes the prior CLAUDE.md-creator skill. The substance of its
standard is folded in here:

- **Progressive Disclosure** — now the Routing model (§3) and the resident-vs-shelf
  split (Ruler 1): the resident charter is a navigation hub; deep guides live in
  shelved files reached by a pointer table.
- **Required sections + "Do Not"** — now the standard-section table (§6), tiered.
- **Atomic-commit discipline** — kept as a workflow norm of the write-enabled
  `scripts/apply/enforce_apply.py` workflow (feature branch + clean worktree),
  not a resident-doc rule.
