#!/usr/bin/env python3
"""CP07 DOGFOOD — the doc-steward skill must pass its OWN audit. Stdlib-only.

Run: python3 test_dogfood.py   (exit 0 = pass) ; also runs under pytest.

The skill is the standard's reference implementation, so it must be the first
repo to satisfy the standard. These tests assert the load-bearing invariants of
the read-only audit entrypoint (`SKILL.md`) + the integration of CP01-06:

  * `doc_lint.py --target <skill root>` returns `passed: true` — i.e. the
    skill's own doc taxonomy (its SKILL.md) is tier-classified, deterministically
    linted, scored, and graded PASS with NOTHING skipped. This is the dogfood:
    if the audit skill cannot pass its own audit, the standard is not real.
    (Regression guard for the glob_taxonomy fix: the intentional-defect test
    FIXTURES under scripts/checks/fixtures/ must NOT be picked up as the skill's
    own docs — pruning them is what lets the dogfood pass.)
  * SKILL.md is <= 500 lines whole-file (the progressive-disclosure budget;
    spec §4.3). A SKILL.md that grows past its budget has stopped delegating.
  * SKILL.md frontmatter passes FRONT-01: the `description` is 40-500 chars,
    verb-first, and carries both "Use when" and "Not for". The skill dogfoods
    the very frontmatter rule it ships.
  * link_check finds ZERO dead pointers across SKILL.md AND references/ — every
    `@path`/relative pointer the skill ships resolves on disk (forward-reference
    discipline: no pointer to a not-yet-created file).
  * every path named in SKILL.md's "read on demand" pointer table EXISTS on disk
    (CP07's responsibility): the router cannot point at a file that isn't there.

These assert intent, not just behaviour: each encodes a property the standard
requires of its own reference implementation, not merely that some code runs.
"""
import io
import contextlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, os.path.join(HERE, ".."))

import doc_lint as D  # noqa: E402
import frontmatter_check as FC  # noqa: E402
import link_check as LC  # noqa: E402
import rules as R  # noqa: E402

# Skill root = two levels up from scripts/checks/.
SKILL_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
SKILL_MD = os.path.join(SKILL_ROOT, "SKILL.md")
REFERENCES = os.path.join(SKILL_ROOT, "references")
FIXTURES = os.path.join(HERE, "fixtures")


# --------------------------------------------------------- the dogfood itself
def test_skill_md_exists():
    # The audit entrypoint must exist before any other invariant can hold.
    assert os.path.isfile(SKILL_MD), f"missing {SKILL_MD}"


def test_doc_lint_target_skill_root_passes():
    # THE DOGFOOD: the skill must pass its own deterministic audit. passed is
    # True iff grade == PASS AND nothing was skipped — so this single assertion
    # covers tier-classify + deterministic lint + score + grade + no-skip.
    report = D.lint(SKILL_ROOT, R.RULES)
    assert report["passed"] is True, report
    assert report["grade"] == "PASS", report
    assert report["skipped"] == [], report["skipped"]
    assert report["composite"] >= 8.0, report["composite"]
    assert report["target_profile"] == "skill-package", report
    assert report["structure_scope"] == "required-document-presence", report


def test_doc_lint_does_not_audit_intentional_defect_fixtures():
    # Regression guard for the glob_taxonomy fix: the fixture sample-repo (whose
    # FRONT-01/FRONT-04/LINK-01 violations are DELIBERATE for CP04's tests) must
    # NOT be walked when auditing the skill root, or the dogfood can never pass.
    paths = D.glob_taxonomy(SKILL_ROOT)
    assert not any(os.sep + "fixtures" + os.sep in p for p in paths), paths
    assert not any("sample-repo" in p for p in paths), paths


def test_skill_md_within_line_budget():
    # Whole-file <= 500 lines (spec §4.3 progressive-disclosure budget).
    with open(SKILL_MD, encoding="utf-8") as fh:
        n = sum(1 for _ in fh)
    assert n <= 500, f"SKILL.md is {n} lines (budget 500)"


def test_skill_md_frontmatter_passes_front_01():
    # The skill dogfoods FRONT-01 on its own frontmatter: description present,
    # 40-500 chars, verb-first, with "Use when" + "Not for", and no other FRONT.
    with open(SKILL_MD, encoding="utf-8") as fh:
        text = fh.read()
    findings = FC.check(text, R.RULES, file=SKILL_MD, doc_id=SKILL_MD)
    front01 = [f for f in findings if f["rule"] == "FRONT-01"]
    assert not front01, front01
    # And the description genuinely satisfies the constituent sub-checks.
    fields, _ = FC._parse_frontmatter(text)
    desc = fields.get("description", "")
    assert 40 <= len(desc) <= 500, len(desc)
    assert FC._is_verb_first(desc), desc
    assert FC._USE_WHEN.search(desc), "description missing 'Use when'"
    assert FC._NOT_FOR.search(desc), "description missing 'Not for'"


def test_no_dead_pointers_across_skill_md_and_references():
    # Forward-reference discipline: every @path/relative pointer in SKILL.md and
    # every references/*.md must resolve on disk — zero LINK-01 across the set.
    docs = [SKILL_MD]
    for name in sorted(os.listdir(REFERENCES)):
        if name.endswith(".md"):
            docs.append(os.path.join(REFERENCES, name))
    findings = LC.check(docs, R.RULES)
    dead = [f for f in findings if f["rule"] == "LINK-01"]
    assert not dead, dead


def test_pointer_table_targets_exist_on_disk():
    # CP07's responsibility: every path named in SKILL.md's "read on demand"
    # pointer table must exist. We harvest backtick-quoted relative paths that
    # look like skill assets (scripts/..., references/..., agents/..., *.py/*.md)
    # and assert each resolves under the skill root.
    with open(SKILL_MD, encoding="utf-8") as fh:
        text = fh.read()
    candidates = _harvest_pointer_paths(text)
    assert candidates, "no pointer-table paths found in SKILL.md"
    missing = [c for c in candidates
               if not os.path.exists(os.path.join(SKILL_ROOT, c))]
    assert not missing, f"pointer-table paths missing on disk: {missing}"


def test_pointer_table_has_no_plugin_command_or_private_overlay_paths():
    # The public skill exposes harness-neutral apply scripts directly. It must
    # not reference a plugin command or an implicit private overlay location.
    with open(SKILL_MD, encoding="utf-8") as fh:
        text = fh.read()
    for forbidden in ("commands/" + "doc-steward-apply.md",
                      "overlay/" + "config.yml"):
        for path in _harvest_pointer_paths(text):
            assert not path.startswith(forbidden.rstrip("/")) \
                and path != forbidden.rstrip("/"), \
                f"SKILL.md file-points at unbuilt {forbidden!r}: {path}"


# ------------------------------------------------------------------ helpers
_PATH_TOKEN = re.compile(
    r"`(scripts/[^`]+?\.(?:py|md)"
    r"|references/[^`]+?\.md"
    r"|agents/[^`]+?\.md"
    r"|scripts/lib/[^`]+?\.py)`")


def _harvest_pointer_paths(text):
    """Backtick-quoted skill-asset relative paths referenced from SKILL.md."""
    found = []
    for m in _PATH_TOKEN.finditer(text):
        path = m.group(1)
        if path not in found:
            found.append(path)
    return found


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
