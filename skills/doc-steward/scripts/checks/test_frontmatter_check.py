#!/usr/bin/env python3
"""Tests for frontmatter_check.py (FRONT-01..05). Stdlib-only.

Run: python3 test_frontmatter_check.py   (exit 0 = pass) ; also runs under pytest.

Each test encodes a RULE INVARIANT, not a code path: every bad-fixture proves
the finding fires, every good-fixture proves it does NOT. `check()` is pure —
it takes `frontmatter_text` and the rule list as ARGUMENTS (DI seam); the CLI is
the only place that loads real assets.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import frontmatter_check as F  # noqa: E402
import rules as R  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def _read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def _ids(violations):
    return {v["rule"] for v in violations}


# ---------------------------------------------------------------- FRONT-01
def test_front01_fires_on_bad_description():
    # Short (<40), non-verb-first ("The"), no "Use when"/"Not for".
    v = F.check(_read("front_bad_desc.md"), R.RULES)
    assert "FRONT-01" in _ids(v), f"FRONT-01 must fire on bad desc: {_ids(v)}"


def test_front01_silent_on_good_description():
    v = F.check(_read("front_good.md"), R.RULES)
    assert "FRONT-01" not in _ids(v), f"FRONT-01 must not fire on good desc: {v}"


def test_front01_fires_when_too_long():
    # >500 chars description, otherwise well-formed.
    long_desc = "Audit " + ("x" * 600) + " Use when reviewing. Not for prod."
    text = f"---\nname: x\nversion: 1.0.0\ndescription: {long_desc}\n---\n"
    v = F.check(text, R.RULES)
    assert "FRONT-01" in _ids(v), "FRONT-01 must fire when description > 500 chars"


def test_front01_fires_when_missing_use_when_or_not_for():
    # In range, verb-first, English, but missing the required phrases.
    desc = "Audit and steward repository documentation against the standard now."
    text = f"---\nname: x\nversion: 1.0.0\ndescription: {desc}\n---\n"
    v = F.check(text, R.RULES)
    assert "FRONT-01" in _ids(v), "FRONT-01 must fire when 'Use when'/'Not for' absent"


# ---------------------------------------------------------------- FRONT-02
def test_front02_fires_on_non_english_description():
    v = F.check(_read("front_bad_lang.md"), R.RULES)
    assert "FRONT-02" in _ids(v), f"FRONT-02 must fire on CJK desc: {_ids(v)}"


def test_front02_silent_on_english_description():
    v = F.check(_read("front_good.md"), R.RULES)
    assert "FRONT-02" not in _ids(v), f"FRONT-02 must not fire on English: {v}"


# ---------------------------------------------------------------- FRONT-04
def test_front04_fires_on_missing_name_and_bad_version():
    v = F.check(_read("front_bad_meta.md"), R.RULES)
    assert "FRONT-04" in _ids(v), f"FRONT-04 must fire on missing name/bad ver: {_ids(v)}"


def test_front04_silent_on_well_formed_meta():
    v = F.check(_read("front_good.md"), R.RULES)
    assert "FRONT-04" not in _ids(v), f"FRONT-04 must not fire on good meta: {v}"


def test_front04_fires_on_non_semver_version():
    text = "---\nname: ok\nversion: v3\ndescription: |\n  Audit docs now. Use when auditing. Not for builds.\n---\n"
    v = F.check(text, R.RULES)
    assert "FRONT-04" in _ids(v), "FRONT-04 must fire on non-semver version"


# ---------------------------------------------------------------- FRONT-03
def test_front03_fires_on_high_jaccard_overlap_between_two_docs():
    # Multi-doc entry point: `others` carries (doc_id, description) pairs to
    # compare. Near-identical descriptions => Jaccard >= 0.5 => collision.
    base = "Audit and steward repo docs. Use when reviewing docs. Not for builds."
    text = f"---\nname: a\nversion: 1.0.0\ndescription: {base}\n---\n"
    others = [("b", "Audit and steward repo docs. Use when reviewing docs. Not for tests.")]
    v = F.check(text, R.RULES, doc_id="a", others=others)
    assert "FRONT-03" in _ids(v), f"FRONT-03 must fire on >=50% Jaccard: {_ids(v)}"


def test_front03_silent_on_distinct_descriptions():
    base = "Audit and steward repo docs. Use when reviewing docs. Not for builds."
    text = f"---\nname: a\nversion: 1.0.0\ndescription: {base}\n---\n"
    others = [("b", "Render slide decks from markdown. Use when presenting. Not for audits.")]
    v = F.check(text, R.RULES, doc_id="a", others=others)
    assert "FRONT-03" not in _ids(v), f"FRONT-03 must not fire on distinct desc: {v}"


def test_front03_silent_without_other_docs():
    # FRONT-03 needs >=2 docs to compare; single-doc call must never fire it.
    v = F.check(_read("front_good.md"), R.RULES)
    assert "FRONT-03" not in _ids(v), "FRONT-03 must not fire without `others`"


# ---------------------------------------------------------------- scope/DI
def test_plain_agents_and_adr_do_not_require_frontmatter():
    plain = "# Plain document\n\nNo frontmatter is part of this template.\n"
    for path in ("/repo/AGENTS.md",
                 "/repo/docs/decisions/0001-plain.md"):
        assert F.check(plain, R.RULES, file=path) == [], path


def test_exact_skill_md_requires_frontmatter():
    v = F.check("# Skill without metadata\n", R.RULES,
                file="/repo/skills/example/SKILL.md")
    assert _ids(v) == {"FRONT-04"}, v
    assert "leading `---` block" in v[0]["message"], v


def test_skill_md_uses_portable_name_and_description_schema():
    text = ("---\nname: example-skill\n"
            "description: Audit docs. Use when reviewing docs. Not for builds.\n"
            "---\n")
    v = F.check(text, R.RULES, file="/repo/skills/example/SKILL.md")
    assert "FRONT-04" not in _ids(v), v


def test_skill_shaped_fixture_name_does_not_require_frontmatter():
    v = F.check("# Not a discoverable Skill entrypoint\n", R.RULES,
                file="/repo/fixtures/SKILL.fixture.md")
    assert v == [], v


def test_claude_rule_requires_frontmatter_and_accepts_paths_template():
    missing = F.check("# Rule without metadata\n", R.RULES,
                      file="/repo/.claude/rules/python.md")
    assert _ids(missing) == {"FRONT-04"}, missing

    templated = "---\npaths: [\"src/**/*.py\"]\n---\n\nKeep the rule short.\n"
    valid = F.check(templated, R.RULES,
                    file="/repo/.claude/rules/python.md")
    assert "FRONT-04" not in _ids(valid), valid


def test_plain_claude_is_optional_but_existing_frontmatter_is_validated():
    assert F.check("# Plain CLAUDE.md\n", R.RULES,
                   file="/repo/CLAUDE.md") == []

    text = ("---\nname: repo-charter\nversion: 1.0\n"
            "description: The helper.\n---\n")
    findings = F.check(text, R.RULES, file="/repo/CLAUDE.md")
    assert {"FRONT-01", "FRONT-04"} <= _ids(findings), findings
    front04 = next(v for v in findings if v["rule"] == "FRONT-04")
    assert front04["line"] == 3, front04


def test_check_only_emits_frontmatter_rules():
    # DI invariant: check() must only ever return rule ids it owns (checker ==
    # frontmatter_check), never a LINK-*/STRUCT-* id leaked from the catalog.
    owned = {r["id"] for r in R.RULES if r["checker"] == "frontmatter_check"}
    v = F.check(_read("front_bad_desc.md"), R.RULES)
    assert _ids(v) <= owned, f"check emitted non-owned rule ids: {_ids(v) - owned}"


def test_violation_shape_has_rule_and_message():
    v = F.check(_read("front_bad_desc.md"), R.RULES)
    assert v, "expected at least one violation"
    for item in v:
        assert "rule" in item and "message" in item, f"bad violation shape: {item}"


# ---------------------------------------------------------------- parser edges
def test_no_frontmatter_block_yields_only_absent_meta_findings():
    # A doc with no `---` fence has no name/version/description -> FRONT-04
    # (missing name+version) fires; FRONT-01 stays quiet (no description).
    v = F.check("# Just a body, no frontmatter\n", R.RULES)
    ids = _ids(v)
    assert "FRONT-04" in ids, f"missing-meta doc must trip FRONT-04: {ids}"
    assert "FRONT-01" not in ids, "FRONT-01 must not fire when there is no desc"


def test_unterminated_frontmatter_is_treated_as_absent():
    # Opening `---` with no closing fence -> parser yields no fields.
    v = F.check("---\nname: x\n", R.RULES)
    assert "FRONT-04" in _ids(v), "unterminated frontmatter -> meta absent"


def test_non_keyvalue_lines_in_frontmatter_are_ignored():
    text = ("---\n"
            "# a stray comment line inside frontmatter\n"
            "name: ok\nversion: 1.0.0\n"
            "description: |\n  Audit docs now. Use when auditing. Not for builds.\n"
            "---\n")
    v = F.check(text, R.RULES)
    assert "FRONT-04" not in _ids(v), f"valid meta despite stray line: {v}"


def test_front04_fires_on_missing_version_only():
    text = ("---\nname: ok\n"
            "description: |\n  Audit docs now. Use when auditing. Not for builds.\n"
            "---\n")
    v = F.check(text, R.RULES)
    assert "FRONT-04" in _ids(v), "FRONT-04 must fire when only version is missing"


def test_front04_fires_on_missing_description():
    # The direct <frontmatter> API sentinel uses the strict optional-doc policy:
    # name + semver version + description. A doc with valid name + version but
    # NO description must trip FRONT-04 on
    # the ABSENT description (FRONT-01 handles QUALITY of a PRESENT description).
    text = "---\nname: ok\nversion: 1.2.3\n---\n"
    v = F.check(text, R.RULES)
    assert "FRONT-04" in _ids(v), \
        f"FRONT-04 must fire on a missing description: {_ids(v)}"
    f04 = next(item for item in v if item["rule"] == "FRONT-04")
    assert "description" in f04["message"].lower(), f04
    # FRONT-01 (quality) must NOT fire — there is no description to grade.
    assert "FRONT-01" not in _ids(v), \
        "FRONT-01 must stay quiet when description is absent (that's FRONT-04)"


def test_front04_silent_on_present_description():
    # A present (even low-quality) description satisfies FRONT-04's presence check;
    # any quality problems are FRONT-01's job, not FRONT-04's.
    text = "---\nname: ok\nversion: 1.2.3\ndescription: The thing.\n---\n"
    v = F.check(text, R.RULES)
    f04 = [item for item in v if item["rule"] == "FRONT-04"]
    assert not f04, f"FRONT-04 must not fire when a description is present: {f04}"


def test_front03_ignores_empty_other_description():
    text = "---\nname: a\nversion: 1.0.0\ndescription: Audit docs. Use when. Not for x.\n---\n"
    v = F.check(text, R.RULES, doc_id="a", others=[("b", "")])
    assert "FRONT-03" not in _ids(v), "empty other-desc must not trigger FRONT-03"


# ---------------------------------------------------------------- FRONT-05
def test_front05_fires_on_non_glossary_vocab_block():
    # bad-fixture: a bare-term `vocabulary:` value (no `term: definition`).
    v = F.check(_read("front_bad_vocab.md"), R.RULES)
    assert "FRONT-05" in _ids(v), f"FRONT-05 must fire on bare-term vocab: {_ids(v)}"


def test_front05_silent_when_no_vocab_block():
    # good-fixture: no vocabulary block at all -> FRONT-05 stays quiet.
    v = F.check(_read("front_good.md"), R.RULES)
    assert "FRONT-05" not in _ids(v), f"FRONT-05 must not fire without vocab: {v}"


def test_front05_silent_on_glossary_shaped_vocab():
    text = ("---\nname: ok\nversion: 1.0.0\n"
            "description: |\n  Audit docs now. Use when auditing. Not for builds.\n"
            "vocabulary: term: definition\n---\n")
    v = F.check(text, R.RULES)
    assert "FRONT-05" not in _ids(v), f"FRONT-05 must not fire on glossary shape: {v}"


# ---------------------------------------------------------------- CLI
def test_cli_exits_1_and_emits_json_on_violations():
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = F._main(["--json", os.path.join(FIX, "front_bad_desc.md")])
    payload = json.loads(buf.getvalue())
    assert rc == 1, "CLI must exit 1 when violations are found"
    assert payload["passed"] is False and payload["violations"], payload


def test_cli_exits_0_on_clean_file():
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = F._main([os.path.join(FIX, "front_good.md")])
    assert rc == 0, f"CLI must exit 0 on a clean file; got rc={rc}\n{buf.getvalue()}"


def _run():
    tests = [val for k, val in sorted(globals().items()) if k.startswith("test_")]
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
