#!/usr/bin/env python3
"""enforce_apply — doc-steward's ONLY doc-mutation path (design §4.4 ENFORCE).

This is the single write-enabled module. It is **dry-run by default**; an
explicit `--apply` is required to touch the working tree, and `--apply` itself
**refuses (non-zero exit) unless all three** safety gates hold:

  (a) the TARGET repo's current branch is a real checked-out feature branch:
      NOT its detected remote/configured default, NOT a conservative
      `main`/`master`/`trunk` fallback, and NOT detached `HEAD`; AND
  (b) a genuine versioned EVALUATE report is supplied and remains bound to the
      target's canonical path, current Git revision, and content digest; AND
  (c) the target worktree is clean, including untracked files.

The branch gate checks the **TARGET repo being enforced** (the `--target` dir),
NOT doc-steward's own repo — `read_only_git` is invoked with `cwd=target`.

What it applies (and only this):
  * LOW-RISK-AUTO findings whose `autofix_preconditions` HOLD at runtime
    (read each finding's rule from `lib/rules.py`). Per the catalog only LINK-01
    and FRONT-04 are LOW-RISK-AUTO, and each fires only when its precondition is
    satisfiable for that specific finding; otherwise it degrades to ESCALATE.
  * Scaffolds a templated file ONLY when ABSENT (skeletons from
    `references/templates.md`). It NEVER overwrites a PRESENT file
    (overwrite-of-present = always ESCALATE, design line 139) and NEVER deletes
    a non-duplicate (SAFETY-01).

Output: the `ADDED | CHANGED | LEFT-UNTOUCHED | ESCALATED` disposition table
(columns: Finding | rule-id | Disposition | Action | Rationale). ESCALATED rows
are reported, never applied. In dry-run an applicable fix is shown as
LEFT-UNTOUCHED (it WOULD change, but is left untouched this run).

It does NOT `git commit` — it only writes files in the target working tree; the
branch gate is a READ guard via gitio (`scripts/apply/*` writers are the
write-enabled command surface, but committing/PR is CP09's job).

Design seam: the classifier/disposition logic is pure/DI (takes findings + rules
as ARGUMENTS, inspects only the target tree); plan reproduction and branch
detection are explicit read-only I/O boundaries. Stdlib-only.
"""
import argparse
import configparser
import json
import os
import re
import sys
import tempfile

# --------------------------------------------------------------------------
# Cross-dir imports: lib/ (../lib) for rules + the read-only git wrapper.
# --------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "..", "lib"),
           os.path.join(_HERE, "..", "checks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gitio  # noqa: E402
import doc_lint  # noqa: E402
import rules  # noqa: E402

# Branch names that are NEVER a valid --apply target. `HEAD` is what
# `rev-parse --abbrev-ref HEAD` returns under detached HEAD.
_PROTECTED_BRANCHES = frozenset({"main", "master", "trunk", "HEAD"})

# templates.md section keyword -> scaffold kind. The kind selects which fenced
# skeleton to lift for an ABSENT-file scaffold.
_SCAFFOLD_SECTIONS = {
    "agents": "AGENTS.md",
    "claude": "CLAUDE.md",
    "design": "DESIGN.md",
}

# Semver X.Y.Z (mirror of frontmatter_check._SEMVER) — used to validate the
# repo version we would insert for FRONT-04.
_SEMVER = re.compile(r"^\d+\.\d+\.\d+([-+][0-9A-Za-z.\-]+)?$")

# ==========================================================================
# Branch gate (pure predicate + the single I/O boundary)
# ==========================================================================
def is_feature_branch(branch, protected_branches=None):
    """True iff `branch` is a real checked-out branch that is safe to write on.

    Pure. ``protected_branches`` may add the target's detected default branch;
    the conservative built-in fallback is always retained.
    """
    if not branch:
        return False
    protected = set(_PROTECTED_BRANCHES)
    protected.update(protected_branches or ())
    return branch.strip() not in protected


def current_branch(target):
    """The target repo's current branch via the read-only git wrapper (I/O).

    Returns the stripped branch name, or None if git could not report it (e.g.
    `target` is not a git repo). It runs against `cwd=target` — the repo being
    enforced, not doc-steward's own.
    """
    try:
        out = gitio.read_only_git(
            ["rev-parse", "--abbrev-ref", "HEAD"], cwd=target)
    except Exception:  # noqa: BLE001 — not a repo / git unavailable -> ungated
        return None
    return out.strip() or None


def _normalise_branch(value, remote=None):
    """Normalise a full ref or remote-qualified name to a local branch name."""
    value = (value or "").strip()
    if value.startswith("refs/heads/"):
        value = value[len("refs/heads/"):]
    if value.startswith("refs/remotes/"):
        value = value[len("refs/remotes/"):]
    if remote and value.startswith(remote + "/"):
        value = value[len(remote) + 1:]
    return value or None


def _remote_default_branch(target):
    """Read a symbolic remote HEAD using only the read-only git choke point."""
    try:
        remotes = gitio.read_only_git(["remote"], cwd=target).splitlines()
    except Exception:  # noqa: BLE001 — no remotes / non-Git
        return None
    ordered = sorted({r.strip() for r in remotes if r.strip()},
                     key=lambda r: (r != "origin", r))
    for remote in ordered:
        ref = "refs/remotes/%s/HEAD" % remote
        try:
            value = gitio.read_only_git(
                ["rev-parse", "--abbrev-ref", ref], cwd=target).strip()
        except Exception:  # noqa: BLE001 — this remote has no symbolic HEAD
            continue
        branch = _normalise_branch(value, remote=remote)
        if branch and branch != "HEAD" and branch != ref:
            return branch
    return None


def _configured_default_branch(target):
    """Read repository-local ``init.defaultBranch`` without invoking git config.

    Git has no immutable local "default branch" record. When no symbolic remote
    HEAD exists, a repository-local ``[init] defaultBranch`` is the explicit
    offline signal. The config path itself is resolved by whitelisted
    ``git rev-parse --git-common-dir`` and then parsed read-only.
    """
    try:
        common = gitio.read_only_git(
            ["rev-parse", "--git-common-dir"], cwd=target).strip()
        if not os.path.isabs(common):
            common = os.path.join(target, common)
        config_path = os.path.join(os.path.realpath(common), "config")
        parser = configparser.RawConfigParser(strict=False)
        with open(config_path, encoding="utf-8") as fh:
            parser.read_file(fh)
        value = parser.get("init", "defaultbranch", fallback="")
    except Exception:  # noqa: BLE001 — absent/malformed config => fallback
        return None
    return _normalise_branch(value)


def default_branch(target):
    """Return the target's detected default branch, or None if not declared."""
    return _remote_default_branch(target) or _configured_default_branch(target)


def protected_branches(target):
    """Return built-in protected names plus the target's actual default."""
    protected = set(_PROTECTED_BRANCHES)
    detected = default_branch(target)
    if detected:
        protected.add(detected)
    return frozenset(protected)


def worktree_is_clean(target):
    """Return True only when the target has no tracked or untracked changes."""
    try:
        out = gitio.read_only_git(
            ["status", "--porcelain", "--untracked-files=all"], cwd=target)
    except Exception:  # not a repo / git unavailable -> fail closed
        return False
    return not out.strip()


# ==========================================================================
# Plan (EVALUATE artifact) loading + validation
# ==========================================================================
def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_finding(finding, *, target=None):
    """Validate one finding against the canonical deterministic rule catalog."""
    if not isinstance(finding, dict):
        return False
    rid = finding.get("rule")
    try:
        rule = rules.get_rule(rid)
    except (KeyError, TypeError):
        return False
    if rule.get("check") != "deterministic":
        return False
    file_path = finding.get("file")
    if not isinstance(file_path, str) or not file_path or not os.path.isabs(file_path):
        return False
    if target is not None and not is_within_target(file_path, target):
        return False
    line = finding.get("line")
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        return False
    if not isinstance(finding.get("message"), str) or not finding["message"].strip():
        return False
    return (
        finding.get("severity") == rule.get("severity")
        and finding.get("confidence") == 10
        and finding.get("remedy") == rule.get("remedy")
        and bool(str(rule.get("remedy", "")).strip())
    )


def is_valid_plan(obj, *, target=None):
    """True iff ``obj`` is a complete versioned doc_lint EVALUATE report.

    This validates the persisted schema and catalog-owned finding fields. The
    separate ``plan_authenticity_error`` gate additionally re-runs doc_lint and
    requires byte-for-byte semantic equality with the target's current report.
    """
    if not isinstance(obj, dict):
        return False
    required = {
        "schema_version", "canonical_target", "git_revision",
        "content_digest", "passed", "tier", "composite", "grade",
        "findings", "skipped", "scope", "target_profile",
        "structure_scope", "dimensions", "severity_counts",
    }
    if not required.issubset(obj):
        return False
    if obj.get("schema_version") != doc_lint.REPORT_SCHEMA_VERSION:
        return False
    canonical = obj.get("canonical_target")
    if (not isinstance(canonical, str) or not os.path.isabs(canonical)
            or os.path.realpath(canonical) != canonical):
        return False
    if target is not None and canonical != doc_lint.canonical_target(target):
        return False
    revision = obj.get("git_revision")
    if revision is not None and not (
            isinstance(revision, str)
            and re.fullmatch(r"[0-9a-fA-F]{40,64}", revision)):
        return False
    digest = obj.get("content_digest")
    if not (isinstance(digest, str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
        return False
    if not isinstance(obj.get("findings"), list):
        return False
    if not all(_valid_finding(f, target=target) for f in obj["findings"]):
        return False
    # An incomplete deterministic run is evidence, but not a safe mutation
    # plan: ENFORCE refuses if any checker was skipped.
    if obj.get("skipped") != []:
        return False
    if obj.get("scope") != "deterministic":
        return False
    if obj.get("structure_scope") != "required-document-presence":
        return False
    if obj.get("target_profile") not in ("repository", "skill-package"):
        return False
    if obj.get("tier") not in ("Simple", "Standard", "Complex"):
        return False
    if obj.get("grade") not in ("PASS", "PASS_WITH_CONCERNS", "FAIL"):
        return False
    if not isinstance(obj.get("passed"), bool):
        return False
    composite = obj.get("composite")
    if not _number(composite) or not 0 <= composite <= 10:
        return False
    expected_grade = ("PASS" if composite >= 8 else
                      ("PASS_WITH_CONCERNS" if composite >= 5 else "FAIL"))
    if obj["grade"] != expected_grade or obj["passed"] != (expected_grade == "PASS"):
        return False
    dimensions = obj.get("dimensions")
    if not isinstance(dimensions, dict) or set(dimensions) != {
            "structure", "frontmatter", "links"}:
        return False
    if not all(_number(v) and 0 <= v <= 10 for v in dimensions.values()):
        return False
    counts = obj.get("severity_counts")
    if not isinstance(counts, dict) or set(counts) != {"P0", "P1", "P2"}:
        return False
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
               for v in counts.values()):
        return False
    actual_counts = {
        severity: sum(f["severity"] == severity for f in obj["findings"])
        for severity in ("P0", "P1", "P2")
    }
    return counts == actual_counts


def load_plan(path):
    """Parse + validate a plan file. Returns the plan dict or None on any error."""
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, ValueError):
        return None
    return obj if is_valid_plan(obj) else None


def current_evaluate_report(target):
    """Run the canonical default EVALUATE contract against ``target`` now."""
    return doc_lint.lint(doc_lint.canonical_target(target), rules.RULES)


def plan_authenticity_error(plan, target):
    """Return a fail-closed reason when a plan is forged, stale, or mismatched."""
    if not is_valid_plan(plan, target=target):
        return "invalid schema, target binding, or catalog finding fields"
    try:
        current = current_evaluate_report(target)
    except Exception as exc:  # noqa: BLE001 — EVALUATE failure blocks mutation
        return "could not reproduce current EVALUATE report (%s)" % type(exc).__name__
    # Object equality is deliberate: a plan must be the complete current
    # versioned report, not merely carry a matching digest around forged rows.
    if plan != current:
        if plan.get("git_revision") != current.get("git_revision"):
            return "stale Git revision"
        if plan.get("content_digest") != current.get("content_digest"):
            return "stale target content digest"
        if plan.get("canonical_target") != current.get("canonical_target"):
            return "plan belongs to another canonical target"
        return "report body does not match a current canonical EVALUATE run"
    return None


# ==========================================================================
# Frontmatter helpers (minimal, mirrors frontmatter_check's subset parser)
# ==========================================================================
def _frontmatter_bounds(text):
    """Return (start_idx, end_idx) line indices of the leading `---` block.

    `start_idx` is the opening fence line (0), `end_idx` is the closing fence
    line. Returns None when there is no well-formed leading frontmatter block.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return (0, i)
    return None


def _frontmatter_field(text, key):
    """Return the value of a simple `key: value` frontmatter field, or ""."""
    bounds = _frontmatter_bounds(text)
    if not bounds:
        return ""
    _, end = bounds
    lines = text.splitlines()
    pat = re.compile(r"^%s:\s*(.*)$" % re.escape(key))
    for i in range(1, end):
        m = pat.match(lines[i])
        if m:
            return m.group(1).strip()
    return ""


def insert_version(text, version):
    """Return `text` with a `version: "X.Y.Z"` line inserted into frontmatter.

    Inserts right after the `name:` line when present, else right after the
    opening fence. Pure — returns new text; never deletes existing content.
    Raises ValueError if `text` has no frontmatter block to insert into.
    """
    bounds = _frontmatter_bounds(text)
    if not bounds:
        raise ValueError("no frontmatter block to insert version into")
    lines = text.splitlines(keepends=True)
    _, end = bounds
    # Prefer inserting after `name:`; else after the opening fence (line 0).
    insert_at = 1
    for i in range(1, end):
        if re.match(r"^name:\s*", lines[i]):
            insert_at = i + 1
            break
    newline = "\n"
    new_line = 'version: "%s"%s' % (version, newline)
    lines.insert(insert_at, new_line)
    return "".join(lines)


# ==========================================================================
# Pure disposition classifier (no git; inspects the target tree only)
# ==========================================================================
def _row(finding, disposition, action, rationale, *, applicable, write=None):
    return {
        "finding": finding.get("message", ""),
        "rule": finding.get("rule", ""),
        "file": finding.get("file", ""),
        "disposition": disposition,
        "action": action,
        "rationale": rationale,
        "applicable": applicable,
        # write: dict describing the planned mutation (kind/path/...), or None.
        "write": write,
    }


def _front04_precondition_holds(finding, target, repo_version):
    """FRONT-04 autofix precondition: missing version insertable; desc present.

    Holds iff: (1) a known repo version is supplied and is valid semver;
    (2) the finding is specifically a MISSING-version case (not a malformed,
    present version); (3) the audited doc has a `description` already present
    and currently has NO version. The doc-side checks read the target file.
    """
    if not repo_version or not _SEMVER.match(repo_version):
        return False
    if "missing `version`" not in finding.get("message", ""):
        return False
    path = finding.get("file", "")
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    if not _frontmatter_field(text, "description"):
        return False
    if _frontmatter_field(text, "version"):
        return False
    return True


def _link01_rename_target(finding, target, link_mappings=None):
    """LINK-01 precondition: explicit old->new mapping + one occurrence.

    A unique basename is not rename evidence; it can be an unrelated file. The
    caller must explicitly map the exact dead target to one repository-relative,
    existing in-root file. The autofix is safe ONLY when:
      * an explicit mapping exists for the exact dead target;
      * the mapped file is a regular in-root file; and
      * the EXACT dead-pointer token (`@<target>`) occurs EXACTLY ONCE.

    Returns (dead_pointer, rename_target) iff BOTH hold; otherwise None
    (-> ESCALATE; f15 — never guess which pointer to rewrite).
    """
    m = re.search(r"@(\S+)", finding.get("message", ""))
    if not m:
        return None
    dead = m.group(1)
    dead_pointer = "@" + dead
    mapped = (link_mappings or {}).get(dead)
    if not mapped:
        return None
    rename_target = (mapped if os.path.isabs(mapped)
                     else os.path.join(target, mapped))
    if (not is_within_target(rename_target, target)
            or not os.path.isfile(rename_target)):
        return None
    # Occurrence guard (f15): the exact dead pointer must appear EXACTLY once in
    # the audited file, else repointing would touch the wrong (or an ambiguous)
    # pointer. Zero or >1 -> ESCALATE.
    if _dead_pointer_count(finding.get("file", ""), dead_pointer) != 1:
        return None
    return (dead_pointer, os.path.realpath(rename_target))


def _dead_pointer_count(doc_path, dead_pointer):
    """Count exact occurrences of `dead_pointer` (the `@<target>` token) in the
    audited file. Returns 0 when the file is unreadable. The count uses a
    boundary so `@./broken.md` does not also match `@./broken.md.bak`."""
    if not doc_path or not os.path.isfile(doc_path):
        return 0
    try:
        with open(doc_path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return 0
    return len(re.findall(re.escape(dead_pointer) + r"(?![^\s)\]\"'])", text))


def is_within_target(write_path, target):
    """True iff `write_path` resolves to a location INSIDE `target` (pure).

    Containment is decided on REALPATH-resolved absolute paths, so:
      * a legitimate ABSOLUTE in-tree path (as doc_lint emits) passes — we do
        NOT reject absolute paths, only out-of-tree ones;
      * a `../` traversal or a sibling/foreign absolute path is rejected;
      * a symlink INSIDE target that points OUTSIDE is rejected, because
        realpath follows symlinks before the commonpath compare.
    Fail-closed: any path math error (mixed drives, etc.) returns False.
    """
    try:
        rt = os.path.realpath(target)
        rw = os.path.realpath(write_path)
        return os.path.commonpath([rw, rt]) == rt
    except (ValueError, OSError):
        return False


def _escape_row(finding, target):
    """Build the ESCALATED row for a write that would escape `target`.

    Carries `escape_attempted=True` so the CLI turns an attempted escape into a
    hard, non-zero refusal (a tampered plan is not a silent skip).
    """
    r = _row(finding, "ESCALATED", "report",
             "write target escapes --target (path traversal) — refused; "
             "never written",
             applicable=False)
    r["escape_attempted"] = True
    return r


def classify_disposition(finding, rule_list, *, target, repo_version=None,
                         link_mappings=None):
    """Classify ONE finding into a disposition row (pure; reads target tree).

    Returns a row dict (see `_row`). A row is `applicable` iff its rule is
    LOW-RISK-AUTO in the catalog AND its autofix_preconditions hold for this
    finding AND the write path is CONTAINED within `target`. A write that would
    escape `target` is ESCALATED with `escape_attempted=True`. Everything else
    is ESCALATED with `applicable=False` and no write plan.
    """
    rid = finding.get("rule", "")
    try:
        rule = rules.get_rule(rid)
    except KeyError:
        return _row(finding, "ESCALATED", "report",
                    "unknown rule id — not in catalog", applicable=False)

    if rule.get("auto") != "LOW-RISK-AUTO":
        return _row(finding, "ESCALATED", "report",
                    "rule is ESCALATE in catalog (human review)",
                    applicable=False)

    # CONTAINMENT GUARD: any finding that touches a file outside --target is a
    # tampered/poisoned plan — refuse it before considering the autofix.
    fpath = finding.get("file", "")
    if fpath and not is_within_target(fpath, target):
        return _escape_row(finding, target)

    # FRONT-04 — insert a missing version from the known repo version.
    if rid == "FRONT-04":
        if _front04_precondition_holds(finding, target, repo_version):
            return _row(
                finding, "CHANGED",
                'insert version: "%s"' % repo_version,
                "autofix_preconditions hold: missing version insertable from "
                "the repo's known version; description present",
                applicable=True,
                write={"kind": "insert_version", "path": finding["file"],
                       "version": repo_version})
        return _row(finding, "ESCALATED", "report",
                    "autofix_preconditions NOT met (no known version, version "
                    "present/malformed, or description absent)",
                    applicable=False)

    # LINK-01 — repoint only through an explicit reviewed old->new mapping.
    if rid == "LINK-01":
        resolved = _link01_rename_target(
            finding, target, link_mappings=link_mappings)
        if resolved:
            dead_pointer, tgt = resolved
            return _row(
                finding, "CHANGED", "repoint %s -> %s" % (dead_pointer, tgt),
                "autofix_preconditions hold: explicit old-to-new mapping names "
                "one existing in-root target AND the dead pointer occurs "
                "exactly once in the file",
                applicable=True,
                write={"kind": "repoint", "path": finding["file"],
                       "dead_pointer": dead_pointer, "rename_target": tgt})
        return _row(finding, "ESCALATED", "report",
                    "autofix_preconditions NOT met: no explicit safe old-to-new "
                    "mapping, or the dead pointer does not occur exactly once "
                    "in the file",
                    applicable=False)

    # Any other (theoretically) LOW-RISK-AUTO rule has no implemented autofix.
    return _row(finding, "ESCALATED", "report",
                "no implemented autofix for this rule", applicable=False)


def classify_scaffold(rel_path, kind, *, target):
    """Classify a scaffold request (ABSENT-file bootstrap) into a row (pure).

    ADDED+applicable iff the target file is ABSENT, the scaffold kind is known,
    AND the resolved path is CONTAINED within `target`. A PRESENT target is
    ESCALATED (overwrite-of-present is always ESCALATE — never clobbered); a
    path that escapes `target` (e.g. `../escape`) is ESCALATED with
    `escape_attempted=True`. Synthesizes a finding-shaped row so the scaffold
    shares the disposition table with the findings.
    """
    abs_path = os.path.join(target, rel_path)
    synth = {"rule": "STRUCT-01", "file": abs_path,
             "message": "required doc %r absent" % rel_path}
    if kind not in _SCAFFOLD_SECTIONS:
        return _row(synth, "ESCALATED", "report",
                    "unknown scaffold kind %r" % kind, applicable=False)
    # CONTAINMENT GUARD: a scaffold path must not escape --target.
    if not is_within_target(abs_path, target):
        return _escape_row(synth, target)
    if os.path.exists(abs_path):
        return _row(synth, "ESCALATED", "report",
                    "target file already PRESENT — overwrite-of-present always "
                    "escalates; never clobbered",
                    applicable=False)
    return _row(synth, "ADDED", "scaffold %s from templates.md" % rel_path,
                "file ABSENT — bootstrap from the canonical %s skeleton" % kind,
                applicable=True,
                write={"kind": "scaffold", "path": abs_path,
                       "scaffold_kind": kind})


# ==========================================================================
# Template extraction (read-only) for scaffolds
# ==========================================================================
def _templates_path():
    # references/ lives two levels up from scripts/apply/.
    return os.path.normpath(
        os.path.join(_HERE, "..", "..", "references", "templates.md"))


def extract_template(kind, templates_text):
    """Return the first fenced ```markdown block of the `kind` section, or None.

    `kind` is a key of _SCAFFOLD_SECTIONS; the section is located by its target
    filename appearing in a `## ...` heading, and the first fenced code block
    after that heading is the skeleton. Pure over the supplied text.
    """
    target_name = _SCAFFOLD_SECTIONS.get(kind)
    if not target_name:
        return None
    lines = templates_text.splitlines()
    # Find the section heading that mentions the target filename.
    sec_start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and target_name in ln:
            sec_start = i
            break
    if sec_start is None:
        return None
    # Walk to the first fenced block within the section (until the next `## `).
    i = sec_start + 1
    while i < len(lines):
        if lines[i].startswith("## "):
            return None  # section ended without a fence
        if lines[i].strip().startswith("```"):
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            return "\n".join(body) + "\n"
        i += 1
    return None


# ==========================================================================
# Apply engine — performs the writes for applicable rows (only when do_apply)
# ==========================================================================
def _repoint_pointer(text, dead_pointer, rename_target, doc_path):
    """Rewrite the EXACT `dead_pointer` occurrence in `text` -> `rename_target`.

    f15: replaces ONLY the specific broken `@<target>` token the LINK-01 finding
    named — never the first/any other `@pointer` — so a valid pointer elsewhere in
    the file is left byte-identical. The replacement is the path of
    `rename_target` relative to the doc's dir, so the repointed link resolves.
    Returns new text (unchanged if the dead pointer is not present). Never deletes
    content. The boundary lookahead prevents `@a.md` from matching `@a.md.bak`.
    """
    rel = os.path.relpath(rename_target, os.path.dirname(os.path.abspath(doc_path)))
    return re.sub(re.escape(dead_pointer) + r"(?![^\s)\]\"'])",
                  "@" + rel, text)


class MutationError(RuntimeError):
    """A fail-closed mutation preparation, commit, or rollback error."""


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _prepare_mutation(row, *, templates_text, target):
    """Build one immutable mutation from the current bytes without writing.

    Preparation captures the exact preimage used later for both a race check and
    rollback.  Final-component symlinks are refused: replacing a symlink rather
    than its referent would make the classifier and mutator disagree about the
    affected file.
    """
    plan = row.get("write")
    if not plan:
        raise MutationError("applicable row has no write plan")
    path = os.path.abspath(plan.get("path", ""))
    if not path or not is_within_target(path, target):
        raise MutationError("write path is outside target")
    if os.path.islink(path):
        raise MutationError("write path is a symlink")

    kind = plan.get("kind")
    existed = os.path.exists(path)
    if existed and not os.path.isfile(path):
        raise MutationError("write path is not a regular file")
    preimage = _read_bytes(path) if existed else None
    mode = (os.stat(path, follow_symlinks=False).st_mode & 0o777
            if existed else 0o644)

    if kind == "insert_version":
        if preimage is None:
            raise MutationError("version target disappeared")
        text = preimage.decode("utf-8")
        new_text = insert_version(text, plan["version"])
    elif kind == "repoint":
        if preimage is None:
            raise MutationError("pointer target disappeared")
        text = preimage.decode("utf-8")
        new_text = _repoint_pointer(
            text, plan["dead_pointer"], plan["rename_target"], path)
        if new_text == text:
            raise MutationError("dead pointer changed before apply")
    elif kind == "scaffold":
        if existed:
            raise MutationError("scaffold target appeared before apply")
        new_text = extract_template(plan["scaffold_kind"], templates_text)
        if new_text is None:
            raise MutationError("scaffold template unavailable")
    else:
        raise MutationError("unknown mutation kind")

    return {
        "path": path,
        "preimage": preimage,
        "new_bytes": new_text.encode("utf-8"),
        "existed": existed,
        "mode": mode,
        "created_dirs": [],
    }


def _missing_parent_dirs(path, target):
    """Return absent parents below target, outermost first (no writes)."""
    root = os.path.realpath(target)
    current = os.path.dirname(os.path.abspath(path))
    missing = []
    while current != root and not os.path.exists(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            raise MutationError("cannot resolve mutation parent")
        current = parent
    if not is_within_target(current, target):
        raise MutationError("mutation parent escapes target")
    return list(reversed(missing))


def _atomic_replace_bytes(path, data, mode=0o644):
    """Atomically replace/create ``path`` from a same-directory temp file."""
    parent = os.path.dirname(os.path.abspath(path))
    fd, temp_path = tempfile.mkstemp(prefix=".doc-steward-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if os.path.lexists(temp_path):
            os.unlink(temp_path)


def _commit_mutation(mutation, *, target):
    """Commit one prepared mutation atomically after a byte-level race check."""
    path = mutation["path"]
    if not is_within_target(path, target) or os.path.islink(path):
        raise MutationError("write boundary changed before commit")
    now_exists = os.path.exists(path)
    if now_exists != mutation["existed"]:
        raise MutationError("write target existence changed before commit")
    if now_exists and _read_bytes(path) != mutation["preimage"]:
        raise MutationError("write target content changed before commit")

    created_dirs = _missing_parent_dirs(path, target)
    for directory in created_dirs:
        os.mkdir(directory)
    mutation["created_dirs"] = created_dirs
    if not is_within_target(path, target):
        raise MutationError("write parent changed before atomic replace")
    _atomic_replace_bytes(path, mutation["new_bytes"], mutation["mode"])
    return mutation


def _rollback_mutations(completed, *, target):
    """Restore every completed mutation and verify byte-identical rollback.

    Returns a JSON-safe receipt.  Rollback is best effort but fail-visible: any
    restore or verification error sets ``verified`` false and is reported by
    type, never swallowed.
    """
    errors = []
    for mutation in reversed(completed):
        path = mutation["path"]
        try:
            if not is_within_target(path, target) or os.path.islink(path):
                raise MutationError("rollback boundary changed")
            if mutation["existed"]:
                _atomic_replace_bytes(
                    path, mutation["preimage"], mutation["mode"])
            elif os.path.lexists(path):
                os.unlink(path)
            for directory in reversed(mutation.get("created_dirs", [])):
                try:
                    os.rmdir(directory)
                except OSError:
                    pass
        except Exception as exc:  # noqa: BLE001 — receipt must survive failure
            errors.append(type(exc).__name__)

    for mutation in completed:
        try:
            if mutation["existed"]:
                ok = (os.path.isfile(mutation["path"]) and
                      not os.path.islink(mutation["path"]) and
                      _read_bytes(mutation["path"]) == mutation["preimage"])
            else:
                ok = not os.path.lexists(mutation["path"])
            if not ok:
                errors.append("VerificationError")
        except Exception as exc:  # noqa: BLE001
            errors.append(type(exc).__name__)
    return {
        "attempted": len(completed),
        "restored": len(completed) if not errors else None,
        "verified": not errors,
        "errors": errors,
    }


def _cleanup_failed_mutation_dirs(mutation, *, target):
    """Remove empty parents created by a mutation that never committed."""
    errors = []
    for directory in reversed(mutation.get("created_dirs", [])):
        try:
            if not is_within_target(directory, target):
                raise MutationError("failed-mutation directory escaped target")
            os.rmdir(directory)
        except OSError:
            # A non-empty directory may contain concurrent/user data; never
            # recurse or delete it. Report that byte-identical cleanup was not
            # verified instead.
            errors.append("DirectoryCleanupError")
        except Exception as exc:  # noqa: BLE001
            errors.append(type(exc).__name__)
    return errors


def perform_write(row, *, templates_text, target):
    """Prepare and atomically commit one row; return its rollback receipt.

    Multi-row callers must retain this receipt and call `_rollback_mutations`
    if a later mutation fails.  The CLI does so and emits the verification
    receipt in every partial-failure report.
    """
    mutation = _prepare_mutation(
        row, templates_text=templates_text, target=target)
    return _commit_mutation(mutation, target=target)


# ==========================================================================
# Orchestration (pure planning) + the disposition table renderer
# ==========================================================================
def plan_dispositions(findings, scaffolds, rule_list, *, target,
                      repo_version=None, link_mappings=None):
    """Build the disposition rows for all findings + scaffold requests (pure).

    `scaffolds` is a list of (rel_path, kind). Returns the ordered row list with
    each row's intended disposition; no writes happen here.
    """
    rows = []
    for f in findings:
        rows.append(classify_disposition(
            f, rule_list, target=target, repo_version=repo_version,
            link_mappings=link_mappings))
    for rel_path, kind in scaffolds:
        rows.append(classify_scaffold(rel_path, kind, target=target))
    return rows


def finalize_rows(rows, *, do_apply):
    """Stamp the FINAL disposition per run mode (mutates a copy of each row).

    In dry-run, an applicable row's planned ADDED/CHANGED becomes
    LEFT-UNTOUCHED (it WOULD change, but is left untouched this run). ESCALATED
    rows are unaffected. Returns a new list; never writes.
    """
    out = []
    for r in rows:
        r = dict(r)
        if r["applicable"] and not do_apply:
            r["disposition"] = "LEFT-UNTOUCHED"
            r["action"] = "would " + r["action"] + " (dry-run)"
        out.append(r)
    return out


def render_table(rows):
    """Render the ADDED|CHANGED|LEFT-UNTOUCHED|ESCALATED markdown table."""
    header = "| Finding | rule-id | Disposition | Action | Rationale |"
    sep = "|---|---|---|---|---|"
    lines = [header, sep]
    for r in rows:
        finding = (r["finding"] or "").replace("|", "\\|")
        action = (r["action"] or "").replace("|", "\\|")
        rationale = (r["rationale"] or "").replace("|", "\\|")
        lines.append("| %s | %s | %s | %s | %s |" % (
            finding, r["rule"], r["disposition"], action, rationale))
    return "\n".join(lines)


# ==========================================================================
# CLI — the only place that loads real assets + performs the gated apply.
# ==========================================================================
def _parse_scaffolds(specs):
    """Parse `--scaffold REL=kind` specs into (rel_path, kind) tuples."""
    out = []
    for spec in specs or []:
        if "=" not in spec:
            continue
        rel, kind = spec.split("=", 1)
        out.append((rel.strip(), kind.strip()))
    return out


def _parse_link_mappings(specs):
    """Parse repeatable ``--link-map OLD=NEW`` specs, rejecting ambiguity."""
    out = {}
    for spec in specs or []:
        if "=" not in spec:
            raise ValueError("link mapping must be OLD=NEW")
        old, new = (part.strip() for part in spec.split("=", 1))
        if not old or not new or old in out:
            raise ValueError("link mapping must be unique non-empty OLD=NEW")
        out[old] = new
    return out


def _main(argv=None):
    parser = argparse.ArgumentParser(
        description="doc-steward ENFORCE writer — dry-run by default, "
                    "branch+plan-gated --apply")
    parser.add_argument("--target", default=".",
                        help="target repo/dir to enforce (default: cwd)")
    parser.add_argument("--plan", help="EVALUATE plan file (CP04 doc_lint JSON)")
    parser.add_argument("--apply", action="store_true",
                        help="actually write (refused unless gates pass)")
    parser.add_argument("--repo-version",
                        help="the repo's known version (for FRONT-04 insertion)")
    parser.add_argument("--scaffold", action="append", default=[],
                        metavar="REL=kind",
                        help="scaffold an ABSENT file, e.g. AGENTS.md=agents")
    parser.add_argument("--link-map", action="append", default=[],
                        metavar="OLD=NEW",
                        help="explicit LINK-01 mapping from the exact dead "
                             "target to an in-repository replacement")
    parser.add_argument("--json", action="store_true",
                        help="emit the disposition rows as JSON")
    args = parser.parse_args(argv)

    target = doc_lint.canonical_target(args.target)
    plan = load_plan(args.plan)
    scaffolds = _parse_scaffolds(args.scaffold)
    try:
        link_mappings = _parse_link_mappings(args.link_map)
    except ValueError as exc:
        link_mappings = {}
        mapping_refusal = str(exc)
    else:
        mapping_refusal = None
    # ---- Gate: --apply requires a valid plan, feature branch, and clean tree. ----
    do_apply = args.apply
    refusal = None
    if args.apply:
        if mapping_refusal:
            refusal = "--apply refused: %s" % mapping_refusal
        elif plan is None:
            refusal = ("--apply refused: no complete versioned EVALUATE plan "
                       "(doc_lint JSON) supplied via --plan")
        else:
            plan_error = plan_authenticity_error(plan, target)
            if plan_error:
                refusal = ("--apply refused: EVALUATE plan is invalid or does "
                           "not match the target's current state (%s)" %
                           plan_error)
            branch = current_branch(target)
            protected = protected_branches(target)
            if not refusal and not is_feature_branch(branch, protected):
                refusal = ("--apply refused: target branch %r is not a writable "
                           "feature branch (protected/default/detached; "
                           "protected=%s)" %
                           (branch, ",".join(sorted(protected))))
            elif not refusal and not worktree_is_clean(target):
                refusal = ("--apply refused: target worktree is not clean "
                           "(commit, stash, or remove tracked/untracked changes)")
        if refusal:
            do_apply = False  # hard stop: classify/report only, write nothing

    # ---- Build the dispositions (pure). Findings come from the plan if any. ----
    findings = plan["findings"] if plan else []
    rows = plan_dispositions(findings, scaffolds, rules.RULES, target=target,
                             repo_version=args.repo_version,
                             link_mappings=link_mappings)

    # ---- Containment: an attempted out-of-target write is a tampered plan -> a
    # hard refusal (non-zero exit), not a silent skip. ENFORCE is all-or-nothing
    # at the pre-write boundary: one refused row aborts the entire write set. ----
    if args.apply and any(r.get("escape_attempted") for r in rows) and not refusal:
        refusal = ("--apply refused: a planned write escapes --target "
                   "(path traversal) — see ESCALATED row(s); the entire apply "
                   "is aborted and no planned row is written")

    # Central fail-closed gate. Every refusal known before the write loop must
    # turn apply off, including refusals discovered while classifying rows.
    if refusal:
        do_apply = False

    # ---- Apply only when the gate passed.  Prepare every mutation first, then
    # atomically commit one file at a time.  A late failure rolls back every
    # completed path and emits a verification receipt; nothing is swallowed. ----
    applied_any = False
    rollback = None
    mutation_failure = None
    failure_row_index = None
    if do_apply:
        try:
            with open(_templates_path(), encoding="utf-8") as fh:
                templates_text = fh.read()
        except OSError:
            templates_text = ""

        prepared = []
        seen_paths = set()
        try:
            for index, row in enumerate(rows):
                if not row["applicable"]:
                    continue
                failure_row_index = index
                mutation = _prepare_mutation(
                    row, templates_text=templates_text, target=target)
                canonical_path = os.path.realpath(mutation["path"])
                if canonical_path in seen_paths:
                    raise MutationError(
                        "multiple planned mutations target the same file")
                seen_paths.add(canonical_path)
                prepared.append((index, mutation))
        except Exception as exc:  # noqa: BLE001 — fail closed before writes
            refusal = ("--apply refused: mutation preparation failed; no file "
                       "was written (error type: %s)" % type(exc).__name__)
            mutation_failure = {
                "phase": "prepare",
                "error_type": type(exc).__name__,
                "failed_row": failure_row_index,
            }
            do_apply = False

        # Close the initial validation -> preparation TOCTOU window. A target
        # change that lands after the first authenticity/cleanliness gate but
        # before commit must invalidate the plan; prepared preimages alone do
        # not prove they came from the approved EVALUATE snapshot.
        if do_apply:
            post_prepare_error = plan_authenticity_error(plan, target)
            if post_prepare_error or not worktree_is_clean(target):
                refusal = (
                    "--apply refused: target changed during mutation "
                    "preparation; no file was written (%s)" %
                    (post_prepare_error or "worktree became dirty")
                )
                mutation_failure = {
                    "phase": "precommit-revalidation",
                    "error_type": "TargetChanged",
                    "failed_row": None,
                }
                failure_row_index = None
                do_apply = False

        completed = []
        if do_apply:
            for index, mutation in prepared:
                try:
                    failure_row_index = index
                    completed.append(_commit_mutation(mutation, target=target))
                except Exception as exc:  # noqa: BLE001 — rollback + report
                    rollback = _rollback_mutations(completed, target=target)
                    cleanup_errors = _cleanup_failed_mutation_dirs(
                        mutation, target=target)
                    if cleanup_errors:
                        rollback["errors"].extend(cleanup_errors)
                        rollback["verified"] = False
                        rollback["restored"] = None
                    mutation_failure = {
                        "phase": "commit",
                        "error_type": type(exc).__name__,
                        "failed_row": index,
                    }
                    refusal = (
                        "--apply failed during an atomic file replacement; "
                        "completed paths were rolled back (verified=%s, "
                        "error type: %s)" % (
                            str(rollback["verified"]).lower(),
                            type(exc).__name__,
                        )
                    )
                    do_apply = False
                    # If verification failed, conservatively report that a
                    # mutation may remain; callers must inspect/restore.
                    applied_any = bool(completed) and not rollback["verified"]
                    break
            else:
                applied_any = bool(completed)

    final_rows = finalize_rows(rows, do_apply=do_apply)

    # Make the complete disposition table truthful after an aborted apply.
    if mutation_failure is not None and failure_row_index is not None:
        rollback_verified = bool(rollback and rollback.get("verified"))
        for index, row in enumerate(final_rows):
            if not rows[index].get("applicable"):
                continue
            if index < failure_row_index and mutation_failure["phase"] == "commit":
                row["disposition"] = (
                    "LEFT-UNTOUCHED" if rollback_verified else "ESCALATED")
                row["action"] = (
                    "rolled back after later write failure" if rollback_verified
                    else "inspect and restore; rollback was not verified")
                row["rationale"] = (
                    "atomic preimage restoration verified byte-identical"
                    if rollback_verified else
                    "automatic rollback verification failed")
            elif index == failure_row_index:
                row["disposition"] = "ESCALATED"
                row["action"] = "write failed; apply aborted"
                row["rationale"] = (
                    "%s failure (%s); no later row attempted" % (
                        mutation_failure["phase"],
                        mutation_failure["error_type"],
                    )
                )
            else:
                row["disposition"] = "LEFT-UNTOUCHED"
                row["action"] = "not attempted after earlier failure"
                row["rationale"] = "all-or-nothing apply stopped at failed row"

    if args.json:
        print(json.dumps({
            "applied": applied_any,
            "refused": refusal,
            "mutation_failure": mutation_failure,
            "rollback": rollback,
            "target_branch": current_branch(target),
            "rows": final_rows,
        }, indent=2, sort_keys=True))
    else:
        if refusal:
            print("REFUSED: " + refusal)
        mode = ("REFUSED" if refusal else
                ("APPLY" if applied_any else
                 ("DRY-RUN" if not do_apply else "APPLY (no-op)")))
        print("DOC-STEWARD ENFORCE — target=%s mode=%s" % (target, mode))
        if rollback is not None:
            print("ROLLBACK: attempted=%s restored=%s verified=%s errors=%s" % (
                rollback["attempted"], rollback["restored"],
                str(rollback["verified"]).lower(),
                ",".join(rollback["errors"]) or "none"))
        print(render_table(final_rows))

    # Exit code: a refused --apply is non-zero; otherwise success.
    return 1 if refusal else 0


if __name__ == "__main__":
    sys.exit(_main())
