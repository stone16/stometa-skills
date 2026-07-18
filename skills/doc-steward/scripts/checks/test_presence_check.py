#!/usr/bin/env python3
"""Tests for the deterministic STRUCT-06 required-document preflight."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import presence_check as P  # noqa: E402
import rules as R  # noqa: E402


def _touch(root, relative, text="# fixture\n"):
    path = os.path.join(str(root), relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _one(root, tier):
    findings = P.check(str(root), R.RULES, tier=tier)
    assert len(findings) == 1, findings
    return findings[0]


def test_empty_simple_requires_one_root_charter(tmp_path):
    finding = _one(tmp_path, "Simple")
    assert finding["rule"] == "STRUCT-06", finding
    assert finding["missing"] == ["AGENTS.md or CLAUDE.md"], finding
    assert finding["root_charter_present"] is False, finding
    assert finding["target_profile"] == "repository", finding
    assert finding["file"] == os.path.abspath(str(tmp_path)), finding


def test_simple_accepts_either_exact_root_charter(tmp_path):
    _touch(tmp_path, "AGENTS.md")
    assert P.check(str(tmp_path), R.RULES, tier="Simple") == []


def test_standard_requires_both_root_charters(tmp_path):
    _touch(tmp_path, "CLAUDE.md")
    finding = _one(tmp_path, "Standard")
    assert finding["missing"] == ["AGENTS.md"], finding
    assert finding["root_charter_present"] is True, finding


def test_complex_requires_rules_and_decisions(tmp_path):
    _touch(tmp_path, "AGENTS.md")
    _touch(tmp_path, "CLAUDE.md")
    finding = _one(tmp_path, "Complex")
    assert finding["missing"] == [
        ".claude/rules/*.md", "docs/decisions/*.md"
    ], finding
    _touch(tmp_path, ".claude/rules/python.md")
    _touch(tmp_path, "docs/decisions/0001-contract.md")
    assert P.check(str(tmp_path), R.RULES, tier="Complex") == []


def test_root_skill_is_a_self_contained_skill_package(tmp_path):
    _touch(tmp_path, "SKILL.md")
    assert P.target_profile(str(tmp_path)) == "skill-package"
    for tier in ("Simple", "Standard", "Complex"):
        assert P.check(str(tmp_path), R.RULES, tier=tier) == []


def test_nested_skill_and_charter_do_not_satisfy_repository_root(tmp_path):
    _touch(tmp_path, "skills/demo/SKILL.md")
    _touch(tmp_path, "service/AGENTS.md")
    assert P.target_profile(str(tmp_path)) == "repository"
    finding = _one(tmp_path, "Simple")
    assert finding["root_charter_present"] is False, finding


def test_checker_emits_nothing_when_catalog_does_not_assign_struct06(tmp_path):
    foreign = [dict(rule) for rule in R.RULES]
    for rule in foreign:
        if rule["id"] == "STRUCT-06":
            rule["checker"] = "someone_else"
    assert P.check(str(tmp_path), foreign, tier="Simple") == []


def test_unknown_tier_is_rejected(tmp_path):
    try:
        P.check(str(tmp_path), R.RULES, tier="Huge")
    except ValueError as exc:
        assert "tier" in str(exc)
    else:
        raise AssertionError("unknown tier must fail deterministically")
