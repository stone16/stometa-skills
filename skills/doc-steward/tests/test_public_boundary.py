"""Public packaging boundary for doc-steward."""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".txt"}
PERSONAL_HOME = re.compile(r"/(?:Users|home)/[^/\s]+/")
WINDOWS_PERSONAL_HOME = re.compile(
    r"\b[A-Za-z]:[\\/]Users[\\/][^\\/\s]+[\\/]", re.IGNORECASE)
FORBIDDEN_PRIVATE_MARKERS = (
    "leilei-" + "skillsets",
    "stometa-" + "skillset",
    "BEGIN " + "OPENSSH PRIVATE KEY",
    "BEGIN " + "RSA PRIVATE KEY",
)


def iter_files():
    for directory, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [name for name in dirnames
                       if name not in {"__pycache__", ".pytest_cache"}]
        for name in filenames:
            yield os.path.join(directory, name)


def test_single_discoverable_skill_entrypoint():
    entries = [path for path in iter_files()
               if os.path.basename(path) == "SKILL.md"]
    assert entries == [os.path.join(ROOT, "SKILL.md")]


def test_public_extension_surface_is_minimal():
    sinks = os.path.join(ROOT, "sinks")
    sink_modules = sorted(
        name for name in os.listdir(sinks)
        if name.endswith(".py") and not name.startswith("test_"))
    assert sink_modules == ["noop.py"]
    assert not os.path.exists(os.path.join(ROOT, "commands"))
    assert not os.path.exists(os.path.join(ROOT, "overlay"))


def test_public_text_has_no_personal_paths_or_private_markers():
    for path in iter_files():
        if os.path.splitext(path)[1] not in TEXT_SUFFIXES:
            continue
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        assert not PERSONAL_HOME.search(body), path
        assert not WINDOWS_PERSONAL_HOME.search(body), path
        for marker in FORBIDDEN_PRIVATE_MARKERS:
            assert marker.lower() not in body.lower(), (path, marker)


def test_skill_frontmatter_is_portable():
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        body = fh.read()
    frontmatter = body.split("---", 2)[1]
    keys = set(re.findall(r"^([a-z][a-z0-9_-]*):", frontmatter, re.MULTILINE))
    name = re.search(r"^name:\s*(\S+)\s*$", frontmatter, re.MULTILINE)
    assert keys == {"name", "description"}
    assert name and name.group(1) == "doc-steward"


def test_public_cli_smoke():
    commands = [
        [sys.executable, os.path.join(ROOT, "scripts", "checks", "doc_lint.py"),
         "--target", os.path.join(ROOT, "scripts", "checks", "fixtures",
                                  "sample-repo"), "--json"],
        [sys.executable, os.path.join(ROOT, "scripts", "apply",
                                     "enforce_apply.py"), "--help"],
        [sys.executable, os.path.join(ROOT, "scripts", "apply",
                                     "learn_capture.py"), "--help"],
    ]
    lint = subprocess.run(commands[0], capture_output=True, text=True)
    assert lint.returncode in (0, 1)
    assert "findings" in json.loads(lint.stdout)
    for command in commands[1:]:
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
