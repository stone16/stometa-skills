# AGENTS.md — Stometa Skills

## Product boundary

This repository is the canonical public source for promoted Stometa agent skills. It is not an incubation workspace, personal dotfiles repository, or generated mirror of a private repository.

## Invariants

1. Keep published skills flat at `skills/<skill-name>/SKILL.md`.
2. Keep incubating, private, customer-specific, and deprecated experiments out of `skills/`.
3. Require `name` and `description` frontmatter. Keep platform-specific invocation policy under `agents/` when possible.
4. Add every published skill to `catalog/skills.yaml` and one or more entries in `catalog/collections.yaml`.
5. Add `evidence/<skill-name>.yaml` for every published skill.
6. Transfer canonical ownership during promotion. Delete the old implementation or replace it with an explicit profile/pointer.
7. Never commit secrets, customer identifiers, personal paths, private repository names, raw prompts, or private task output.
8. Keep runtime adapters thin. Do not duplicate skill bodies for different harnesses.

## Required checks

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate_repo.py
python3 -m unittest discover -s tests
```

## Git workflow

- Use a branch and pull request for every change after repository initialization.
- Keep commits atomic and in English.
- Never use `--no-verify`, force-push, or add `Co-Authored-By` lines.
- A skill promotion PR must follow `docs/promotion-policy.md` and the pull request template.

## Documentation

- State evidence level and known limits explicitly.
- Do not advertise installation or compatibility before the corresponding smoke test exists.
- Update English and Chinese entry documentation together when product behavior changes.

