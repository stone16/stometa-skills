#!/usr/bin/env python3
"""Canonical doc-steward rule catalog — 48 rules / 11 categories.

This module is the SINGLE SOURCE OF TRUTH for the rule set (design doc §5/§6).
`references/rule-catalog.md` is generated from here (gen_rule_catalog.py) and the
ENFORCE classifier + scorer read these tags. Stdlib-only, pure data + a lookup.

Per-rule fields (design line 141 + CP01 encoding guidance):
  id                    — stable rule id (e.g. "STRUCT-02")
  category              — the §5 category HEADING the rule appears under
  severity              — P0 | P1 | P2
  min_tier             — Simple | Standard | Complex (lowest tier where required)
  source                — spec-required | house-opinion
  auto                  — LOW-RISK-AUTO | ESCALATE (the classifier's disposition)
  check                 — deterministic | inspector | manual (who owns the check)
  checker               — exact script/inspector name ("" or "manual" for human-only)
  evidence_required     — what a finding must cite
  remedy                — catalog-owned copy-pasteable repair action
  autofix_preconditions — runtime gate; LOW-RISK-AUTO fires ONLY when this holds
  enforces_ruler        — bool; True iff the skill dogfoods this rule on its own
                          catalog (design line 147: obeys its own STRUCT-02/VOL-01)

NOTE: `category` (the §5 heading) and `checker` (ownership) differ on purpose —
e.g. RESID-02 sits under "staleness/volatility" but is owned by inspector-structure;
CROSS-02 sits under "structure/residency" but is owned by inspector-taxonomy.
"""

# Default evidence string (design SAFETY-01); a couple of rules extend it.
_EV = "severity + file:line + copy-pasteable Action"

# autofix_preconditions for the only two LOW-RISK-AUTO (A*) rules.
_PRE_LINK01 = (
    "explicit OLD=NEW mapping names one existing in-root replacement and the "
    "dead pointer occurs exactly once"
)
_PRE_FRONT04 = (
    "missing `version` insertable from the repo's known version; "
    "description already present"
)

# Deterministic remedies are report data, not formatter prose. Keeping them here
# makes JSON and text output share one catalog-owned repair action per rule.
_REMEDY_LINK01 = (
    "Replace the cited pointer or Markdown-link target with a repository-relative "
    "path that exists, then rerun `python3 scripts/checks/doc_lint.py --target "
    "<repo-root> --json`."
)
_REMEDY_LINK02 = (
    "Replace the cited `@import` edge with a direct pointer to the canonical "
    "document so the graph is acyclic and no chain exceeds five hops."
)
_REMEDY_LINK03 = (
    "Rewrite the cited pointer as `When <recognizable situation>, read "
    "<relative-path>` and keep the target repository-relative."
)
_REMEDY_LINK04 = (
    "Replace the nested pointer chain with one direct pointer from the cited "
    "document to the final target."
)
_REMEDY_FRONT01 = (
    "Rewrite `description` to 40-500 English characters, start with an action "
    "verb, and include `Use when ...` plus `Not for ...`."
)
_REMEDY_FRONT02 = (
    "Keep `description` English-only and move translated trigger text to a "
    "separate field or document."
)
_REMEDY_FRONT03 = (
    "Differentiate the two `description` trigger clauses so each `Use when "
    "...` names a distinct situation."
)
_REMEDY_FRONT04 = (
    "Add a leading `---` frontmatter block with the fields required for this "
    "document type; write `version` as `X.Y.Z` when present."
)
_REMEDY_FRONT05 = (
    "Replace the cited value with glossary entries in `term: definition` form."
)
_REMEDY_STRUCT06 = (
    "Create the missing required root document surface(s): Simple needs "
    "`<target>/AGENTS.md` or `<target>/CLAUDE.md`; Standard and Complex need "
    "both; Complex also needs `.claude/rules/<name>.md` and "
    "`docs/decisions/0001-<title>.md`. Scaffold only after an explicit request."
)


def _rule(rid, category, severity, min_tier, source, auto, check, checker,
          evidence_required=_EV, remedy="", autofix_preconditions="",
          enforces_ruler=False):
    return {
        "id": rid,
        "category": category,
        "severity": severity,
        "min_tier": min_tier,
        "source": source,
        "auto": auto,
        "check": check,
        "checker": checker,
        "evidence_required": evidence_required,
        "remedy": remedy,
        "autofix_preconditions": autofix_preconditions,
        "enforces_ruler": enforces_ruler,
    }


RULES = [
    # ---------------- cross-tool ----------------
    _rule("CROSS-01", "cross-tool", "P0", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-taxonomy"),

    # ---------------- structure / residency ----------------
    _rule("CROSS-02", "structure/residency", "P0", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-taxonomy"),
    _rule("STRUCT-01", "structure/residency", "P1", "Simple", "spec-required",
          "ESCALATE", "inspector", "inspector-structure"),
    _rule("STRUCT-02", "structure/residency", "P0", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-structure", enforces_ruler=True),
    _rule("STRUCT-03", "structure/residency", "P2", "Simple", "house-opinion",
          "ESCALATE", "inspector", "inspector-structure"),
    _rule("STRUCT-04", "structure/residency", "P1", "Simple", "spec-required",
          "ESCALATE", "inspector", "inspector-structure"),
    _rule("STRUCT-05", "structure/residency", "P1", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-structure"),
    _rule("STRUCT-06", "structure/residency", "P1", "Simple", "spec-required",
          "ESCALATE", "deterministic", "presence_check",
          remedy=_REMEDY_STRUCT06),
    _rule("RESID-01", "structure/residency", "P1", "Simple", "spec-required",
          "ESCALATE", "inspector", "inspector-structure"),
    _rule("RESID-03", "structure/residency", "P1", "Simple", "house-opinion",
          "ESCALATE", "inspector", "inspector-structure"),

    # ---------------- staleness / volatility ----------------
    # RESID-02 sits under this §5 heading but is owned by inspector-structure.
    _rule("RESID-02", "staleness/volatility", "P1", "Standard", "house-opinion",
          "ESCALATE", "inspector", "inspector-structure"),
    _rule("VOL-01", "staleness/volatility", "P1", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-staleness", enforces_ruler=True),
    _rule("VOL-02", "staleness/volatility", "P1", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-staleness"),
    _rule("STALE-01", "staleness/volatility", "P1", "Simple", "spec-required",
          "ESCALATE", "inspector", "inspector-staleness"),
    _rule("STALE-02", "staleness/volatility", "P2", "Standard", "house-opinion",
          "ESCALATE", "inspector", "inspector-staleness"),

    # ---------------- taxonomy / altitude ----------------
    _rule("TAXO-01", "taxonomy/altitude", "P1", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-taxonomy"),
    _rule("TAXO-02", "taxonomy/altitude", "P2", "Standard", "house-opinion",
          "ESCALATE", "inspector", "inspector-taxonomy"),
    _rule("TAXO-03", "taxonomy/altitude", "P1", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-taxonomy"),
    _rule("TAXO-04", "taxonomy/altitude", "P1", "Standard", "house-opinion",
          "ESCALATE", "inspector", "inspector-taxonomy"),

    # ---------------- links / routing ----------------
    _rule("LINK-01", "links/routing", "P1", "Simple", "spec-required",
          "LOW-RISK-AUTO", "deterministic", "link_check",
          remedy=_REMEDY_LINK01,
          autofix_preconditions=_PRE_LINK01),
    _rule("LINK-02", "links/routing", "P0", "Standard", "spec-required",
          "ESCALATE", "deterministic", "link_check", remedy=_REMEDY_LINK02),
    _rule("LINK-03", "links/routing", "P1", "Standard", "house-opinion",
          "ESCALATE", "deterministic", "link_check", remedy=_REMEDY_LINK03),
    _rule("LINK-04", "links/routing", "P2", "Standard", "house-opinion",
          "ESCALATE", "deterministic", "link_check", remedy=_REMEDY_LINK04),

    # ---------------- frontmatter / discoverability ----------------
    _rule("FRONT-01", "frontmatter/discoverability", "P1", "Simple",
          "house-opinion", "ESCALATE", "deterministic", "frontmatter_check",
          remedy=_REMEDY_FRONT01),
    _rule("FRONT-02", "frontmatter/discoverability", "P2", "Simple",
          "house-opinion", "ESCALATE", "deterministic", "frontmatter_check",
          remedy=_REMEDY_FRONT02),
    _rule("FRONT-03", "frontmatter/discoverability", "P2", "Standard",
          "house-opinion", "ESCALATE", "deterministic", "frontmatter_check",
          remedy=_REMEDY_FRONT03),
    _rule("FRONT-04", "frontmatter/discoverability", "P1", "Simple",
          "house-opinion", "LOW-RISK-AUTO", "deterministic", "frontmatter_check",
          remedy=_REMEDY_FRONT04,
          autofix_preconditions=_PRE_FRONT04),
    _rule("FRONT-05", "frontmatter/discoverability", "P2", "Standard",
          "house-opinion", "ESCALATE", "deterministic", "frontmatter_check",
          remedy=_REMEDY_FRONT05),

    # ---------------- verification (human-only) ----------------
    _rule("VERIFY-01", "verification", "P0", "Simple", "spec-required",
          "ESCALATE", "manual", "manual",
          evidence_required=_EV + " or URL"),
    _rule("VERIFY-02", "verification", "P0", "Simple", "spec-required",
          "ESCALATE", "manual", "manual"),
    _rule("VERIFY-03", "verification", "P2", "Standard", "house-opinion",
          "ESCALATE", "manual", "manual"),

    # ---------------- decisions / ADR (human-only) ----------------
    _rule("DECISION-01", "decisions/ADR", "P1", "Standard", "spec-required",
          "ESCALATE", "manual", "manual"),
    _rule("DECISION-02", "decisions/ADR", "P1", "Standard", "spec-required",
          "ESCALATE", "manual", "manual"),
    _rule("DECISION-03", "decisions/ADR", "P2", "Standard", "house-opinion",
          "ESCALATE", "manual", "manual"),

    # ---------------- learning (human-only) ----------------
    _rule("LEARN-01", "learning", "P1", "Standard", "spec-required",
          "ESCALATE", "manual", "manual"),
    _rule("LEARN-02", "learning", "P1", "Simple", "spec-required",
          "ESCALATE", "manual", "manual"),
    _rule("LEARN-03", "learning", "P2", "Standard", "house-opinion",
          "ESCALATE", "manual", "manual"),
    _rule("LEARN-04", "learning", "P2", "Complex", "house-opinion",
          "ESCALATE", "manual", "manual"),

    # ---------------- safety-rails (human-only) ----------------
    _rule("SAFETY-01", "safety-rails", "P0", "Simple", "spec-required",
          "ESCALATE", "manual", "manual"),

    # ---------------- design-system (frontend profile) ----------------
    _rule("DESIGN-01", "design-system", "P0", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-design"),
    _rule("DESIGN-02", "design-system", "P1", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-design"),
    _rule("DESIGN-03", "design-system", "P1", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-design"),
    _rule("DESIGN-04", "design-system", "P1", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-design"),
    _rule("DESIGN-05", "design-system", "P2", "Standard", "spec-required",
          "ESCALATE", "inspector", "inspector-design"),
    _rule("DESIGN-06", "design-system", "P2", "Standard", "house-opinion",
          "ESCALATE", "inspector", "inspector-design"),
    _rule("DESIGN-07", "design-system", "P2", "Standard", "house-opinion",
          "ESCALATE", "inspector", "inspector-design"),
    _rule("DESIGN-08", "design-system", "P2", "Standard", "house-opinion",
          "ESCALATE", "inspector", "inspector-design"),
    _rule("DESIGN-09", "design-system", "P2", "Standard", "house-opinion",
          "ESCALATE", "inspector", "inspector-design"),
]

# id -> rule, for O(1) lookup.
_BY_ID = {r["id"]: r for r in RULES}


def get_rule(rule_id):
    """Return the rule dict for `rule_id`; raise KeyError if unknown."""
    return _BY_ID[rule_id]


if __name__ == "__main__":
    # Tiny self-report when run directly (no I/O beyond stdout).
    core = [r for r in RULES if not r["id"].startswith("DESIGN-")]
    design = [r for r in RULES if r["id"].startswith("DESIGN-")]
    auto = [r["id"] for r in RULES if r["auto"] == "LOW-RISK-AUTO"]
    print(f"{len(RULES)} rules = {len(core)} core + {len(design)} DESIGN")
    print(f"LOW-RISK-AUTO: {auto}")
