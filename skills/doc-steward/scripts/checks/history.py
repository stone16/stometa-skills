#!/usr/bin/env python3
"""doc-steward run-history log + trend delta + OSS/public inference.

This is the audit skill's ONLY self-write: an append-only JSONL run-log at
`.doc-steward/history.jsonl` (design §4.4 line 122). It NEVER touches an
audited user doc, and writes EXACTLY that one path — `--no-history` (write=False)
skips even that.

OSS/public inference (design §4.5 line 132) uses LOCAL deterministic signals
ONLY: an OSI-recognized LICENSE file (caller-supplied boolean) + a public-host
git remote read via `lib/gitio.read_only_git(["remote", ...])`. There is NO
`gh` code path and no network repo-visibility query; when the remote is unknown
we default to the lower (private / non-OSS) tier.

`classify`-style determinism is kept pure: `trend()` and `infer_public()` take
their inputs as arguments; only `append_record`/`read_records` touch disk, and
only ever the one run-log path. History I/O is anchored to an open target
directory and refuses symlinks, hard links, special files, and hosts without
the required no-follow directory primitives.

Stdlib-only.
"""
import argparse
import json
import os
import stat
import sys
import time

# Sub-path of the run-log relative to the repo root. The ONLY path this module
# ever writes. Kept as a constant so the single-path invariant is auditable.
HISTORY_DIR = ".doc-steward"
HISTORY_FILE = "history.jsonl"

# Git hosts considered "public" for OSS inference (local signal only — we read
# the configured remote URL, we never query the host for true visibility).
_PUBLIC_HOSTS = (
    "github.com", "gitlab.com", "bitbucket.org", "codeberg.org",
    "sr.ht", "sourceforge.net", "gitea.com",
)


class HistoryBoundaryError(RuntimeError):
    """The optional history write cannot be proven to stay inside its target."""


def _require_secure_fs_primitives():
    """Fail closed when this host cannot anchor/no-follow the history path."""
    has_dir_fd = (os.open in os.supports_dir_fd
                  and os.mkdir in os.supports_dir_fd)
    if (not has_dir_fd or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY")):
        raise HistoryBoundaryError(
            "secure history I/O is unavailable on this host; "
            "refusing the optional history operation")


def _directory_flags():
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _open_root(repo_root, *, missing_ok=False):
    """Open the target itself as a real directory, never through a symlink."""
    _require_secure_fs_primitives()
    root = os.path.abspath(os.fspath(repo_root))
    try:
        return os.open(root, _directory_flags())
    except FileNotFoundError:
        if missing_ok:
            return None
        raise HistoryBoundaryError(
            "target root does not exist; refusing the history write") from None
    except OSError as exc:
        raise HistoryBoundaryError(
            "target root is not a directly opened real directory "
            "(symlinked or inaccessible target refused)") from exc


def _open_history_dir(repo_root, *, create):
    """Return a directory fd anchored below `repo_root`, or None if absent.

    Both path components are opened relative to an already-open target fd with
    ``O_NOFOLLOW``. Therefore replacing ``target/.doc-steward`` with a symlink
    cannot redirect either the directory creation or the later file open.
    """
    root_fd = _open_root(repo_root, missing_ok=not create)
    if root_fd is None:
        return None
    try:
        if create:
            try:
                os.mkdir(HISTORY_DIR, mode=0o700, dir_fd=root_fd)
            except FileExistsError:
                pass
            except OSError as exc:
                raise HistoryBoundaryError(
                    "could not create the in-target .doc-steward directory; "
                    "refusing the history write") from exc
        try:
            return os.open(HISTORY_DIR, _directory_flags(), dir_fd=root_fd)
        except FileNotFoundError:
            if not create:
                return None
            raise HistoryBoundaryError(
                "the in-target .doc-steward directory disappeared; "
                "refusing the history write") from None
        except OSError as exc:
            raise HistoryBoundaryError(
                ".doc-steward is not a directly opened real directory "
                "(symlink or non-directory refused)") from exc
    finally:
        os.close(root_fd)


def _validate_regular_single_link(fd):
    """Reject devices/FIFOs and hard links that could mutate an outside alias."""
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise HistoryBoundaryError(
            "history.jsonl is not a regular file; refusing history I/O")
    if info.st_nlink != 1:
        raise HistoryBoundaryError(
            "history.jsonl has multiple hard links; refusing history I/O")


def _history_path(repo_root):
    return os.path.join(repo_root, HISTORY_DIR, HISTORY_FILE)


def append_record(repo_root, record, write=True):
    """Append one JSONL record to .doc-steward/history.jsonl (and no other path).

    Returns the stored record (with a `ts` timestamp added). When write=False
    (the `--no-history` path) nothing is written and no directory is created;
    the timestamped record is still returned for in-memory use.
    """
    rec = dict(record)
    rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    if not write:
        return rec
    history_fd = _open_history_dir(repo_root, create=True)
    file_fd = None
    try:
        flags = (os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
                 | getattr(os, "O_NONBLOCK", 0))
        try:
            file_fd = os.open(HISTORY_FILE, flags, 0o600,
                              dir_fd=history_fd)
        except OSError as exc:
            raise HistoryBoundaryError(
                "history.jsonl could not be opened without following links; "
                "refusing the history write") from exc
        _validate_regular_single_link(file_fd)
        with os.fdopen(file_fd, "a", encoding="utf-8") as fh:
            file_fd = None  # fdopen owns and closes it from here.
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(history_fd)
    return rec


def read_records(repo_root):
    """Return records without following either history path component."""
    history_fd = _open_history_dir(repo_root, create=False)
    if history_fd is None:
        return []
    file_fd = None
    records = []
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        try:
            file_fd = os.open(HISTORY_FILE, flags, dir_fd=history_fd)
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise HistoryBoundaryError(
                "history.jsonl could not be opened without following links; "
                "refusing history I/O") from exc
        _validate_regular_single_link(file_fd)
        with os.fdopen(file_fd, encoding="utf-8") as fh:
            file_fd = None  # fdopen owns and closes it from here.
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(history_fd)
    return records


def trend(records, last_n=5):
    """Classify the score trajectory over the last N records.

    Returns IMPROVING / REGRESSING / STABLE from the delta between the oldest
    and newest score in the window; UNKNOWN when there are fewer than 2 records.
    Pure — operates only on the supplied list.
    """
    scored = [r for r in records if isinstance(r.get("score"), (int, float))]
    window = scored[-last_n:]
    if len(window) < 2:
        return "UNKNOWN"
    delta = window[-1]["score"] - window[0]["score"]
    if delta > 0:
        return "IMPROVING"
    if delta < 0:
        return "REGRESSING"
    return "STABLE"


def _default_git_reader(args, cwd=None):
    """Reach git ONLY through the canonical read-only wrapper lib/gitio."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "lib"))
    import gitio  # noqa: E402
    return gitio.read_only_git(args, cwd=cwd)


def _remote_is_public(remote_text):
    """True iff a configured remote URL points at a known public host."""
    if not remote_text or not remote_text.strip():
        return False
    return any(host in remote_text for host in _PUBLIC_HOSTS)


def infer_public(has_osi_license, git_reader=None, cwd=None):
    """Infer OSS/public status from LOCAL signals only.

    Public iff: an OSI LICENSE is present (has_osi_license) AND a configured git
    remote points at a public host. The remote is read via `git remote -v`
    through `git_reader` (defaults to lib/gitio.read_only_git — NEVER gh). When
    the remote is missing/unknown we default to private (the lower tier).
    """
    if not has_osi_license:
        return False
    reader = git_reader or _default_git_reader
    try:
        remote_text = reader(["remote", "-v"], cwd=cwd)
    except Exception:  # noqa: BLE001 — any git failure => unknown => private
        return False
    return _remote_is_public(remote_text)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _main(argv=None):
    parser = argparse.ArgumentParser(
        description="Append a doc-steward run-record and report the trend")
    parser.add_argument("root", nargs="?", default=".",
                        help="repo root (default: cwd)")
    parser.add_argument("--score", type=float, required=True,
                        help="composite score for this run (0-10)")
    parser.add_argument("--p0", type=int, default=0, help="P0 finding count")
    parser.add_argument("--no-history", action="store_true",
                        help="do not write the run-log")
    parser.add_argument("--last-n", type=int, default=5,
                        help="window size for the trend delta")
    args = parser.parse_args(argv)

    try:
        prior = read_records(args.root)
        rec = append_record(args.root, {"score": args.score, "p0": args.p0},
                            write=not args.no_history)
    except HistoryBoundaryError as exc:
        print(f"HISTORY REFUSED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — CLI failures must stay visible
        print(f"HISTORY FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    delta = trend(prior + [rec], last_n=args.last_n)
    print(json.dumps({"trend": delta, "record": rec,
                      "history_count": len(prior) + 1}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
