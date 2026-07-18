#!/usr/bin/env python3
"""Tests for enforce_apply.py (CP08) — the ENFORCE writer's safety invariants.

Run: python3 test_enforce_apply.py   (exit 0 = pass) ; also runs under pytest.

enforce_apply is doc-steward's ONLY doc-mutation path. It is dry-run by default
and refuses `--apply` unless all gates hold:
  (a) the TARGET repo's current branch is a real checked-out feature branch —
      not the symbolic/configured default, not main/master/trunk, not detached;
  (b) a complete versioned EVALUATE report reproduces for the canonical target,
      current Git revision/content digest, and canonical catalog fields; and
  (c) the target worktree is clean, including untracked files.
It applies ONLY LOW-RISK-AUTO findings whose autofix_preconditions hold, scaffolds
a templated file ONLY when ABSENT (never overwrites a PRESENT file), and never
deletes a non-duplicate (SAFETY-01). It emits the ADDED|CHANGED|LEFT-UNTOUCHED|
ESCALATED disposition table; ESCALATED rows are reported, not applied.

The six headline SAFETY invariants are pinned in a REAL temp git fixture:
  1. refuses --apply on `main`, `master`, `trunk`, or a detected default
  2. refuses --apply on detached HEAD (rev-parse --abbrev-ref HEAD == "HEAD")
  3. refuses --apply without a plan (and with an invalid/unparseable plan)
  4. dry-run (default) writes nothing — target tree byte-unchanged
  5. overwrite-of-present is rejected — a PRESENT file is never overwritten
  6. a low-risk fix IS applied on a valid feature branch + valid plan

The pure classifier (disposition logic) is exercised WITHOUT git via direct
calls; the git branch gate is the I/O boundary, exercised via subprocess-built
temp repos in distinct branch states.
"""
import hashlib
import io
import contextlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import enforce_apply as E  # noqa: E402
import rules as R  # noqa: E402


# --------------------------------------------------------------------------
# temp-git fixture helpers
# --------------------------------------------------------------------------
def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def _init_repo(root, branch="feature/docs"):
    """Make a real git repo at `root` with one commit, checked out on `branch`."""
    os.makedirs(root, exist_ok=True)
    _git(["init", "-q"], root)
    _git(["config", "user.email", "t@t.t"], root)
    _git(["config", "user.name", "t"], root)
    _git(["config", "commit.gpgsign", "false"], root)
    # Seed a file so there is a commit to anchor HEAD.
    with open(os.path.join(root, "seed.txt"), "w", encoding="utf-8") as fh:
        fh.write("seed\n")
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "seed"], root)
    # Move onto the requested branch name (default branch may be main/master,
    # so use -B to create-or-reset rather than failing when it already exists).
    _git(["checkout", "-q", "-B", branch], root)
    return root


def _detach_head(root):
    """Put `root` into detached-HEAD state at its current commit."""
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                         capture_output=True, text=True).stdout.strip()
    _git(["checkout", "-q", sha], root)


def _checkout_named(root, branch):
    _git(["checkout", "-q", "-B", branch], root)


def _set_remote_default(root, branch, remote="origin"):
    """Declare a local symbolic remote HEAD without contacting a network."""
    remotes = subprocess.run(["git", "remote"], cwd=root, check=True,
                             capture_output=True, text=True).stdout.split()
    if remote not in remotes:
        _git(["remote", "add", remote, root], root)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                         capture_output=True, text=True).stdout.strip()
    _git(["update-ref", "refs/remotes/%s/%s" % (remote, branch), sha], root)
    _git(["symbolic-ref", "refs/remotes/%s/HEAD" % remote,
          "refs/remotes/%s/%s" % (remote, branch)], root)


def _tree_digest(root):
    """A stable digest of every file's path+bytes under `root` (excl .git)."""
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(filenames):
            p = os.path.join(dirpath, name)
            h.update(os.path.relpath(p, root).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


# A genuine ENFORCE plan is the current, versioned doc_lint report. Keep it
# outside the target so creating the artifact cannot dirty/change its binding.
def _write_plan(root, forged_findings=None):
    if os.path.isdir(os.path.join(root, ".git")):
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root, check=True, capture_output=True, text=True).stdout
        if status.strip():
            _git(["add", "-A"], root)
            _git(["commit", "-q", "-m", "prepare evaluate target"], root)
    plan = E.current_evaluate_report(root)
    if forged_findings is not None:
        plan["findings"] = forged_findings
        plan["severity_counts"] = {
            severity: sum(f.get("severity") == severity
                          for f in forged_findings)
            for severity in ("P0", "P1", "P2")
        }
    p = os.path.realpath(root) + ".evaluate.json"
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(plan, fh)
    return p


def _front04_doc(root, name="CLAUDE.md", version=True):
    """Write a doc whose frontmatter has a description but (optionally) no version."""
    lines = ["---", "name: demo",
             "description: Demo charter. Use when editing. Not for prod."]
    if version:
        lines.append('version: "1.0.0"')
    lines += ["---", "", "# Demo", "", "body", ""]
    p = os.path.join(root, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return p


def _front04_finding(file_path):
    rule = R.get_rule("FRONT-04")
    return {"rule": "FRONT-04", "file": os.path.realpath(file_path), "line": 2,
            "message": "frontmatter: missing `version`",
            "severity": rule["severity"], "confidence": 10,
            "remedy": rule["remedy"]}


# --------------------------------------------------------------------------
# PURE classifier unit tests (no git)
# --------------------------------------------------------------------------
def test_is_feature_branch_rejects_main_master_and_detached():
    for bad in ("main", "master", "trunk", "HEAD", "", None):
        assert E.is_feature_branch(bad) is False, bad
    for ok in ("feature/x", "feat/doc-steward-skill", "fix/y", "develop"):
        assert E.is_feature_branch(ok) is True, ok
    assert E.is_feature_branch("production", {"production"}) is False


def test_worktree_clean_gate_detects_untracked_and_tracked_changes(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    assert E.worktree_is_clean(root) is True
    with open(os.path.join(root, "untracked.txt"), "w", encoding="utf-8") as fh:
        fh.write("dirty\n")
    assert E.worktree_is_clean(root) is False


def test_classify_escalate_rule_is_never_auto():
    # SAFETY-01 / STRUCT-02 etc. are ESCALATE in rules.py -> never low-risk-auto.
    finding = {"rule": "SAFETY-01", "file": "x", "line": 1, "message": "m"}
    row = E.classify_disposition(finding, R.RULES, repo_version="1.0.0",
                                 target=HERE)
    assert row["disposition"] == "ESCALATED", row
    assert row["applicable"] is False, row


def test_classify_front04_missing_version_is_low_risk_auto(tmp_path):
    root = str(tmp_path)
    doc = _front04_doc(root, version=False)
    row = E.classify_disposition(_front04_finding(doc), R.RULES,
                                 repo_version="2.3.4", target=root)
    assert row["applicable"] is True, row
    assert row["rule"] == "FRONT-04", row


def test_classify_front04_without_repo_version_escalates(tmp_path):
    # The precondition needs a KNOWN repo version; absent it, FRONT-04 escalates.
    root = str(tmp_path)
    doc = _front04_doc(root, version=False)
    row = E.classify_disposition(_front04_finding(doc), R.RULES,
                                 repo_version=None, target=root)
    assert row["applicable"] is False, row
    assert row["disposition"] == "ESCALATED", row


def test_classify_front04_malformed_version_escalates(tmp_path):
    # Precondition is "MISSING version insertable" — a malformed (present but bad)
    # version is NOT a mechanical insert, so it must escalate.
    root = str(tmp_path)
    doc = _front04_doc(root, version=False)
    bad = {"rule": "FRONT-04", "file": doc, "line": 2,
           "message": "frontmatter: `version` 'v1' is not semver X.Y.Z"}
    row = E.classify_disposition(bad, R.RULES, repo_version="2.3.4", target=root)
    assert row["applicable"] is False, row


# --------------------------------------------------------------------------
# SAFETY INVARIANT 1 — refuses --apply on main / master
# --------------------------------------------------------------------------
def test_apply_refused_on_main(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"), branch="main")
    _checkout_named(root, "main")
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, "must refuse --apply on main"
    assert _tree_digest(root) == before, "no write allowed on main"


def test_apply_refused_on_master(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"), branch="master")
    _checkout_named(root, "master")
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, "must refuse --apply on master"
    assert _tree_digest(root) == before, "no write allowed on master"


def test_apply_refused_on_trunk_fallback(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"), branch="trunk")
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, "must refuse --apply on conservative trunk fallback"
    assert "mode=REFUSED" in buf.getvalue(), buf.getvalue()
    assert _tree_digest(root) == before, "no write allowed on trunk"
    with open(doc, encoding="utf-8") as fh:
        assert "version:" not in fh.read()


def test_apply_refused_on_symbolic_remote_default(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"), branch="production")
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    _set_remote_default(root, "production")
    assert E.default_branch(root) == "production"
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, "must refuse the repository's symbolic remote default"
    assert "production" in buf.getvalue(), buf.getvalue()
    assert _tree_digest(root) == before
    with open(doc, encoding="utf-8") as fh:
        assert "version:" not in fh.read()


def test_repo_config_default_branch_is_protected_fallback(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"), branch="release/v1")
    _git(["config", "init.defaultBranch", "release/v1"], root)
    assert E.default_branch(root) == "release/v1"
    assert E.is_feature_branch("release/v1", E.protected_branches(root)) is False


def test_feature_branch_allowed_when_remote_default_is_different(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"), branch="production")
    _set_remote_default(root, "production")
    _checkout_named(root, "feature/docs")
    assert E.is_feature_branch(E.current_branch(root),
                               E.protected_branches(root)) is True


# --------------------------------------------------------------------------
# SAFETY INVARIANT 2 — refuses --apply on detached HEAD
# --------------------------------------------------------------------------
def test_apply_refused_on_detached_head(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    _detach_head(root)
    # Sanity: rev-parse --abbrev-ref HEAD really returns "HEAD" when detached.
    import gitio
    assert gitio.read_only_git(
        ["rev-parse", "--abbrev-ref", "HEAD"], cwd=root).strip() == "HEAD"
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, "must refuse --apply on detached HEAD"
    assert _tree_digest(root) == before, "no write on detached HEAD"


# --------------------------------------------------------------------------
# SAFETY INVARIANT 3 — refuses --apply without a (valid) plan
# --------------------------------------------------------------------------
def test_apply_refused_without_plan(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--apply", "--repo-version", "1.2.3",
                      "--scaffold", "AGENTS.md=agents"])
    assert rc != 0, "must refuse --apply with no plan"
    assert _tree_digest(root) == before, "no write without a plan"
    assert not os.path.exists(os.path.join(root, "AGENTS.md")), \
        "no-plan refusal must also block an otherwise-applicable scaffold"
    assert doc  # silence lint; the doc exists but stays untouched


def test_apply_refused_on_dirty_worktree_blocks_applicable_fix(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    with open(os.path.join(root, "seed.txt"), "a", encoding="utf-8") as fh:
        fh.write("dirty\n")
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, "dirty worktree must refuse apply"
    assert _tree_digest(root) == before, \
        "dirty-worktree preflight refusal must apply zero planned rows"
    with open(doc, encoding="utf-8") as fh:
        assert 'version: "1.2.3"' not in fh.read(), \
            "applicable fix must remain untouched after dirty refusal"


def test_apply_refused_with_unparseable_plan(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    _front04_doc(root, version=False)
    bad = os.path.join(root, "plan.json")
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write("{ this is not json ")
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", bad, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, "must refuse --apply with unparseable plan"
    assert _tree_digest(root) == before, "no write on bad plan"


def test_apply_refused_with_wrong_shape_plan(tmp_path):
    # Valid JSON but NOT a doc_lint plan (no `findings`) must be rejected.
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    _front04_doc(root, version=False)
    bad = os.path.join(root, "plan.json")
    with open(bad, "w", encoding="utf-8") as fh:
        json.dump({"hello": "world"}, fh)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", bad, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, "must refuse a plan that is not a doc_lint report"
    assert _tree_digest(root) == before, "no write on wrong-shape plan"


def test_apply_refuses_forged_report_body_with_valid_catalog_fields(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    plan_path = _write_plan(root)
    with open(plan_path, encoding="utf-8") as fh:
        forged = json.load(fh)
    # All required fields remain present and catalog-valid; only the alleged
    # checker-owned message is forged. Exact current-report reproduction must
    # still reject it.
    forged["findings"][0]["message"] += " [forged]"
    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(forged, fh)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan_path, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, buf.getvalue()
    assert "mode=REFUSED" in buf.getvalue(), buf.getvalue()
    assert _tree_digest(root) == before
    with open(doc, encoding="utf-8") as fh:
        assert "version:" not in fh.read()


def test_apply_refuses_stale_plan_after_new_clean_revision(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    with open(os.path.join(root, "seed.txt"), "a", encoding="utf-8") as fh:
        fh.write("new revision\n")
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "advance target"], root)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, buf.getvalue()
    assert "stale Git revision" in buf.getvalue(), buf.getvalue()
    assert _tree_digest(root) == before
    with open(doc, encoding="utf-8") as fh:
        assert "version:" not in fh.read()


def test_apply_refuses_stale_plan_after_uncommitted_content_change(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    with open(os.path.join(root, "seed.txt"), "a", encoding="utf-8") as fh:
        fh.write("content changed without a revision\n")
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, buf.getvalue()
    assert "stale target content digest" in buf.getvalue(), buf.getvalue()
    assert _tree_digest(root) == before
    with open(doc, encoding="utf-8") as fh:
        assert "version:" not in fh.read()


def test_apply_refuses_plan_bound_to_another_canonical_target(tmp_path):
    first = _init_repo(os.path.join(str(tmp_path), "first"))
    _front04_doc(first, version=False)
    other_plan = _write_plan(first)

    second = _init_repo(os.path.join(str(tmp_path), "second"))
    second_doc = _front04_doc(second, version=False)
    _write_plan(second)  # commit the target; its own report is intentionally unused
    before = _tree_digest(second)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", second, "--plan", other_plan, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, buf.getvalue()
    assert "mode=REFUSED" in buf.getvalue(), buf.getvalue()
    assert _tree_digest(second) == before
    with open(second_doc, encoding="utf-8") as fh:
        assert "version:" not in fh.read()


# --------------------------------------------------------------------------
# SAFETY INVARIANT 4 — dry-run (default) writes nothing
# --------------------------------------------------------------------------
def test_dry_run_is_default_and_writes_nothing(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan,
                      "--repo-version", "1.2.3"])  # NO --apply
    out = buf.getvalue()
    assert rc == 0, out
    assert _tree_digest(root) == before, "dry-run must not change the tree"
    # The applicable fix is shown as LEFT-UNTOUCHED in dry-run (not ADDED/CHANGED).
    assert "LEFT-UNTOUCHED" in out, out
    assert "FRONT-04" in out, out


def test_dry_run_table_has_all_disposition_columns(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        E._main(["--target", root, "--plan", plan, "--repo-version", "1.2.3"])
    out = buf.getvalue()
    for col in ("Finding", "rule-id", "Disposition", "Action", "Rationale"):
        assert col in out, (col, out)


# --------------------------------------------------------------------------
# SAFETY INVARIANT 5 — overwrite-of-present is rejected (ESCALATED, never written)
# --------------------------------------------------------------------------
def test_scaffold_of_present_file_is_escalated_not_overwritten(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    # A scaffold request whose target file ALREADY EXISTS must escalate.
    existing = os.path.join(root, "AGENTS.md")
    original = "# Hand-written charter — do not clobber\n"
    with open(existing, "w", encoding="utf-8") as fh:
        fh.write(original)
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3",
                      "--scaffold", "AGENTS.md=agents"])
    out = buf.getvalue()
    assert rc == 0, out
    assert "ESCALATED" in out, out
    # The present file is byte-for-byte preserved (never overwritten).
    with open(existing, encoding="utf-8") as fh:
        assert fh.read() == original, "PRESENT file must never be overwritten"


def test_overwrite_of_present_via_pure_classifier_escalates(tmp_path):
    # The pure scaffold classifier also refuses a present target.
    root = str(tmp_path)
    present = os.path.join(root, "AGENTS.md")
    with open(present, "w", encoding="utf-8") as fh:
        fh.write("present\n")
    row = E.classify_scaffold("AGENTS.md", "agents", target=root)
    assert row["disposition"] == "ESCALATED", row
    assert row["applicable"] is False, row


# --------------------------------------------------------------------------
# SAFETY INVARIANT 6 — a low-risk fix IS applied (feature branch + valid plan)
# --------------------------------------------------------------------------
def test_front04_version_insert_is_applied_as_changed(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    with open(doc, encoding="utf-8") as fh:
        assert "version:" not in fh.read(), "precondition: version absent"
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "7.8.9"])
    out = buf.getvalue()
    assert rc == 0, out
    assert "CHANGED" in out, out
    # The version line was actually inserted from the known repo version.
    with open(doc, encoding="utf-8") as fh:
        body = fh.read()
    assert "7.8.9" in body, body
    assert "version:" in body, body
    # And the description was NOT clobbered.
    assert "Demo charter." in body, body


def test_scaffold_of_absent_file_is_added(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    target_doc = os.path.join(root, "AGENTS.md")
    assert not os.path.exists(target_doc), "precondition: file absent"
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3",
                      "--scaffold", "AGENTS.md=agents"])
    out = buf.getvalue()
    assert rc == 0, out
    assert "ADDED" in out, out
    assert os.path.exists(target_doc), "absent file should have been scaffolded"
    with open(target_doc, encoding="utf-8") as fh:
        scaffolded = fh.read()
    assert "Identity & Context Awareness" not in scaffolded
    assert "IDENTITY" + "_CANARY" not in scaffolded


def test_extract_template_has_no_personal_response_ritual():
    with open(E._templates_path(), encoding="utf-8") as fh:
        text = fh.read()
    body = E.extract_template("agents", text)
    assert body
    assert "IDENTITY" + "_CANARY" not in body
    assert "Address the user as" not in body


def test_apply_never_deletes_files(tmp_path):
    # SAFETY-01: applying fixes must never remove a non-duplicate file.
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    keep = os.path.join(root, "keep.md")
    with open(keep, "w", encoding="utf-8") as fh:
        fh.write("keep me\n")
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        E._main(["--target", root, "--plan", plan, "--apply",
                 "--repo-version", "1.2.3"])
    assert os.path.exists(keep), "SAFETY-01: must never delete a non-duplicate"
    assert os.path.exists(os.path.join(root, "seed.txt")), "seed survives"


# --------------------------------------------------------------------------
# JSON surface + no-commit guarantee
# --------------------------------------------------------------------------
def test_json_mode_emits_disposition_rows(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        E._main(["--target", root, "--plan", plan, "--json",
                 "--repo-version", "1.2.3"])
    payload = json.loads(buf.getvalue())
    assert "rows" in payload and "applied" in payload, payload
    assert isinstance(payload["rows"], list) and payload["rows"], payload
    assert payload["applied"] is False, payload  # dry-run


def test_apply_does_not_create_a_commit(tmp_path):
    # enforce_apply writes the working tree only; committing is CP09's job.
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    before = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root,
                            check=True, capture_output=True, text=True).stdout
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        E._main(["--target", root, "--plan", plan, "--apply",
                 "--repo-version", "1.2.3"])
    after = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root,
                           check=True, capture_output=True, text=True).stdout
    assert before == after, "enforce_apply must not create a commit"


# --------------------------------------------------------------------------
# LINK-01 autofix path (second real low-risk application) + its precondition
# --------------------------------------------------------------------------
def _link01_finding(file_path, dead_target):
    rule = R.get_rule("LINK-01")
    return {"rule": "LINK-01", "file": os.path.realpath(file_path), "line": 1,
            "message": "dead pointer @%s (resolves to no file)" % dead_target,
            "severity": rule["severity"], "confidence": 10,
            "remedy": rule["remedy"]}


def test_link01_explicit_mapping_is_applied_as_changed(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    # The caller explicitly maps the dead pointer to the reviewed replacement.
    os.makedirs(os.path.join(root, "docs"))
    moved = os.path.join(root, "docs", "guide.md")
    with open(moved, "w", encoding="utf-8") as fh:
        fh.write("# moved guide\n")
    doc = os.path.join(root, "CLAUDE.md")
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write("see @old/guide.md for details\n")
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3", "--link-map",
                      "old/guide.md=docs/guide.md"])
    out = buf.getvalue()
    assert rc == 0, out
    assert "CHANGED" in out, out
    with open(doc, encoding="utf-8") as fh:
        body = fh.read()
    # The dead pointer was repointed to the single found target.
    assert "guide.md" in body and "old/guide.md" not in body, body


def test_link01_repoints_only_the_dead_pointer_not_a_valid_one(tmp_path):
    # f15 corruption case: a VALID pointer appears BEFORE the dead one. The
    # autofix must repoint ONLY the dead @./broken.md and leave @./good.md
    # byte-identical (the old code rewrote the FIRST pointer, corrupting the
    # valid one and leaving the broken one untouched).
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    # @./good.md resolves (a real file next to the doc) -> a VALID pointer.
    with open(os.path.join(root, "good.md"), "w", encoding="utf-8") as fh:
        fh.write("# good\n")
    # the single unambiguous rename target for the dead pointer.
    os.makedirs(os.path.join(root, "docs"))
    with open(os.path.join(root, "docs", "broken.md"), "w", encoding="utf-8") as fh:
        fh.write("# moved\n")
    doc = os.path.join(root, "CLAUDE.md")
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write("first see @./good.md then see @./broken.md for the rest\n")
    # the LINK-01 finding is for the DEAD pointer @./broken.md only.
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3", "--link-map",
                      "./broken.md=docs/broken.md"])
    out = buf.getvalue()
    assert rc == 0, out
    assert "CHANGED" in out, out
    with open(doc, encoding="utf-8") as fh:
        body = fh.read()
    # the VALID pointer is preserved byte-identical
    assert "@./good.md" in body, "the valid pointer must NOT be rewritten: %r" % body
    # the DEAD pointer was repointed away (no longer the dead @./broken.md token)
    assert "@./broken.md" not in body, \
        "the dead pointer must be repointed: %r" % body
    # and it now points at the single rename target
    assert "broken.md" in body, body


def test_link01_dead_pointer_appearing_twice_escalates(tmp_path):
    # f15 precondition tightening: if the dead pointer occurs >1 time in the
    # audited file it is ambiguous (which occurrence to fix?) -> ESCALATE, write
    # nothing. Aligns LINK-01's "exactly one" precondition with occurrences too.
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    os.makedirs(os.path.join(root, "docs"))
    with open(os.path.join(root, "docs", "broken.md"), "w", encoding="utf-8") as fh:
        fh.write("# moved\n")
    doc = os.path.join(root, "CLAUDE.md")
    original = "see @./broken.md here and again @./broken.md there\n"
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write(original)
    finding = _link01_finding(doc, "./broken.md")
    # pure classifier: ambiguous occurrence -> not applicable / ESCALATED
    row = E.classify_disposition(finding, R.RULES, target=root,
                                 repo_version="1.0.0",
                                 link_mappings={"./broken.md": "docs/broken.md"})
    assert row["applicable"] is False, row
    assert row["disposition"] == "ESCALATED", row
    # end to end: --apply writes nothing (the doc is byte-identical)
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        E._main(["--target", root, "--plan", plan, "--apply",
                 "--repo-version", "1.0.0", "--link-map",
                 "./broken.md=docs/broken.md"])
    with open(doc, encoding="utf-8") as fh:
        assert fh.read() == original, "an ambiguous dead pointer must not be touched"


def test_link01_dead_pointer_absent_from_file_escalates(tmp_path):
    # If the dead pointer the finding names does not actually occur in the file
    # (zero occurrences — stale plan), the autofix must ESCALATE, not guess.
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    os.makedirs(os.path.join(root, "docs"))
    with open(os.path.join(root, "docs", "broken.md"), "w", encoding="utf-8") as fh:
        fh.write("# moved\n")
    doc = os.path.join(root, "CLAUDE.md")
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write("this doc has no such pointer\n")
    row = E.classify_disposition(_link01_finding(doc, "./broken.md"),
                                 R.RULES, target=root, repo_version="1.0.0",
                                 link_mappings={"./broken.md": "docs/broken.md"})
    assert row["applicable"] is False, row
    assert row["disposition"] == "ESCALATED", row


def test_link01_no_mapping_escalates_even_with_matching_basenames(tmp_path):
    # Basename matches (one or many) are not rename evidence without a mapping.
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "a"))
    os.makedirs(os.path.join(root, "b"))
    for d in ("a", "b"):
        with open(os.path.join(root, d, "guide.md"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
    doc = os.path.join(root, "CLAUDE.md")
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write("@old/guide.md\n")
    row = E.classify_disposition(_link01_finding(doc, "old/guide.md"),
                                 R.RULES, target=root, repo_version="1.0.0")
    assert row["applicable"] is False, row
    assert row["disposition"] == "ESCALATED", row
    assert "explicit" in row["rationale"], row


def test_link01_unique_basename_without_explicit_mapping_escalates(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "docs"))
    with open(os.path.join(root, "docs", "guide.md"), "w", encoding="utf-8") as fh:
        fh.write("unrelated file with the same basename\n")
    doc = os.path.join(root, "CLAUDE.md")
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write("@old/guide.md\n")
    row = E.classify_disposition(
        _link01_finding(doc, "old/guide.md"), R.RULES, target=root,
        repo_version="1.0.0")
    assert row["applicable"] is False, row
    assert "explicit" in row["rationale"], row


def test_link01_explicit_mapping_must_stay_inside_target(tmp_path):
    root = os.path.join(str(tmp_path), "repo")
    os.makedirs(root)
    outside = os.path.join(str(tmp_path), "guide.md")
    with open(outside, "w", encoding="utf-8") as fh:
        fh.write("outside\n")
    doc = os.path.join(root, "CLAUDE.md")
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write("@old/guide.md\n")
    row = E.classify_disposition(
        _link01_finding(doc, "old/guide.md"), R.RULES, target=root,
        repo_version="1.0.0",
        link_mappings={"old/guide.md": outside})
    assert row["applicable"] is False, row


def test_parse_link_mappings_rejects_duplicates_and_malformed_specs():
    assert E._parse_link_mappings(["old/a.md=docs/a.md"]) == {
        "old/a.md": "docs/a.md"
    }
    for specs in (["missing-equals"], ["=new.md"],
                  ["old.md="], ["a.md=x.md", "a.md=y.md"]):
        try:
            E._parse_link_mappings(specs)
        except ValueError:
            continue
        raise AssertionError("unsafe link mapping must be rejected: %r" % specs)


def test_link01_no_target_escalates(tmp_path):
    root = str(tmp_path)
    doc = os.path.join(root, "CLAUDE.md")
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write("@gone/missing.md\n")
    row = E.classify_disposition(_link01_finding(doc, "gone/missing.md"),
                                 R.RULES, target=root, repo_version="1.0.0")
    assert row["applicable"] is False, row


def test_link01_message_without_pointer_escalates(tmp_path):
    # A LINK-01 message with no parseable @pointer -> no rename target -> ESCALATE.
    root = str(tmp_path)
    row = E.classify_disposition(
        {"rule": "LINK-01", "file": os.path.join(root, "x.md"), "line": 1,
         "message": "dead pointer (unparseable)"},
        R.RULES, target=root, repo_version="1.0.0")
    assert row["applicable"] is False, row


def test_unknown_rule_id_escalates():
    row = E.classify_disposition({"rule": "NOPE-99", "file": "x", "line": 1,
                                  "message": "m"}, R.RULES, target=HERE)
    assert row["disposition"] == "ESCALATED", row
    assert "unknown rule id" in row["rationale"], row


# --------------------------------------------------------------------------
# Refusal rendering (JSON + text) and CLI edge cases
# --------------------------------------------------------------------------
def test_refusal_is_reported_in_json_mode(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"), branch="main")
    _checkout_named(root, "main")
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply", "--json",
                      "--repo-version", "1.2.3"])
    payload = json.loads(buf.getvalue())
    assert rc != 0, payload
    assert payload["refused"], payload
    assert payload["applied"] is False, payload


def test_refusal_is_reported_in_text_mode(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"), branch="main")
    _checkout_named(root, "main")
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        E._main(["--target", root, "--plan", plan, "--apply",
                 "--repo-version", "1.2.3"])
    assert "REFUSED:" in buf.getvalue(), buf.getvalue()
    assert "mode=REFUSED" in buf.getvalue(), buf.getvalue()


def test_apply_on_non_git_target_is_refused(tmp_path):
    # A target that is not a git repo -> current_branch None -> not a feature
    # branch -> --apply refused (fail safe, never write).
    root = str(tmp_path)
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3"])
    assert rc != 0, "non-git target must be refused"
    assert _tree_digest(root) == before, "no write on a non-git target"
    assert doc  # the doc exists but stays untouched


def test_malformed_scaffold_spec_is_ignored():
    assert E._parse_scaffolds(["AGENTS.md=agents", "bogus-no-eq", ""]) == \
        [("AGENTS.md", "agents")]


def test_json_dry_run_marks_left_untouched(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        E._main(["--target", root, "--plan", plan, "--json",
                 "--repo-version", "1.2.3"])
    payload = json.loads(buf.getvalue())
    dispositions = {r["disposition"] for r in payload["rows"]}
    assert "LEFT-UNTOUCHED" in dispositions, payload


# --------------------------------------------------------------------------
# Template extraction + frontmatter helpers (pure)
# --------------------------------------------------------------------------
def test_extract_template_lifts_agents_skeleton():
    with open(E._templates_path(), encoding="utf-8") as fh:
        text = fh.read()
    body = E.extract_template("agents", text)
    assert body and "# [Project Name]" in body, body
    assert "IDENTITY" + "_CANARY" not in body
    assert "Address the user as" not in body


def test_extract_template_unknown_kind_returns_none():
    assert E.extract_template("nope", "## AGENTS.md\n```\nx\n```\n") is None


def test_extract_template_missing_section_returns_none():
    assert E.extract_template("agents", "# no agents section here\n") is None


def test_insert_version_without_frontmatter_raises():
    try:
        E.insert_version("no frontmatter here\n", "1.0.0")
    except ValueError:
        return
    raise AssertionError("insert_version must raise without a frontmatter block")


def test_insert_version_after_name_line():
    text = "---\nname: x\ndescription: d\n---\nbody\n"
    out = E.insert_version(text, "9.9.9")
    lines = out.splitlines()
    # version is inserted directly after the name line.
    assert lines[1] == "name: x", lines
    assert 'version: "9.9.9"' in lines[2], lines


def test_unknown_scaffold_kind_escalates(tmp_path):
    row = E.classify_scaffold("X.md", "totally-unknown", target=str(tmp_path))
    assert row["disposition"] == "ESCALATED", row
    assert row["applicable"] is False, row


def test_is_valid_plan_requires_full_versioned_catalog_contract(tmp_path):
    assert E.is_valid_plan(["not", "a", "dict"]) is False
    assert E.is_valid_plan({"findings": "not a list"}) is False
    assert E.is_valid_plan({"findings": []}) is False
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    _front04_doc(root, version=False)
    plan_path = _write_plan(root)
    with open(plan_path, encoding="utf-8") as fh:
        plan = json.load(fh)
    assert E.is_valid_plan(plan, target=root) is True, plan
    forged = json.loads(json.dumps(plan))
    forged["findings"][0]["severity"] = "P0"
    assert E.is_valid_plan(forged, target=root) is False


# --------------------------------------------------------------------------
# PATH-CONTAINMENT GUARD (iter-2 HIGH fix) — no out-of-target writes
# --------------------------------------------------------------------------
def test_is_within_target_pure_predicate(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "docs"))
    # In-tree absolute paths -> within; ../ escape and a sibling -> not within.
    assert E.is_within_target(os.path.join(root, "AGENTS.md"), root) is True
    assert E.is_within_target(os.path.join(root, "docs", "x.md"), root) is True
    assert E.is_within_target(os.path.join(root, "..", "escape.md"), root) \
        is False
    assert E.is_within_target("/etc/passwd", root) is False


def test_is_within_target_resolves_symlinked_dir_escape(tmp_path):
    # A symlink INSIDE the target pointing OUTSIDE must be caught (realpath
    # resolves the symlink before the commonpath compare).
    root = os.path.join(str(tmp_path), "target")
    outside = os.path.join(str(tmp_path), "outside")
    os.makedirs(root)
    os.makedirs(outside)
    link = os.path.join(root, "link")
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        return  # platform without symlink support — skip
    # target/link/evil.md realpaths to outside/evil.md -> NOT within target.
    assert E.is_within_target(os.path.join(link, "evil.md"), root) is False


def test_plan_finding_with_absolute_out_of_target_path_is_escalated(tmp_path):
    # SAFETY: a tampered plan whose finding.file is an ABSOLUTE path outside
    # --target must be ESCALATED, the victim file untouched, and --apply exits
    # non-zero.
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    victim = os.path.join(str(tmp_path), "VICTIM.md")
    original = ("---\nname: victim\ndescription: keep me untouched please yes."
                "\n---\nbody\n")
    with open(victim, "w", encoding="utf-8") as fh:
        fh.write(original)
    plan = _write_plan(root, [_front04_finding(victim)])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "9.9.9"])
    out = buf.getvalue()
    assert rc != 0, "out-of-target write must make --apply exit non-zero"
    assert "ESCALATED" in out, out
    with open(victim, encoding="utf-8") as fh:
        assert fh.read() == original, "out-of-tree victim must be byte-unchanged"


def test_plan_finding_with_dotdot_relative_path_is_escalated(tmp_path):
    # A finding.file using ../ traversal (built relative to a doc inside the
    # repo but escaping it) must be refused and the victim untouched.
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    victim = os.path.join(str(tmp_path), "OUT.md")
    original = ("---\nname: out\ndescription: do not touch this file at all ok."
                "\n---\nbody\n")
    with open(victim, "w", encoding="utf-8") as fh:
        fh.write(original)
    # A relative ../ path FROM the target dir that resolves to the victim.
    traversal = os.path.join(root, "..", "OUT.md")
    plan = _write_plan(root, [_front04_finding(traversal)])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "9.9.9"])
    out = buf.getvalue()
    assert rc != 0, "../ traversal write must make --apply exit non-zero"
    assert "ESCALATED" in out, out
    with open(victim, encoding="utf-8") as fh:
        assert fh.read() == original, "../ victim must be byte-unchanged"


def test_scaffold_with_dotdot_escape_creates_nothing_outside_target(tmp_path):
    # --scaffold "../escape.md=agents" must not create a file outside --target
    # and its preflight refusal must also block a legitimate in-tree fix.
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    legit = _front04_doc(root, name="CLAUDE.md", version=False)
    escapee = os.path.join(str(tmp_path), "escape.md")
    assert not os.path.exists(escapee)
    plan = _write_plan(root)
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "1.2.3",
                      "--scaffold", "../escape.md=agents"])
    out = buf.getvalue()
    assert rc != 0, "scaffold escape must make --apply exit non-zero"
    assert "ESCALATED" in out, out
    assert not os.path.exists(escapee), \
        "no file may be created outside --target"
    assert _tree_digest(root) == before, \
        "escape preflight must abort every planned in-tree write"


def test_legit_absolute_in_tree_path_still_applies(tmp_path):
    # Proves we compare RESOLVED paths, not reject absolute: a legitimate
    # absolute path that IS inside --target still applies (CHANGED).
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, version=False)  # absolute, inside root
    assert os.path.isabs(doc) and doc.startswith(root), doc
    plan = _write_plan(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "5.5.5"])
    out = buf.getvalue()
    assert rc == 0, out
    assert "CHANGED" in out, out
    with open(doc, encoding="utf-8") as fh:
        assert "5.5.5" in fh.read(), "legit in-tree absolute path must apply"


def test_escape_aborts_all_legit_rows_in_same_run(tmp_path):
    # A run mixing an escape finding + a legitimate in-tree finding is
    # fail-closed: the preflight refusal applies zero rows and exits non-zero.
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    legit = _front04_doc(root, name="CLAUDE.md", version=False)
    victim = os.path.join(str(tmp_path), "VICTIM.md")
    with open(victim, "w", encoding="utf-8") as fh:
        fh.write("---\nname: v\ndescription: untouched untouched untouched ok.\n"
                 "---\nb\n")
    plan = _write_plan(root, [_front04_finding(legit),
                              _front04_finding(victim)])
    before = _tree_digest(root)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = E._main(["--target", root, "--plan", plan, "--apply",
                      "--repo-version", "3.3.3", "--json"])
    payload = json.loads(buf.getvalue())
    assert rc != 0, "an attempted escape forces non-zero exit"
    assert payload["refused"], payload
    assert payload["applied"] is False, payload
    legit_row = next(row for row in payload["rows"]
                     if os.path.realpath(row.get("file", "")) ==
                     os.path.realpath(legit))
    assert legit_row["disposition"] == "LEFT-UNTOUCHED", legit_row
    assert _tree_digest(root) == before, \
        "preflight refusal must leave the complete target tree byte-identical"
    with open(legit, encoding="utf-8") as fh:
        assert "3.3.3" not in fh.read(), "legit in-tree row must stay untouched"
    with open(victim, encoding="utf-8") as fh:
        assert "3.3.3" not in fh.read(), "escape victim untouched"


def test_second_atomic_write_failure_rolls_back_first_and_reports(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    first = _front04_doc(root, name="AGENTS.md", version=False)
    second = _front04_doc(root, name="CLAUDE.md", version=False)
    plan = _write_plan(root)
    before = {path: open(path, "rb").read() for path in (first, second)}

    original_commit = E._commit_mutation
    calls = {"count": 0}

    def fail_second(mutation, *, target):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("injected second-write failure")
        return original_commit(mutation, target=target)

    E._commit_mutation = fail_second
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = E._main(["--target", root, "--plan", plan, "--apply",
                          "--repo-version", "9.9.9", "--json"])
    finally:
        E._commit_mutation = original_commit

    payload = json.loads(buf.getvalue())
    assert rc != 0, payload
    assert payload["applied"] is False, payload
    assert payload["mutation_failure"]["phase"] == "commit", payload
    assert payload["rollback"] == {
        "attempted": 1,
        "errors": [],
        "restored": 1,
        "verified": True,
    }, payload
    for path, original in before.items():
        with open(path, "rb") as fh:
            assert fh.read() == original, path
    assert not any(name.startswith(".doc-steward-")
                   for name in os.listdir(root))
    dispositions = [row["disposition"] for row in payload["rows"]
                    if row.get("applicable")]
    assert "LEFT-UNTOUCHED" in dispositions, payload
    assert "ESCALATED" in dispositions, payload


def test_target_change_during_preparation_is_refused_before_first_write(tmp_path):
    root = _init_repo(os.path.join(str(tmp_path), "repo"))
    doc = _front04_doc(root, name="CLAUDE.md", version=False)
    plan = _write_plan(root)
    with open(doc, "rb") as fh:
        original_doc = fh.read()

    original_prepare = E._prepare_mutation
    changed = {"done": False}

    def tamper_after_prepare(row, *, templates_text, target):
        mutation = original_prepare(
            row, templates_text=templates_text, target=target)
        if not changed["done"]:
            with open(os.path.join(target, "seed.txt"), "a", encoding="utf-8") as fh:
                fh.write("concurrent change\n")
            changed["done"] = True
        return mutation

    E._prepare_mutation = tamper_after_prepare
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = E._main(["--target", root, "--plan", plan, "--apply",
                          "--repo-version", "9.9.9", "--json"])
    finally:
        E._prepare_mutation = original_prepare

    payload = json.loads(buf.getvalue())
    assert rc != 0, payload
    assert payload["applied"] is False, payload
    assert payload["rollback"] is None, payload
    assert payload["mutation_failure"]["phase"] == \
        "precommit-revalidation", payload
    with open(doc, "rb") as fh:
        assert fh.read() == original_doc, "planned document must not be written"


def _run():
    import tempfile
    import shutil
    import pathlib
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
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
