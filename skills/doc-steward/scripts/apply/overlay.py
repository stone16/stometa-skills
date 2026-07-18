#!/usr/bin/env python3
"""Resolve optional, explicit doc-steward configuration.

The public core has no implicit per-user configuration location. Callers either
pass a config path explicitly or use the safe defaults. The default learning
sink is ``noop`` and learning remains disabled until deliberately configured.

DI seam: `merge(overlay, defaults)` is PURE — it takes parsed dicts and returns a
dict. Only `load_overlay` / `resolve_config` touch disk, and only the supplied
path. YAML is parsed with `yaml.safe_load` (never `yaml.load`). PyYAML is loaded
lazily, so the default no-config path remains stdlib-only.
"""
import os

# Safe defaults for an absent or omitted config.
#   * sink: 'noop' — LEARN is OFF until a sink is configured (sinks/noop.py).
#   * learn_enabled: False — belt-and-suspenders with sink=noop.
#   * tier / profile: None — fall through to auto-detect (tier_assess.py).
#   * private_paths / redaction_terms / rule_toggles: empty.
DEFAULTS = {
    "sink": "noop",
    "sink_path": None,
    "learn_enabled": False,
    "tier": None,
    "profile": None,
    "private_paths": [],
    "redaction_terms": [],
    "rule_toggles": {},
}


def load_overlay(path):
    """Parse a config YAML file, or return ``{}`` when no path is supplied.

    Uses `yaml.safe_load`. An empty/blank file (which parses to None) is
    normalized to {} so callers always get a dict. A non-mapping top-level
    document is rejected (it is a config error, not a silent {}).
    """
    if not path:
        return {}
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required only when an explicit --config path is used"
        ) from exc
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping, got {type(data).__name__}")
    return data


def merge(config, defaults=None):
    """Return explicit config values layered over safe defaults (pure / DI).

    A key present in `config` (even falsy, e.g. False/0/"") wins; a key absent
    from `config` keeps the default. Operates only on the supplied dicts — no
    disk, no globals. `defaults` falls back to DEFAULTS when not supplied.
    """
    base = dict(DEFAULTS if defaults is None else defaults)
    base.update(config or {})
    return base


def resolve_config(path=None, defaults=None):
    """Load only the explicitly supplied path and merge it over defaults."""
    return merge(load_overlay(path), defaults)


# --------------------------------------------------------------------------
# CLI — print the resolved config for inspection (does not load a sink).
# --------------------------------------------------------------------------
def _main(argv=None):
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Resolve an explicit doc-steward config over safe defaults.")
    ap.add_argument("--config", default=None,
                    help="optional YAML config path; omitted uses safe defaults")
    args = ap.parse_args(argv)
    print(json.dumps(resolve_config(args.config), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
