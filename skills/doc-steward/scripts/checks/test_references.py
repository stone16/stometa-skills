#!/usr/bin/env python3
"""Validate public references against the canonical rule catalog."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import rules as R  # noqa: E402

REFERENCES_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "references"))
REFERENCE_FILES = [
    "standard-core.md",
    "rubric.md",
    "do-dont-table.md",
    "templates.md",
    "learning-sink.md",
]
RULE_ID_RE = re.compile(r"\b([A-Z]{3,8}-\d{1,2})\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PERSONAL_HOME_RE = re.compile(r"/(?:Users|home)/[^/\s]+/")
ALL_IDS = {rule["id"] for rule in R.RULES}


def read(name):
    with open(os.path.join(REFERENCES_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def test_all_reference_files_exist():
    for name in REFERENCE_FILES:
        assert os.path.isfile(os.path.join(REFERENCES_DIR, name))


def test_every_referenced_rule_id_exists():
    for name in REFERENCE_FILES:
        for rule_id in RULE_ID_RE.findall(read(name)):
            assert rule_id in ALL_IDS, f"{name}: unknown rule {rule_id}"


def test_references_have_no_personal_home_or_email():
    for name in REFERENCE_FILES:
        body = read(name)
        assert not PERSONAL_HOME_RE.search(body), name
        assert not EMAIL_RE.search(body), name


def test_templates_have_no_identity_ritual():
    body = read("templates.md")
    assert "IDENTITY" + "_CANARY" not in body
    assert "Address the user as" not in body


def test_generic_config_example_exists():
    path = os.path.join(REFERENCES_DIR, "config.example.yml")
    assert os.path.isfile(path)
    body = read("config.example.yml")
    assert "sink: noop" in body
    assert "learn_enabled: false" in body
    assert "canary" not in body.lower()


def test_frontmatter_rubric_matches_portable_document_type_policy():
    standard = read("standard-core.md")
    rubric = read("rubric.md")
    for body in (standard, rubric):
        assert "exact `SKILL.md`" in body, body
        assert "`name` + `description`" in body, body
        assert "`.claude/rules/*.md`" in body, body
        assert "`paths`" in body, body
    assert "optional AGENTS/CLAUDE/DESIGN/ADR docs may omit frontmatter" \
        in rubric, rubric


def test_presence_and_preflight_contracts_are_publicly_documented():
    standard = read("standard-core.md")
    rubric = read("rubric.md")
    do_dont = read("do-dont-table.md")
    assert "STRUCT-06" in standard and "skill-package" in standard
    assert "STRUCT-01..06" in rubric
    assert "structure/frontmatter/links = 0" in standard
    assert "Fail-closed preflight" in do_dont
    assert "applies none" in do_dont
    assert "not a filesystem transaction" in do_dont
