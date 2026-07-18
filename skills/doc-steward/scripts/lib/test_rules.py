#!/usr/bin/env python3
"""Tests for rules.py (the canonical 48-rule catalog). Stdlib-only.

Run: python3 test_rules.py   (exit 0 = pass) ; also runs under pytest.
Each test encodes a rule-set INVARIANT the catalog must hold — not just a
code path. The catalog is the single source of truth consumed downstream
(classifier, scorer, gen_rule_catalog), so drift here is a real defect.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules as R  # noqa: E402

SEVERITIES = {"P0", "P1", "P2"}
TIERS = {"Simple", "Standard", "Complex"}
SOURCES = {"spec-required", "house-opinion"}
AUTOS = {"LOW-RISK-AUTO", "ESCALATE"}
CHECKS = {"deterministic", "inspector", "manual"}

REQUIRED_FIELDS = {
    "id", "category", "severity", "min_tier", "source", "auto",
    "check", "checker", "evidence_required", "remedy",
    "autofix_preconditions",
    "enforces_ruler",
}


def test_total_count_is_48():
    assert len(R.RULES) == 48, f"expected 48 rules, got {len(R.RULES)}"


def test_core_count_is_39_and_design_is_9():
    design = [r for r in R.RULES if r["id"].startswith("DESIGN-")]
    core = [r for r in R.RULES if not r["id"].startswith("DESIGN-")]
    assert len(core) == 39, f"expected 39 core rules, got {len(core)}"
    assert len(design) == 9, f"expected 9 DESIGN rules, got {len(design)}"


def test_ids_unique():
    ids = [r["id"] for r in R.RULES]
    assert len(ids) == len(set(ids)), "duplicate rule ids present"


def test_design_01_through_09_all_present():
    ids = {r["id"] for r in R.RULES}
    for n in range(1, 10):
        rid = f"DESIGN-{n:02d}"
        assert rid in ids, f"missing {rid}"


def test_every_rule_has_all_required_fields():
    for r in R.RULES:
        missing = REQUIRED_FIELDS - set(r.keys())
        assert not missing, f"{r['id']} missing fields: {missing}"


def test_enum_fields_use_valid_values():
    for r in R.RULES:
        assert r["severity"] in SEVERITIES, f"{r['id']} bad severity {r['severity']}"
        assert r["min_tier"] in TIERS, f"{r['id']} bad min_tier {r['min_tier']}"
        assert r["source"] in SOURCES, f"{r['id']} bad source {r['source']}"
        assert r["auto"] in AUTOS, f"{r['id']} bad auto {r['auto']}"
        assert r["check"] in CHECKS, f"{r['id']} bad check {r['check']}"


def test_low_risk_auto_rules_have_nonempty_preconditions():
    # The autofix_preconditions gate is what keeps LOW-RISK-AUTO inside the
    # classifier's safety bound — an auto rule with no precondition is a
    # blind-fire and must never exist.
    for r in R.RULES:
        if r["auto"] == "LOW-RISK-AUTO":
            assert r["autofix_preconditions"].strip(), \
                f"{r['id']} is LOW-RISK-AUTO but has empty autofix_preconditions"


def test_only_link01_and_front04_are_low_risk_auto():
    # Of all 48, ONLY LINK-01 (A*) and FRONT-04 (A*) auto-fix.
    auto_ids = {r["id"] for r in R.RULES if r["auto"] == "LOW-RISK-AUTO"}
    assert auto_ids == {"LINK-01", "FRONT-04"}, \
        f"unexpected LOW-RISK-AUTO set: {auto_ids}"


def test_escalate_rules_may_have_empty_preconditions():
    # Conversely, ESCALATE rules carry no precondition gate (it would be dead).
    for r in R.RULES:
        if r["auto"] == "ESCALATE":
            assert r["autofix_preconditions"] == "", \
                f"{r['id']} is ESCALATE but carries a precondition"


def test_deterministic_rules_have_nonempty_checker():
    # A deterministic rule must name the script that owns it, else nothing runs.
    for r in R.RULES:
        if r["check"] == "deterministic":
            assert r["checker"].strip(), \
                f"{r['id']} is check:deterministic but checker is empty"


def test_deterministic_rules_have_catalog_owned_remedies():
    # Deterministic runner output must be self-sufficient: each emitted rule has
    # a concrete repair action without formatter-side rule metadata.
    for r in R.RULES:
        if r["check"] == "deterministic":
            assert r["remedy"].strip(), \
                f"{r['id']} is deterministic but has no catalog remedy"


def test_checker_ownership_partition():
    # Authoritative script-vs-inspector ownership map (design §4.6 / encoding guidance).
    by_id = {r["id"]: r for r in R.RULES}
    front = [f"FRONT-{n:02d}" for n in range(1, 6)]
    link = [f"LINK-{n:02d}" for n in range(1, 5)]
    for rid in front:
        assert by_id[rid]["check"] == "deterministic"
        assert by_id[rid]["checker"] == "frontmatter_check"
    for rid in link:
        assert by_id[rid]["check"] == "deterministic"
        assert by_id[rid]["checker"] == "link_check"
    assert by_id["STRUCT-06"]["check"] == "deterministic"
    assert by_id["STRUCT-06"]["checker"] == "presence_check"
    for rid in ["STRUCT-01", "STRUCT-02", "STRUCT-03", "STRUCT-04", "STRUCT-05",
                "RESID-01", "RESID-02", "RESID-03"]:
        assert by_id[rid]["checker"] == "inspector-structure", rid
    for rid in ["TAXO-01", "TAXO-02", "TAXO-03", "TAXO-04", "CROSS-01", "CROSS-02"]:
        assert by_id[rid]["checker"] == "inspector-taxonomy", rid
    for rid in ["VOL-01", "VOL-02", "STALE-01", "STALE-02"]:
        assert by_id[rid]["checker"] == "inspector-staleness", rid
    for rid in [f"DESIGN-{n:02d}" for n in range(1, 10)]:
        assert by_id[rid]["checker"] == "inspector-design", rid


def test_manual_rules_have_no_owning_checker():
    manual_ids = {"VERIFY-01", "VERIFY-02", "VERIFY-03",
                  "DECISION-01", "DECISION-02", "DECISION-03",
                  "LEARN-01", "LEARN-02", "LEARN-03", "LEARN-04", "SAFETY-01"}
    for r in R.RULES:
        if r["id"] in manual_ids:
            assert r["check"] == "manual", f"{r['id']} should be check:manual"
            assert r["checker"] in ("", "manual"), \
                f"{r['id']} manual rule must not own a script/inspector"


def test_enforces_ruler_true_only_for_struct02_and_vol01():
    # Design line 147: the skill obeys its OWN STRUCT-02 / VOL-01 (catalog dogfood).
    dogfood = {r["id"] for r in R.RULES if r["enforces_ruler"] is True}
    assert dogfood == {"STRUCT-02", "VOL-01"}, \
        f"unexpected enforces_ruler set: {dogfood}"


def test_get_rule_lookup():
    r = R.get_rule("SAFETY-01")
    assert r["id"] == "SAFETY-01" and r["severity"] == "P0"
    try:
        R.get_rule("NOPE-99")
        assert False, "expected KeyError on unknown id"
    except KeyError:
        pass


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
