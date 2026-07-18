#!/usr/bin/env python3
"""STRUCT-06 deterministic checker — required resident document presence.

The checker distinguishes two target profiles using only exact-root files:

* ``skill-package`` — ``<target>/SKILL.md`` is the resident entrypoint. Repo
  charter, Claude-rule, and ADR presence requirements do not apply.
* ``repository`` — tiered root-charter requirements apply. Nested charters or
  nested ``SKILL.md`` files never satisfy the root contract.

Pure/DI apart from reading filesystem metadata. It never creates or edits a
document. A finding is emitted only when the injected catalog assigns
``STRUCT-06`` to ``presence_check``.
"""
import glob
import os


_TIERS = {"Simple", "Standard", "Complex"}


def target_profile(target_root):
    """Return ``skill-package`` iff an exact-root SKILL.md exists."""
    root = os.path.abspath(os.fspath(target_root))
    return ("skill-package"
            if os.path.isfile(os.path.join(root, "SKILL.md"))
            else "repository")


def _owned(rules):
    return any(rule.get("id") == "STRUCT-06"
               and rule.get("checker") == "presence_check"
               for rule in rules)


def _markdown_exists(directory):
    return any(os.path.isfile(path)
               for path in glob.glob(os.path.join(directory, "*.md")))


def missing_requirements(target_root, *, tier):
    """Return ``(profile, root_charter_present, missing_labels)``.

    Labels are repository-relative requirement surfaces suitable for report
    output. ``tier`` is explicit so callers own classification precedence.
    """
    if tier not in _TIERS:
        raise ValueError("tier must be Simple, Standard, or Complex")

    root = os.path.abspath(os.fspath(target_root))
    profile = target_profile(root)
    if profile == "skill-package":
        return profile, True, []

    has_agents = os.path.isfile(os.path.join(root, "AGENTS.md"))
    has_claude = os.path.isfile(os.path.join(root, "CLAUDE.md"))
    root_charter_present = has_agents or has_claude
    missing = []

    if tier == "Simple":
        if not root_charter_present:
            missing.append("AGENTS.md or CLAUDE.md")
    else:
        if not has_agents:
            missing.append("AGENTS.md")
        if not has_claude:
            missing.append("CLAUDE.md")

    if tier == "Complex":
        if not _markdown_exists(os.path.join(root, ".claude", "rules")):
            missing.append(".claude/rules/*.md")
        if not _markdown_exists(os.path.join(root, "docs", "decisions")):
            missing.append("docs/decisions/*.md")

    return profile, root_charter_present, missing


def check(target_root, rules, *, tier):
    """Emit one aggregate STRUCT-06 finding for missing required surfaces."""
    if not _owned(rules):
        return []

    root = os.path.abspath(os.fspath(target_root))
    profile, root_charter_present, missing = missing_requirements(root, tier=tier)
    if not missing:
        return []

    return [{
        "rule": "STRUCT-06",
        "file": root,
        "line": 1,
        "message": (f"{tier} {profile} is missing required document surface(s): "
                    + ", ".join(missing)),
        "target_profile": profile,
        "missing": missing,
        "root_charter_present": root_charter_present,
    }]
