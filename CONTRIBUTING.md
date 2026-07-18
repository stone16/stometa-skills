# Contributing

Stometa Skills accepts three kinds of changes:

1. Promotion PRs for skills with real-use evidence.
2. Improvements to an existing skill, its evaluations, or its portability.
3. Repository documentation and validation fixes.

## Before proposing a skill

Open a skill proposal first. Include:

- the repeated job the skill handles;
- the repositories or distinct contexts where it has been used;
- why an existing public skill cannot absorb the change;
- what remains repository-specific;
- provenance and license information;
- known side effects and required permissions.

The proposal may be declined even when the content is safe to publish. The public catalog optimizes for maintained, portable behavior rather than volume.

## Promotion PR contract

A promotion PR must include:

- `skills/<name>/SKILL.md` and required bundled resources;
- an entry in `catalog/skills.yaml`;
- membership in at least one catalog collection;
- `evidence/<name>.yaml` conforming to the promotion evidence schema;
- trigger and non-trigger evaluation cases under `evals/<name>/`;
- license and attribution material for adapted work;
- confirmation that the previous source was removed or replaced by an explicit pointer/profile.

## Development checks

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate_repo.py
python3 -m unittest discover -s tests
python3 -m pytest skills -q
```

Use an English, atomic commit message. Do not add `Co-Authored-By` lines.
