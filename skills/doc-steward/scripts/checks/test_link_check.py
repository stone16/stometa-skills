#!/usr/bin/env python3
"""Tests for link_check.py (LINK-01..04). Stdlib-only.

Run: python3 test_link_check.py   (exit 0 = pass) ; also runs under pytest.

Each test encodes a RULE INVARIANT. `check()` is pure w.r.t. its inputs: the
caller supplies `doc_paths` (DI seam); resolving those pointers against the
filesystem is the checker's inherent job. Failure-mode guards (fenced-code,
HTML-comment spans, symlink-not-dead) are asserted explicitly; ATX headings
remain checked Markdown content.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import link_check as L  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def _p(name):
    return os.path.join(FIX, name)


def _ids(violations):
    return {v["rule"] for v in violations}


def _for_file(violations, name):
    target = os.path.abspath(_p(name))
    return [v for v in violations if os.path.abspath(v["file"]) == target]


# ---------------------------------------------------------------- LINK-01
def test_link01_fires_on_dead_pointer():
    v = L.check([_p("link_dead.md")])
    dead = [x for x in v if x["rule"] == "LINK-01"]
    assert dead, f"LINK-01 must fire on dead pointer: {_ids(v)}"
    # Must cite file:line of the real dead pointer, not the guarded ones.
    assert any("nonexistent.md" in x["message"] for x in dead), \
        f"LINK-01 must cite the dead target: {dead}"
    assert all(x.get("line") for x in dead), "LINK-01 must report a line number"


def test_link01_silent_on_live_pointer():
    v = L.check([_p("link_good.md")])
    assert "LINK-01" not in _ids(v), f"LINK-01 must not fire on live pointer: {v}"


def test_link01_skips_fenced_code_pointer():
    # Guard: a dead @path inside a ``` fence must NOT be flagged.
    v = L.check([_p("link_dead.md")])
    assert not any("fenced_dead.md" in x.get("message", "") for x in v), \
        f"fenced-code pointer must be skipped: {v}"


def test_link01_checks_at_pointer_in_atx_heading():
    # Markdown `#` starts an ATX heading, not a comment; its pointer is live text.
    v = L.check([_p("link_dead.md")])
    assert any("hash_dead.md" in x.get("message", "") for x in v), \
        f"ATX-heading pointer must be checked: {v}"


def test_link01_skips_html_comment_pointer():
    # Guard: a dead @path inside <!-- --> must NOT be flagged.
    v = L.check([_p("link_dead.md")])
    assert not any("html_dead.md" in x.get("message", "") for x in v), \
        f"html-comment pointer must be skipped: {v}"


def test_link01_does_not_false_flag_symlink():
    # Guard: a pointer at a symlink whose target EXISTS is not a dead link.
    v = L.check([_p("link_symlink.md")])
    assert "LINK-01" not in _ids(v), \
        f"symlink resolving to a real file must not be a dead link: {v}"


def test_link01_checks_ordinary_markdown_relative_links():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        live = os.path.join(tmp, "live doc.md")
        with open(live, "w", encoding="utf-8") as fh:
            fh.write("# Live\n")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write(
                "[live](live%20doc.md#section)\n"
                "[dead](missing.md)\n"
                "[external](https://example.com/missing.md)\n"
                "[mail](mailto:test@example.com)\n"
                "[anchor](#local)\n"
                "![image](missing.png)\n"
            )
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        assert len(dead) == 1, dead
        assert dead[0]["line"] == 2, dead
        assert "relative link missing.md" in dead[0]["message"], dead


def test_markdown_links_in_atx_headings_are_checked():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(os.path.join(tmp, "live.md"), "w", encoding="utf-8") as fh:
            fh.write("# Live\n")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("## [live](live.md) and [dead](heading-dead.md)\n")
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        assert len(dead) == 1, dead
        assert dead[0]["line"] == 1, dead
        assert "heading-dead.md" in dead[0]["message"], dead


def test_link_before_inline_html_comment_is_checked():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("[before](before.md) <!-- [hidden](hidden.md) -->\n")
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        messages = "\n".join(v["message"] for v in dead)
        assert len(dead) == 1, dead
        assert "before.md" in messages, dead
        assert "hidden.md" not in messages, dead


def test_link_after_inline_html_comment_is_checked():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("<!-- [hidden](hidden.md) --> [after](after.md)\n")
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        messages = "\n".join(v["message"] for v in dead)
        assert len(dead) == 1, dead
        assert "after.md" in messages, dead
        assert "hidden.md" not in messages, dead


def test_markdown_link_fully_inside_html_comment_is_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("<!-- [commented](commented-missing.md) -->\n")
        assert "LINK-01" not in _ids(L.check([source]))


def test_multiline_html_comment_preserves_links_before_open_and_after_close():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write(
                "[before](before-open.md) <!-- [hidden-open](hidden-open.md)\n"
                "[hidden-middle](hidden-middle.md)\n"
                "[hidden-close](hidden-close.md) --> [after](after-close.md)\n"
            )
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        messages = "\n".join(v["message"] for v in dead)
        assert len(dead) == 2, dead
        assert "before-open.md" in messages, dead
        assert "after-close.md" in messages, dead
        assert "hidden-open.md" not in messages, dead
        assert "hidden-middle.md" not in messages, dead
        assert "hidden-close.md" not in messages, dead
        assert {v["line"] for v in dead} == {1, 3}, dead


def test_multiple_html_comments_on_one_line_preserve_all_outside_links():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write(
                "[first](first.md) <!-- [h1](hidden-one.md) --> "
                "[middle](middle.md) <!-- [h2](hidden-two.md) --> "
                "[last](last.md)\n"
            )
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        messages = "\n".join(v["message"] for v in dead)
        assert len(dead) == 3, dead
        for target in ("first.md", "middle.md", "last.md"):
            assert target in messages, dead
        assert "hidden-one.md" not in messages, dead
        assert "hidden-two.md" not in messages, dead


def test_inline_code_comment_opener_does_not_hide_same_line_link():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("`<!--` [real](same-line-dead.md)\n")
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        assert len(dead) == 1, dead
        assert "same-line-dead.md" in dead[0]["message"], dead


def test_inline_code_comment_opener_does_not_hide_next_line_link():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("`<!--`\n[next](next-line-dead.md)\n")
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        assert len(dead) == 1, dead
        assert dead[0]["line"] == 2, dead
        assert "next-line-dead.md" in dead[0]["message"], dead


def test_comment_close_inside_backticks_still_closes_active_comment():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write(
                "<!-- comment opens\n"
                "`-->` [after](after-backtick-close.md)\n"
            )
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        assert len(dead) == 1, dead
        assert dead[0]["line"] == 2, dead
        assert "after-backtick-close.md" in dead[0]["message"], dead


def test_link01_checks_markdown_reference_definitions_and_guards():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "DESIGN.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write(
                "Use [the guide][guide].\n\n"
                "[guide]: ./missing-guide.md \"Guide\"\n"
                "<!-- [hidden]: ./hidden-missing.md -->\n"
                "```markdown\n[fenced](./fenced-missing.md)\n```\n"
            )
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        assert len(dead) == 1, dead
        assert dead[0]["line"] == 3, dead
        assert "missing-guide.md" in dead[0]["message"], dead


def test_markdown_links_inside_multiple_inline_code_spans_are_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write(
                "`[example one](inline-one.md)` "
                "[real](real-missing.md) "
                "``[example two](inline-two.md)``\n"
                r"\`[escaped opener](escaped-missing.md)" "\n"
            )
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        assert len(dead) == 2, dead
        messages = "\n".join(v["message"] for v in dead)
        assert "real-missing.md" in messages, dead
        assert "escaped-missing.md" in messages, dead
        assert "inline-one.md" not in messages, dead
        assert "inline-two.md" not in messages, dead


def test_home_relative_markdown_target_is_out_of_scope():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("[home-local reference](~/private/missing.md)\n")
        assert "LINK-01" not in _ids(L.check([source]))


def test_percent_encoded_absolute_markdown_target_is_unsafe():
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("[encoded escape](%2Ftmp%2Foutside.md)\n")
        dead = [v for v in L.check([source], audit_root=tmp)
                if v["rule"] == "LINK-01"]
        assert len(dead) == 1, dead
        assert "unsafe relative link" in dead[0]["message"], dead


def test_dotdot_existing_target_outside_audit_root_is_unsafe():
    with tempfile.TemporaryDirectory() as parent:
        root = os.path.join(parent, "repo")
        os.makedirs(root)
        outside = os.path.join(parent, "outside.md")
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write("# Outside\n")
        source = os.path.join(root, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("[escape](../outside.md)\n")
        violations = L.check([source], audit_root=root)
        dead = [v for v in violations if v["rule"] == "LINK-01"]
        assert len(dead) == 1, dead
        assert "escapes audit root" in dead[0]["message"], dead


def test_symlink_to_existing_file_outside_audit_root_is_unsafe():
    with tempfile.TemporaryDirectory() as parent:
        root = os.path.join(parent, "repo")
        os.makedirs(root)
        outside = os.path.join(parent, "outside.md")
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write("# Outside\n")
        link = os.path.join(root, "linked.md")
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            return
        source = os.path.join(root, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("[escape](linked.md)\n")
        dead = [v for v in L.check([source], audit_root=root)
                if v["rule"] == "LINK-01"]
        assert len(dead) == 1, dead
        assert "escapes audit root" in dead[0]["message"], dead


def test_at_pointer_inside_inline_code_is_not_a_live_pointer():
    """Documenting a pointer is not having one.

    `_extract` already skips Markdown links inside an inline-code span. The
    `_POINTER` loop three lines above it did not, so a table cell that
    DESCRIBES another file's imports — `| `@VOICE.md` (repo root) | ... |` —
    was audited as this file's own routing, resolved against the wrong base,
    and reported dead. Every honest doc that catalogues its imports got
    penalised for the honesty."""
    text = ("| pointer | scope |\n"
            "|---|---|\n"
            "| `@VOICE.md` (repo root, not this dir) | writing skills |\n"
            "| **`@nested/deep/persona.md`** | persona flow |\n")

    _, pointers = L._extract(text)

    assert [p for p in pointers if p[3] == "at"] == [], pointers


def test_a_bare_at_pointer_outside_code_is_still_extracted():
    """The masking must not swallow real routing — a live `@path` is bare."""
    _, pointers = L._extract("@docs/real-pointer.md\n")

    assert [(p[1], p[3]) for p in pointers] == [("docs/real-pointer.md", "at")]


def test_no_test_is_defined_after_the_direct_run_guard():
    """This file declares that it can be executed directly. Anything defined
    after `sys.exit(_run())` is invisible to that runner while pytest still
    collects it, so the two report different totals and a test can look green
    while never running.

    It has happened twice — the second time by appending with `cat >>`, which
    writes to EOF, below the guard. A reviewer caught it once; this makes the
    shape of the mistake impossible instead of relying on that.
    """
    src = open(__file__, encoding="utf-8").read()
    # rindex, not index: this test quotes the guard in its own docstring, and
    # matching that copy would make everything below it look like it sits
    # after the guard.
    guard = src.rindex("sys.exit(_run())")
    assert "def test_" not in src[guard:], (
        "a test is defined after the direct-run guard and will never run "
        "under `python3 test_link_check.py`")


def test_a_pointer_containing_an_asterisk_or_backtick_is_not_truncated():
    """Narrowing the character class was collateral damage, not a fix.

    Excluding `*` and a backtick to stop `**`@./x.md`**` escaping its span
    also truncated legitimate targets — `@./foo*bar.md` became `./foo`, which
    fabricates a LINK-01 for a path nobody wrote, and `@docs/foo*bar.md`
    vanished entirely. Both characters are legal in a POSIX filename.

    The start-inside `_quoted()` predicate already handles a match that runs
    past a closing backtick, so the class does not need to be narrow."""
    for text, want in (("@./foo*bar.md", "./foo*bar.md"),
                       ("@./foo`bar.md", "./foo`bar.md"),
                       ("@docs/foo*bar.md", "docs/foo*bar.md")):
        _, pointers = L._extract(text)
        assert [p[1] for p in pointers] == [want], (text, pointers)


def test_an_escaped_backtick_closes_an_open_code_span():
    """CommonMark: a backslash escapes in normal text but has NO meaning inside
    a code span. So `\\`` cannot OPEN a span and MUST close one.

    Treating it as escaped in both positions extended the span past its real
    end and swallowed a live pointer — a silent false negative on LINK-01,
    the opposite of what this file previously claimed the deviation could do.
    """
    text = "`quoted \\` @./live.md `\n"

    _, pointers = L._extract(text)

    assert [p[1] for p in pointers] == ["./live.md"], pointers


def test_an_escaped_backtick_still_cannot_open_a_span():
    """The other half of the CommonMark rule, so the fix cannot over-reach:
    outside a span the backslash does escape, so `\\`` opens nothing and a
    pointer after it stays live."""
    _, pointers = L._extract("\\` @./live.md\n")

    assert [p[1] for p in pointers] == ["./live.md"], pointers


def test_backticked_at_import_is_not_audited_as_routing():
    """`_IMPORT` matched before any code-span guard, so a QUOTED import was
    recorded as real routing — and with a space before the closing backtick it
    parsed cleanly, manufacturing an import that the loader never performs and
    that can fabricate a LINK-02 cycle.

    The documentation says "Import parsing skips Markdown code spans", not
    "skips bare @path". Both extractors need the same guard."""
    imports, pointers = L._extract("`@import foo.md` and `@import bar.md `\n")

    assert imports == [], imports
    assert [p for p in pointers if p[3] == "at"] == [], pointers


def test_a_pointer_wrapped_in_bold_and_backticks_is_not_routing():
    """The relative branch of `_POINTER` swallowed the closing backtick and the
    surrounding `**`, so the match extended past the code span and a
    full-containment guard could never fire. Formatting around a quoted
    pointer must not turn it back into routing."""
    _, pointers = L._extract("**`@./still-checked.md`** is quoted\n")

    assert [p for p in pointers if p[3] == "at"] == [], pointers


def test_link04_still_sees_a_bare_pointer_chain():
    """Blast radius the PR did not disclose: bare pointers feed `_ref_graph`,
    so silencing them also removes them from LINK-04 depth detection. A chain
    built from UNQUOTED pointers must still be seen."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, body in (("a.md", "@./b.md\n"), ("b.md", "@./c.md\n"),
                           ("c.md", "x\n")):
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                fh.write(body)
        paths = [os.path.join(tmp, n) for n in ("a.md", "b.md", "c.md")]

        _, pointers = L._extract("@./b.md\n")
        assert [p[1] for p in pointers] == ["./b.md"], pointers
        assert not [v for v in L.check(paths) if v["rule"] == "LINK-01"]


def test_backticked_at_pointer_is_not_audited_as_routing():
    """Backticks are the documented way to mention a path without importing it.

    Claude Code's memory docs: "Import parsing skips Markdown code spans and
    fenced code blocks. To mention a path in your CLAUDE.md without importing
    it, wrap it in backticks: writing `@README` keeps the text literal, while
    @README outside backticks imports the file."
    (https://code.claude.com/docs/en/memory#import-additional-files)

    This test previously asserted the opposite, on the rationale that
    "inline-code filtering is Markdown-link-only" — a statement about the
    implementation, not about the loader. Auditing a backticked pointer
    reports a dead import that the loader never attempts, and it penalises
    exactly the documents that are careful enough to catalogue their imports.
    """
    with tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "AGENTS.md")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write("`@./not-an-import.md` is mentioned, not imported\n")
        dead = [v for v in L.check([source]) if v["rule"] == "LINK-01"]
        assert not dead, dead


# ---------------------------------------------------------------- LINK-02
def test_link02_fires_on_import_cycle():
    v = L.check([_p("cycle_a.md"), _p("cycle_b.md")])
    assert "LINK-02" in _ids(v), f"LINK-02 must fire on @import cycle: {_ids(v)}"


def test_link02_fires_on_over_five_hop_chain():
    chain = [_p(f"chain{i}.md") for i in range(7)]
    v = L.check(chain)
    assert "LINK-02" in _ids(v), f"LINK-02 must fire on >5-hop chain: {_ids(v)}"


def test_link02_silent_on_short_acyclic_chain():
    # 3 nodes / 2 hops, acyclic -> no LINK-02.
    v = L.check([_p("chain4.md"), _p("chain5.md"), _p("chain6.md")])
    assert "LINK-02" not in _ids(v), f"LINK-02 must not fire on a short chain: {v}"


# ---------------------------------------------------------------- LINK-04
def test_link04_fires_on_reference_nesting_over_one_level():
    v = L.check([_p("nest_parent.md"), _p("nest_child.md"), _p("nest_grandchild.md")])
    assert "LINK-04" in _ids(v), f"LINK-04 must fire on nesting depth > 1: {_ids(v)}"


def test_link04_silent_on_single_level_nesting():
    # parent -> child only (depth 1) is allowed.
    v = L.check([_p("nest_parent.md"), _p("nest_child.md")])
    assert "LINK-04" not in _ids(v), f"LINK-04 must not fire on depth 1: {v}"


# ---------------------------------------------------------------- shape
def test_violations_cite_file_and_line():
    v = L.check([_p("link_dead.md")])
    assert v, "expected at least one violation"
    for item in v:
        assert "rule" in item and "file" in item, f"bad violation shape: {item}"


def test_link01_skips_multiline_html_comment_pointer():
    # Guard: a dead @path inside a multi-line <!-- ... --> block is skipped.
    v = L.check([_p("link_dead.md")])
    assert not any("multiline_dead.md" in x.get("message", "") for x in v), \
        f"multi-line HTML-comment pointer must be skipped: {v}"


def test_unreadable_path_does_not_crash():
    # A path that cannot be opened is tolerated (no findings, no exception).
    v = L.check([_p("does_not_exist_doc.md")])
    assert isinstance(v, list), "check must return a list even for unreadable paths"


def test_rules_argument_filters_to_owned_ids():
    # When the catalog is passed, check() must only emit link_check-owned ids.
    import rules as R  # noqa: E402
    owned = {r["id"] for r in R.RULES if r["checker"] == "link_check"}
    v = L.check([_p("link_dead.md"), _p("cycle_a.md"), _p("cycle_b.md")], R.RULES)
    assert _ids(v) <= owned, f"check emitted non-owned ids: {_ids(v) - owned}"


# ---------------------------------------------------------------- CLI
def test_cli_exits_1_and_emits_json_on_violations():
    import io
    import contextlib
    import json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = L._main(["--json", _p("link_dead.md")])
    payload = json.loads(buf.getvalue())
    assert rc == 1, "CLI must exit 1 when violations are found"
    assert payload["passed"] is False and payload["violations"], payload


def test_cli_exits_0_on_clean_file():
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = L._main([_p("link_good.md")])
    assert rc == 0, f"CLI must exit 0 on a clean file; got rc={rc}\n{buf.getvalue()}"


def _run():
    tests = [val for k, val in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
