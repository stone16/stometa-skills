---
description: |
  Process the inputs into outputs. Use when running the pipeline locally.
  Not for production deployments which require the hardened entrypoint.
version: 1.0
---

# FRONT-04 bad fixture

`name` is missing entirely and `version` is "1.0" (not semver X.Y.Z). The
description itself is well-formed so only FRONT-04 should fire here.
