#!/usr/bin/env python3
"""Tests for doc_lint.py + gen_rule_catalog.py (CP04). Stdlib-only.

Run: python3 test_doc_lint.py   (exit 0 = pass) ; also runs under pytest.

doc_lint is the top-level READ-ONLY runner: it globs the doc taxonomy (or a
`--target`), classifies the tier, dispatches ONLY the deterministic checkers
(frontmatter_check, link_check), and aggregates their findings into a scored
report via score.py — mapping tier -> required dimensions itself before calling
score(). The load-bearing invariants asserted here:

  * the aggregate report has the contracted shape and a stable composite for a
    KNOWN-defective fixture repo (fixtures/sample-repo/);
  * specific finding ids fire deterministically off that fixture;
  * the FAILURE-MODE GUARD: a checker that RAISES is recorded in `skipped`
    (with a reason) and its dimension weight redistributes via score.py —
    doc_lint still emits a valid report and never crashes mid-run;
  * `--fail-on` exit-code gating at/above a severity threshold;
  * gen_rule_catalog round-trips: the generated catalog matches the committed
    file (so `--check` is in sync), and a mutated catalog is detected as drift.

The core `run()` is pure/DI: doc paths, rules, tier, and the checker dispatch
table all go in as ARGUMENTS — only the CLI loads real assets. That lets the
raising-checker guard be exercised by injecting a dispatch entry whose callable
raises, with no monkeypatching of the real checkers.
"""
import io
import contextlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, os.path.join(HERE, ".."))

import doc_lint as D  # noqa: E402
import gen_rule_catalog as G  # noqa: E402
import rules as R  # noqa: E402

SAMPLE = os.path.join(HERE, "fixtures", "sample-repo")


def _ids(findings):
    return {f["rule"] for f in findings}


# ----------------------------------------------------------- taxonomy globbing
def test_glob_taxonomy_finds_known_doc_types():
    paths = D.glob_taxonomy(SAMPLE)
    names = {os.path.basename(p) for p in paths}
    # The fixture ships two audited charters. Its skill-shaped sample is named
    # SKILL.fixture.md so the public package contains no nested discoverable skill.
    assert "CLAUDE.md" in names, names
    assert "AGENTS.md" in names, names
    assert "SKILL.md" not in names, names
    assert os.path.isfile(os.path.join(SAMPLE, "SKILL.fixture.md"))


def test_glob_taxonomy_ignores_unrelated_files():
    paths = D.glob_taxonomy(SAMPLE)
    names = {os.path.basename(p) for p in paths}
    # The fixture's package.json / src files must NOT be audited as docs.
    assert "package.json" not in names, names
    assert not any(n.endswith(".py") for n in names), names


# ------------------------------------------------------ tier -> required_dims
def test_required_dims_are_subset_of_scored_dims():
    # Whatever the tier, required dims must be a non-empty subset of the
    # deterministic scored dims (score() rejects an empty required set).
    for tier in ("Simple", "Standard", "Complex"):
        req = D.tier_required_dims(tier, R.RULES, D.scored_dimensions(R.RULES))
        assert req, f"{tier} produced empty required_dims"
        assert set(req) <= set(D.scored_dimensions(R.RULES)), req


def test_scored_dims_are_only_the_deterministic_ones():
    # doc_lint only scores dimensions it can compute deterministically:
    # required-doc structure (presence_check), frontmatter, and links. Semantic
    # structure plus inspector/manual dimensions are NOT scored here.
    dims = set(D.scored_dimensions(R.RULES))
    assert dims == {"structure", "frontmatter", "links"}, dims


# ------------------------------------------------------------ aggregate shape
def test_report_has_contracted_shape():
    report = D.lint(SAMPLE, R.RULES)
    for key in ("passed", "tier", "composite", "grade", "findings", "skipped",
                "scope", "target_profile", "structure_scope", "dimensions",
                "severity_counts", "schema_version", "canonical_target",
                "git_revision", "content_digest"):
        assert key in report, f"missing key {key!r}: {sorted(report)}"
    assert isinstance(report["findings"], list), report
    assert isinstance(report["skipped"], list), report
    assert 0.0 <= report["composite"] <= 10.0, report["composite"]
    assert report["grade"] in ("PASS", "PASS_WITH_CONCERNS", "FAIL"), report
    assert report["scope"] == "deterministic", report
    assert report["target_profile"] == "repository", report
    assert report["structure_scope"] == "required-document-presence", report
    assert report["dimensions"] == {
        "frontmatter": 4.0, "links": 7.0, "structure": 10.0
    }, report
    assert set(report["severity_counts"]) == {"P0", "P1", "P2"}, report
    assert report["schema_version"] == D.REPORT_SCHEMA_VERSION, report
    assert report["canonical_target"] == os.path.realpath(SAMPLE), report
    assert report["git_revision"] is not None, report
    assert report["content_digest"].startswith("sha256:"), report


def test_non_git_report_has_null_revision_and_stable_content_binding(tmp_path):
    _write_doc(tmp_path, "AGENTS.md", "# one\n")
    first = D.lint(str(tmp_path), R.RULES, tier_override="Simple")
    second = D.lint(os.path.join(str(tmp_path), "."), R.RULES,
                    tier_override="Simple")
    assert first["canonical_target"] == os.path.realpath(str(tmp_path)), first
    assert first["git_revision"] is None, first
    assert first["content_digest"] == second["content_digest"], (first, second)


def test_content_binding_changes_with_current_target_content(tmp_path):
    doc = _write_doc(tmp_path, "AGENTS.md", "# before\n")
    before = D.lint(str(tmp_path), R.RULES, tier_override="Simple")
    with open(doc, "a", encoding="utf-8") as fh:
        fh.write("after\n")
    after = D.lint(str(tmp_path), R.RULES, tier_override="Simple")
    assert before["content_digest"] != after["content_digest"], (before, after)


def test_history_append_does_not_change_evaluate_content_binding(tmp_path):
    _write_doc(tmp_path, "AGENTS.md", "# stable\n")
    before = D.target_content_digest(str(tmp_path))
    history_dir = os.path.join(str(tmp_path), ".doc-steward")
    os.makedirs(history_dir)
    with open(os.path.join(history_dir, "history.jsonl"), "w",
              encoding="utf-8") as fh:
        fh.write('{"score": 10}\n')
    assert D.target_content_digest(str(tmp_path)) == before


def test_known_fixture_fires_specific_finding_ids():
    # The sample-repo CLAUDE.md has a deliberately weak description (FRONT-01)
    # and a missing semver version (FRONT-04); AGENTS.md has a dead pointer
    # (LINK-01). These deterministic ids MUST appear.
    report = D.lint(SAMPLE, R.RULES)
    ids = _ids(report["findings"])
    assert "FRONT-01" in ids, ids
    assert "FRONT-04" in ids, ids
    assert "LINK-01" in ids, ids


def test_known_fixture_has_exact_findings_and_front04_field_anchor():
    report = D.lint(SAMPLE, R.RULES)
    assert len(report["findings"]) == 3, report["findings"]
    assert [f["rule"] for f in report["findings"]] == [
        "FRONT-01", "FRONT-04", "LINK-01"
    ], report["findings"]
    front04 = next(f for f in report["findings"] if f["rule"] == "FRONT-04")
    assert os.path.basename(front04["file"]) == "CLAUDE.md", front04
    assert front04["line"] == 3, front04
    assert report["severity_counts"] == {"P0": 0, "P1": 3, "P2": 0}, report


def test_every_deterministic_finding_is_self_sufficient():
    report = D.lint(SAMPLE, R.RULES)
    for finding in report["findings"]:
        rule = R.get_rule(finding["rule"])
        assert finding["severity"] == rule["severity"], finding
        assert finding["confidence"] == 10, finding
        assert finding["remedy"] == rule["remedy"], finding
        assert finding["remedy"].strip(), finding


def test_finding_enrichment_preserves_checker_owned_extra_keys():
    def checker(doc_paths, rules):
        return [{"rule": "LINK-01", "file": "AGENTS.md", "line": 7,
                 "message": "dead pointer @missing.md", "sentinel": "kept"}]

    report = D.run([], R.RULES, tier="Simple", dispatch={"links": checker})
    assert report["findings"][0]["sentinel"] == "kept", report


def test_known_fixture_composite_is_below_pass_and_stable():
    # With real deterministic defects in both scored dimensions, the composite
    # must drop below the PASS threshold (8.0) and the run must NOT pass.
    report = D.lint(SAMPLE, R.RULES)
    assert report["composite"] < 8.0, report["composite"]
    assert report["passed"] is False, report
    # Stability: re-running yields the identical composite (pure aggregation).
    again = D.lint(SAMPLE, R.RULES)
    assert again["composite"] == report["composite"], (again, report)


def test_clean_inputs_score_perfect_and_pass():
    # The context-free DI core retains its clean-input behavior. A real target
    # uses lint(), which binds the required-document presence preflight below.
    report = D.run([], R.RULES, tier="Standard",
                   dispatch=D.default_dispatch())
    assert report["composite"] == 10.0, report
    assert report["passed"] is True, report
    assert report["findings"] == [], report
    assert report["skipped"] == [], report


# ------------------------------------------ required-document presence preflight
def _write_doc(root, relative, text="# fixture\n"):
    path = os.path.join(str(root), relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def test_real_empty_target_fails_with_zeroed_core_dimensions(tmp_path):
    report = D.lint(str(tmp_path), R.RULES)
    assert _ids(report["findings"]) == {"STRUCT-06"}, report
    assert report["dimensions"] == {
        "frontmatter": 0.0, "links": 0.0, "structure": 0.0
    }, report
    assert report["composite"] == 0.0, report
    assert report["grade"] == "FAIL" and report["passed"] is False, report
    finding = report["findings"][0]
    assert finding["root_charter_present"] is False, finding
    assert finding["missing"] == ["AGENTS.md or CLAUDE.md"], finding


def test_simple_target_with_one_root_charter_passes(tmp_path):
    _write_doc(tmp_path, "AGENTS.md")
    report = D.lint(str(tmp_path), R.RULES, tier_override="Simple")
    assert report["findings"] == [], report
    assert report["composite"] == 10.0 and report["passed"] is True, report


def test_standard_missing_one_root_surface_is_a_weighted_p1_concern(tmp_path):
    _write_doc(tmp_path, "CLAUDE.md")
    report = D.lint(str(tmp_path), R.RULES, tier_override="Standard")
    assert _ids(report["findings"]) == {"STRUCT-06"}, report
    finding = report["findings"][0]
    assert finding["severity"] == "P1", finding
    assert finding["missing"] == ["AGENTS.md"], finding
    assert report["dimensions"]["structure"] == 4.0, report
    assert abs(report["composite"] - 7.0) < 1e-9, report
    assert report["grade"] == "PASS_WITH_CONCERNS", report


def test_complex_requires_rules_and_decision_surfaces(tmp_path):
    _write_doc(tmp_path, "AGENTS.md")
    _write_doc(tmp_path, "CLAUDE.md")
    report = D.lint(str(tmp_path), R.RULES, tier_override="Complex")
    finding = next(f for f in report["findings"]
                   if f["rule"] == "STRUCT-06")
    assert finding["missing"] == [
        ".claude/rules/*.md", "docs/decisions/*.md"
    ], finding
    assert report["grade"] == "PASS_WITH_CONCERNS", report


def test_nested_only_charters_and_skill_do_not_satisfy_root(tmp_path):
    _write_doc(tmp_path, "service/AGENTS.md")
    _write_doc(tmp_path, "skills/demo/SKILL.md", """---
name: demo
description: Audit demo docs. Use when checking fixtures. Not for deployment.
---
""")
    report = D.lint(str(tmp_path), R.RULES, tier_override="Simple")
    assert report["target_profile"] == "repository", report
    assert report["composite"] == 0.0 and report["grade"] == "FAIL", report
    finding = next(f for f in report["findings"]
                   if f["rule"] == "STRUCT-06")
    assert finding["root_charter_present"] is False, finding


def test_root_skill_uses_skill_package_profile_without_repo_charters(tmp_path):
    _write_doc(tmp_path, "SKILL.md", """---
name: demo
description: Audit demo docs. Use when checking fixtures. Not for deployment.
---
""")
    report = D.lint(str(tmp_path), R.RULES, tier_override="Complex")
    assert report["target_profile"] == "skill-package", report
    assert "STRUCT-06" not in _ids(report["findings"]), report
    assert report["composite"] == 10.0 and report["passed"] is True, report


# --------------------------------------------- FAILURE-MODE GUARD (critical)
def test_raising_checker_is_caught_as_skipped_not_a_crash():
    # Inject a dispatch whose `links` checker RAISES. doc_lint MUST catch it,
    # record `links` in `skipped` with a reason, redistribute its weight via
    # score.py, and still produce a valid report — never propagate the error.
    def boom(doc_paths, rules):
        raise RuntimeError("synthetic checker explosion")

    dispatch = {
        "frontmatter": D.default_dispatch()["frontmatter"],
        "links": boom,
    }
    report = D.run(D.glob_taxonomy(SAMPLE), R.RULES, tier="Standard",
                   dispatch=dispatch)

    skipped_dims = {s["dimension"] for s in report["skipped"]}
    assert "links" in skipped_dims, report["skipped"]
    reason = next(s for s in report["skipped"] if s["dimension"] == "links")
    assert "RuntimeError" in reason["reason"] or "explosion" in reason["reason"], \
        reason
    # The report is still well-formed and the surviving dimension still scored.
    assert 0.0 <= report["composite"] <= 10.0, report["composite"]
    assert report["grade"] in ("PASS", "PASS_WITH_CONCERNS", "FAIL"), report
    # No `links` findings leaked from the crashed checker.
    assert "LINK-01" not in _ids(report["findings"]), report["findings"]


def test_skipped_dimension_weight_redistributes_not_zeroed():
    # A skipped dimension must NOT drag the composite to zero — its weight
    # redistributes onto the surviving dimensions (score.py invariant). With
    # frontmatter the only survivor, the composite equals frontmatter's own
    # per-dimension score (effective weight 1.0 after redistribution).
    def boom(doc_paths, rules):
        raise ValueError("down")

    dispatch = {"frontmatter": D.default_dispatch()["frontmatter"],
                "links": boom}
    report = D.run(D.glob_taxonomy(SAMPLE), R.RULES, tier="Standard",
                   dispatch=dispatch)
    # frontmatter alone is required+scored; composite is exactly its dim score.
    front_only = D.run(D.glob_taxonomy(SAMPLE), R.RULES, tier="Standard",
                       dispatch={"frontmatter":
                                 D.default_dispatch()["frontmatter"]})
    assert abs(report["composite"] - front_only["composite"]) < 1e-9, \
        (report["composite"], front_only["composite"])


def test_emits_valid_json_even_when_all_checkers_raise():
    # Belt-and-suspenders: if EVERY checker raises, doc_lint still emits a
    # valid report (all dims skipped -> composite 0 / FAIL, never a crash).
    def boom(doc_paths, rules):
        raise RuntimeError("everything is on fire")

    dispatch = {"frontmatter": boom, "links": boom}
    report = D.run(D.glob_taxonomy(SAMPLE), R.RULES, tier="Standard",
                   dispatch=dispatch)
    assert {s["dimension"] for s in report["skipped"]} == {"frontmatter",
                                                           "links"}, report
    assert report["composite"] == 0.0, report
    assert report["grade"] == "FAIL", report
    assert report["passed"] is False, report


# ------------------------------------------------------------- CLI behaviour
def test_cli_json_output_is_parseable():
    import json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = D._main(["--target", SAMPLE, "--json"])
    payload = json.loads(buf.getvalue())
    assert "composite" in payload and "findings" in payload, payload
    # Defective fixture -> non-zero exit even without --fail-on (passed False).
    assert rc != 0, rc


def test_cli_no_config_does_not_require_pyyaml():
    # `-S` omits site-packages, including PyYAML. The default audit still emits
    # its normal JSON report because YAML is needed only for explicit --config.
    result = subprocess.run(
        [sys.executable, "-S", D.__file__, "--target", SAMPLE, "--json"],
        capture_output=True, text=True)
    assert result.returncode == 1, (result.stdout, result.stderr)
    payload = __import__("json").loads(result.stdout)
    assert payload["scope"] == "deterministic", payload
    assert "yaml" not in result.stderr.lower(), result.stderr


def test_cli_explicit_config_fails_clearly_without_pyyaml(tmp_path):
    config = os.path.join(str(tmp_path), "config.yml")
    with open(config, "w", encoding="utf-8") as fh:
        fh.write("tier: Simple\n")
    result = subprocess.run(
        [sys.executable, "-S", D.__file__, "--target", SAMPLE, "--json",
         "--config", config], capture_output=True, text=True)
    assert result.returncode != 0, (result.stdout, result.stderr)
    assert "PyYAML is required only when an explicit --config path is used" \
        in result.stderr, result.stderr


def test_cli_fail_on_p1_exits_nonzero_when_p1_present():
    # FRONT-01 is a P1; --fail-on P1 must force a non-zero exit.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = D._main(["--target", SAMPLE, "--json",
                      "--fail-on", "P1"])
    assert rc != 0, rc


def test_cli_fail_on_p0_exits_zero_when_no_p0():
    # The deterministic defects in the fixture are P1/P2 (FRONT-01/04, LINK-01).
    # LINK-01 is P1, FRONT-04 is P1 — none are P0 — so --fail-on P0 passes the
    # gate (exit 0) even though findings exist.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = D._main(["--target", SAMPLE, "--json",
                      "--fail-on", "P0"])
    assert rc == 0, rc


def test_cli_tier_override_is_honored():
    import json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D._main(["--target", SAMPLE, "--json",
                 "--tier", "Complex"])
    payload = json.loads(buf.getvalue())
    assert payload["tier"] == "Complex", payload


# ----------------------------------------------------- explicit config wiring
def test_cli_config_tier_raises_effective_tier(tmp_path):
    import json
    config = os.path.join(str(tmp_path), "config.yml")
    with open(config, "w", encoding="utf-8") as fh:
        fh.write("tier: Complex\n")
    # Baseline: without config the small fixture auto-detects below Complex.
    buf0 = io.StringIO()
    with contextlib.redirect_stdout(buf0):
        D._main(["--target", SAMPLE, "--json"])
    base_tier = json.loads(buf0.getvalue())["tier"]
    assert base_tier != "Complex", base_tier
    # Explicit config raises the effective tier to Complex.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D._main(["--target", SAMPLE, "--json", "--config", config])
    assert json.loads(buf.getvalue())["tier"] == "Complex"


def test_cli_explicit_tier_beats_config_tier(tmp_path):
    import json
    config = os.path.join(str(tmp_path), "config.yml")
    with open(config, "w", encoding="utf-8") as fh:
        fh.write("tier: Complex\n")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D._main(["--target", SAMPLE, "--json", "--config", config,
                 "--tier", "Simple"])
    assert json.loads(buf.getvalue())["tier"] == "Simple"


def test_lint_threads_overlay_tier_into_classify(tmp_path):
    # The lint() helper (not only the CLI) must accept and apply an overlay tier.
    report = D.lint(SAMPLE, R.RULES, overlay={"tier": "Complex"})
    assert report["tier"] == "Complex", report


def test_cli_default_writes_no_history(tmp_path):
    import shutil
    # Copy the sample-repo into a writable tmp dir so we can assert no write.
    dst = os.path.join(str(tmp_path), "repo")
    shutil.copytree(SAMPLE, dst)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D._main(["--target", dst, "--json"])
    assert not os.path.exists(os.path.join(dst, ".doc-steward")), \
        "default audit must not write a run-log"


def test_cli_history_flag_appends_history_log(tmp_path):
    import shutil
    dst = os.path.join(str(tmp_path), "repo")
    shutil.copytree(SAMPLE, dst)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D._main(["--target", dst, "--json", "--history"])
    payload = __import__("json").loads(buf.getvalue())
    assert payload["history"] == {
        "status": "appended", "path": ".doc-steward/history.jsonl"
    }, payload
    log = os.path.join(dst, ".doc-steward", "history.jsonl")
    assert os.path.exists(log), "--history must append the run-log"
    # The audited docs themselves must be byte-for-byte untouched (read-only).
    with open(os.path.join(dst, "CLAUDE.md"), encoding="utf-8") as fh:
        body = fh.read()
    assert "The helper." in body, "audited doc must not be mutated"


def test_cli_history_refuses_symlink_escape_with_visible_nonzero_report(tmp_path):
    import json
    import shutil
    dst = os.path.join(str(tmp_path), "repo")
    outside = os.path.join(str(tmp_path), "outside")
    shutil.copytree(SAMPLE, dst)
    os.mkdir(outside)
    os.symlink(outside, os.path.join(dst, ".doc-steward"),
               target_is_directory=True)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = D._main(["--target", dst, "--json", "--history",
                      "--fail-on", "P0"])
    payload = json.loads(buf.getvalue())

    assert rc != 0, rc
    assert payload["history"]["status"] == "refused", payload
    assert "HistoryBoundaryError" in payload["history"]["reason"], payload
    assert not os.path.exists(os.path.join(outside, "history.jsonl"))


def test_cli_default_audit_does_not_touch_symlinked_history_directory(tmp_path):
    import json
    import shutil
    dst = os.path.join(str(tmp_path), "repo")
    outside = os.path.join(str(tmp_path), "outside")
    shutil.copytree(SAMPLE, dst)
    os.mkdir(outside)
    marker = os.path.join(outside, "marker")
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write("unchanged\n")
    os.symlink(outside, os.path.join(dst, ".doc-steward"),
               target_is_directory=True)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = D._main(["--target", dst, "--json", "--fail-on", "P0"])
    payload = json.loads(buf.getvalue())

    assert rc == 0, rc
    assert "history" not in payload, payload
    assert os.listdir(outside) == ["marker"], os.listdir(outside)
    with open(marker, encoding="utf-8") as fh:
        assert fh.read() == "unchanged\n"


def test_cli_text_history_refusal_does_not_render_pass(tmp_path):
    import shutil
    dst = os.path.join(str(tmp_path), "repo")
    outside = os.path.join(str(tmp_path), "outside")
    shutil.copytree(SAMPLE, dst)
    os.mkdir(outside)
    os.symlink(outside, os.path.join(dst, ".doc-steward"),
               target_is_directory=True)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = D._main(["--target", dst, "--history", "--fail-on", "P0"])
    output = buf.getvalue()

    assert rc != 0, rc
    assert "[HISTORY] refused" in output, output
    assert output.rstrip().endswith(
        "NOT-PASS (requested history write refused)"), output


def test_cli_text_output_is_human_readable():
    # Default (non-JSON) text mode renders a header + finding lines + verdict.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        D._main(["--target", SAMPLE])
    out = buf.getvalue()
    assert "DOC-STEWARD LINT" in out, out
    assert "tier=" in out and "composite=" in out, out
    assert "FRONT-01" in out, out
    assert "scope=deterministic" in out, out
    assert "profile=repository" in out, out
    assert "structure-scope=required-document-presence" in out, out
    assert "dimensions=frontmatter=4.00,links=7.00,structure=10.00" in out, out
    assert "COUNTS — P0=0 P1=3 P2=0" in out, out
    assert "(confidence: 10/10)" in out and " → " in out, out


def test_text_output_renders_skipped_lines():
    # The text formatter must surface skipped dimensions (guard visibility).
    def boom(doc_paths, rules):
        raise RuntimeError("kaboom")
    report = D.run(D.glob_taxonomy(SAMPLE), R.RULES, tier="Standard",
                   dispatch={"frontmatter": D.default_dispatch()["frontmatter"],
                             "links": boom})
    text = D._format_text(report)
    assert "[SKIPPED] links" in text, text


def test_unavailable_checker_is_skipped():
    # A dispatch entry that is None (checker unavailable) is recorded skipped
    # with a reason, exercising the non-exception branch of the guard.
    report = D.run(D.glob_taxonomy(SAMPLE), R.RULES, tier="Standard",
                   dispatch={"frontmatter": D.default_dispatch()["frontmatter"],
                             "links": None})
    reasons = {s["dimension"]: s["reason"] for s in report["skipped"]}
    assert "links" in reasons, report["skipped"]
    assert "unavailable" in reasons["links"], reasons


# ------------------------------------------------------ gen_rule_catalog drift
def test_generated_catalog_matches_committed_file():
    # The committed references/rule-catalog.md must equal freshly-generated
    # content, i.e. `gen_rule_catalog.py --check` is in sync after generation.
    generated = G.render(R.RULES)
    with open(G.catalog_path(), encoding="utf-8") as fh:
        on_disk = fh.read()
    assert generated == on_disk, \
        "rule-catalog.md drifted from lib/rules.py — run gen_rule_catalog.py"


def test_check_mode_reports_in_sync():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = G._main(["--check"])
    assert rc == 0, f"--check should be 0 (in sync), got {rc}: {buf.getvalue()}"


def test_check_mode_detects_drift(tmp_path):
    # Point the generator at a mutated copy and assert --check returns 1.
    mutated = os.path.join(str(tmp_path), "rule-catalog.md")
    with open(mutated, "w", encoding="utf-8") as fh:
        fh.write("# totally wrong content\n")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = G._main(["--check", "--out", mutated])
    assert rc == 1, f"--check must detect drift (exit 1), got {rc}"


def test_render_includes_every_rule_id():
    # The generated catalog must mention every rule id from lib/rules.py
    # (no silent rule drops — dogfoods STRUCT-02 single-source).
    text = G.render(R.RULES)
    for rule in R.RULES:
        assert rule["id"] in text, f"{rule['id']} missing from generated catalog"


def test_render_is_deterministic():
    assert G.render(R.RULES) == G.render(R.RULES)


def test_generate_writes_file(tmp_path):
    out = os.path.join(str(tmp_path), "cat.md")
    G.generate(R.RULES, out)
    with open(out, encoding="utf-8") as fh:
        assert fh.read() == G.render(R.RULES)


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    import tempfile
    import shutil
    import pathlib
    failed = 0
    for t in tests:
        tmp = None
        try:
            argc = t.__code__.co_argcount
            if "tmp_path" in t.__code__.co_varnames[:argc]:
                tmp = tempfile.mkdtemp()
                t(pathlib.Path(tmp))
            else:
                t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
