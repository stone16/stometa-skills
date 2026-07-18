#!/usr/bin/env python3
"""Tests for the four deep-mode inspector checklists (agents/inspector-*.md).

Run: python3 test_inspectors.py   (exit 0 = pass) ; also runs under pytest.

These inspectors are READ-ONLY judgment-mode agents (design §4.6 line 141:
semantic rules are `check: inspector` and never auto-fix). This test gates the
markdown authoring against `lib/rules.py` (the single source of truth) so the
checklists and the catalog cannot drift. Invariants encoded:

  * Each inspector file exists and parses VALID frontmatter (`name` +
    `description`) — the harness agent-file shape (frontmatter + body).
  * Every `rule_id` an inspector references EXISTS in `lib/rules.py`.
  * No inspector references a `check: deterministic` rule (FRONT-*/LINK-*):
    those are owned by `scripts/` linters, never by a judgment inspector
    (design line 141: the script-vs-inspector ownership map).
  * Each inspector references EXACTLY the owned-id set derived from
    `lib/rules.py` (rules whose `checker == "inspector-<name>"`). Deriving the
    expected set from rules.py — not hardcoding it — keeps inspectors and the
    catalog consistent by construction and catches any future drift.

The validation helpers (`parse_frontmatter`, `referenced_rule_ids`,
`owned_ids_for`) are pure string/data functions exercised directly by the unit
tests below, so coverage lands on the helper logic, not just file I/O.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import rules as R  # noqa: E402

AGENTS_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "agents"))

# inspector short-name -> agent filename. The short name is the `checker`
# suffix in rules.py (checker == "inspector-<short>").
INSPECTORS = {
    "structure": "inspector-structure.md",
    "taxonomy": "inspector-taxonomy.md",
    "staleness": "inspector-staleness.md",
    "design": "inspector-design.md",
}

# Matches any rule id token (e.g. STRUCT-02, RESID-1, DESIGN-09) anywhere in
# the body. Anchored on a word boundary so "STRUCT" alone never matches.
_RULE_ID_RE = re.compile(r"\b([A-Z]{3,8}-\d{1,2})\b")

# All ids that actually exist in the canonical catalog.
_ALL_IDS = {r["id"] for r in R.RULES}


# --------------------------------------------------------------- pure helpers
def parse_frontmatter(text):
    """Parse a leading `---`-delimited YAML-ish frontmatter block.

    Stdlib-only (no pyyaml): supports the flat `key: value` shape the harness
    agent files use. Returns a dict of the keys found, or {} when there is no
    well-formed frontmatter block. Quotes around values are stripped.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm = {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return fm
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        fm[key.strip()] = val.strip().strip('"').strip("'")
    # No closing delimiter => not a valid frontmatter block.
    return {}


def referenced_rule_ids(body):
    """Return the SET of rule-id tokens appearing in an inspector body."""
    return set(_RULE_ID_RE.findall(body))


def owned_ids_for(short_name):
    """Owned-id set derived from rules.py: checker == 'inspector-<short>'."""
    target = "inspector-" + short_name
    return {r["id"] for r in R.RULES if r["checker"] == target}


def deterministic_ids():
    """Set of ids whose check is owned by a deterministic `scripts/` linter."""
    return {r["id"] for r in R.RULES if r["check"] == "deterministic"}


def _read(short_name):
    path = os.path.join(AGENTS_DIR, INSPECTORS[short_name])
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _split(text):
    """Split a file into (frontmatter_dict, body_text)."""
    fm = parse_frontmatter(text)
    # Body is everything after the closing `---`.
    parts = text.split("---", 2)
    body = parts[2] if len(parts) == 3 else text
    return fm, body


# ---------------------------------------------------- helper unit tests (pure)
def test_parse_frontmatter_extracts_keys():
    fm = parse_frontmatter("---\nname: x\ndescription: y\n---\nbody\n")
    assert fm == {"name": "x", "description": "y"}, fm


def test_parse_frontmatter_strips_quotes():
    fm = parse_frontmatter('---\nname: "quoted"\ndescription: \'q2\'\n---\n')
    assert fm["name"] == "quoted" and fm["description"] == "q2", fm


def test_parse_frontmatter_no_block_returns_empty():
    assert parse_frontmatter("no frontmatter here\nname: x\n") == {}


def test_parse_frontmatter_unclosed_block_returns_empty():
    # Missing closing delimiter is not a valid frontmatter block.
    assert parse_frontmatter("---\nname: x\nno closing fence\n") == {}


def test_parse_frontmatter_ignores_comment_and_blank_lines():
    fm = parse_frontmatter("---\n# a comment\n\nname: x\n---\n")
    assert fm == {"name": "x"}, fm


def test_referenced_rule_ids_finds_tokens():
    ids = referenced_rule_ids("see STRUCT-02 and RESID-01 here")
    assert ids == {"STRUCT-02", "RESID-01"}, ids


def test_referenced_rule_ids_ignores_bare_category_words():
    # A bare category word without a number must NOT register as a rule id.
    assert referenced_rule_ids("the STRUCT family and DESIGN system") == set()


def test_owned_ids_for_matches_checker_field():
    assert owned_ids_for("staleness") == {"VOL-01", "VOL-02",
                                          "STALE-01", "STALE-02"}


def test_deterministic_ids_match_presence_front_and_link_owners():
    det = deterministic_ids()
    assert det == {"STRUCT-06"} | {
        r["id"] for r in R.RULES
        if r["id"].startswith(("FRONT-", "LINK-"))
    }


# ------------------------------------------------- file-level invariant tests
def test_all_inspector_files_exist():
    for short, fname in INSPECTORS.items():
        path = os.path.join(AGENTS_DIR, fname)
        assert os.path.isfile(path), f"missing inspector file: {path}"


def test_inspectors_have_valid_frontmatter():
    for short in INSPECTORS:
        fm, _body = _split(_read(short))
        assert fm.get("name"), f"{short}: missing frontmatter `name`"
        assert fm.get("description"), f"{short}: missing `description`"


def test_inspector_name_matches_owned_inspector():
    # Frontmatter name must end with the inspector's short name so the file's
    # identity matches the rule-ownership group it documents.
    for short in INSPECTORS:
        fm, _body = _split(_read(short))
        assert fm["name"].endswith(short), (short, fm["name"])


def test_every_referenced_id_exists_in_rules():
    for short in INSPECTORS:
        _fm, body = _split(_read(short))
        for rid in referenced_rule_ids(body):
            assert rid in _ALL_IDS, f"{short}: unknown rule id {rid!r}"


def test_no_inspector_references_deterministic_rule():
    det = deterministic_ids()
    for short in INSPECTORS:
        _fm, body = _split(_read(short))
        offenders = referenced_rule_ids(body) & det
        assert not offenders, f"{short} references deterministic rule(s): {offenders}"


def test_each_inspector_references_exactly_its_owned_set():
    for short in INSPECTORS:
        _fm, body = _split(_read(short))
        referenced = referenced_rule_ids(body)
        owned = owned_ids_for(short)
        assert referenced == owned, (
            f"{short}: referenced {sorted(referenced)} != owned "
            f"{sorted(owned)} (missing={sorted(owned - referenced)}, "
            f"extra={sorted(referenced - owned)})")


def test_every_finding_must_cite_file_line_and_rule_id():
    # The contract: each inspector requires findings to cite file:line + rule_id.
    for short in INSPECTORS:
        _fm, body = _split(_read(short))
        low = body.lower()
        assert "file:line" in low, f"{short}: must require `file:line` citation"
        assert "rule_id" in low or "rule id" in low, (
            f"{short}: must require a rule_id citation")


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
