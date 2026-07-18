#!/usr/bin/env python3
"""CP12 wiring — real-caller threading for the READ path (asserts only). Stdlib-only.

Run: python3 test_wiring.py   (exit 0 = pass) ; also runs under pytest.

This is a VERIFICATION checkpoint: it asserts that the production runner
`doc_lint.py` is wired to the REAL CP01-11 primitives — `lib/rules.py` plus
EACH `checks/*` checker (presence_check, frontmatter_check, link_check,
tier_assess, score) —
and that the aggregated JSON report reflects each checker's REAL contribution on
a fixture repo. NO seam under test is mocked, monkeypatched, or stubbed: the
whole point of CP12 is to prove the integration is real, end to end.

The seam map this file pins (caller -> primitive -> what proves it is REAL):
  * doc_lint.lint -> tier_assess.gather_signals/classify  (tier in the report
    equals the value the real classifier returns for the fixture)
  * doc_lint.default_dispatch -> frontmatter_check.check   (FRONT-* findings in
    the aggregate preserve the real frontmatter checker's raw fields)
  * doc_lint.default_dispatch -> link_check.check          (LINK-* findings in
    the aggregate preserve the real link checker's raw fields)
  * doc_lint.default_dispatch -> presence_check.check      (STRUCT-06 presence
    preflight contributes the real structure score)
  * doc_lint.run -> score.score                            (composite equals the
    real scorer's output for the real per-dimension dim_scores)
  * doc_lint enrichment -> rules.get_rule                  (severity/remedy and
    severity ordering in the report are driven by the real catalog)

The RED-state anti-mock guard (`test_wiring_breaks_if_a_seam_is_mocked`) proves
these assertions actually constrain the wiring: if a checker seam were swapped
for a stub that drops its findings, the aggregate would change and the guard
fails. That guard does NOT mock the production run under verification — it only
demonstrates that the real-vs-fake distinction is observable, so a future
regression that severs a seam cannot pass silently.
"""
import io
import contextlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, os.path.join(HERE, ".."))

import doc_lint as D  # noqa: E402
import frontmatter_check as FC  # noqa: E402
import link_check as LC  # noqa: E402
import presence_check as PC  # noqa: E402
import rules as R  # noqa: E402
import score as SC  # noqa: E402
import tier_assess as TA  # noqa: E402

SAMPLE = os.path.join(HERE, "fixtures", "sample-repo")


def _ids(findings):
    return {f["rule"] for f in findings}


# ==========================================================================
# RED-state anti-mock guard — proves the real-caller assertions have teeth.
# ==========================================================================
def test_wiring_breaks_if_a_seam_is_mocked():
    """A stubbed checker seam changes the aggregate — so REAL wiring is observable.

    This is the conceptual RED: the production `D.lint(SAMPLE, R.RULES)` runs the
    REAL checkers and yields LINK-01. If we instead build a dispatch whose `links`
    checker is a stub that returns nothing (the failure-mode #12 shape — mocking
    the seam under test), the aggregate LOSES LINK-01. The two reports differ,
    proving that the real-vs-mocked distinction is detectable: a regression that
    swaps the real checker for a fake CANNOT produce the real report. The
    production path itself is NEVER mocked in any other test here.
    """
    real = D.lint(SAMPLE, R.RULES)
    assert "LINK-01" in _ids(real["findings"]), \
        "real link_check must contribute LINK-01 to the aggregate"

    def _stub_links(doc_paths, rules):  # a fake seam — for contrast ONLY
        return []

    faked = D.run(D.glob_taxonomy(SAMPLE), R.RULES, tier=real["tier"],
                  dispatch={"frontmatter": D.default_dispatch()["frontmatter"],
                            "links": _stub_links})
    assert "LINK-01" not in _ids(faked["findings"]), \
        "a stubbed link seam must NOT yield LINK-01 (else the test is toothless)"
    # The real aggregate and the stubbed aggregate genuinely differ — the
    # real-caller assertions below therefore constrain the actual wiring.
    assert _ids(real["findings"]) != _ids(faked["findings"]), \
        "real and mocked aggregates must differ — proves the seam matters"


# ==========================================================================
# GREEN — full real-caller threading assertions (NOTHING mocked below).
# ==========================================================================
def test_doc_lint_threads_real_tier_assess():
    """The report's tier IS the value real tier_assess returns for the fixture.

    doc_lint.lint calls tier_assess.gather_signals + tier_assess.classify (no
    override). We compute the tier with the REAL tier_assess directly and assert
    the runner threaded the same value into the report — proving the tier seam is
    real, not a hard-coded constant.
    """
    report = D.lint(SAMPLE, R.RULES)
    expected_tier = TA.classify(TA.gather_signals(SAMPLE))
    assert report["tier"] == expected_tier, (report["tier"], expected_tier)
    assert report["tier"] in ("Simple", "Standard", "Complex"), report["tier"]


def test_doc_lint_threads_real_frontmatter_checker():
    """FRONT-* findings in the aggregate came from the REAL frontmatter_check.

    We run frontmatter_check.check ourselves over the same fixture corpus exactly
    as doc_lint._frontmatter_dispatch does, then assert the aggregate's FRONT-*
    finding ids are EXACTLY the real checker's FRONT-* ids. If doc_lint had
    stubbed/dropped the frontmatter seam, these would diverge.
    """
    report = D.lint(SAMPLE, R.RULES)
    doc_paths = D.glob_taxonomy(SAMPLE)

    # Reproduce the real frontmatter checker's output independently.
    corpus = []
    for p in doc_paths:
        with open(p, encoding="utf-8") as fh:
            fields, _ = FC._parse_frontmatter(fh.read())
        corpus.append((p, fields.get("description", "")))
    real_front = []
    for p in doc_paths:
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        others = [(oid, od) for (oid, od) in corpus if oid != p]
        real_front.extend(FC.check(text, R.RULES, file=p, doc_id=p, others=others))

    aggregate_front = [f for f in report["findings"]
                       if f["rule"].startswith("FRONT-")]
    real_front_ids = {f["rule"] for f in real_front}
    agg_front_ids = {f["rule"] for f in aggregate_front}
    assert agg_front_ids == real_front_ids, (agg_front_ids, real_front_ids)
    raw_fields = lambda f: (f["rule"], f["file"], f["line"], f["message"])
    assert {raw_fields(f) for f in aggregate_front} == {
        raw_fields(f) for f in real_front
    }
    # The fixture is KNOWN-defective: the real frontmatter checker must fire.
    assert "FRONT-01" in agg_front_ids, agg_front_ids
    assert "FRONT-04" in agg_front_ids, agg_front_ids


def test_doc_lint_threads_real_link_checker():
    """LINK-* findings in the aggregate came from the REAL link_check.

    Run link_check.check over the same audited doc set and assert the aggregate's
    LINK-* finding ids equal the real checker's. The fixture's AGENTS.md carries a
    deliberate dead pointer, so LINK-01 must be present — and it must originate
    from the real link checker, not be injected.
    """
    report = D.lint(SAMPLE, R.RULES)
    doc_paths = D.glob_taxonomy(SAMPLE)
    real_links = LC.check(list(doc_paths), R.RULES)
    aggregate_links = [f for f in report["findings"]
                       if f["rule"].startswith("LINK-")]
    real_link_ids = {f["rule"] for f in real_links}
    agg_link_ids = {f["rule"] for f in aggregate_links}
    assert agg_link_ids == real_link_ids, (agg_link_ids, real_link_ids)
    raw_fields = lambda f: (f["rule"], f["file"], f["line"], f["message"])
    assert {raw_fields(f) for f in aggregate_links} == {
        raw_fields(f) for f in real_links
    }
    assert "LINK-01" in agg_link_ids, agg_link_ids


def test_doc_lint_threads_real_presence_checker():
    """The structure dimension comes from the REAL required-doc preflight."""
    report = D.lint(SAMPLE, R.RULES)
    real_presence = PC.check(SAMPLE, R.RULES, tier=report["tier"])
    aggregate = [f for f in report["findings"] if f["rule"] == "STRUCT-06"]
    assert aggregate == real_presence == [], (aggregate, real_presence)
    assert report["target_profile"] == PC.target_profile(SAMPLE), report
    assert report["dimensions"]["structure"] == 10.0, report


def test_doc_lint_aggregate_is_union_of_real_checkers():
    """Every finding traces to a real presence, frontmatter, or link run.

    No finding appears in the aggregate that neither real deterministic checker
    produced — i.e. doc_lint does not invent findings; it threads the union of its
    three real checkers' outputs.
    """
    report = D.lint(SAMPLE, R.RULES)
    doc_paths = D.glob_taxonomy(SAMPLE)
    real_union = set()
    real_union |= {f["rule"] for f in PC.check(
        SAMPLE, R.RULES, tier=report["tier"])}
    real_union |= {f["rule"] for f in D._frontmatter_dispatch(doc_paths, R.RULES)}
    real_union |= {f["rule"] for f in D._link_dispatch(doc_paths, R.RULES)}
    agg_ids = _ids(report["findings"])
    assert agg_ids == real_union, (agg_ids, real_union)


def test_doc_lint_threads_real_score():
    """The report composite equals the REAL score.score over real dim_scores.

    We recompute each dimension's per-dimension score from the REAL checkers'
    finding counts (exactly doc_lint.dimension_score), build the same required-dim
    list doc_lint does, and call the REAL score.score. The result must equal the
    runner's composite — proving the composite is the real scorer's output, not a
    fabricated number.
    """
    report = D.lint(SAMPLE, R.RULES)
    tier = report["tier"]
    doc_paths = D.glob_taxonomy(SAMPLE)

    front = D._frontmatter_dispatch(doc_paths, R.RULES)
    links = D._link_dispatch(doc_paths, R.RULES)
    presence = PC.check(SAMPLE, R.RULES, tier=tier)
    dim_scores = {
        "frontmatter": D.dimension_score(len(front)),
        "links": D.dimension_score(len(links)),
        "structure": D.dimension_score(len(presence), dimension="structure"),
    }
    scored_dims = D.scored_dimensions(R.RULES)
    required = [d for d in D.tier_required_dims(tier, R.RULES, scored_dims)
               if d in dim_scores]
    expected_composite, expected_grade = SC.score(dim_scores, required)
    assert abs(report["composite"] - expected_composite) < 1e-9, \
        (report["composite"], expected_composite)
    assert report["grade"] == expected_grade, (report["grade"], expected_grade)


def test_doc_lint_threads_real_rules_for_severity_ordering():
    """Severity ordering in the report is driven by the REAL rules catalog.

    doc_lint._rule_severity reads rules.get_rule(rid).severity. The findings come
    back severity-sorted (P0 < P1 < P2). We assert the order matches what the REAL
    catalog says for each finding's rule id — so the ordering seam is the real
    catalog, not a stub.
    """
    report = D.lint(SAMPLE, R.RULES)
    ranks = {"P0": 0, "P1": 1, "P2": 2}
    observed = [ranks.get(R.get_rule(f["rule"])["severity"], 9)
                for f in report["findings"]]
    assert observed == sorted(observed), \
        "findings must be ordered by the REAL catalog severity: %r" % observed


def test_doc_lint_threads_real_rules_into_finding_metadata_and_counts():
    report = D.lint(SAMPLE, R.RULES)
    for finding in report["findings"]:
        canonical = R.get_rule(finding["rule"])
        assert finding["severity"] == canonical["severity"], finding
        assert finding["remedy"] == canonical["remedy"], finding
        assert finding["confidence"] == 10, finding
    expected = {severity: sum(
        1 for finding in report["findings"]
        if R.get_rule(finding["rule"])["severity"] == severity)
        for severity in ("P0", "P1", "P2")}
    assert report["severity_counts"] == expected, report


def test_doc_lint_cli_uses_real_rules_loader():
    """The CLI boundary loads the REAL rules.RULES and threads them end to end.

    _load_rules() returns the real catalog; running _main over the fixture must
    fire the same real FRONT-/LINK- ids the in-process real run does — confirming
    the production CLI path (not just the DI core) is wired to the real primitives.
    """
    import json
    assert D._load_rules() is R.RULES, "CLI loads the real rules.RULES object"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D._main(["--target", SAMPLE, "--json"])
    payload = json.loads(buf.getvalue())
    ids = [f["rule"] for f in payload["findings"]]
    assert ids == ["FRONT-01", "FRONT-04", "LINK-01"], ids


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
