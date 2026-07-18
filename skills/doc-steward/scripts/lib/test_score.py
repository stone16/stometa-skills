#!/usr/bin/env python3
"""Tests for score.py (the tiered weighted-composite scorer). Stdlib-only.

Run: python3 test_score.py   (exit 0 = pass) ; also runs under pytest.
The scorer is pure/DI: per-dimension scores + the tier's required dims go in,
a 0-10 composite + verdict come out. The load-bearing invariant is
weight-redistribution: a dimension not required at this tier must not be
allowed to drag the composite down — its weight redistributes onto the
required dims.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score as S  # noqa: E402

# A controlled weight table (fixture) so tests stay stable as real weights evolve.
WEIGHTS = {
    "structure": 0.30,
    "staleness": 0.20,
    "taxonomy": 0.20,
    "links": 0.15,
    "frontmatter": 0.15,
}
ALL_DIMS = list(WEIGHTS.keys())


def test_all_dims_required_is_plain_weighted_mean():
    findings = {"structure": 8, "staleness": 8, "taxonomy": 8,
                "links": 8, "frontmatter": 8}
    composite, verdict = S.score(findings, ALL_DIMS, WEIGHTS)
    assert abs(composite - 8.0) < 1e-9, composite


def test_skipped_dim_redistributes_and_never_lowers_score():
    # The skipped dim ("frontmatter") scores LOW. With all dims present it drags
    # the composite down; once frontmatter is not required at this tier, its
    # weight redistributes across the remaining dims and the composite MUST be
    # >= the all-present baseline computed from the same per-dim scores.
    findings = {"structure": 9, "staleness": 9, "taxonomy": 9,
                "links": 9, "frontmatter": 1}
    baseline, _ = S.score(findings, ALL_DIMS, WEIGHTS)
    required = ["structure", "staleness", "taxonomy", "links"]  # frontmatter skipped
    redistributed, _ = S.score(findings, required, WEIGHTS)
    assert redistributed >= baseline, (redistributed, baseline)
    # And here, since every required dim outscores the skipped one, it strictly rises.
    assert redistributed > baseline, (redistributed, baseline)


def test_redistribution_preserves_weight_sum():
    # When only a subset is required, the effective weights over the required dims
    # must still sum to 1.0, so a perfect required set scores a perfect 10.
    findings = {"structure": 10, "staleness": 10}
    composite, _ = S.score(findings, ["structure", "staleness"], WEIGHTS)
    assert abs(composite - 10.0) < 1e-9, composite


def test_required_dim_missing_from_findings_scores_zero():
    # If a tier-required dimension produced no score, it counts as 0 (a gap is
    # a finding, not a free pass). Redistribution is PROPORTIONAL to base mass,
    # not equal: base structure=0.30, staleness=0.20 over total 0.50 →
    # eff structure=0.60, staleness=0.40 → 10*0.60 + 0*0.40 = 6.0.
    findings = {"structure": 10}  # staleness required but absent
    composite, _ = S.score(findings, ["structure", "staleness"], WEIGHTS)
    assert abs(composite - 6.0) < 1e-9, composite


def test_redistribution_is_proportional_to_base_mass():
    # Two equal-scored dims with UNEQUAL base weights must keep their relative
    # influence after redistribution (proportional, not flattened to equal).
    findings = {"structure": 9, "links": 3}  # base 0.30 vs 0.15
    composite, _ = S.score(findings, ["structure", "links"], WEIGHTS)
    # eff structure=0.30/0.45=2/3, links=0.15/0.45=1/3 → 9*2/3 + 3*1/3 = 7.0
    assert abs(composite - 7.0) < 1e-9, composite


def test_verdict_thresholds():
    # PASS >= 8.0 ; FAIL < 5.0 ; PASS_WITH_CONCERNS in between.
    def verdict_for(s):
        findings = {"structure": s}
        _, v = S.score(findings, ["structure"], WEIGHTS)
        return v

    assert verdict_for(10) == "PASS"
    assert verdict_for(8) == "PASS"
    assert verdict_for(7.9) == "PASS_WITH_CONCERNS"
    assert verdict_for(5) == "PASS_WITH_CONCERNS"
    assert verdict_for(4.9) == "FAIL"
    assert verdict_for(0) == "FAIL"


def test_composite_clamped_to_0_10():
    composite, _ = S.score({"structure": 10}, ["structure"], WEIGHTS)
    assert 0.0 <= composite <= 10.0


def test_empty_required_raises():
    try:
        S.score({"structure": 5}, [], WEIGHTS)
        assert False, "expected error on empty required_dims"
    except ValueError:
        pass


def test_unknown_required_dim_raises():
    try:
        S.score({"structure": 5}, ["nope"], WEIGHTS)
        assert False, "expected error on unknown required dim"
    except (KeyError, ValueError):
        pass


def test_zero_base_mass_falls_back_to_uniform():
    # Degenerate weight table (required dims all weight 0) must NOT divide by
    # zero; it falls back to uniform weights over the required dims.
    zero_weights = {"a": 0.0, "b": 0.0}
    composite, _ = S.score({"a": 10, "b": 0}, ["a", "b"], zero_weights)
    # uniform 0.5/0.5 → (10 + 0)/2 = 5.0
    assert abs(composite - 5.0) < 1e-9, composite


def test_module_default_weights_usable():
    # When weights omitted, the module-level DEFAULT_WEIGHTS apply (DI default).
    composite, verdict = S.score({d: 8 for d in S.DEFAULT_WEIGHTS},
                                 list(S.DEFAULT_WEIGHTS))
    assert abs(composite - 8.0) < 1e-9, composite
    assert verdict == "PASS"


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
