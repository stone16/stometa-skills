#!/usr/bin/env python3
"""Tier classification + frontend-profile predicate (design §4.5 / §6).

PURE/DI design: `classify()` and `frontend_profile()` take a `repo_signals`
dict and NEVER touch the filesystem — the determinism invariants are testable
with synthetic dicts. Only `gather_signals()` / `__main__` walk a real tree to
build that dict; that walk is the single side-effecting place.

`repo_signals` shape (all keys optional; missing => falsy):
  source_file_count : int   # files left AFTER exclusions (see gather_signals)
  has_workspaces_marker : bool   # pnpm/lerna/turbo/nx/cargo/go workspace marker
  has_components_json : bool     # shadcn components.json (frontend branch A)
  ui_framework_dep : bool        # react|vue|svelte|@angular/core|next|astro|...
  styling_engine : bool          # tailwindcss|styled-components|@emotion|...
  styling_config : bool          # tailwind.config.* | postcss.config.*
  has_component_dir : bool        # components/|ui/ dir with >=1 component file
  has_storybook : bool            # .storybook/ dir
  has_token_file : bool           # tokens.json|*.tokens.json|theme*.css|globals.css*
  public_oss : bool               # OSI LICENSE + public-host remote (history.infer_public)
  tier_signal_unknown : bool      # a tier signal isn't inferable offline

Thresholds (design line 132): Simple <50, Standard 50-5000, Complex >5000
source files OR a workspaces/monorepo marker. Final-tier precedence:
`--tier` flag > explicit config > auto-detect; when a signal isn't inferable offline,
auto-detect rounds DOWN to the lower tier.

Stdlib-only.
"""
import argparse
import json
import os
import sys

_TIERS = ("Simple", "Standard", "Complex")

# Source-count thresholds. Simple is strictly below SIMPLE_MAX; Complex is
# strictly above COMPLEX_MIN. Everything in [SIMPLE_MAX, COMPLEX_MIN] is Standard.
SIMPLE_MAX = 50      # < 50  -> Simple
COMPLEX_MIN = 5000   # > 5000 -> Complex

# Directories excluded from the source-file count, at ANY depth.
_EXCLUDED_DIRS = frozenset({".git", "node_modules", "dist", "build", "vendor"})

# Lockfiles excluded from the source-file count (generated, not authored).
_LOCKFILES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json",
    "poetry.lock", "Pipfile.lock", "Cargo.lock", "go.sum", "composer.lock",
    "Gemfile.lock", "uv.lock",
})

# Files whose presence marks a workspaces/monorepo (forces Complex).
_WORKSPACE_MARKERS = frozenset({
    "pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json",
    "rush.json", "go.work",
})

# UI-framework dependency tokens (build signal, branch B).
_UI_FRAMEWORK_DEPS = (
    "react", "vue", "svelte", "@angular/core", "next", "astro",
    "solid-js", "@remix-run",
)
# Styling-engine dependency tokens (build signal, branch B).
_STYLING_ENGINES = (
    "tailwindcss", "@tailwindcss/postcss", "styled-components",
    "@vanilla-extract", "@emotion",
)

# Extensions counted as authored source for tier sizing.
_SOURCE_EXTS = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".go", ".rs",
    ".rb", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".swift",
    ".scala", ".sh", ".css", ".scss", ".html", ".md", ".json", ".yaml", ".yml",
    ".toml",
})

# Extensions that count as a "component file" inside components/|ui/.
_COMPONENT_EXTS = frozenset({".tsx", ".jsx", ".vue", ".svelte"})


def _auto_tier(signals):
    """Auto-detect tier from size + workspaces marker + public/OSS (no override).

    A public/OSS repo (design §4.5 line 132) rounds to the STRICTER tier: a small
    public charter still deserves the Standard checks, so an otherwise-Simple
    count is bumped to Standard. The public/OSS bump never LOWERS a tier.
    """
    if signals.get("has_workspaces_marker"):
        return "Complex"
    count = signals.get("source_file_count", 0)
    if count < SIMPLE_MAX:
        tier = "Simple"
    elif count <= COMPLEX_MIN:
        tier = "Standard"
    else:
        tier = "Complex"
    # Public/OSS rounds Simple up to the stricter Standard (never downgrades).
    if signals.get("public_oss") and tier == "Simple":
        tier = "Standard"
    return tier


def _round_down(tier):
    """Drop to the next-lower tier; Simple is the floor."""
    idx = _TIERS.index(tier)
    return _TIERS[max(0, idx - 1)]


def classify(repo_signals, tier_override=None, overlay_tier=None):
    """Return 'Simple' | 'Standard' | 'Complex' for the given signals.

    Precedence: tier_override (--tier) > overlay_tier (explicit config) >
    auto-detect. An override that isn't a valid tier is
    ignored (we never silently mislabel on a typo). When a tier signal isn't
    inferable offline (`tier_signal_unknown`), the auto-detected tier rounds
    DOWN to the lower tier (Simple is the floor). Pure — no filesystem access.
    """
    if tier_override in _TIERS:
        return tier_override
    if overlay_tier in _TIERS:
        return overlay_tier
    tier = _auto_tier(repo_signals)
    if repo_signals.get("tier_signal_unknown"):
        tier = _round_down(tier)
    return tier


def frontend_profile(repo_signals):
    """True iff the frontend profile fires (design §6, lines 216-222).

    Fires iff (A) OR (B):
      (A) a shadcn components.json exists (definitive on its own); OR
      (B) a BUILD signal AND a SURFACE signal are both present, where
          build   = ui_framework_dep OR styling_engine OR styling_config
          surface = has_component_dir OR has_storybook OR has_token_file
    A UI-framework dep ALONE never fires (no surface signal). Pure.
    """
    if repo_signals.get("has_components_json"):
        return True
    build = (repo_signals.get("ui_framework_dep")
             or repo_signals.get("styling_engine")
             or repo_signals.get("styling_config"))
    surface = (repo_signals.get("has_component_dir")
               or repo_signals.get("has_storybook")
               or repo_signals.get("has_token_file"))
    return bool(build and surface)


# --------------------------------------------------------------------------
# Signal gatherer — the ONLY filesystem-touching code in this module.
# --------------------------------------------------------------------------
def _iter_source_files(root):
    """Yield abs paths of authored source files, excluding _EXCLUDED_DIRS at
    ANY depth (recursive node_modules/.git/dist/build/vendor) and lockfiles."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded dirs in place so we never descend into them (this is
        # what makes node_modules/ exclusion recursive — at every level).
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        for name in filenames:
            if name in _LOCKFILES:
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in _SOURCE_EXTS:
                yield os.path.join(dirpath, name)


def _read_package_json_deps(root):
    """Return the union of dependency names declared in a root package.json."""
    pkg = os.path.join(root, "package.json")
    deps = set()
    try:
        with open(pkg, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return deps
    for field in ("dependencies", "devDependencies",
                  "peerDependencies", "optionalDependencies"):
        block = data.get(field)
        if isinstance(block, dict):
            deps.update(block.keys())
    if "workspaces" in data:
        deps.add("__workspaces__")  # package.json workspaces marker
    return deps


def _has_component_dir(root):
    """True iff a components/ or ui/ dir holds >=1 component file (any depth)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        base = os.path.basename(dirpath)
        if base in ("components", "ui"):
            for name in filenames:
                if os.path.splitext(name)[1].lower() in _COMPONENT_EXTS:
                    return True
    return False


def _has_token_file(root):
    """True iff a design-token file exists (tokens.json / *.tokens.json /
    theme*.css / a globals.css carrying CSS custom properties)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        for name in filenames:
            lower = name.lower()
            if lower == "tokens.json" or lower.endswith(".tokens.json"):
                return True
            if lower.startswith("theme") and lower.endswith(".css"):
                return True
            if lower == "globals.css":
                try:
                    with open(os.path.join(dirpath, name),
                              encoding="utf-8") as fh:
                        text = fh.read()
                    if ("--" in text or "@theme" in text
                            or "@layer base" in text):
                        return True
                except OSError:
                    pass
    return False


# OSI-recognized license families we sniff from a LICENSE file's first lines.
_OSI_LICENSE_MARKERS = (
    "mit license", "apache license", "gnu general public license",
    "gnu lesser general public license", "gnu affero general public license",
    "bsd ", "mozilla public license", "the unlicense", "isc license",
    "boost software license", "eclipse public license",
)
_LICENSE_FILENAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING",
                      "COPYING.md")


def _has_osi_license(root):
    """True iff a LICENSE-shaped file at the root names an OSI license family.

    LOCAL signal only (design §4.5 line 132): read the first lines of a LICENSE
    file and match a known OSI marker. No network, no SPDX lookup.
    """
    for name in _LICENSE_FILENAMES:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                head = fh.read(2000).lower()
        except OSError:
            continue
        if any(marker in head for marker in _OSI_LICENSE_MARKERS):
            return True
    return False


def _infer_public_oss(root, git_reader=None):
    """Infer public/OSS status via history.infer_public (routes git through gitio).

    Reuses the canonical LOCAL-signals-only inference (OSI LICENSE + public-host
    remote read through lib/gitio — never gh). `git_reader` is injected for tests;
    production passes None so infer_public uses lib/gitio.read_only_git.
    """
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
        import history  # noqa: WPS433 (sibling check module)
        return bool(history.infer_public(
            _has_osi_license(root), git_reader=git_reader, cwd=root))
    except Exception:  # noqa: BLE001 — any failure => unknown => private (False)
        return False


def _exists_any(root, names):
    return any(os.path.exists(os.path.join(root, n)) for n in names)


def _glob_config(root, prefixes):
    """True iff a top-level file matches one of the config prefixes
    (e.g. tailwind.config.* / postcss.config.*)."""
    try:
        for name in os.listdir(root):
            for pref in prefixes:
                if name.startswith(pref):
                    return True
    except OSError:
        pass
    return False


def gather_signals(root, git_reader=None):
    """Walk a real repo tree and build the `repo_signals` dict (side-effecting).

    This is the ONLY filesystem-touching function; classify()/frontend_profile()
    consume its output but never call it, keeping them pure for unit testing.

    `git_reader` is injected only for tests of the public/OSS inference; in
    production it stays None so history.infer_public reaches git through the
    canonical lib/gitio read-only wrapper.
    """
    source_files = list(_iter_source_files(root))
    deps = _read_package_json_deps(root)

    has_workspaces_marker = (
        _exists_any(root, _WORKSPACE_MARKERS)
        or "__workspaces__" in deps
        or os.path.exists(os.path.join(root, "Cargo.toml"))
        and _cargo_has_workspace(os.path.join(root, "Cargo.toml"))
    )

    components_json = os.path.join(root, "components.json")
    return {
        "source_file_count": len(source_files),
        "has_workspaces_marker": bool(has_workspaces_marker),
        "has_components_json": os.path.exists(components_json),
        "ui_framework_dep": any(d in deps for d in _UI_FRAMEWORK_DEPS),
        "styling_engine": any(d in deps for d in _STYLING_ENGINES),
        "styling_config": _glob_config(
            root, ("tailwind.config.", "postcss.config.")),
        "has_component_dir": _has_component_dir(root),
        "has_storybook": os.path.isdir(os.path.join(root, ".storybook")),
        "has_token_file": _has_token_file(root),
        "public_oss": _infer_public_oss(root, git_reader=git_reader),
        "tier_signal_unknown": False,
    }


def _cargo_has_workspace(cargo_path):
    try:
        with open(cargo_path, encoding="utf-8") as fh:
            return "[workspace]" in fh.read()
    except OSError:
        return False


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _main(argv=None):
    parser = argparse.ArgumentParser(
        description="Classify repo tier + frontend profile")
    parser.add_argument("root", nargs="?", default=".",
                        help="repo root to assess (default: cwd)")
    parser.add_argument("--tier", choices=list(_TIERS),
                        help="force the tier (highest precedence)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    signals = gather_signals(args.root)
    tier = classify(signals, tier_override=args.tier)
    profile = frontend_profile(signals)
    out = {"tier": tier, "frontend_profile": profile, "signals": signals}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"tier={tier} frontend_profile={profile} "
              f"source_files={signals['source_file_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
