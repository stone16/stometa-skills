#!/usr/bin/env python3
"""LINK-* deterministic checker — reference / routing integrity.

Pure DI design: `check(doc_paths, ...)` takes the list of documents to audit as
an ARGUMENT. Resolving a pointer against the filesystem is the checker's
inherent job, so reads of the audited docs / pointer targets are expected; the
DI seam is that the *set* of docs is injected, never discovered here. The CLI is
the only place that imports the canonical rule catalog from ../lib/rules.py.

Rules implemented (design §5 / lines 176-179):
  LINK-01  dead pointer: an `@path` or ordinary Markdown relative link that
           resolves to no real file. Reports file:line.               [P1·S·A*]
  LINK-02  `@import` cycle OR a chain longer than 5 hops.            [P0·S·E]
  LINK-04  reference nesting deeper than 1 level.                    [P2·H·E]
  LINK-03  pointer-wording reliability — see note below; the
           deterministic surface is intentionally thin.             [P1·H·E]

Failure-mode guards (REQUIRED): pointers inside fenced code blocks and inside
`<!-- -->` HTML comment spans are SKIPPED; Markdown ATX headings remain live
content. A relative target must remain inside the injected audit root after
percent decoding, normalization, and symlink resolution. In-root symlinks that
resolve to a real in-root file are live; escapes are LINK-01 findings.

Stdlib-only. A finding dict is {rule, file, line, message}.
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import unquote

_MAX_HOPS = 5          # LINK-02: chains longer than this are flagged.
_MAX_NEST = 1          # LINK-04: reference nesting deeper than this is flagged.

# An @import directive:  @import ./foo.md   (optionally with surrounding text).
_IMPORT = re.compile(r"@import\s+(\S+)")
# A bare pointer:  @./foo.md  /  @path/to/foo.md  (target up to whitespace).
_POINTER = re.compile(r"@(\.{0,2}/[^\s)\]\"']+|[A-Za-z0-9_][^\s)\]\"']*\.md)")
# Ordinary inline Markdown links and reference definitions. Images are excluded
# by the negative lookbehind; external/mailto/anchor targets are filtered by
# `_relative_markdown_target` after extraction.
_MD_INLINE = re.compile(
    r"(?<!!)\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
_MD_REFERENCE = re.compile(
    r"(?<!!)^[ \t]*\[[^\]]+\]:[ \t]*(?:<([^>]+)>|(\S+))")
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _strip_guarded_lines(text):
    """Yield (line_no, line_text) for lines OUTSIDE guarded regions.

    Fenced code-block lines are skipped. HTML comment *spans* are replaced with
    spaces so live Markdown before/after a comment on the same line remains
    parseable at its original offsets. Markdown has no generic ``#`` line
    comment syntax, so ATX heading content is deliberately preserved.
    """
    in_fence = False
    in_html_comment = False
    for idx, line in enumerate(text.splitlines(), start=1):
        if in_fence:
            # Comment syntax inside a code fence is literal; only a closing
            # fence can change state while the guarded block is active.
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = False
            continue

        line, in_html_comment = _mask_html_comment_spans(
            line, in_html_comment=in_html_comment)

        # Detect opening fences only after comment spans are masked, so a fence
        # written inside an HTML comment cannot accidentally change parser state.
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = True
            continue

        yield idx, line


def _mask_html_comment_spans(line, *, in_html_comment):
    """Return ``(masked_line, still_in_comment)`` for one Markdown line.

    Every character inside ``<!-- ... -->`` becomes a space, preserving both
    line length and the offsets used by inline-code filtering. Handles comments
    spanning lines and multiple comments on one line. A ``<!--`` opener wholly
    inside a balanced inline-code span is literal Markdown and ignored. Once a
    multi-line comment is active, code syntax has no meaning and any ``-->``
    closes it normally. Text outside each comment is returned unchanged.
    """
    masked = list(line)
    inline_code_spans = (() if in_html_comment else _inline_code_spans(line))
    cursor = 0
    while cursor < len(line):
        if in_html_comment:
            close = line.find("-->", cursor)
            if close < 0:
                masked[cursor:] = " " * (len(line) - cursor)
                return "".join(masked), True
            end = close + len("-->")
            masked[cursor:end] = " " * (end - cursor)
            cursor = end
            in_html_comment = False
            # Backticks inside a comment have no Markdown meaning. Recompute
            # spans after masking them so only the live suffix protects openers.
            inline_code_spans = _inline_code_spans("".join(masked))
            continue

        opening = _next_comment_open(line, cursor, inline_code_spans)
        if opening < 0:
            break
        close = line.find("-->", opening + len("<!--"))
        if close < 0:
            masked[opening:] = " " * (len(line) - opening)
            return "".join(masked), True
        end = close + len("-->")
        masked[opening:end] = " " * (end - opening)
        cursor = end
        inline_code_spans = _inline_code_spans("".join(masked))

    return "".join(masked), in_html_comment


def _next_comment_open(line, cursor, inline_code_spans):
    """Find the next ``<!--`` not wholly inside an inline-code span."""
    while True:
        opening = line.find("<!--", cursor)
        if opening < 0:
            return -1
        end = opening + len("<!--")
        if not any(start <= opening and end <= stop
                   for start, stop in inline_code_spans):
            return opening
        cursor = end


def _extract(text):
    """Return (imports, pointers) found in unguarded lines.

    imports  -> list of (line_no, target) for @import directives.
    pointers -> list of (line_no, target, is_import, kind) for every pointer or
                relative Markdown link, used for LINK-01 dead detection. `kind`
                is `at` or `markdown` so reporting/graph logic stays explicit.
    """
    imports, pointers = [], []
    for line_no, line in _strip_guarded_lines(text):
        seen_spans = []
        inline_code = _inline_code_spans(line)
        for m in _IMPORT.finditer(line):
            target = m.group(1)
            imports.append((line_no, target))
            pointers.append((line_no, target, True, "at"))
            seen_spans.append(m.span())
        for m in _POINTER.finditer(line):
            # Skip the @path that belongs to an @import already captured.
            if any(s <= m.start() < e for s, e in seen_spans):
                continue
            pointers.append((line_no, m.group(1), False, "at"))
        for pattern in (_MD_INLINE, _MD_REFERENCE):
            for m in pattern.finditer(line):
                if any(start <= m.start() and m.end() <= end
                       for start, end in inline_code):
                    continue
                parsed_target = _relative_markdown_target(
                    m.group(1) or m.group(2))
                if parsed_target is not None:
                    target, safe_relative = parsed_target
                    kind = ("markdown" if safe_relative
                            else "markdown-unsafe")
                    pointers.append((line_no, target, False, kind))
    return imports, pointers


def _inline_code_spans(line):
    """Return `(start, end)` ranges for balanced Markdown code spans.

    Supports multiple spans and equal-length backtick delimiter runs. A backtick
    preceded by an odd number of backslashes is escaped and cannot open or close
    a span. Unbalanced delimiters are ignored. The ranges include delimiters so
    Markdown links wholly inside the span can be suppressed without altering the
    existing `@` pointer extractor.
    """
    spans = []
    opening = None
    i = 0
    while i < len(line):
        if line[i] != "`" or _is_escaped(line, i):
            i += 1
            continue
        end = i + 1
        while end < len(line) and line[end] == "`":
            end += 1
        width = end - i
        if opening is None:
            opening = (i, width)
        elif width == opening[1]:
            spans.append((opening[0], end))
            opening = None
        i = end
    return spans


def _is_escaped(text, index):
    """True when the character at `index` has an odd backslash prefix."""
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _relative_markdown_target(raw_target):
    """Return ``(decoded_target, safe_relative)`` or ``None``.

    Fragments and query strings do not affect filesystem existence. External
    schemes, protocol-relative/site-root links, home links, pure anchors, and
    empty targets written literally are deliberately outside this checker.
    Percent decoding happens before the second safety classification: an encoded
    absolute/URI target that masqueraded as relative is retained as unsafe so
    LINK-01 can report it instead of treating an external file as live.
    """
    raw = (raw_target or "").strip()
    if (not raw or raw.startswith(("#", "//", "/", "~/"))
            or _URI_SCHEME.match(raw)):
        return None
    target = raw.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    target = unquote(target).strip()
    if not target:
        return None
    safe_relative = not (
        target.startswith(("#", "//", "/", "~/"))
        or _URI_SCHEME.match(target)
    )
    return target, safe_relative


def _resolve(base_file, target):
    """Resolve a pointer target relative to the doc that contains it."""
    base_dir = os.path.dirname(os.path.abspath(base_file))
    return os.path.normpath(os.path.join(base_dir, target))


def _audit_root_for(doc_paths, audit_root=None):
    """Return the canonical boundary for repository-relative references."""
    if audit_root is not None:
        return os.path.realpath(os.path.abspath(audit_root))
    docs = [os.path.abspath(path) for path in doc_paths]
    if not docs:
        return os.path.realpath(os.getcwd())
    try:
        common = os.path.commonpath(docs)
    except ValueError:
        return os.path.realpath(os.path.dirname(docs[0]))
    if common in docs or os.path.isfile(common):
        common = os.path.dirname(common)
    return os.path.realpath(common)


def _target_within_audit(base_file, target, audit_root):
    """True iff a syntactically relative target resolves within audit_root."""
    if (not target or target.startswith(("#", "//", "/", "~/"))
            or _URI_SCHEME.match(target)):
        return False
    try:
        resolved = os.path.realpath(_resolve(base_file, target))
        return os.path.commonpath([resolved, audit_root]) == audit_root
    except (OSError, ValueError):
        return False


def _owned_ids(rules):
    return {r["id"] for r in rules if r.get("checker") == "link_check"}


def check(doc_paths, rules=None, audit_root=None):
    """Emit LINK-* violations for the given documents (pure w.r.t. inputs).

    Args:
      doc_paths: list of file paths to audit (the injected document set).
      rules: optional rule list; when given, only ids whose `checker` is
             "link_check" are emitted. When None, all LINK-* ids are eligible
             (keeps `check(paths)` callable with a single argument, per spec).
      audit_root: optional repository root. Relative targets that resolve outside
                  it (including through symlinks) are LINK-01 violations. When
                  omitted, the common parent of `doc_paths` is used.

    Returns a list of {rule, file, line, message} dicts.
    """
    owned = (_owned_ids(rules) if rules is not None
             else {"LINK-01", "LINK-02", "LINK-03", "LINK-04"})

    audit_root = _audit_root_for(doc_paths, audit_root)
    parsed = {}
    for p in doc_paths:
        try:
            with open(p, encoding="utf-8") as fh:
                parsed[os.path.abspath(p)] = _extract(fh.read())
        except OSError:
            parsed[os.path.abspath(p)] = ([], [])

    out = []

    def add(rid, file, line, msg):
        if rid in owned:
            out.append({"rule": rid, "file": file, "line": line, "message": msg})

    # ---- LINK-01: dead pointers (symlinks that resolve are NOT dead) ----
    for p, (_, pointers) in parsed.items():
        for line_no, target, _is_imp, kind in pointers:
            if (kind == "markdown-unsafe"
                    or not _target_within_audit(p, target, audit_root)):
                label = (f"relative link {target}" if kind.startswith("markdown")
                         else f"pointer @{target}")
                add("LINK-01", p, line_no,
                    f"unsafe {label} escapes audit root or is not "
                    "repository-relative")
                continue
            resolved = _resolve(p, target)
            # os.path.exists follows symlinks -> a link to a real file is live.
            if not os.path.exists(resolved):
                label = (f"relative link {target}" if kind == "markdown"
                         else f"pointer @{target}")
                add("LINK-01", p, line_no,
                    f"dead {label} (resolves to no file)")

    # ---- import graph (abs path -> [abs import targets that exist]) ----
    graph = {}
    for p, (imports, _) in parsed.items():
        edges = []
        for _line_no, target in imports:
            if _target_within_audit(p, target, audit_root):
                edges.append(_resolve(p, target))
        graph[p] = edges

    # ---- LINK-02: @import cycle OR chain > 5 hops ----
    if "LINK-02" in owned:
        _check_import_chains(graph, parsed, add)

    # ---- LINK-04: reference nesting > 1 level (bare @path refs) ----
    if "LINK-04" in owned:
        _check_reference_nesting(parsed, add, audit_root)

    # ---- LINK-03: pointer-wording reliability ----
    # The reliability of a pointer's *wording* (design line 178) is a judgment
    # property best owned by an inspector; the only deterministic slice is an
    # empty/whitespace pointer target, which _POINTER never matches, so LINK-03
    # has no deterministic finding here by design (documented, not omitted).

    return out


def _ref_graph(parsed, audit_root):
    """Build a bare-pointer reference graph (abs path -> [abs targets])."""
    graph = {}
    for p, (_imports, pointers) in parsed.items():
        edges = []
        for _line_no, target, is_imp, kind in pointers:
            if is_imp or kind == "markdown":
                continue
            if _target_within_audit(p, target, audit_root):
                edges.append(_resolve(p, target))
        graph[p] = edges
    return graph


def _check_import_chains(graph, parsed, add):
    """DFS each import root; flag cycles and chains exceeding _MAX_HOPS."""
    for root in graph:
        stack = [(root, [root])]
        while stack:
            node, path = stack.pop()
            for nxt in graph.get(node, []):
                if nxt in path:
                    add("LINK-02", path[0], _import_line(parsed, node, nxt),
                        f"@import cycle: {' -> '.join(os.path.basename(x) for x in path + [nxt])}")
                    continue
                new_path = path + [nxt]
                hops = len(new_path) - 1
                if hops > _MAX_HOPS:
                    add("LINK-02", path[0], _import_line(parsed, node, nxt),
                        f"@import chain {hops} hops > {_MAX_HOPS}: "
                        f"{' -> '.join(os.path.basename(x) for x in new_path)}")
                    continue  # stop descending this over-long branch
                if nxt in graph:
                    stack.append((nxt, new_path))


def _import_line(parsed, node, target):
    """Best-effort line number of the @import edge node->target."""
    imports = parsed.get(node, ([], []))[0]
    base = os.path.basename(target)
    for line_no, t in imports:
        if os.path.basename(t) == base:
            return line_no
    return 1


def _check_reference_nesting(parsed, add, audit_root):
    """Flag any bare-pointer reference chain deeper than _MAX_NEST levels.

    Nesting is measured WITHIN the audited document set: an edge is only
    traversed when its target is itself one of the supplied docs. A pointer to
    a file outside `doc_paths` ends the chain at the referrer's depth (so
    auditing parent+child alone is depth 1, even if child also points further).
    """
    graph = _ref_graph(parsed, audit_root)
    in_scope = set(parsed)
    for root in graph:
        # DFS measuring depth; report when a path exceeds the nesting budget.
        stack = [(root, [root])]
        while stack:
            node, path = stack.pop()
            for nxt in graph.get(node, []):
                if nxt not in in_scope:
                    continue  # target outside the audited set ends the chain
                if nxt in path:
                    continue  # cycle guard for the nesting walk
                new_path = path + [nxt]
                depth = len(new_path) - 1
                if depth > _MAX_NEST:
                    add("LINK-04", path[0], 1,
                        f"reference nesting depth {depth} > {_MAX_NEST}: "
                        f"{' -> '.join(os.path.basename(x) for x in new_path)}")
                    continue  # one finding per over-deep branch root
                stack.append((nxt, new_path))


# --------------------------------------------------------------------------
# CLI: the ONLY place that imports the canonical rule catalog.
# --------------------------------------------------------------------------
def _load_rules():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "lib"))
    import rules  # noqa: E402
    return rules.RULES


def _main(argv=None):
    parser = argparse.ArgumentParser(description="LINK-* reference checker")
    parser.add_argument("paths", nargs="+", help="markdown file(s) to check")
    parser.add_argument("--json", action="store_true",
                        help='emit {"passed": bool, "violations": [...]}')
    args = parser.parse_args(argv)

    rules = _load_rules()
    violations = check(args.paths, rules)
    passed = not violations
    if args.json:
        print(json.dumps({"passed": passed, "violations": violations}, indent=2))
    else:
        for v in violations:
            print(f"[{v['rule']}] {v['file']}:{v['line']} — {v['message']}")
        print("PASS" if passed else f"FAIL ({len(violations)} violation(s))")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(_main())
