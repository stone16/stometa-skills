#!/usr/bin/env python3
"""Tests for tier_assess.py — tier classification + frontend-profile predicate.

Run: python3 test_tier_assess.py   (exit 0 = pass) ; also runs under pytest.

Each test encodes a DETERMINISM INVARIANT from design §4.5/§6 (lines 132,
216-222). `classify()` and `frontend_profile()` are PURE/DI: they take a
`repo_signals` dict and never touch the filesystem, so the invariants are
exercised with synthetic signal dicts (no 50+ real files). The ONE real-tree
test covers the `__main__` signal-gatherer's recursive `node_modules/`
exclusion via tmp_path.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import tier_assess as T  # noqa: E402


def _sig(**over):
    """A baseline 'nothing detected' signals dict; override per test."""
    base = {
        "source_file_count": 0,
        "has_workspaces_marker": False,
        "has_components_json": False,
        "ui_framework_dep": False,
        "styling_engine": False,
        "styling_config": False,
        "has_component_dir": False,
        "has_storybook": False,
        "has_token_file": False,
        "tier_signal_unknown": False,
    }
    base.update(over)
    return base


# ----------------------------------------------------------- tier boundaries
def test_classify_simple_below_50():
    assert T.classify(_sig(source_file_count=49)) == "Simple"


def test_classify_standard_at_50_boundary():
    # 50 is the Simple/Standard boundary: Simple is strictly < 50.
    assert T.classify(_sig(source_file_count=50)) == "Standard"


def test_classify_standard_at_5000_boundary():
    # 5000 is still Standard; Complex is strictly > 5000.
    assert T.classify(_sig(source_file_count=5000)) == "Standard"


def test_classify_complex_above_5000():
    assert T.classify(_sig(source_file_count=5001)) == "Complex"


def test_classify_complex_on_workspaces_marker_even_when_small():
    # A workspaces/monorepo marker forces Complex regardless of file count.
    assert T.classify(_sig(source_file_count=10,
                           has_workspaces_marker=True)) == "Complex"


# ----------------------------------------------------------- tier overrides
def test_tier_override_wins_over_autodetect():
    # --tier override beats the auto-detected Complex.
    assert T.classify(_sig(source_file_count=9000), tier_override="Simple") \
        == "Simple"


def test_invalid_tier_override_is_ignored():
    # A bogus override must NOT silently mislabel; fall back to auto-detect.
    assert T.classify(_sig(source_file_count=49), tier_override="Bogus") \
        == "Simple"


def test_unknown_signal_rounds_down_at_boundary():
    # When a tier signal isn't inferable offline, auto-detect rounds DOWN.
    # 5001 would be Complex, but with an unknown signal it drops to Standard.
    assert T.classify(_sig(source_file_count=5001,
                           tier_signal_unknown=True)) == "Standard"


def test_unknown_signal_rounds_down_from_standard_to_simple():
    assert T.classify(_sig(source_file_count=60,
                           tier_signal_unknown=True)) == "Simple"


def test_unknown_signal_does_not_round_below_simple():
    # Simple is the floor — rounding down from Simple stays Simple.
    assert T.classify(_sig(source_file_count=10,
                           tier_signal_unknown=True)) == "Simple"


# ----------------------------------------------- frontend profile predicate
def test_frontend_profile_fires_on_shadcn_components_json_alone():
    # Branch (A): shadcn components.json is definitive on its own.
    assert T.frontend_profile(_sig(has_components_json=True)) is True


def test_frontend_profile_fires_on_framework_dep_plus_component_dir():
    # REQUIRED: UI-framework dep (build signal) + components/ dir holding a
    # component file (surface signal) => True.
    assert T.frontend_profile(_sig(ui_framework_dep=True,
                                   has_component_dir=True)) is True


def test_frontend_profile_false_on_framework_dep_only():
    # REQUIRED: a UI-framework dep ALONE never fires (no surface signal).
    assert T.frontend_profile(_sig(ui_framework_dep=True)) is False


def test_frontend_profile_false_on_surface_signal_only():
    # A surface signal with no build signal also must not fire.
    assert T.frontend_profile(_sig(has_component_dir=True)) is False


def test_frontend_profile_fires_on_styling_engine_plus_storybook():
    # build signal = styling engine; surface signal = .storybook/.
    assert T.frontend_profile(_sig(styling_engine=True,
                                   has_storybook=True)) is True


def test_frontend_profile_fires_on_styling_config_plus_token_file():
    # build signal = tailwind/postcss config; surface signal = token file.
    assert T.frontend_profile(_sig(styling_config=True,
                                   has_token_file=True)) is True


def test_frontend_profile_false_when_nothing_detected():
    assert T.frontend_profile(_sig()) is False


# --------------------------------------------------- real-tree signal gather
def test_gather_signals_excludes_recursive_node_modules(tmp_path):
    # Build a tiny real tree: 2 source files at top + a DEEPLY nested
    # node_modules with many files that MUST be excluded recursively.
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    deep = tmp_path / "src" / "node_modules" / "pkg" / "node_modules" / "dep"
    deep.mkdir(parents=True)
    for i in range(40):
        (deep / f"junk{i}.js").write_text("// junk\n")
    # also a top-level node_modules to prove depth-0 exclusion too
    nm = tmp_path / "node_modules" / "lib"
    nm.mkdir(parents=True)
    for i in range(40):
        (nm / f"more{i}.js").write_text("// more\n")

    sig = T.gather_signals(str(tmp_path))
    # Only a.py + b.py count; the 80 node_modules files are excluded.
    assert sig["source_file_count"] == 2, sig


def test_gather_signals_excludes_git_dist_build_vendor_and_lockfiles(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n")
    for d in (".git", "dist", "build", "vendor"):
        sub = tmp_path / d
        sub.mkdir()
        (sub / "f.py").write_text("noise\n")
    (tmp_path / "package-lock.json").write_text("{}\n")
    (tmp_path / "poetry.lock").write_text("\n")
    sig = T.gather_signals(str(tmp_path))
    assert sig["source_file_count"] == 1, sig


def test_gather_signals_detects_workspaces_marker(tmp_path):
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'pkg/*'\n")
    sig = T.gather_signals(str(tmp_path))
    assert sig["has_workspaces_marker"] is True, sig


def test_gather_signals_detects_package_json_workspaces(tmp_path):
    # A `workspaces` field in package.json is itself a monorepo marker.
    (tmp_path / "package.json").write_text(
        '{"workspaces": ["packages/*"]}\n')
    sig = T.gather_signals(str(tmp_path))
    assert sig["has_workspaces_marker"] is True, sig


def test_gather_signals_detects_cargo_workspace(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[workspace]\nmembers = [\"a\"]\n")
    sig = T.gather_signals(str(tmp_path))
    assert sig["has_workspaces_marker"] is True, sig


def test_gather_signals_reads_ui_framework_and_styling_deps(tmp_path):
    # package.json deps drive the build-signal booleans.
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "^18"},'
        ' "devDependencies": {"tailwindcss": "^3"}}\n')
    sig = T.gather_signals(str(tmp_path))
    assert sig["ui_framework_dep"] is True, sig
    assert sig["styling_engine"] is True, sig


def test_gather_signals_tolerates_broken_package_json(tmp_path):
    # Malformed package.json must not raise; deps just come back empty.
    (tmp_path / "package.json").write_text("{not json")
    sig = T.gather_signals(str(tmp_path))
    assert sig["ui_framework_dep"] is False, sig


def test_gather_signals_detects_styling_config_glob(tmp_path):
    (tmp_path / "tailwind.config.ts").write_text("export default {}\n")
    sig = T.gather_signals(str(tmp_path))
    assert sig["styling_config"] is True, sig


def test_gather_signals_detects_components_json(tmp_path):
    (tmp_path / "components.json").write_text(
        '{"$schema": "https://ui.shadcn.com/schema.json"}\n')
    sig = T.gather_signals(str(tmp_path))
    assert sig["has_components_json"] is True, sig
    assert T.frontend_profile(sig) is True, sig


def test_gather_signals_detects_component_dir(tmp_path):
    comp = tmp_path / "src" / "components"
    comp.mkdir(parents=True)
    (comp / "Button.tsx").write_text("export const Button = () => null\n")
    sig = T.gather_signals(str(tmp_path))
    assert sig["has_component_dir"] is True, sig


def test_gather_signals_component_dir_ignores_non_component_files(tmp_path):
    comp = tmp_path / "components"
    comp.mkdir()
    (comp / "README.md").write_text("# docs\n")  # not a component file
    sig = T.gather_signals(str(tmp_path))
    assert sig["has_component_dir"] is False, sig


def test_gather_signals_detects_storybook(tmp_path):
    (tmp_path / ".storybook").mkdir()
    sig = T.gather_signals(str(tmp_path))
    assert sig["has_storybook"] is True, sig


def test_gather_signals_detects_token_files(tmp_path):
    (tmp_path / "tokens.json").write_text("{}\n")
    assert T.gather_signals(str(tmp_path))["has_token_file"] is True


def test_gather_signals_detects_theme_css_token_file(tmp_path):
    (tmp_path / "theme.css").write_text(":root { color: red; }\n")
    assert T.gather_signals(str(tmp_path))["has_token_file"] is True


def test_gather_signals_globals_css_with_custom_props_is_token(tmp_path):
    (tmp_path / "globals.css").write_text(":root { --brand: #abc; }\n")
    assert T.gather_signals(str(tmp_path))["has_token_file"] is True


def test_gather_signals_globals_css_without_custom_props_not_token(tmp_path):
    (tmp_path / "globals.css").write_text("body { margin: 0; }\n")
    assert T.gather_signals(str(tmp_path))["has_token_file"] is False


def test_cli_default_text_output_does_not_crash(tmp_path):
    import io
    import contextlib
    (tmp_path / "a.py").write_text("x = 1\n")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = T._main([str(tmp_path)])
    assert rc == 0
    assert "tier=Simple" in buf.getvalue(), buf.getvalue()


def test_cli_tier_override_and_json(tmp_path):
    import io
    import contextlib
    import json
    (tmp_path / "a.py").write_text("x = 1\n")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = T._main([str(tmp_path), "--tier", "Complex", "--json"])
    payload = json.loads(buf.getvalue())
    assert rc == 0
    assert payload["tier"] == "Complex", payload
    assert "signals" in payload and "frontend_profile" in payload


def test_classify_overlay_used_when_no_override():
    # overlay tier is honored when --tier is absent, but loses to --tier.
    assert T.classify(_sig(source_file_count=10),
                      overlay_tier="Complex") == "Complex"
    assert T.classify(_sig(source_file_count=10),
                      tier_override="Simple",
                      overlay_tier="Complex") == "Simple"


# ----------------------------------------------- f9: public/OSS rounds stricter
def test_classify_public_oss_small_repo_is_not_simple():
    # A small public/OSS repo (would be Simple on file count alone) rounds UP to
    # the stricter tier — a public charter deserves the Standard checks.
    assert T.classify(_sig(source_file_count=10, public_oss=True)) == "Standard"


def test_classify_private_small_repo_stays_simple():
    # Without the public/OSS signal, a small repo is still Simple (no over-strict).
    assert T.classify(_sig(source_file_count=10, public_oss=False)) == "Simple"


def test_classify_public_oss_does_not_downgrade_complex():
    # The public/OSS bump never LOWERS a tier — a large public repo stays Complex.
    assert T.classify(_sig(source_file_count=9000, public_oss=True)) == "Complex"


def test_tier_override_beats_public_oss_bump():
    # --tier still wins over the public/OSS auto-bump.
    assert T.classify(_sig(source_file_count=10, public_oss=True),
                      tier_override="Simple") == "Simple"


def test_gather_signals_sets_public_oss_from_inference(tmp_path):
    # gather_signals must call public/OSS inference and surface a `public_oss`
    # boolean. With an OSI LICENSE present AND a public-host remote (via an
    # injected reader through lib/gitio), the signal is True.
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "LICENSE").write_text(
        "MIT License\n\nPermission is hereby granted, free of charge, ...\n")

    def fake_remote(args, cwd=None):
        if args and args[0] == "remote":
            return "origin\thttps://github.com/acme/widget.git (fetch)\n"
        return ""

    sig = T.gather_signals(str(tmp_path), git_reader=fake_remote)
    assert sig["public_oss"] is True, sig
    # And a small public/OSS repo classifies stricter than Simple.
    assert T.classify(sig) == "Standard", sig


def test_gather_signals_public_oss_false_without_license(tmp_path):
    # No OSI LICENSE -> public/OSS inference is False even on a public remote.
    (tmp_path / "a.py").write_text("x = 1\n")

    def fake_remote(args, cwd=None):
        return "origin\thttps://github.com/acme/widget.git (fetch)\n"

    sig = T.gather_signals(str(tmp_path), git_reader=fake_remote)
    assert sig["public_oss"] is False, sig


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    # tmp_path-based tests need a fixture; provide a real temp dir for them.
    import tempfile
    import shutil
    failed = 0
    for t in tests:
        tmp = None
        try:
            if "tmp_path" in t.__code__.co_varnames[:t.__code__.co_argcount]:
                import pathlib
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
