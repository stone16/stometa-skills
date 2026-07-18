#!/usr/bin/env python3
"""learn_capture — doc-steward's LEARN writer (design §4.5 / references/learning-sink.md).

The CAPTURE+DISTILL half of the learning loop. It is **explicit-trigger only** (it
never fires on an EVALUATE run) and writes exactly ONE distilled finding to a
**pluggable sink**. The corresponding rules are LEARN-01..02 in `scripts/lib/rules.py`.

Design seam (DI): the core `capture(finding, sink)` is PURE — the sink is injected
as an argument and `capture` never imports a sink module. Only `__main__`/the CLI
loads only the safe `noop` sink unless the user explicitly passes a local sink
module. This keeps `capture` sink-agnostic and reusable by private profiles.

What `capture` does, per the spec:
  1. Runs the finding through the 6-field candidate matrix (LEARN-01 intake gate):
     repeated? invariant? layer/altitude? verifier? redaction-risk? provenance?
  2. STRIPS PROVENANCE (LEARN-02): removes incident-specific absolute paths AND
     line numbers, so the lesson earns residency by what it PREVENTS, not its
     origin (this is also the cross-project-contamination guard).
  3. Picks the DOC-* namespace tag from the finding's category
     (DOC-IMPL-DRIFT / DOC-VERIFY-GAP / DOC-CONTRACT-MISSING).
  4. Writes the distilled record via the injected sink (`sink.write(record)`).

Stdlib-only.
"""
import argparse
import json
import os
import re
import sys

# lib/ (../lib) holds the canonical rule catalog — used to derive a finding's
# severity/category when it arrives in doc_lint's shape (which carries neither).
_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.join(_HERE, "..", "lib") not in sys.path:
    sys.path.insert(0, os.path.join(_HERE, "..", "lib"))

# Category -> DOC-* namespace tag (references/learning-sink.md §4).
#   DOC-IMPL-DRIFT      docs vs code drift
#   DOC-VERIFY-GAP      ungrounded / unverified claim
#   DOC-CONTRACT-MISSING a required charter element absent
_TAG_BY_CATEGORY = {
    "impl-drift": "DOC-IMPL-DRIFT",
    "verify-gap": "DOC-VERIFY-GAP",
    "contract-missing": "DOC-CONTRACT-MISSING",
}
_DEFAULT_TAG = "DOC-IMPL-DRIFT"

# A URI with an explicit RFC-style ``scheme:`` prefix embedded anywhere —
# redacted whole (scheme, authority, opaque part, and path can all carry
# provenance). This covers hierarchical and opaque forms: ``https://``,
# ``file:/``, ``mailto:``, ``urn:``, and ``ssh:user@host/path``. Match it before
# path/email/date scrubbers so punctuation cannot become a surviving fragment.
_URI = re.compile(
    r"\b[A-Za-z][A-Za-z0-9+.-]{0,31}:[^\s)>\]\"',;]+",
    re.IGNORECASE,
)

# An email address (PII), including local/private domains without a public TLD.
# Redacted whole; no local-domain fragment may survive.
_EMAIL = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?")

# Absolute filesystem paths. These deliberately include single-segment POSIX and
# drive-rooted paths; a short path can be just as identifying as a long one.
_POSIX_PATH = re.compile(
    r"(?<![\w:/])/(?:[^\s/\\|,;:!?()\[\]{}\"'<>]+"
    r"(?:/[^\s/\\|,;:!?()\[\]{}\"'<>]+)*)")
_WINDOWS_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/])"
    r"(?:[^\s\\/:*?\"<>|]+(?:[\\/][^\s\\/:*?\"<>|]+)*)")
_UNC_PATH = re.compile(
    r"(?<!\\)\\\\[^\\\s/:*?\"<>|]+\\[^\\\s/:*?\"<>|]+"
    r"(?:\\[^\\\s/:*?\"<>|]+)*")

# A `~/...`-rooted home path (e.g. ~/dev/secret-repo) — incident-specific machine
# provenance, scrubbed like an absolute path.
_HOME_PATH = re.compile(r"~/[^\s|]+")

# ISO-style dates: YYYY-MM-DD and YYYY/MM/DD (the incident narrative's "when").
_ISO_DATE = re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b")

# Ticket/issue ids: an ABC-123 tracker key, or a #1234 issue reference.
_TICKET_KEY = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")
_TICKET_HASH = re.compile(r"#\d+\b")

# Provenance line-number forms:
#   "...file.py:42"  (a ":<number>" suffix, e.g. on a file:line citation)
#   "line 117" / "Line 42" (a bare line-number phrase)
_FILE_LINE_SUFFIX = re.compile(r":\d+\b")
_BARE_LINE = re.compile(r"\bline\s+\d+\b", re.IGNORECASE)

# The COMPLETE set of provenance patterns strip_provenance removes. This is the
# single source the candidate-matrix flagging shares with the scrubber (f13), so
# `redaction_risk`/`provenance_to_strip` can never drift from what is actually
# scrubbed: every class here is both detected (for flagging) AND stripped.
_PROVENANCE_PATTERNS = (
    _URI, _EMAIL, _WINDOWS_PATH, _UNC_PATH, _HOME_PATH, _POSIX_PATH,
    _ISO_DATE, _TICKET_KEY, _TICKET_HASH, _FILE_LINE_SUFFIX, _BARE_LINE,
)

# A residual high-risk token that, if it survives scrubbing, means the lesson is
# NOT confidently clean — used by the fail-closed check below. Narrower than the
# full set on purpose: the broad `:\d+` / `#\d+` / "line N" forms would
# false-positive on benign post-scrub text (e.g. a "50:50" ratio), so the
# fail-closed residual check uses only the high-confidence-leak classes.
_RESIDUAL_HIGH_RISK = (
    _URI, _EMAIL, _WINDOWS_PATH, _UNC_PATH, _HOME_PATH, _POSIX_PATH,
    _ISO_DATE, _TICKET_KEY,
)

# Structured catalog identifiers legitimately resemble issue keys (for example
# FRONT-01), so do not apply the ticket-id detector to those fields.  URI, PII,
# path, date, and configured-private-token checks still apply before the narrow
# identifier grammar below.
_METADATA_HIGH_RISK = (
    _URI, _EMAIL, _WINDOWS_PATH, _UNC_PATH, _HOME_PATH, _POSIX_PATH,
    _ISO_DATE,
)

# Structured sink fields are identifiers, not prose.  Scrubbing an unsafe value
# would silently change its meaning, so reject the whole capture instead.  Keep
# the grammar deliberately narrow and bounded: catalog rule ids, severities,
# and altitude/layer names all fit this portable token form.
_METADATA_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_CANONICAL_LAYERS = frozenset({"global", "repo", "subtree", "shelf"})

# Defense-in-depth scan for every string that will reach a sink. Ticket ids are
# deliberately excluded here because canonical catalog ids look like FRONT-01;
# lesson prose is already checked with the stricter residual set above.
_RECORD_HIGH_RISK = (
    _URI, _EMAIL, _WINDOWS_PATH, _UNC_PATH, _HOME_PATH, _POSIX_PATH,
    _ISO_DATE,
)


def _text_has_provenance(text, patterns, overlay=None):
    """True iff text carries a built-in or explicitly configured private token.

    Pure — the single high-risk detector both the
    candidate-matrix flagging and the fail-closed residual check delegate to."""
    for pat in patterns:
        if pat.search(text):
            return True
    config = overlay or {}
    for priv in (config.get("private_paths") or []) + (
            config.get("redaction_terms") or []):
        if priv and re.search(re.escape(str(priv)), text, flags=re.IGNORECASE):
            return True
    return False


# ==========================================================================
# DISTILL — strip-provenance (LEARN-02)
# ==========================================================================
def strip_provenance(text, overlay=None):
    """Remove incident-specific provenance from a finding message (LEARN-02).

    Strips, in order (broadest/most-specific first so fragments never survive):
      * URIs with an explicit scheme (including http(s), ssh, and file) and
        email addresses (PII),
      * POSIX (including single-segment), Windows-drive, UNC, and `~/...` paths,
      * ISO dates (YYYY-MM-DD / YYYY/MM/DD) and ticket ids (ABC-123, #1234),
      * file:line suffixes (":42") and bare line-number phrases ("line 117"),
      * explicitly configured `private_paths` and `redaction_terms`.

    Pure. Returns the distilled, behavior-focused text with whitespace collapsed.
    A rule earns residency by what it PREVENTS, not by the story of how it was
    learned — and this scrub is the cross-project-contamination guard.
    """
    out = text or ""
    # URIs + emails first — they contain "/", ":", "." that the path/date/line
    # scrubbers would otherwise chew into a surviving fragment.
    out = _URI.sub("", out)
    out = _EMAIL.sub("", out)
    # Explicitly configured private tokens, when supplied.
    out = _scrub_config_tokens(out, overlay)
    # Paths (most distinctive syntaxes first), then dates/tickets/line numbers.
    out = _WINDOWS_PATH.sub("", out)
    out = _UNC_PATH.sub("", out)
    out = _HOME_PATH.sub("", out)
    out = _POSIX_PATH.sub("", out)
    out = _ISO_DATE.sub("", out)
    out = _TICKET_KEY.sub("", out)
    out = _TICKET_HASH.sub("", out)
    out = _FILE_LINE_SUFFIX.sub("", out)
    out = _BARE_LINE.sub("", out)
    # tidy artifacts left by removals: dangling articles/preps + double spaces
    out = re.sub(r"\b(?:in|at|of|on|see|see also)\s+(?=[,.;]|$)", "", out,
                 flags=re.IGNORECASE)
    out = re.sub(r"\s+([,.;])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" ,;").strip()


def _scrub_config_tokens(text, config):
    """Redact explicitly configured paths and terms from `text`.

    Pure. When `config` is falsy or carries no tokens, returns `text` unchanged.
    Tokens are matched literally and case-insensitively.
    """
    if not config:
        return text
    out = text
    tokens = (config.get("private_paths") or []) + (
        config.get("redaction_terms") or [])
    for priv in tokens:
        if priv:
            out = re.sub(re.escape(str(priv)), "", out,
                         flags=re.IGNORECASE)
    return out


def has_residual_high_risk(text, overlay=None):
    """True iff a high-risk token survives in `text` AFTER a scrub (fail-closed).

    A lesson that still carries a path/URL/email/date/ticket/private token could
    not be confidently scrubbed; the caller marks it low-confidence (or drops it)
    rather than persist a leak. Delegates to the shared `_text_has_provenance`
    core with the conservative residual pattern set. Pure.
    """
    return _text_has_provenance(text, _RESIDUAL_HIGH_RISK, overlay=overlay)


# ==========================================================================
# NORMALIZE — one internal finding shape (accepts doc_lint's REAL shape)
# ==========================================================================
def _rule_severity(rule_id):
    """Severity for `rule_id` from the canonical catalog, or "" if unknown.

    Imported lazily so `capture` has no hard import-time dependency on the
    catalog when a finding already carries an explicit severity.
    """
    if not rule_id:
        return ""
    try:
        import rules  # noqa: WPS433 (lib/rules.py via the sys.path shim above)
        return rules.get_rule(rule_id).get("severity", "")
    except Exception:  # noqa: BLE001 — unknown id / catalog unavailable
        return ""


def normalize_finding(finding):
    """Return a single canonical internal finding shape (pure).

    doc_lint findings are {rule, file, line, message}; legacy/test findings use
    {rule_id, category, severity, description}. This accepts EITHER and resolves:
      * rule_id  <- `rule_id` else `rule`        (doc_lint's field)
      * text     <- `description` else `message` (doc_lint's field)
      * severity <- explicit `severity` else get_rule(rule_id).severity (catalog)
      * category <- explicit DOC-* `category` (kept as-is; doc_lint has none, so
                    tag_for falls back to the default DOC-* tag)
    Other fields (file/line/occurrences/volatile/layer) pass through.
    """
    f = dict(finding)
    rule_id = f.get("rule_id") or f.get("rule") or ""
    f["rule_id"] = rule_id
    f["description"] = f.get("description") or f.get("message") or ""
    if not f.get("severity"):
        f["severity"] = _rule_severity(rule_id)
    return f


# ==========================================================================
# DISTILL — the 6-field candidate matrix (LEARN-01 intake gate)
# ==========================================================================
def candidate_matrix(finding, overlay=None):
    """Answer the 6-field candidate matrix for a finding (LEARN-01).

    Pure. Each field is the intake question from references/learning-sink.md §2.
    Heuristic answers are conservative; the matrix is attached to the record so the
    downstream PROMOTE step (≥3/last-10 or critical) can reason over it. The
    redaction fields use the SAME provenance detector strip_provenance scrubs with
    (f13), so they can never under-report a class that is actually stripped.
    """
    severity = str(finding.get("severity", "")).upper()
    has_prov = _has_provenance(finding, overlay=overlay)
    return {
        # 1. Repeated? — recurrence count if known, else first sighting.
        "repeated": int(finding.get("occurrences", 1)) > 1,
        # 2. Invariant? — a stable rule, not a volatile value masquerading as one.
        "invariant": not bool(finding.get("volatile", False)),
        # 3. Layer (altitude)? — where it is universally true.
        "layer": finding.get("layer", "repo"),
        # 4. Verifier? — can a machine check it (linter/inspector/hook)?
        "verifier": bool(finding.get("rule_id")),
        # 5. Redaction-risk? — does the raw finding carry private specifics?
        "redaction_risk": has_prov,
        # 6. Provenance to strip? — incident-specific context to remove.
        "provenance_to_strip": has_prov,
        # carried so PROMOTE can apply the critical override.
        "critical": severity in ("P0", "CRITICAL"),
    }


def _has_provenance(finding, overlay=None):
    """True iff the raw finding carries strippable provenance (f13).

    Uses the COMPLETE `_PROVENANCE_PATTERNS` set (paths, line numbers, URLs,
    emails, dates, ticket ids) — the same classes strip_provenance removes — over
    the finding's text, plus configured private/redaction tokens, plus the
    structured `file`/`line` fields. Shares the `_text_has_provenance` core with
    the residual check so the candidate flags stay in sync with the scrub.
    """
    desc = str(finding.get("description", ""))
    if _text_has_provenance(desc, _PROVENANCE_PATTERNS, overlay=overlay):
        return True
    return finding.get("line") is not None or "/" in str(finding.get("file", ""))


def tag_for(finding):
    """The DOC-* namespace tag for a finding's category."""
    return _TAG_BY_CATEGORY.get(finding.get("category"), _DEFAULT_TAG)


def _unsafe_sink_metadata_field(finding, overlay=None):
    """Return the first unsafe sink-bound metadata field, else ``None``.

    ``rule_id``, ``severity``, and candidate ``layer`` originate in the input
    report and are copied to a sink record.  Unlike the lesson prose, these
    identifiers must never be rewritten by redaction.  Reject them before
    constructing a candidate record if they carry provenance, configured
    private tokens, URI/path punctuation, control characters, or unbounded
    free-form text.
    """
    if not isinstance(finding.get("description"), str):
        return "description"
    if (finding.get("category") is not None
            and not isinstance(finding.get("category"), str)):
        return "category"
    values = {
        "rule_id": finding.get("rule_id", ""),
        "severity": finding.get("severity", ""),
        "layer": finding.get("layer", "repo"),
    }
    for field, raw in values.items():
        value = str(raw or "")
        if not value:
            continue
        if _text_has_provenance(
                value, _METADATA_HIGH_RISK, overlay=overlay):
            return field
        if not _METADATA_TOKEN.fullmatch(value):
            return field
    rule_id = str(values["rule_id"] or "")
    try:
        catalog_rule = __import__("rules").get_rule(rule_id)
    except (KeyError, TypeError):
        return "rule_id"
    if str(values["severity"] or "") != catalog_rule.get("severity"):
        return "severity"
    if str(values["layer"] or "") not in _CANONICAL_LAYERS:
        return "layer"
    occurrences = finding.get("occurrences", 1)
    if (not isinstance(occurrences, int) or isinstance(occurrences, bool)
            or not 1 <= occurrences <= 1_000_000):
        return "occurrences"
    return None


def _unsafe_metadata_rejection():
    """Return a fixed, non-sensitive rejection receipt for unsafe metadata."""
    return {
        "tag": _DEFAULT_TAG,
        "candidate": {},
        "severity": "",
        "rule_id": "",
        "occurrences": 0,
        "total": 0,
        "low_confidence": True,
        "rejected": True,
        "status": "Rejected-UnsafeMetadata",
    }


def _iter_record_strings(value):
    """Yield every string nested in a sink-bound record."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _iter_record_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_record_strings(item)


def _record_has_high_risk(record, overlay=None):
    """True iff any complete-record string still carries sensitive syntax."""
    return any(_text_has_provenance(
        value, _RECORD_HIGH_RISK, overlay=overlay)
        for value in _iter_record_strings(record))


# ==========================================================================
# CAPTURE (pure / DI) — distill then write via the INJECTED sink
# ==========================================================================
def capture(finding, sink, overlay=None):
    """Distill one EVALUATE finding into a lesson and write it via `sink`.

    PURE w.r.t. the sink: the sink is injected (DI) — `capture` never imports or
    selects a sink. It NORMALIZES the finding (accepting doc_lint's real
    {rule, message} shape as well as the legacy {rule_id, description} shape),
    builds the distilled record (DOC-* tag + strip-provenance'd lesson + the
    6-field matrix), and calls `sink.write(record)` exactly once.

    FAIL-CLOSED (LEARN-02 + f7): if a high-risk token survives scrubbing, or a
    sink-bound structured field is not a safe identifier token, the record is
    rejected, contains no lesson text or attacker value, and the sink is not
    called.

    `overlay` (optional, retained as a compatibility parameter) supplies generic
    `private_paths` and `redaction_terms`. Returns the record written.
    """
    f = normalize_finding(finding)
    if _unsafe_sink_metadata_field(f, overlay=overlay):
        return _unsafe_metadata_rejection()
    lesson = strip_provenance(f["description"], overlay=overlay)
    low_confidence = has_residual_high_risk(lesson, overlay=overlay)
    record = {
        "tag": tag_for(f),
        "candidate": candidate_matrix(f, overlay=overlay),
        "severity": f.get("severity", ""),
        "rule_id": f.get("rule_id", ""),
        "occurrences": int(f.get("occurrences", 1)),
        "total": int(f.get("occurrences", 1)),
        "low_confidence": low_confidence,
        "rejected": low_confidence,
    }
    if low_confidence:
        record["status"] = "Rejected-ResidualHighRisk"
        return record
    record["lesson"] = lesson
    record["status"] = "Captured"
    if _record_has_high_risk(record, overlay=overlay):
        return _unsafe_metadata_rejection()
    sink.write(record)
    return record


# ==========================================================================
# CLI / __main__ — the ONLY place that loads a real sink (keeps capture pure)
# ==========================================================================
def _load_sink(name="noop", path=None, module_path=None):
    """Import and construct the configured real sink adapter.

    A local module is loaded only when the user explicitly supplies
    ``--sink-module``. It must expose a ``Sink`` class. No config or default path
    can cause external code loading.
    """
    if module_path:
        import importlib.util
        module_path = os.path.abspath(module_path)
        if not os.path.isfile(module_path):
            raise SystemExit(f"sink module not found: {module_path}")
        spec = importlib.util.spec_from_file_location(
            "doc_steward_explicit_sink", module_path)
        if spec is None or spec.loader is None:
            raise SystemExit(f"cannot load sink module: {module_path}")
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        sink_cls = getattr(adapter, "Sink", None)
        if sink_cls is None:
            raise SystemExit("sink module must expose a Sink class")
        return sink_cls(path=path) if path else sink_cls()
    sinks_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "sinks")
    if sinks_dir not in sys.path:
        sys.path.insert(0, sinks_dir)
    if name == "noop":
        import noop as adapter  # noqa: WPS433
        return adapter.Sink()
    raise SystemExit(f"unknown built-in sink: {name!r} (expected 'noop')")


def _load_findings(plan_path):
    """Load the `findings` list from a CP04 EVALUATE doc_lint JSON report."""
    with open(plan_path, encoding="utf-8") as fh:
        obj = json.load(fh)
    if not isinstance(obj, dict) or not isinstance(obj.get("findings"), list):
        raise SystemExit(f"not a valid EVALUATE plan (no findings list): {plan_path}")
    return obj["findings"]


def _resolve_config(config_path):
    """Resolve only an explicitly supplied config via overlay.py.

    The cross-module import lives HERE in the CLI boundary only, so the pure
    `capture`/`strip_provenance` stay overlay-agnostic (DI). Returns the resolved
    config dict (sink=noop, learn_enabled=False out of the box).
    """
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import overlay as _overlay  # noqa: WPS433
    return _overlay.resolve_config(config_path)


def _main(argv=None):
    ap = argparse.ArgumentParser(
        description="doc-steward LEARN writer: distill one finding to a sink.")
    ap.add_argument("--plan", required=True,
                    help="EVALUATE plan file (CP04 doc_lint JSON report)")
    ap.add_argument("--sink", default=None, choices=("noop",),
                    help="built-in sink; passing it is explicit capture intent")
    ap.add_argument("--sink-module", default=None,
                    help="explicit local Python module exposing Sink; never "
                         "loaded unless this flag is present")
    ap.add_argument("--sink-path", default=None,
                    help="optional path forwarded to the selected Sink")
    ap.add_argument("--config", default=None,
                    help="optional generic YAML config path; omitted uses safe "
                         "defaults (noop, LEARN off)")
    ap.add_argument("--index", type=int, default=0,
                    help="which finding to capture (default 0 — explicit trigger "
                         "writes exactly one)")
    args = ap.parse_args(argv)

    config = _resolve_config(args.config)
    explicit_sink = args.sink is not None or args.sink_module is not None
    sink_name = args.sink or config.get("sink", "noop")
    sink_path = args.sink_path or config.get("sink_path")

    findings = _load_findings(args.plan)
    if not findings:
        print("no findings to capture")
        return 0
    if not (0 <= args.index < len(findings)):
        raise SystemExit(f"--index {args.index} out of range (0..{len(findings)-1})")

    # REFUSE unless LEARN is explicitly enabled in config OR the user passed
    # an explicit sink flag. Out-of-box ->
    # learn_enabled False + no --sink -> refuse, write nothing.
    if not config.get("learn_enabled", False) and not explicit_sink:
        print("LEARN disabled: no explicit config enablement or sink; "
              "nothing captured (safe default).")
        return 0

    sink = _load_sink(sink_name, path=sink_path,
                      module_path=args.sink_module)
    record = capture(findings[args.index], sink, overlay=config)
    if record.get("rejected"):
        print("capture rejected: residual high-risk content; sink not called")
        return 1
    print(f"captured {record['tag']}: {record['lesson']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
