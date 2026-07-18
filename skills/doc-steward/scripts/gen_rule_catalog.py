#!/usr/bin/env python3
"""gen_rule_catalog — regenerate references/rule-catalog.md from lib/rules.py.

`lib/rules.py` is the SINGLE SOURCE OF TRUTH for the rule set; the human-readable
`references/rule-catalog.md` is GENERATED from it (design §4.3 line 99, §5 line
147 "references/rule-catalog.md is generated from lib/rules.py"). This script is
that generator. There is NO CI runner (design Card §6) — it ships as a runnable
script with a `--check` drift gate so the dogfooded STRUCT-02/VOL-01 single-
source invariant can be verified by hand or by a future hook.

Modes:
  (default)        write the rendered catalog to references/rule-catalog.md
  --check          exit 1 if the on-disk file differs from freshly rendered
                   content (drift), 0 if in sync — writes nothing
  --out <path>     override the catalog path (used by tests)

Pure/DI: `render(rules)` turns the rule list into the markdown string with no
I/O; only `generate()` / `_main()` touch the filesystem. Stdlib-only.
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "lib"))

# Auto = tag in the §5 catalog: A=LOW-RISK-AUTO, A* = auto only when
# autofix_preconditions hold (else escalate), E = escalate.
_AUTO_TAG = {"LOW-RISK-AUTO": "A*", "ESCALATE": "E"}
# Src = S (spec-required) | H (house-opinion).
_SRC_TAG = {"spec-required": "S", "house-opinion": "H"}

_HEADER = (
    "<!-- GENERATED FILE — do not edit by hand.\n"
    "     Source of truth: scripts/lib/rules.py\n"
    "     Regenerate: python3 scripts/gen_rule_catalog.py\n"
    "     Drift check: python3 scripts/gen_rule_catalog.py --check -->\n"
    "\n"
    "# doc-steward Rule Catalog\n"
    "\n"
    "Generated from `scripts/lib/rules.py` (the canonical rule set). Tags:\n"
    "**Sev** P0/P1/P2 · **Tier** min tier where required · "
    "**Auto** A\\*=auto-when-preconditions-hold / E=escalate · "
    "**Src** S=spec-required / H=house-opinion · "
    "**Check** deterministic/inspector/manual (owner).\n"
)


def _auto(rule):
    base = _AUTO_TAG.get(rule.get("auto"), rule.get("auto", "?"))
    return base


def _src(rule):
    return _SRC_TAG.get(rule.get("source"), rule.get("source", "?"))


def render(rules):
    """Return the full markdown catalog string for `rules` (pure, no I/O).

    Rules are grouped under their `category` heading in first-appearance order,
    so the rendered structure mirrors lib/rules.py's own section ordering.
    """
    # Preserve first-appearance order of categories.
    categories = []
    by_cat = {}
    for r in rules:
        cat = r["category"]
        if cat not in by_cat:
            by_cat[cat] = []
            categories.append(cat)
        by_cat[cat].append(r)

    parts = [_HEADER]
    parts.append(f"\n_{len(rules)} rules across {len(categories)} categories._\n")
    for cat in categories:
        parts.append(f"\n## {cat}\n")
        for r in by_cat[cat]:
            tags = (f"[{r['severity']}·{r['min_tier']}·{_auto(r)}·{_src(r)}]")
            owner = f"{r['check']}:{r['checker']}"
            line = f"- **{r['id']}** {tags} — owner `{owner}`"
            if r.get("enforces_ruler"):
                line += " · self-ruler"
            if r.get("autofix_preconditions"):
                line += f" · autofix-when: {r['autofix_preconditions']}"
            if r.get("remedy"):
                line += f" · remedy: {r['remedy']}"
            parts.append(line)
    return "\n".join(parts) + "\n"


def catalog_path():
    """Absolute path of the generated catalog (skill-root references/)."""
    return os.path.normpath(
        os.path.join(_HERE, "..", "references", "rule-catalog.md"))


def generate(rules, out_path):
    """Render `rules` and write the catalog to `out_path` (creates dirs)."""
    text = render(rules)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def _load_rules():
    import rules  # noqa: E402
    return rules.RULES


def _main(argv=None):
    parser = argparse.ArgumentParser(
        description="Regenerate references/rule-catalog.md from lib/rules.py")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 on drift (no write), 0 if in sync")
    parser.add_argument("--out", default=None,
                        help="catalog path override (default: "
                             "references/rule-catalog.md)")
    args = parser.parse_args(argv)

    rules = _load_rules()
    out_path = args.out or catalog_path()
    rendered = render(rules)

    if args.check:
        try:
            with open(out_path, encoding="utf-8") as fh:
                on_disk = fh.read()
        except OSError:
            print(f"DRIFT: {out_path} is missing")
            return 1
        if on_disk == rendered:
            print(f"in sync: {out_path}")
            return 0
        print(f"DRIFT: {out_path} differs from lib/rules.py — regenerate")
        return 1

    generate(rules, out_path)
    print(f"wrote {out_path} ({len(rules)} rules)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
