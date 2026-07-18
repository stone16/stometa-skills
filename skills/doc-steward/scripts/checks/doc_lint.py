#!/usr/bin/env python3
"""doc_lint — top-level READ-ONLY doc-steward runner (design §4.3 line 91).

Globs the doc taxonomy (CLAUDE.md / AGENTS.md / SKILL.md / `.claude/rules` /
`docs/decisions` / DESIGN.md) — or a single `--target <dir>` — classifies the
repo tier via `tier_assess`, dispatches the DETERMINISTIC checkers
(`presence_check`, `frontmatter_check`, `link_check`; rules whose
`check == "deterministic"`),
and aggregates their findings into one scored report via `score.py`:

    {"schema_version": "doc-steward.evaluate.v1",
     "canonical_target": str, "git_revision": str|null,
     "content_digest": "sha256:<hex>",
     "passed": bool, "tier": str, "composite": 0-10 float,
     "grade": str, "findings": [...], "skipped": [...],
     "scope": "deterministic", "target_profile": str,
     "structure_scope": "required-document-presence",
     "dimensions": {dimension: 0-10 float},
     "severity_counts": {"P0": int, "P1": int, "P2": int}}

This runner is STRUCTURALLY read-only by default. An append-only run-log is
written only when the caller explicitly opts in with ``--history``. It NEVER
edits or creates an audited doc. Inspector/manual rules are NOT run here; deep
inspection is an explicitly requested agent/checklist step whose judgment
findings belong in an unscored appendix.

FAILURE-MODE GUARD (load-bearing): each deterministic checker dispatch is
wrapped in try/except. A checker that is unavailable OR raises is recorded in
`skipped` (with a reason string) and DROPPED from the tier's required
dimensions, so `score.py` redistributes its weight across the survivors — the
run always emits a valid report and never crashes mid-run.

Design seam (`score.py`): score()'s real signature is
`score(findings, required_dims, weights=None)` — it does NOT take a tier. So
this runner maps tier -> required dimensions itself (`tier_required_dims`)
before calling score(). The scored dimensions are exactly the ones doc_lint can
compute deterministically — required-document `structure`, `frontmatter`, and
`links`; semantic structure plus the inspector/manual dimensions
(staleness/taxonomy/verification/decisions) are out of scope for deterministic
lint. Every emitted
deterministic finding is enriched from the injected canonical catalog with
severity, confidence=10, and a copy-pasteable remedy.

Pure/DI core: `run()` takes doc paths, the rule list, the tier, and the checker
DISPATCH TABLE as ARGUMENTS — only the CLI (`_main`) loads real assets and the
real dispatch. Stdlib-only.
"""
import argparse
import hashlib
import json
import os
import stat
import sys

# --------------------------------------------------------------------------
# Cross-dir imports: sibling checkers (this dir) + lib/ (../lib).
# --------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "..", "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import frontmatter_check  # noqa: E402
import link_check  # noqa: E402
import presence_check  # noqa: E402
import score as _score  # noqa: E402
import tier_assess  # noqa: E402

# Persisted EVALUATE artifact contract. ENFORCE accepts only this exact schema
# version and re-runs EVALUATE against the bound target before any mutation.
REPORT_SCHEMA_VERSION = "doc-steward.evaluate.v1"

# A content binding should cover authored repository inputs without hashing
# dependency/build trees that the audit itself deliberately ignores.
_BINDING_EXCLUDED_DIRS = frozenset({
    ".git", ".doc-steward", ".venv", "venv", ".tox", ".mypy_cache",
    ".pytest_cache", ".hypothesis", ".cache", "__pycache__",
    "node_modules", "dist", "build", "vendor",
})

# Map a deterministic rule's `checker` name -> the scored dimension it feeds.
# Only these checkers contribute deterministic scores.
_CHECKER_DIMENSION = {
    "presence_check": "structure",
    "frontmatter_check": "frontmatter",
    "link_check": "links",
}

# Severity ordering for the --fail-on gate (P0 is the most severe).
_SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2}

# Doc taxonomy the runner audits (design §4.3). Filenames matched anywhere in
# the tree; the two directory roots are matched by their path segment.
_DOC_FILENAMES = ("CLAUDE.md", "AGENTS.md", "SKILL.md", "DESIGN.md")
_DOC_DIRS = (os.path.join(".claude", "rules"), os.path.join("docs", "decisions"))
# Pruned at any depth DURING the walk (mirrors tier_assess._EXCLUDED_DIRS, plus
# test-fixture/test dirs). The fixture dirs carry INTENTIONAL-defect docs that
# exist only to feed the checkers' own tests — auditing them would make every
# repo that ships doc-steward fail its own lint (the CP07 dogfood). This prunes
# subdirs encountered during traversal; it does NOT reject an explicit --target
# that IS a fixture dir, so doc_lint --target fixtures/sample-repo still lints it.
_EXCLUDED_DIRS = frozenset({
    ".git", "node_modules", "dist", "build", "vendor",
    "fixtures", "test", "tests", "__tests__",
})


# --------------------------------------------------------------------------
# Versioned target binding for persisted EVALUATE reports.
# --------------------------------------------------------------------------
def canonical_target(target):
    """Return the canonical absolute target used by EVALUATE and ENFORCE."""
    return os.path.realpath(os.path.abspath(target))


def git_revision(target):
    """Return the target's exact HEAD revision, or None outside Git.

    ``None`` is the deterministic non-Git sentinel. The content digest still
    binds non-Git reports, although ENFORCE's branch gate refuses mutation
    outside a checked-out Git feature branch.
    """
    try:
        import gitio
        value = gitio.read_only_git(
            ["rev-parse", "--verify", "HEAD"], cwd=target).strip()
    except Exception:  # noqa: BLE001 — non-Git/unborn repo => sentinel
        return None
    return value or None


def target_content_digest(target):
    """Return a deterministic SHA-256 binding for current target content.

    The digest includes sorted repository-relative paths plus file bytes for
    every non-excluded regular file. Symlinks are hashed as links (path and
    link target) and never followed outside the repository. This makes a stale
    or other-target EVALUATE artifact detectable even outside Git.
    """
    root = canonical_target(target)
    digest = hashlib.sha256()
    digest.update(b"doc-steward-target-content-v1\0")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames if d not in _BINDING_EXCLUDED_DIRS)
        rel_dir = os.path.relpath(dirpath, root)

        # os.walk does not descend through directory symlinks when
        # followlinks=False, so record their identity explicitly.
        for dirname in dirnames:
            path = os.path.join(dirpath, dirname)
            if not os.path.islink(path):
                continue
            rel = os.path.normpath(os.path.join(rel_dir, dirname))
            try:
                link_target = os.readlink(path)
            except OSError:
                link_target = "<unreadable>"
            digest.update(b"L\0" + rel.encode("utf-8", "surrogateescape")
                          + b"\0" + link_target.encode(
                              "utf-8", "surrogateescape") + b"\0")

        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            rel = os.path.normpath(os.path.join(rel_dir, filename))
            rel_bytes = rel.encode("utf-8", "surrogateescape")
            try:
                mode = os.lstat(path).st_mode
                if stat.S_ISLNK(mode):
                    link_target = os.readlink(path)
                    digest.update(
                        b"L\0" + rel_bytes + b"\0" + link_target.encode(
                            "utf-8", "surrogateescape") + b"\0")
                    continue
                if not stat.S_ISREG(mode):
                    digest.update(b"S\0" + rel_bytes + b"\0")
                    continue
                digest.update(b"F\0" + rel_bytes + b"\0")
                with open(path, "rb") as fh:
                    while True:
                        chunk = fh.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                digest.update(b"\0")
            except OSError:
                # A concurrent disappearance/read failure changes the binding
                # deterministically into a fail-closed unreadable marker.
                digest.update(b"E\0" + rel_bytes + b"\0")
    return "sha256:" + digest.hexdigest()


def target_binding(target):
    """Return the persisted identity/current-content fields for a target."""
    root = canonical_target(target)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "canonical_target": root,
        "git_revision": git_revision(root),
        "content_digest": target_content_digest(root),
    }


# --------------------------------------------------------------------------
# Taxonomy globbing.
# --------------------------------------------------------------------------
def glob_taxonomy(target):
    """Return the sorted list of doc-taxonomy markdown files under `target`.

    Matches the known doc filenames anywhere in the tree, plus every `.md`
    under a `.claude/rules` or `docs/decisions` directory. Excluded dirs
    (`.git`, `node_modules`, build outputs, vendor) are pruned at any depth.
    """
    found = set()
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        rel = os.path.relpath(dirpath, target)
        in_doc_dir = any(rel == d or rel.endswith(os.sep + d) for d in _DOC_DIRS)
        for name in filenames:
            if name in _DOC_FILENAMES or (in_doc_dir and name.endswith(".md")):
                found.add(os.path.join(dirpath, name))
    return sorted(found)


# --------------------------------------------------------------------------
# tier -> required scored dimensions.
# --------------------------------------------------------------------------
_TIER_ORDER = {"Simple": 0, "Standard": 1, "Complex": 2}


def scored_dimensions(rules):
    """The dimensions doc_lint can score deterministically, derived from rules.

    A dimension is scorable iff at least one rule with `check == "deterministic"`
    maps to it (via `_CHECKER_DIMENSION`). Data-driven so the runner tracks the
    catalog (dogfoods STRUCT-02 single-source) rather than hard-coding a list.
    """
    dims = set()
    for r in rules:
        if r.get("check") == "deterministic":
            dim = _CHECKER_DIMENSION.get(r.get("checker"))
            if dim:
                dims.add(dim)
    return sorted(dims)


def tier_required_dims(tier, rules, scored_dims):
    """Map a detected tier -> the scored dimensions REQUIRED at that tier.

    A scored dimension is required at `tier` iff at least one deterministic rule
    feeding that dimension has `min_tier <= tier` (i.e. it is in force at the
    detected tier). This is the tier->required_dims mapping score.py expects but
    does not perform itself. Falls back to all scored dims if the derivation is
    empty (score() requires a non-empty required set).
    """
    cutoff = _TIER_ORDER.get(tier, 0)
    required = set()
    for r in rules:
        if r.get("check") != "deterministic":
            continue
        dim = _CHECKER_DIMENSION.get(r.get("checker"))
        if dim not in scored_dims:
            continue
        if _TIER_ORDER.get(r.get("min_tier"), 99) <= cutoff:
            required.add(dim)
    out = [d for d in scored_dims if d in required]
    return out or list(scored_dims)


# --------------------------------------------------------------------------
# Per-dimension scoring + the checker dispatch table.
# --------------------------------------------------------------------------
def dimension_score(n_findings, *, dimension=None):
    """Map a dimension's deterministic finding count -> a 0-10 dim score.

    Clean (0 findings) = 10. Required-document absence is the rubric's explicit
    structure=4 anchor; other deterministic dimensions subtract 3 per finding,
    floored at 0. Deterministic and monotonic run-to-run.
    """
    if dimension == "structure" and n_findings:
        return 4.0
    return float(max(0, 10 - 3 * n_findings))


def _frontmatter_dispatch(doc_paths, rules):
    """Run frontmatter_check across the corpus (FRONT-03 cross-doc aware)."""
    # Build the (doc_id, description) corpus so FRONT-03 can compare triggers,
    # mirroring frontmatter_check._main's own corpus construction.
    corpus = []
    for p in doc_paths:
        try:
            with open(p, encoding="utf-8") as fh:
                fields, _ = frontmatter_check._parse_frontmatter(fh.read())
            corpus.append((p, fields.get("description", "")))
        except OSError:
            corpus.append((p, ""))
    findings = []
    for p in doc_paths:
        try:
            with open(p, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        others = [(oid, od) for (oid, od) in corpus if oid != p]
        findings.extend(
            frontmatter_check.check(text, rules, file=p, doc_id=p,
                                    others=others))
    return findings


def _link_dispatch(doc_paths, rules, audit_root=None):
    """Run link_check across the whole audited doc set at once."""
    return link_check.check(list(doc_paths), rules, audit_root=audit_root)


def _presence_dispatch(target_root, tier):
    """Bind target/tier to the STRUCT-06 checker dispatch signature."""
    def dispatch(doc_paths, rules):
        return presence_check.check(target_root, rules, tier=tier)
    return dispatch


def default_dispatch(*, target_root=None, tier=None):
    """The real deterministic dispatch table: dimension -> checker callable.

    Each callable has signature (doc_paths, rules) -> [finding dict]. Returned
    fresh so callers (and the failure-mode tests) can mutate a copy safely.
    """
    dispatch = {"frontmatter": _frontmatter_dispatch}
    if target_root is None:
        dispatch["links"] = _link_dispatch
    else:
        def link_dispatch(doc_paths, rules):
            return _link_dispatch(doc_paths, rules, audit_root=target_root)
        dispatch["links"] = link_dispatch
    if target_root is not None:
        if tier is None:
            raise ValueError("tier is required when target_root is supplied")
        dispatch["structure"] = _presence_dispatch(target_root, tier)
    return dispatch


# --------------------------------------------------------------------------
# Core aggregation (pure / DI).
# --------------------------------------------------------------------------
def run(doc_paths, rules, *, tier, dispatch, weights=None, target_root=None):
    """Aggregate the deterministic checkers into one scored report (pure/DI).

    Args:
      doc_paths : the injected set of doc files to audit.
      rules     : the canonical rule list (lib/rules.py RULES).
      tier      : the detected tier ("Simple"|"Standard"|"Complex").
      dispatch  : {dimension -> callable(doc_paths, rules) -> [finding]}.
                  A callable that raises is the FAILURE-MODE GUARD path.
      weights   : optional base weight table for score.py (defaults to its
                  DEFAULT_WEIGHTS).
      target_root: optional audited root, used only to report its target profile.

    Returns the report dict. Existing compatibility keys are retained and the
    deterministic-report contract adds `scope`, per-dimension scores, and
    P0/P1/P2 `severity_counts`.
    """
    scored_dims = scored_dimensions(rules)
    findings = []
    skipped = []
    dim_scores = {}
    survived = []  # dims whose checker ran without raising

    for dim, checker in dispatch.items():
        if checker is None:
            skipped.append({"dimension": dim, "reason": "checker unavailable"})
            continue
        try:
            dim_findings = _enrich_findings(checker(doc_paths, rules), rules)
        except Exception as exc:  # noqa: BLE001 — guard: never crash mid-run
            skipped.append({"dimension": dim,
                            "reason": f"{type(exc).__name__}: {exc}"})
            continue
        findings.extend(dim_findings)
        dim_scores[dim] = dimension_score(len(dim_findings), dimension=dim)
        survived.append(dim)

    # A repository with no resident root charter has no meaningful structure,
    # frontmatter, or routing surface. Do not let empty input masquerade as a
    # perfect audit merely because the per-document checkers found nothing.
    if any(f.get("rule") == "STRUCT-06"
           and f.get("root_charter_present") is False for f in findings):
        for dim in ("structure", "frontmatter", "links"):
            if dim in dim_scores:
                dim_scores[dim] = 0.0

    # Required dims for the tier, restricted to the ones that actually ran. A
    # required-but-crashed dim drops out here, so score.py redistributes its
    # weight onto the survivors (it never drags the composite down).
    required = [d for d in tier_required_dims(tier, rules, scored_dims)
                if d in survived]

    if not required:
        # Every required/scored dimension was skipped (or none required ran):
        # there is nothing to score against — composite floors at 0 / FAIL.
        composite, grade = 0.0, _score.verdict_for(0.0)
    else:
        composite, grade = _score.score(dim_scores, required, weights)

    findings = _sort_findings(findings)
    severity_counts = {
        severity: sum(1 for finding in findings
                      if finding.get("severity") == severity)
        for severity in ("P0", "P1", "P2")
    }
    passed = grade == "PASS" and not skipped
    return {
        # The pure core identifies the report contract but cannot bind a real
        # filesystem target. lint() overwrites the three None sentinels below
        # with target_binding() at the side-effecting boundary.
        "schema_version": REPORT_SCHEMA_VERSION,
        "canonical_target": None,
        "git_revision": None,
        "content_digest": None,
        "passed": passed,
        "tier": tier,
        "composite": composite,
        "grade": grade,
        "findings": findings,
        "skipped": skipped,
        "scope": "deterministic",
        "target_profile": (presence_check.target_profile(target_root)
                           if target_root is not None else "unspecified"),
        "structure_scope": "required-document-presence",
        "dimensions": {dim: dim_scores[dim] for dim in scored_dims
                       if dim in dim_scores},
        "severity_counts": severity_counts,
    }


def _enrich_findings(findings, rules):
    """Copy checker findings and attach canonical deterministic report data.

    Rule severity and remedy come only from the injected catalog. Missing or
    incomplete metadata raises inside the caller's failure-mode guard, causing
    that checker dimension to be reported as skipped instead of emitting a
    partial, non-actionable finding.
    """
    catalog = {rule["id"]: rule for rule in rules}
    enriched = []
    for finding in findings:
        rule_id = finding.get("rule", "")
        rule = catalog.get(rule_id)
        if rule is None:
            raise KeyError(f"checker emitted unknown rule {rule_id!r}")
        remedy = str(rule.get("remedy", "")).strip()
        if not remedy:
            raise ValueError(f"deterministic rule {rule_id} has no remedy")
        item = dict(finding)
        item["severity"] = rule["severity"]
        item["confidence"] = 10
        item["remedy"] = remedy
        enriched.append(item)
    return enriched


def _sort_findings(findings):
    """Stable severity-then-rule-then-location ordering for a deterministic report."""
    def key(f):
        return (
            _SEVERITY_RANK.get(f.get("severity"),
                               _rule_severity(f.get("rule", ""))),
            f.get("rule", ""),
            f.get("file", ""),
            f.get("line", 0),
        )
    return sorted(findings, key=key)


_RULE_SEVERITY_CACHE = {}


def _rule_severity(rule_id):
    """Best-effort severity rank for a rule id (defaults to least-severe)."""
    if rule_id not in _RULE_SEVERITY_CACHE:
        try:
            import rules as _rules
            sev = _rules.get_rule(rule_id).get("severity", "P2")
        except Exception:  # noqa: BLE001
            sev = "P2"
        _RULE_SEVERITY_CACHE[rule_id] = _SEVERITY_RANK.get(sev, 9)
    return _RULE_SEVERITY_CACHE[rule_id]


def _apply_rule_toggles(rules, rule_toggles):
    """Return `rules` with any overlay-disabled rule ids removed (pure).

    `rule_toggles` maps rule id -> a value; a falsy value or the strings
    "off"/"false"/"no"/"disable"/"disabled" turns the rule OFF for this repo. An
    empty/None toggle map returns the rules unchanged.
    """
    if not rule_toggles:
        return rules
    off = set()
    for rid, val in rule_toggles.items():
        if val is False or (isinstance(val, str)
                            and val.strip().lower() in
                            ("off", "false", "no", "disable", "disabled")):
            off.add(rid)
    if not off:
        return rules
    return [r for r in rules if r.get("id") not in off]


def lint(target, rules, *, tier_override=None, overlay=None, weights=None):
    """Convenience: classify the tier for `target`, then run() over its docs.

    Loads the doc set via glob_taxonomy and the tier via tier_assess (the
    side-effecting glue). When a config dict is supplied, its `tier` feeds
    tier_assess.classify as `overlay_tier` (precedence --tier > config >
    auto-detect) and its
    `rule_toggles` disable rules for this repo. Does NOT touch history — `_main`
    owns the explicit opt-in.
    """
    target = canonical_target(target)
    overlay = overlay or {}
    rules = _apply_rule_toggles(rules, overlay.get("rule_toggles"))
    signals = tier_assess.gather_signals(target)
    tier = tier_assess.classify(signals, tier_override=tier_override,
                                overlay_tier=overlay.get("tier"))
    doc_paths = glob_taxonomy(target)
    report = run(doc_paths, rules, tier=tier,
                 dispatch=default_dispatch(target_root=target, tier=tier),
                 weights=weights, target_root=target)
    report.update(target_binding(target))
    return report


# --------------------------------------------------------------------------
# CLI — the ONLY place that loads real assets + the optional history self-write.
# --------------------------------------------------------------------------
def _load_rules():
    import rules  # noqa: E402  (resolved via the sys.path shim above)
    return rules.RULES


def _resolve_config(config_path):
    """Resolve explicit config (safe defaults when omitted) via apply/overlay.py.

    The overlay resolver lives in scripts/apply/; importing it here (the CLI
    boundary) keeps the pure run()/lint() core overlay-agnostic except for the
    plain dict it receives. Returns the resolved config dict.
    """
    apply_dir = os.path.join(_HERE, "..", "apply")
    if apply_dir not in sys.path:
        sys.path.insert(0, apply_dir)
    import overlay as _overlay  # noqa: E402
    return _overlay.resolve_config(config_path)


def _fail_on_triggered(findings, threshold):
    """True iff any finding is at/above `threshold` severity (P0 most severe)."""
    limit = _SEVERITY_RANK[threshold]
    for f in findings:
        rank = _SEVERITY_RANK.get(
            f.get("severity"), _rule_severity(f.get("rule", "")))
        if rank <= limit:
            return True
    return False


def _format_text(report):
    dimensions = ",".join(
        f"{name}={value:.2f}"
        for name, value in report.get("dimensions", {}).items()) or "none"
    lines = [f"DOC-STEWARD LINT — scope={report.get('scope', 'deterministic')} "
             f"profile={report.get('target_profile', 'unspecified')} "
             f"structure-scope={report.get('structure_scope', 'unspecified')} "
             f"dimensions={dimensions} tier={report['tier']} "
             f"composite={report['composite']:.2f} grade={report['grade']}"]
    counts = report.get("severity_counts", {})
    lines.append("COUNTS — " + " ".join(
        f"{severity}={counts.get(severity, 0)}"
        for severity in ("P0", "P1", "P2")))
    for f in report["findings"]:
        lines.append(f"[{f.get('severity')}] "
                     f"(confidence: {f.get('confidence')}/10) "
                     f"{f['rule']} {f.get('file')}:{f.get('line')} — "
                     f"{f.get('message')} → {f.get('remedy')}")
    for s in report["skipped"]:
        lines.append(f"[SKIPPED] {s['dimension']}: {s['reason']}")
    if "history" in report:
        history = report["history"]
        detail = f": {history['reason']}" if history.get("reason") else ""
        lines.append(f"[HISTORY] {history['status']}{detail}")
    if report.get("history", {}).get("status") == "refused":
        lines.append("NOT-PASS (requested history write refused)")
    else:
        lines.append("PASS" if report["passed"]
                     else f"NOT-PASS ({len(report['findings'])} finding(s), "
                          f"{len(report['skipped'])} skipped)")
    return "\n".join(lines)


def _main(argv=None):
    parser = argparse.ArgumentParser(
        description="doc-steward read-only deterministic doc linter")
    parser.add_argument("--target", default=".",
                        help="repo/dir root to audit (default: cwd)")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    parser.add_argument("--fail-on", choices=["P0", "P1", "P2"],
                        help="exit non-zero when a finding at/above this "
                             "severity exists")
    parser.add_argument("--tier", choices=["Simple", "Standard", "Complex"],
                        help="force the tier (highest precedence)")
    parser.add_argument("--config", default=None,
                        help="optional YAML config path; supplies tier/profile/"
                             "rule_toggles (precedence --tier > config > "
                             "auto-detect)")
    parser.add_argument("--history", action="store_true",
                        help="opt in to appending .doc-steward/history.jsonl")
    args = parser.parse_args(argv)

    rules = _load_rules()
    overlay = _resolve_config(args.config)
    report = lint(args.target, rules, tier_override=args.tier, overlay=overlay)

    # History is an explicit opt-in; the default audit has no writes.
    history_refused = False
    if args.history:
        try:
            import history
            history.append_record(
                args.target,
                {"score": report["composite"],
                 "p0": report["severity_counts"]["P0"]},
                write=True)
            report["history"] = {
                "status": "appended",
                "path": ".doc-steward/history.jsonl",
            }
        except Exception as exc:  # noqa: BLE001 — report refusal, never hide it
            history_refused = True
            report["history"] = {
                "status": "refused",
                "reason": f"{type(exc).__name__}: {exc}",
            }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_format_text(report))

    # An explicitly requested history operation that was refused is always a
    # visible non-zero result, even when --fail-on would otherwise pass.
    if history_refused:
        return 2

    # Exit code: --fail-on gates on severity; otherwise non-zero iff not passed.
    if args.fail_on:
        return 1 if _fail_on_triggered(report["findings"], args.fail_on) else 0
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(_main())
