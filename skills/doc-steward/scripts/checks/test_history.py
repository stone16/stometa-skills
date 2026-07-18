#!/usr/bin/env python3
"""Tests for history.py — append-only run-log + trend delta + OSS inference.

Run: python3 test_history.py   (exit 0 = pass) ; also runs under pytest.

Invariants encoded (design §4.4 line 122, §4.5 line 132):
  * `append_record` writes EXACTLY ONE path — `.doc-steward/history.jsonl` —
    and NOTHING else (asserted against a temp dir: no other file may appear).
  * `--no-history` / write=False skips writing entirely.
  * history I/O refuses symlink and hard-link escapes explicitly and never
    mutates the outside referent.
  * `trend` computes IMPROVING / REGRESSING / STABLE from the last N records.
  * OSS/public inference uses LOCAL signals only: an OSI LICENSE file + a
    public-host remote read via `lib/gitio.read_only_git(["remote", ...])`.
    NEVER `gh`, never a network visibility query. Unknown => private/non-OSS.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import history as H  # noqa: E402


def _assert_boundary_refused(operation):
    try:
        operation()
    except H.HistoryBoundaryError as exc:
        assert "refus" in str(exc).lower(), str(exc)
        return str(exc)
    raise AssertionError("expected HistoryBoundaryError")


# ----------------------------------------------- single-path write invariant
def test_append_writes_only_history_jsonl(tmp_path):
    repo = str(tmp_path)
    H.append_record(repo, {"score": 7.0, "p0": 0})
    # The ONLY artifact created under the repo is .doc-steward/history.jsonl.
    created = []
    for root, _dirs, files in os.walk(repo):
        for f in files:
            created.append(os.path.relpath(os.path.join(root, f), repo))
    assert created == [os.path.join(".doc-steward", "history.jsonl")], created


def test_append_is_jsonl_one_record_per_line(tmp_path):
    repo = str(tmp_path)
    H.append_record(repo, {"score": 5.0})
    H.append_record(repo, {"score": 6.0})
    path = os.path.join(repo, ".doc-steward", "history.jsonl")
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    assert len(lines) == 2, lines
    assert json.loads(lines[0])["score"] == 5.0
    assert json.loads(lines[1])["score"] == 6.0


def test_append_each_record_carries_timestamp(tmp_path):
    repo = str(tmp_path)
    rec = H.append_record(repo, {"score": 8.0})
    assert "ts" in rec and rec["ts"], rec


def test_no_history_writes_nothing(tmp_path):
    repo = str(tmp_path)
    H.append_record(repo, {"score": 9.0}, write=False)
    # No .doc-steward dir, no file — nothing at all.
    created = []
    for _root, _dirs, files in os.walk(repo):
        created.extend(files)
    assert created == [], created


def test_append_refuses_symlinked_history_directory_without_escape(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (repo / ".doc-steward").symlink_to(outside, target_is_directory=True)

    _assert_boundary_refused(
        lambda: H.append_record(str(repo), {"score": 9.0}))

    assert not (outside / "history.jsonl").exists()


def test_append_refuses_symlinked_history_file_without_escape(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside.jsonl"
    (repo / ".doc-steward").mkdir(parents=True)
    outside.write_text("sentinel\n", encoding="utf-8")
    (repo / ".doc-steward" / "history.jsonl").symlink_to(outside)

    _assert_boundary_refused(
        lambda: H.append_record(str(repo), {"score": 9.0}))

    assert outside.read_text(encoding="utf-8") == "sentinel\n"


def test_append_refuses_hard_linked_history_file_without_escape(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside.jsonl"
    (repo / ".doc-steward").mkdir(parents=True)
    outside.write_text("sentinel\n", encoding="utf-8")
    os.link(outside, repo / ".doc-steward" / "history.jsonl")

    _assert_boundary_refused(
        lambda: H.append_record(str(repo), {"score": 9.0}))

    assert outside.read_text(encoding="utf-8") == "sentinel\n"


def test_read_refuses_symlinked_history_directory(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (outside / "history.jsonl").write_text(
        '{"score": 10.0}\n', encoding="utf-8")
    (repo / ".doc-steward").symlink_to(outside, target_is_directory=True)

    _assert_boundary_refused(lambda: H.read_records(str(repo)))


def test_cli_boundary_refusal_is_explicit_and_nonzero(tmp_path):
    import contextlib
    import io
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (repo / ".doc-steward").symlink_to(outside, target_is_directory=True)

    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        rc = H._main([str(repo), "--score", "5.0"])
    assert rc != 0
    assert "HISTORY REFUSED" in stderr.getvalue(), stderr.getvalue()
    assert not (outside / "history.jsonl").exists()


# ------------------------------------------------------------- trend delta
def test_trend_improving_when_score_rises():
    recs = [{"score": 4.0}, {"score": 6.0}, {"score": 8.0}]
    assert H.trend(recs) == "IMPROVING"


def test_trend_regressing_when_score_falls():
    recs = [{"score": 9.0}, {"score": 6.0}, {"score": 5.0}]
    assert H.trend(recs) == "REGRESSING"


def test_trend_stable_when_score_flat():
    recs = [{"score": 7.0}, {"score": 7.0}]
    assert H.trend(recs) == "STABLE"


def test_trend_uses_last_n_only():
    # An old low score outside the window must not drag the delta down.
    recs = [{"score": 1.0}, {"score": 5.0}, {"score": 5.0}, {"score": 5.0}]
    assert H.trend(recs, last_n=3) == "STABLE"


def test_trend_unknown_on_insufficient_history():
    assert H.trend([{"score": 7.0}]) == "UNKNOWN"
    assert H.trend([]) == "UNKNOWN"


def test_read_records_after_append_roundtrip(tmp_path):
    repo = str(tmp_path)
    H.append_record(repo, {"score": 3.0})
    H.append_record(repo, {"score": 7.0})
    recs = H.read_records(repo)
    assert [r["score"] for r in recs] == [3.0, 7.0], recs
    assert H.trend(recs) == "IMPROVING"


def test_read_records_empty_when_no_history(tmp_path):
    assert H.read_records(str(tmp_path)) == []


# --------------------------------------------------- OSS / public inference
class _FakeGit:
    """Stand-in for lib.gitio.read_only_git capturing the args it received."""

    def __init__(self, remote_out):
        self.remote_out = remote_out
        self.calls = []

    def __call__(self, args, cwd=None):
        self.calls.append(args)
        if args and args[0] == "remote":
            return self.remote_out
        return ""


def test_oss_true_only_with_license_and_public_remote():
    git = _FakeGit("origin\thttps://github.com/acme/widget.git (fetch)\n")
    assert H.infer_public(has_osi_license=True, git_reader=git) is True
    # And it asked git for the remote (read-only), via the injected reader.
    assert any(c and c[0] == "remote" for c in git.calls), git.calls


def test_oss_false_without_license_even_on_public_remote():
    git = _FakeGit("origin\thttps://github.com/acme/widget.git (fetch)\n")
    assert H.infer_public(has_osi_license=False, git_reader=git) is False


def test_oss_false_on_private_host_remote():
    git = _FakeGit("origin\tgit@git.internal.acme.corp:team/app.git (fetch)\n")
    assert H.infer_public(has_osi_license=True, git_reader=git) is False


def test_oss_defaults_private_when_remote_unknown():
    # No remote configured => unknown => default to the lower (non-OSS) tier.
    git = _FakeGit("")
    assert H.infer_public(has_osi_license=True, git_reader=git) is False


def test_oss_inference_never_invokes_gh():
    # Structural guarantee: the only external reader is the injected git_reader,
    # and it is only ever asked for `remote`. There is no gh code path.
    git = _FakeGit("origin\thttps://gitlab.com/acme/widget.git (fetch)\n")
    H.infer_public(has_osi_license=True, git_reader=git)
    for call in git.calls:
        assert call and call[0] == "remote", \
            f"only `git remote` reads are allowed, got: {call}"


def test_oss_uses_real_gitio_reader_by_default():
    # When no reader is injected, infer_public must reach git through the
    # canonical lib/gitio.read_only_git — not gh, not raw subprocess here.
    import inspect
    src = inspect.getsource(H)
    assert "gitio" in src, "history must import lib/gitio for remote reads"
    assert "read_only_git" in src, "must use the read-only git wrapper"
    # And it must NOT shell out to gh anywhere.
    assert '"gh"' not in src and "'gh'" not in src, \
        "OSS inference must never call gh"


def test_default_reader_reaches_real_gitio_remote(tmp_path):
    # With NO injected reader, infer_public must reach the real
    # lib/gitio.read_only_git for the remote read. This repo IS a git checkout
    # but has no OSI LICENSE flag passed, so the license gate short-circuits to
    # False BEFORE any git call — we instead prove the default reader path by
    # passing the license flag and pointing cwd at this real repo. The remote
    # may or may not be public; we only assert it returns a bool without error
    # and without ever importing gh.
    here = os.path.dirname(os.path.abspath(__file__))
    result = H.infer_public(has_osi_license=True, cwd=here)
    assert isinstance(result, bool), result


def test_default_reader_handles_git_failure_as_private(tmp_path):
    # Run the default reader in a NON-git dir: gitio raises -> treated as
    # unknown -> private (False), with no gh fallback.
    result = H.infer_public(has_osi_license=True, cwd=str(tmp_path))
    assert result is False, result


def test_cli_writes_record_and_reports_trend(tmp_path):
    import io
    import contextlib
    import json
    repo = str(tmp_path)
    # First run establishes a baseline; second run should compute a trend.
    H.append_record(repo, {"score": 4.0})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = H._main([repo, "--score", "8.0", "--p0", "1"])
    payload = json.loads(buf.getvalue())
    assert rc == 0
    assert payload["trend"] == "IMPROVING", payload
    assert payload["record"]["score"] == 8.0
    # The run-log now holds both records.
    assert len(H.read_records(repo)) == 2


def test_cli_no_history_writes_nothing(tmp_path):
    import io
    import contextlib
    repo = str(tmp_path)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = H._main([repo, "--score", "5.0", "--no-history"])
    assert rc == 0
    assert H.read_records(repo) == []
    created = []
    for _root, _dirs, files in os.walk(repo):
        created.extend(files)
    assert created == [], created


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    import tempfile
    import shutil
    import pathlib
    failed = 0
    for t in tests:
        tmp = None
        try:
            argnames = t.__code__.co_varnames[:t.__code__.co_argcount]
            if "tmp_path" in argnames:
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
