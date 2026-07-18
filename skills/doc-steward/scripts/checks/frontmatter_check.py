#!/usr/bin/env python3
"""FRONT-* deterministic checker — frontmatter quality / discoverability.

Pure DI design: `check(frontmatter_text, rules, ...)` takes the raw document
text and the rule list as ARGUMENTS and returns a list of violation dicts. It
performs no skill-owned I/O. Only the `__main__` CLI loads real assets (reads
the target file(s) and imports the canonical rule catalog from ../lib/rules.py).

Rules implemented (design §5 / lines 182-186):
  FRONT-01  description outside 40-500 chars, OR not verb-first, OR missing
            "Use when" / "Not for".                                  [P1·H·E]
  FRONT-02  description is not English (CJK / high non-ASCII ratio).  [P2·H·E]
  FRONT-03  trigger overlap >= 0.5 Jaccard between two docs.          [P2·H·E]
            Multi-doc rule: pass `doc_id` + `others=[(id, desc), ...]`.
  FRONT-04  malformed/missing `name`, `version` (semver X.Y.Z), or a
            wholly ABSENT `description` (presence; quality is FRONT-01). [P1·H·A*]
  FRONT-05  resident vocabulary block must stay a glossary.           [P2·H·E]
            Deterministic surface is narrow — see FRONT-05 note below.

Scope follows the shipped templates: FRONT-* validates every document that
already starts with a frontmatter fence. A leading block is required only for an
exact ``SKILL.md`` and for ``.claude/rules/*.md``. Plain AGENTS.md, CLAUDE.md,
DESIGN.md, and ADRs are valid without frontmatter and are skipped. SKILL.md and
other frontmatter-bearing docs use name/version/description metadata; Claude rule
docs use their template's required ``paths`` field. Skill entrypoints require
the portable ``name`` + ``description`` frontmatter accepted by skill runtimes;
other frontmatter-bearing docs also require semver ``version``.

Stdlib-only. A finding dict is {rule, file, line, message}.
"""
import argparse
import json
import os
import re
import sys

# Description length window (design line 182; spec also caps at 1024/1536 but
# FRONT-01's house rule is the tighter 40-500 window).
_MIN_DESC, _MAX_DESC = 40, 500

# Semver X.Y.Z with optional -prerelease / +build (PEP-440-ish, kept simple).
_SEMVER = re.compile(r"^\d+\.\d+\.\d+([-+][0-9A-Za-z.\-]+)?$")

# First-word stop set: openers that mean the description is NOT verb-first.
_NON_VERB_OPENERS = {"a", "an", "the", "this", "that", "it", "these", "those"}

# FRONT-01 required phrase markers ("Use when" / "Not for"), case-insensitive.
_USE_WHEN = re.compile(r"use\s+when", re.IGNORECASE)
_NOT_FOR = re.compile(r"not\s+for", re.IGNORECASE)

# Word tokenizer for Jaccard (FRONT-03).
_WORD = re.compile(r"[a-z0-9]+")


def _parse_frontmatter(text):
    """Return (fields, line_of) from a leading `---` YAML-ish block.

    `fields` maps key -> value (block scalars `key: |` are joined with spaces).
    `line_of` maps key -> 1-based line number where the key was declared.
    Stdlib-only mini-parser for the `key: value` + `key: |` subset doc-steward
    frontmatter uses; not a general YAML parser.
    """
    fields, line_of = {}, {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return fields, line_of
    # Find the closing fence.
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return fields, line_of

    i = 1
    while i < end:
        raw = lines[i]
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", raw)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2)
        decl_line = i + 1  # 1-based
        if val.strip() in ("|", ">", "|-", ">-", "|+", ">+"):
            # Block scalar: gather more-indented following lines.
            block = []
            j = i + 1
            while j < end and (lines[j].strip() == "" or lines[j][:1] in (" ", "\t")):
                block.append(lines[j].strip())
                j += 1
            fields[key] = " ".join(b for b in block if b).strip()
            i = j
        else:
            fields[key] = val.strip()
            i += 1
        line_of[key] = decl_line
    return fields, line_of


def _has_leading_frontmatter(text):
    """True when `text` starts with a frontmatter opening fence."""
    lines = text.splitlines()
    return bool(lines and lines[0].strip() == "---")


def _frontmatter_policy(file):
    """Return ``skill-required``, ``rule-required``, ``strict``, or ``optional``.

    The sentinel used by direct unit/API calls retains the strict historical
    contract. Real file paths are classified by exact filename/path so a
    skill-shaped fixture such as ``SKILL.fixture.md`` is not accidentally made
    required.
    """
    if file == "<frontmatter>":
        return "strict"
    if os.path.basename(file) == "SKILL.md":
        return "skill-required"
    parts = os.path.normpath(str(file)).replace("\\", "/").split("/")
    for idx in range(len(parts) - 2):
        if (parts[idx:idx + 2] == [".claude", "rules"]
                and parts[-1].endswith(".md")):
            return "rule-required"
    return "optional"


def _non_english_ratio(s):
    """Fraction of letter-bearing chars that are non-ASCII (CJK etc.).

    Stdlib heuristic for FRONT-02: counts CJK/full-width and other non-ASCII
    letters against total alpha chars. Punctuation/digits/spaces are ignored.
    """
    alpha = [c for c in s if c.isalpha()]
    if not alpha:
        return 0.0
    non_ascii = sum(1 for c in alpha if ord(c) > 0x7F)
    return non_ascii / len(alpha)


def _is_verb_first(desc):
    """Heuristic verb-first test for FRONT-01.

    Deterministic surface: a description is treated as NOT verb-first when its
    first word is an article/pronoun/demonstrative (stop set) or a gerund
    (`-ing`) — both reliable non-imperative signals — else it is accepted.
    """
    m = re.match(r"\s*([A-Za-z][A-Za-z'-]*)", desc)
    if not m:
        return False
    first = m.group(1).lower()
    if first in _NON_VERB_OPENERS:
        return False
    if first.endswith("ing"):
        return False
    return True


def _owned_ids(rules):
    return {r["id"] for r in rules if r.get("checker") == "frontmatter_check"}


def _tokens(s):
    return set(_WORD.findall(s.lower()))


def _jaccard(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def check(frontmatter_text, rules, *, file="<frontmatter>", doc_id=None,
          others=None):
    """Emit FRONT-* violations for one document's frontmatter (pure / DI).

    Args:
      frontmatter_text: raw doc text (frontmatter block + body).
      rules: the canonical rule list; only ids whose `checker` is
             "frontmatter_check" are eligible to be emitted.
      file: label used in `file:line` evidence.
      doc_id / others: FRONT-03 multi-doc entry point. `others` is a list of
             (other_doc_id, other_description); FRONT-03 fires on Jaccard>=0.5.

    Returns a list of {rule, file, line, message} dicts.
    """
    owned = _owned_ids(rules)
    out = []

    def add(rid, line, msg):
        if rid in owned:
            out.append({"rule": rid, "file": file, "line": line, "message": msg})

    policy = _frontmatter_policy(file)
    has_frontmatter = _has_leading_frontmatter(frontmatter_text)
    if not has_frontmatter:
        if policy in ("skill-required", "rule-required", "strict"):
            add("FRONT-04", 1,
                "frontmatter: missing required leading `---` block")
        return out

    fields, line_of = _parse_frontmatter(frontmatter_text)
    desc = fields.get("description", "")

    desc_line = line_of.get("description", 1)

    # ---- FRONT-01: description quality ----
    # FRONT-01 audits the quality of a PRESENT description; a wholly absent
    # description is a FRONT-04 (required-frontmatter) concern, not a quality
    # one, so we don't double-report it here.
    if "FRONT-01" in owned and desc:
        problems = []
        n = len(desc)
        if n < _MIN_DESC or n > _MAX_DESC:
            problems.append(f"length {n} outside {_MIN_DESC}-{_MAX_DESC}")
        if not _is_verb_first(desc):
            problems.append("not verb-first")
        if not _USE_WHEN.search(desc):
            problems.append('missing "Use when"')
        if not _NOT_FOR.search(desc):
            problems.append('missing "Not for"')
        if problems:
            add("FRONT-01", desc_line,
                "description quality: " + "; ".join(problems))

    # ---- FRONT-02: English-only description ----
    if "FRONT-02" in owned and desc and _non_english_ratio(desc) >= 0.2:
        add("FRONT-02", desc_line,
            "description is not English; move multilingual triggers to a "
            "separate field")

    # ---- FRONT-04: required schema + semver validation ----
    # SKILL.md uses the portable name/description schema accepted by skill
    # runtimes. Optional docs that elect to carry frontmatter use the strict
    # name/version/description schema. `.claude/rules/*.md` follows its shipped
    # template instead: the block itself and a non-empty `paths` field are
    # required. Any present version is validated. FRONT-01 owns QUALITY of a
    # present description.
    if "FRONT-04" in owned:
        meta_problems = []
        ver = fields.get("version", "").strip().strip('"').strip("'")
        specific_lines = []
        if policy == "rule-required":
            if not fields.get("paths", "").strip():
                meta_problems.append("missing `paths`")
            if "version" in fields and not ver:
                meta_problems.append("empty `version`")
                specific_lines.append(line_of.get("version", 1))
        else:
            name = fields.get("name", "").strip()
            if not name:
                meta_problems.append("missing `name`")
                if "name" in fields:
                    specific_lines.append(line_of.get("name", 1))
            if policy != "skill-required" and not ver:
                meta_problems.append("missing `version`")
                if "version" in fields:
                    specific_lines.append(line_of.get("version", 1))
            if not desc:
                meta_problems.append("missing `description`")
                if "description" in fields:
                    specific_lines.append(line_of.get("description", 1))
        if ver and not _SEMVER.match(ver):
            meta_problems.append(f"`version` {ver!r} is not semver X.Y.Z")
            specific_lines.append(line_of.get("version", 1))
        if meta_problems:
            add("FRONT-04", specific_lines[0] if specific_lines else 1,
                "frontmatter: " + "; ".join(meta_problems))

    # ---- FRONT-03: cross-doc trigger overlap (needs >=2 docs) ----
    if "FRONT-03" in owned and desc and others:
        for other_id, other_desc in others:
            if not other_desc:
                continue
            j = _jaccard(desc, other_desc)
            if j >= 0.5:
                add("FRONT-03", desc_line,
                    f"trigger overlap {j:.0%} (Jaccard) with "
                    f"{other_id!r} >= 50% — discoverability collision")

    # ---- FRONT-05: vocabulary block must be a glossary ----
    # Deterministic surface is narrow (design line 186). We only flag the
    # unambiguous case: a `vocabulary:`/`vocab:` frontmatter entry whose value
    # is a bare term with no `term: definition` glossary shape. Richer
    # glossary-vs-prose judgment is an inspector concern, not deterministic.
    if "FRONT-05" in owned:
        for vk in ("vocabulary", "vocab"):
            if vk in fields and fields[vk] and ":" not in fields[vk]:
                add("FRONT-05", line_of.get(vk, 1),
                    f"`{vk}` block is not a glossary (no `term: definition`)")

    return out


# --------------------------------------------------------------------------
# CLI: the ONLY place that loads real assets (reads files + imports the catalog).
# --------------------------------------------------------------------------
def _load_rules():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "lib"))
    import rules  # noqa: E402
    return rules.RULES


def _main(argv=None):
    parser = argparse.ArgumentParser(description="FRONT-* frontmatter checker")
    parser.add_argument("paths", nargs="+", help="markdown file(s) to check")
    parser.add_argument("--json", action="store_true",
                        help='emit {"passed": bool, "violations": [...]}')
    args = parser.parse_args(argv)

    rules = _load_rules()
    # Build the (doc_id, description) corpus for FRONT-03 cross-doc comparison.
    corpus = []
    for p in args.paths:
        with open(p, encoding="utf-8") as fh:
            fields, _ = _parse_frontmatter(fh.read())
        corpus.append((p, fields.get("description", "")))

    violations = []
    for p in args.paths:
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        others = [(oid, od) for (oid, od) in corpus if oid != p]
        violations.extend(check(text, rules, file=p, doc_id=p, others=others))

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
