#!/usr/bin/env python3
"""Tests for gitio.py (the whitelisted read-only git wrapper). Stdlib-only.

Run: python3 test_gitio.py   (exit 0 = pass) ; also runs under pytest.
This wrapper is what makes the §10 read-only guarantee STRUCTURAL: the audit
path can only reach git through here, and here refuses anything that could
mutate the repo. The tests encode the safety contract, not the happy path.
The read assertions run real git against THIS repo (always a git checkout).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitio as G  # noqa: E402

def _repo(tmp_path):
    root = str(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"],
                   cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    with open(os.path.join(root, "seed.txt"), "w", encoding="utf-8") as fh:
        fh.write("seed\n")
    subprocess.run(["git", "add", "seed.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=root, check=True)
    return root


# ---------- refusals (the safety contract) ----------

def test_non_whitelisted_subcommand_refused():
    for bad in (["commit", "-m", "x"], ["push"], ["checkout", "main"],
                ["reset", "--hard"], ["add", "."], ["clean", "-fd"]):
        try:
            G.read_only_git(bad)
            assert False, f"expected refusal for {bad}"
        except G.GitWriteRefused:
            pass


def test_write_flag_output_long_form_refused():
    try:
        G.read_only_git(["diff", "--output=/tmp/x"])
        assert False, "expected refusal for --output="
    except G.GitWriteRefused:
        pass


def test_write_flag_output_space_form_refused():
    try:
        G.read_only_git(["diff", "--output", "/tmp/x"])
        assert False, "expected refusal for --output <path>"
    except G.GitWriteRefused:
        pass


def test_write_flag_short_O_refused():
    try:
        G.read_only_git(["show", "-O/tmp/x"])
        assert False, "expected refusal for -O"
    except G.GitWriteRefused:
        pass


def test_redirection_token_refused():
    # A '>' redirection only has meaning in a shell; passing it as an arg is a
    # smell of an attempt to mutate — refuse it structurally.
    for bad in (["log", ">", "out.txt"], ["status", ">>", "out.txt"]):
        try:
            G.read_only_git(bad)
            assert False, f"expected refusal for {bad}"
        except G.GitWriteRefused:
            pass


def test_empty_args_refused():
    try:
        G.read_only_git([])
        assert False, "expected refusal for empty args"
    except G.GitWriteRefused:
        pass


# ---------- allowed reads (must actually return output) ----------

def test_whitelisted_rev_parse_returns_branch(tmp_path):
    out = G.read_only_git(["rev-parse", "--abbrev-ref", "HEAD"],
                          cwd=_repo(tmp_path))
    assert isinstance(out, str) and out.strip(), out


def test_whitelisted_status_porcelain_returns(tmp_path):
    # --porcelain is read-only; should not raise and should return a string
    # (possibly empty if the tree is clean — the point is it RAN).
    out = G.read_only_git(["status", "--porcelain"], cwd=_repo(tmp_path))
    assert isinstance(out, str)


def test_all_whitelisted_subcommands_accepted_shape():
    # rev-parse with --git-dir proves every whitelisted verb is reachable; we
    # assert the whitelist itself contains exactly the §10 verbs. f10 adds
    # `check-ignore` (read-only: it queries .gitignore, never mutates).
    assert G.READ_ONLY_SUBCOMMANDS == frozenset(
        {"log", "diff", "status", "ls-files", "rev-parse", "remote", "show",
         "check-ignore"}
    )


def test_check_ignore_is_whitelisted_and_runs(tmp_path):
    root = _repo(tmp_path)
    with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write("local-config.yml\n")
    rc = G.read_only_git_rc(["check-ignore", "local-config.yml"], cwd=root)
    assert rc == 0, "check-ignore must report a gitignored path as ignored (rc 0)"
    # A tracked file is NOT ignored -> non-zero rc (a normal answer, not an error).
    rc2 = G.read_only_git_rc(["check-ignore", "seed.txt"], cwd=root)
    assert rc2 != 0, "a tracked file is not ignored -> non-zero check-ignore rc"


def test_check_ignore_still_refuses_write_flags():
    # Even on the newly-whitelisted check-ignore, a write-capable flag is refused
    # (the guard composes: subcommand whitelist AND no write flag). Both the
    # stdout entrypoint and the exit-code entrypoint share the guard.
    for entry in (G.read_only_git, G.read_only_git_rc):
        try:
            entry(["check-ignore", "--output=/tmp/x", "foo"])
            assert False, "expected refusal for a write flag on check-ignore"
        except G.GitWriteRefused:
            pass


def test_is_write_flag_predicate():
    assert G.is_write_flag("--output=x") is True
    assert G.is_write_flag("--output") is True
    assert G.is_write_flag("-O") is True
    assert G.is_write_flag("-O/tmp/x") is True
    assert G.is_write_flag(">") is True
    assert G.is_write_flag(">>") is True
    assert G.is_write_flag("--abbrev-ref") is False
    assert G.is_write_flag("--porcelain") is False


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
