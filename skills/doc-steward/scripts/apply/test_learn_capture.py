#!/usr/bin/env python3
"""Tests for the public LEARN core and explicit sink extension seam."""
import contextlib
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "sinks"))

import learn_capture as L  # noqa: E402
import noop as NOOP  # noqa: E402


class CapturingSink:
    def __init__(self):
        self.records = []

    def write(self, record):
        self.records.append(record)


def finding(**updates):
    value = {
        "rule": "FRONT-01",
        "file": "/srv/internal/project/AGENTS.md",
        "line": 42,
        "message": (
            "at /srv/internal/project/AGENTS.md:42 the description is too weak; "
            "see issue ABC-123 on 2026-06-21"
        ),
    }
    value.update(updates)
    return value


def write_plan(tmp_path, findings=None):
    path = os.path.join(str(tmp_path), "plan.json")
    report = {"tier": "Standard", "grade": "FAIL",
              "findings": findings if findings is not None else [finding()]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh)
    return path


def test_capture_writes_one_distilled_record():
    sink = CapturingSink()
    record = L.capture(finding(), sink)
    assert sink.records == [record]
    assert record["rule_id"] == "FRONT-01"
    assert record["tag"].startswith("DOC-")
    assert "/srv/internal" not in record["lesson"]
    assert "ABC-123" not in record["lesson"]
    assert "2026-06-21" not in record["lesson"]
    assert not re.search(r"\bline\s+\d+\b", record["lesson"], re.I)


def test_configured_redaction_terms_and_paths_are_removed():
    config = {
        "redaction_terms": ["Secret Project"],
        "private_paths": ["/opt/company/hidden"],
    }
    text = "Secret Project failed under /opt/company/hidden during audit"
    out = L.strip_provenance(text, overlay=config)
    assert "secret project" not in out.lower()
    assert "/opt/company/hidden" not in out
    assert L.candidate_matrix(
        {"description": text, "file": "", "line": None},
        overlay=config)["redaction_risk"] is True


def test_single_segment_posix_windows_and_unc_paths_are_removed():
    cases = (
        ("failed under /secret during audit", "/secret"),
        (r"failed under C:\secret during audit", r"C:\secret"),
        (r"failed under \\server\share\secret during audit",
         r"\\server\share\secret"),
    )
    for text, private_path in cases:
        out = L.strip_provenance(text)
        assert private_path not in out, (private_path, out)
        assert not L.has_residual_high_risk(out), (private_path, out)
        assert L.candidate_matrix(
            {"description": text, "file": "", "line": None}
        )["redaction_risk"] is True, private_path


def test_capture_rejects_without_calling_sink_when_risk_survives():
    sink = CapturingSink()
    original = L.strip_provenance
    try:
        # Exercise the fail-closed guard independently of the current scrubber:
        # a future redaction regression must not turn into a sink write.
        L.strip_provenance = lambda text, overlay=None: "still at /secret"
        record = L.capture(finding(), sink)
    finally:
        L.strip_provenance = original
    assert sink.records == []
    assert record["rejected"] is True
    assert record["status"] == "Rejected-ResidualHighRisk"
    assert "lesson" not in record
    assert "/secret" not in repr(record)


def test_capture_rejects_unsafe_structured_metadata_before_sink():
    cases = (
        {"rule_id": "ssh://internal.example/rule", "rule": ""},
        {"layer": "file:///private/altitude"},
        {"severity": "P1\nprivate-note"},
        {"rule_id": "SecretProject", "rule": ""},
        {"layer": "internal-team"},
        {"severity": "P2"},
        {"message": {"private": "urn:secret:value"}},
    )
    for update in cases:
        sink = CapturingSink()
        raw = finding(**update)
        record = L.capture(raw, sink)
        assert sink.records == [], update
        assert record["rejected"] is True
        assert record["status"] == "Rejected-UnsafeMetadata"
        assert "lesson" not in record
        for value in update.values():
            if value:
                assert str(value) not in repr(record)


def test_capture_accepts_portable_structured_metadata_tokens():
    sink = CapturingSink()
    record = L.capture(
        finding(rule="", rule_id="FRONT-01", severity="P1", layer="repo"),
        sink,
    )
    assert sink.records == [record]
    assert record["candidate"]["layer"] == "repo"
    assert record["rule_id"] == "FRONT-01"


def test_strip_provenance_removes_non_web_uri_schemes():
    text = (
        "inspect ssh://internal.example/repo file:///private/secret "
        "file:/private/one mailto:alice@internal urn:secret:thing "
        "ssh:user@internal/path"
    )
    out = L.strip_provenance(text)
    assert "ssh://" not in out
    assert "file://" not in out
    assert "file:/" not in out
    assert "mailto:" not in out
    assert "urn:" not in out
    assert "ssh:" not in out
    assert not L.has_residual_high_risk(out)


def test_local_domain_email_is_redacted_and_flagged():
    text = "contact alice@internal before publishing"
    out = L.strip_provenance(text)
    assert "alice@internal" not in out
    assert L.candidate_matrix(
        {"description": text, "file": "", "line": None}
    )["redaction_risk"] is True


def test_complete_record_residual_scan_blocks_sink():
    sink = CapturingSink()
    original = L.candidate_matrix
    try:
        L.candidate_matrix = lambda finding, overlay=None: {
            "repeated": False,
            "invariant": True,
            "layer": "repo",
            "verifier": True,
            "redaction_risk": False,
            "provenance_to_strip": False,
            "critical": False,
            "extra": "urn:private:record",
        }
        record = L.capture(
            finding(rule="", rule_id="FRONT-01", severity="P1", layer="repo"),
            sink,
        )
    finally:
        L.candidate_matrix = original
    assert sink.records == []
    assert record["rejected"] is True
    assert "urn:private:record" not in repr(record)


def test_noop_sink_has_no_side_effect(tmp_path):
    before = sorted(os.listdir(str(tmp_path)))
    L.capture(finding(), NOOP.Sink())
    assert sorted(os.listdir(str(tmp_path))) == before


def test_cli_default_is_disabled_and_writes_nothing(tmp_path):
    plan = write_plan(tmp_path)
    before = sorted(os.listdir(str(tmp_path)))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert L._main(["--plan", plan]) == 0
    assert sorted(os.listdir(str(tmp_path))) == before
    assert "disabled" in buf.getvalue().lower()


def test_cli_default_does_not_require_pyyaml(tmp_path):
    plan = write_plan(tmp_path)
    result = subprocess.run(
        [sys.executable, "-S", L.__file__, "--plan", plan],
        capture_output=True, text=True)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "disabled" in result.stdout.lower(), result.stdout
    assert "yaml" not in result.stderr.lower(), result.stderr


def test_cli_explicit_noop_is_valid_intent(tmp_path):
    plan = write_plan(tmp_path)
    assert L._main(["--plan", plan, "--sink", "noop"]) == 0


def test_cli_rejection_is_nonzero_and_does_not_call_sink(tmp_path):
    plan = write_plan(tmp_path)
    sink = CapturingSink()
    original_strip = L.strip_provenance
    original_load = L._load_sink
    try:
        L.strip_provenance = lambda text, overlay=None: "still at /secret"
        L._load_sink = lambda name="noop", path=None, module_path=None: sink
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = L._main(["--plan", plan, "--sink", "noop"])
    finally:
        L.strip_provenance = original_strip
        L._load_sink = original_load
    assert rc == 1
    assert sink.records == []
    assert "rejected" in buf.getvalue().lower()
    assert "/secret" not in buf.getvalue()


def test_explicit_sink_module_is_loaded_only_when_requested(tmp_path):
    plan = write_plan(tmp_path)
    output = os.path.join(str(tmp_path), "records.jsonl")
    module = os.path.join(str(tmp_path), "sink_adapter.py")
    with open(module, "w", encoding="utf-8") as fh:
        fh.write(
            "import json\n"
            "class Sink:\n"
            "    def __init__(self, path=None): self.path = path\n"
            "    def write(self, record):\n"
            "        with open(self.path, 'a', encoding='utf-8') as out:\n"
            "            out.write(json.dumps(record) + '\\n')\n"
        )
    assert not os.path.exists(output)
    rc = L._main(["--plan", plan, "--sink-module", module,
                  "--sink-path", output])
    assert rc == 0
    with open(output, encoding="utf-8") as fh:
        record = json.loads(fh.readline())
    assert record["tag"].startswith("DOC-")


def test_sink_module_must_expose_sink(tmp_path):
    module = os.path.join(str(tmp_path), "bad_adapter.py")
    with open(module, "w", encoding="utf-8") as fh:
        fh.write("VALUE = 1\n")
    try:
        L._load_sink(module_path=module)
    except SystemExit:
        return
    raise AssertionError("sink module without Sink must be refused")


def test_invalid_plan_is_rejected(tmp_path):
    path = os.path.join(str(tmp_path), "bad.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"not_findings": []}, fh)
    try:
        L._main(["--plan", path, "--sink", "noop"])
    except SystemExit:
        return
    raise AssertionError("invalid plan must be rejected")
