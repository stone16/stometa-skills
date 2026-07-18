#!/usr/bin/env python3
"""Tests for explicit, generic doc-steward configuration."""
import contextlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import overlay as O  # noqa: E402


def test_safe_defaults_are_generic_and_learning_off():
    config = O.resolve_config()
    assert config["sink"] == "noop"
    assert config["learn_enabled"] is False
    assert config["private_paths"] == []
    assert config["redaction_terms"] == []
    assert "canary" not in config


def test_merge_explicit_values_over_defaults():
    config = O.merge({"tier": "Complex", "redaction_terms": ["internal"]})
    assert config["tier"] == "Complex"
    assert config["redaction_terms"] == ["internal"]
    assert config["sink"] == "noop"


def test_resolve_explicit_yaml(tmp_path):
    path = os.path.join(str(tmp_path), "config.yml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("tier: Standard\nprivate_paths:\n  - /srv/internal/project\n")
    config = O.resolve_config(path)
    assert config["tier"] == "Standard"
    assert config["private_paths"] == ["/srv/internal/project"]


def test_missing_explicit_path_is_an_error(tmp_path):
    try:
        O.resolve_config(os.path.join(str(tmp_path), "missing.yml"))
    except FileNotFoundError:
        return
    raise AssertionError("a mistyped explicit config path must fail closed")


def test_non_mapping_config_is_rejected(tmp_path):
    path = os.path.join(str(tmp_path), "config.yml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("- not\n- a\n- mapping\n")
    try:
        O.resolve_config(path)
    except ValueError:
        return
    raise AssertionError("config must be a mapping")


def test_example_matches_public_defaults():
    example = os.path.normpath(
        os.path.join(HERE, "..", "..", "references", "config.example.yml"))
    config = O.resolve_config(example)
    assert config["sink"] == "noop"
    assert config["learn_enabled"] is False
    assert "canary" not in config


def test_cli_uses_only_explicit_config(tmp_path):
    path = os.path.join(str(tmp_path), "config.yml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("profile: frontend\n")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert O._main(["--config", path]) == 0
    assert json.loads(buf.getvalue())["profile"] == "frontend"
