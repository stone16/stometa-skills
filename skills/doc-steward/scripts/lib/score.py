#!/usr/bin/env python3
"""Tiered weighted-composite scorer for doc-steward audits. Stdlib-only, pure/DI.

A doc-steward audit scores several dimensions (structure, staleness, taxonomy,
links, frontmatter, ...). Not every dimension is required at every tier — a
Simple repo is not graded on the dimensions a Complex repo is. The load-bearing
behaviour is WEIGHT REDISTRIBUTION: a dimension that is not required at this tier
is dropped, and its base weight is redistributed proportionally across the
dimensions that ARE required. A skipped dimension therefore can never drag the
composite down — it simply doesn't count.

`score(findings, required_dims, weights)` is pure: per-dimension scores and the
tier's required dimension list go in; a clamped 0-10 composite and a verdict come
out. `weights` defaults to the module-level DEFAULT_WEIGHTS (DI seam); callers
may pass their own table. No I/O.
"""

# Base weights over ALL dimensions; must sum to 1.0. The DI default — callers may
# override by passing their own `weights` table to score().
DEFAULT_WEIGHTS = {
    "structure": 0.25,
    "staleness": 0.15,
    "taxonomy": 0.20,
    "links": 0.15,
    "frontmatter": 0.10,
    "verification": 0.10,
    "decisions": 0.05,
}

# Verdict thresholds on the 0-10 composite.
PASS_THRESHOLD = 8.0
FAIL_THRESHOLD = 5.0


def verdict_for(composite):
    """Map a 0-10 composite to PASS | PASS_WITH_CONCERNS | FAIL."""
    if composite >= PASS_THRESHOLD:
        return "PASS"
    if composite >= FAIL_THRESHOLD:
        return "PASS_WITH_CONCERNS"
    return "FAIL"


def _redistributed_weights(required_dims, weights):
    """Return effective weights over `required_dims` that sum to 1.0.

    The base weights of the (skipped) non-required dimensions are redistributed
    proportionally to each required dimension's share of the required base mass.
    """
    base = {d: weights[d] for d in required_dims}  # KeyError on unknown dim
    total = sum(base.values())
    if total <= 0:
        # Degenerate base mass (e.g. all-zero weights): fall back to uniform.
        n = len(required_dims)
        return {d: 1.0 / n for d in required_dims}
    return {d: w / total for d, w in base.items()}


def score(findings, required_dims, weights=None):
    """Compute the tiered composite and verdict.

    findings      — dict dimension -> per-dimension score (0-10). A required
                    dimension absent from `findings` counts as 0 (a gap is a
                    finding, not a free pass).
    required_dims — the dimensions graded at this tier. Skipped dims redistribute
                    their weight across these.
    weights       — base weight table over all dimensions (defaults to
                    DEFAULT_WEIGHTS). Every required dim must appear here.

    Returns (composite: float in [0,10], verdict: str).
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    if not required_dims:
        raise ValueError("required_dims must be non-empty")
    unknown = [d for d in required_dims if d not in weights]
    if unknown:
        raise ValueError(f"unknown required dimension(s): {unknown}")

    eff = _redistributed_weights(required_dims, weights)
    composite = sum(eff[d] * float(findings.get(d, 0)) for d in required_dims)
    composite = max(0.0, min(10.0, composite))
    return composite, verdict_for(composite)


if __name__ == "__main__":
    demo = {d: 8 for d in DEFAULT_WEIGHTS}
    c, v = score(demo, list(DEFAULT_WEIGHTS))
    print(f"all-8 baseline: composite={c:.2f} verdict={v}")
