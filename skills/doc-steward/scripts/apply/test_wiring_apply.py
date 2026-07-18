#!/usr/bin/env python3
"""Cross-module wiring tests for EVALUATE, ENFORCE, and LEARN."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS = os.path.normpath(os.path.join(HERE, "..", "checks"))
LIB = os.path.normpath(os.path.join(HERE, "..", "lib"))
for path in (HERE, CHECKS, LIB):
    sys.path.insert(0, path)

import doc_lint as D  # noqa: E402
import enforce_apply as E  # noqa: E402
import learn_capture as L  # noqa: E402
import rules as R  # noqa: E402


class CapturingSink:
    def __init__(self):
        self.records = []

    def write(self, record):
        self.records.append(record)


def write_skill(path, version=False):
    lines = [
        "---",
        "name: sample-skill",
        "description: Audits sample docs. Use when checking docs. Not for code.",
    ]
    if version:
        lines.append('version: "1.0.0"')
    lines += ["---", "", "# Sample", ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def test_real_evaluate_plan_flows_into_enforce_classifier(tmp_path):
    root = str(tmp_path)
    # Skill runtime frontmatter intentionally has no top-level version field.
    # Use an optional charter that elects into strict frontmatter to exercise
    # the missing-version FRONT-04 -> ENFORCE seam.
    charter = os.path.join(root, "CLAUDE.md")
    write_skill(charter, version=False)
    report = D.lint(root, R.RULES, tier_override="Simple")
    assert report["findings"]
    rows = E.plan_dispositions(report["findings"], [], R.RULES,
                               target=root, repo_version="2.0.0")
    front04 = [row for row in rows if row["rule"] == "FRONT-04"]
    assert front04 and front04[0]["applicable"] is True


def test_real_evaluate_finding_flows_into_learn_capture(tmp_path):
    root = str(tmp_path)
    write_skill(os.path.join(root, "CLAUDE.md"), version=False)
    report = D.lint(root, R.RULES, tier_override="Simple")
    sink = CapturingSink()
    record = L.capture(report["findings"][0], sink)
    assert sink.records == [record]
    assert record["rule_id"]
    assert record["lesson"]


def test_default_learning_sink_is_noop():
    sink = L._load_sink("noop")
    assert sink.__class__.__name__ == "Sink"
