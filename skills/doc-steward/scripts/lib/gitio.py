#!/usr/bin/env python3
"""Whitelisted read-only git wrapper — makes the §10 read-only guarantee STRUCTURAL.

The doc-steward audit path reaches git ONLY through `read_only_git()`. This
wrapper is the choke point: it runs git iff (a) the subcommand is on a small
read-only whitelist AND (b) no write-capable flag is present. Anything else is
refused with `GitWriteRefused` — there is no code path here that can mutate the
repo, so the read-only property is enforced by construction, not by convention.

Stdlib-only. `read_only_git()` shells out to the real `git` via subprocess only
after the guard passes; the guard itself (`is_write_flag`, whitelist check) is
pure and unit-testable without touching the filesystem.
"""
import subprocess

# The only git subcommands the audit may invoke (design §10). `check-ignore`
# queries .gitignore (read-only — it reports whether a path is ignored and never
# mutates the repo), so the OSS packaging guard can route through this choke point.
READ_ONLY_SUBCOMMANDS = frozenset(
    {"log", "diff", "status", "ls-files", "rev-parse", "remote", "show",
     "check-ignore"}
)

# Flags / tokens that can write to disk or imply shell redirection. Even on an
# otherwise read-only subcommand these can mutate state (git diff --output=FILE,
# git format-patch -O...), so they are refused unconditionally.
_WRITE_FLAG_PREFIXES = ("--output", "-O")
_REDIRECTION_TOKENS = (">", ">>", "1>", "2>", "&>")


class GitWriteRefused(Exception):
    """Raised when read_only_git is asked to run anything write-capable."""


def is_write_flag(arg):
    """True iff `arg` is a write-capable flag or a shell-redirection token.

    Matches `--output`, `--output=...`, `-O`, `-O<path>`, and redirection
    operators (`>`, `>>`, `1>`, `2>`, `&>`). Pure — no side effects.
    """
    if arg in _REDIRECTION_TOKENS:
        return True
    for pref in _WRITE_FLAG_PREFIXES:
        if arg == pref or arg.startswith(pref + "=") or (
            pref == "-O" and arg.startswith("-O") and len(arg) > 2
        ):
            return True
    return False


def _guard(args):
    """Run the read-only guard; raise GitWriteRefused on any violation (pure)."""
    if not args:
        raise GitWriteRefused("empty git args")
    sub = args[0]
    if sub not in READ_ONLY_SUBCOMMANDS:
        raise GitWriteRefused(
            f"subcommand {sub!r} is not read-only "
            f"(allowed: {sorted(READ_ONLY_SUBCOMMANDS)})"
        )
    bad = [a for a in args[1:] if is_write_flag(a)]
    if bad:
        raise GitWriteRefused(f"write-capable flag(s) refused: {bad}")


def read_only_git(args, cwd=None):
    """Run a read-only git command and return its stdout.

    Refuses (raises GitWriteRefused) when args is empty, the subcommand is not on
    READ_ONLY_SUBCOMMANDS, or any argument is a write-capable flag. On a passing
    guard, executes `git <args>` and returns stdout as a string (raises
    CalledProcessError on a non-zero git exit).
    """
    _guard(args)
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def read_only_git_rc(args, cwd=None):
    """Run a read-only git command behind the SAME guard; return its exit code.

    For read-only verbs whose EXIT CODE is the signal (e.g. `check-ignore` exits
    0 when ignored / 1 when not; `ls-files --error-unmatch` exits 1 when a path is
    untracked). Goes through `_guard` so the read-only boundary is identical to
    `read_only_git`; a non-zero exit is a normal answer here, not an error.
    """
    _guard(args)
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode


if __name__ == "__main__":
    # Read-only self-demo against the current repo.
    print(read_only_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip())
