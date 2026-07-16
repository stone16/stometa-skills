#!/usr/bin/env python3
"""Validate the public repository contract without modifying the checkout."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised by operator setup
    raise SystemExit("PyYAML is required: python3 -m pip install -r requirements-dev.txt") from exc

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - exercised by operator setup
    raise SystemExit("jsonschema is required: python3 -m pip install -r requirements-dev.txt") from exc


ROOT = Path(__file__).resolve().parents[1]
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_LIFECYCLES = {"stable", "deprecated"}
ALLOWED_COMPATIBILITY = {"verified", "expected", "unsupported"}
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".sh", ".js", ".mjs", ".ts"}
FORBIDDEN_TEXT = (
    "/" + "Users/",
    "C:" + "\\Users\\",
    "leilei-" + "skillsets",
    "stometa-" + "skillset",
    "-----BEGIN " + "PRIVATE KEY-----",
)


class ValidationError(Exception):
    pass


def load_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{path.relative_to(ROOT)}: expected a mapping")
    return data


def parse_frontmatter(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValidationError(f"{path.relative_to(ROOT)}: missing YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: unclosed YAML frontmatter") from exc
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{path.relative_to(ROOT)}: frontmatter must be a mapping")
    return data


def skill_directories() -> dict[str, Path]:
    root = ROOT / "skills"
    result: dict[str, Path] = {}
    for skill_md in root.rglob("SKILL.md"):
        relative = skill_md.relative_to(root)
        if len(relative.parts) != 2:
            raise ValidationError(f"{skill_md.relative_to(ROOT)}: skills must be one directory deep")
        name = relative.parts[0]
        if not NAME_RE.fullmatch(name):
            raise ValidationError(f"{skill_md.relative_to(ROOT)}: invalid skill directory name")
        result[name] = skill_md.parent
    return result


def validate_skill(name: str, path: Path, catalog_entry: dict) -> None:
    frontmatter = parse_frontmatter(path / "SKILL.md")
    if frontmatter.get("name") != name:
        raise ValidationError(f"skills/{name}/SKILL.md: frontmatter name must equal directory name")
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValidationError(f"skills/{name}/SKILL.md: description is required")
    if catalog_entry.get("path") != f"skills/{name}":
        raise ValidationError(f"catalog/skills.yaml: {name}.path must be skills/{name}")
    if catalog_entry.get("lifecycle") not in ALLOWED_LIFECYCLES:
        raise ValidationError(f"catalog/skills.yaml: {name} has invalid lifecycle")
    maintainers = catalog_entry.get("maintainers")
    if not isinstance(maintainers, list) or not maintainers:
        raise ValidationError(f"catalog/skills.yaml: {name} requires a maintainer")
    provenance = catalog_entry.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("kind") not in {"original", "adapted"}:
        raise ValidationError(f"catalog/skills.yaml: {name} requires provenance")
    if provenance.get("kind") == "adapted" and not all(
        provenance.get(field) for field in ("upstream", "upstream_commit")
    ):
        raise ValidationError(f"catalog/skills.yaml: adapted skill {name} requires pinned upstream")
    compatibility = catalog_entry.get("compatibility")
    if not isinstance(compatibility, dict) or any(
        value not in ALLOWED_COMPATIBILITY for value in compatibility.values()
    ):
        raise ValidationError(f"catalog/skills.yaml: {name} has invalid compatibility state")
    if not (ROOT / "evidence" / f"{name}.yaml").is_file():
        raise ValidationError(f"evidence/{name}.yaml: missing promotion evidence")
    if not (ROOT / "evals" / name).is_dir():
        raise ValidationError(f"evals/{name}: stable public skills require evaluations")
    if (path / "scripts").is_dir() and not (path / "tests").is_dir():
        raise ValidationError(f"skills/{name}: scripts require a tests directory")


def validate_catalogs() -> None:
    skill_catalog = load_yaml(ROOT / "catalog" / "skills.yaml")
    collection_catalog = load_yaml(ROOT / "catalog" / "collections.yaml")
    if skill_catalog.get("schema_version") != 1 or collection_catalog.get("schema_version") != 1:
        raise ValidationError("catalog schema_version must be 1")
    catalog_skills = skill_catalog.get("skills")
    collections = collection_catalog.get("collections")
    if not isinstance(catalog_skills, dict) or not isinstance(collections, dict):
        raise ValidationError("catalog skills and collections must be mappings")
    directories = skill_directories()
    if set(catalog_skills) != set(directories):
        missing = sorted(set(directories) - set(catalog_skills))
        stale = sorted(set(catalog_skills) - set(directories))
        raise ValidationError(f"catalog mismatch: missing={missing}, stale={stale}")
    for name, path in directories.items():
        entry = catalog_skills[name]
        if not isinstance(entry, dict):
            raise ValidationError(f"catalog/skills.yaml: {name} must be a mapping")
        validate_skill(name, path, entry)
    for collection_id, collection in collections.items():
        if not NAME_RE.fullmatch(collection_id) or not isinstance(collection, dict):
            raise ValidationError(f"catalog/collections.yaml: invalid collection {collection_id}")
        members = collection.get("skills")
        if not isinstance(members, list) or len(members) != len(set(members)):
            raise ValidationError(f"catalog/collections.yaml: {collection_id} has invalid members")
        unknown = sorted(set(members) - set(catalog_skills))
        if unknown:
            raise ValidationError(f"catalog/collections.yaml: {collection_id} references {unknown}")
        deprecated = sorted(
            member for member in members if catalog_skills[member].get("lifecycle") == "deprecated"
        )
        if deprecated:
            raise ValidationError(
                f"catalog/collections.yaml: {collection_id} includes deprecated skills {deprecated}"
            )


def validate_public_boundary() -> None:
    excluded = {".git", ".venv", "__pycache__"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_TEXT:
            if marker in text:
                raise ValidationError(f"{path.relative_to(ROOT)}: forbidden private marker detected")


def validate_schema_files() -> None:
    for path in (ROOT / "schemas").glob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"{path.relative_to(ROOT)}: invalid JSON: {exc}") from exc


def validate_evidence() -> None:
    schema_path = ROOT / "schemas" / "promotion-evidence.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as exc:
        raise ValidationError(
            f"{schema_path.relative_to(ROOT)}: invalid JSON Schema: {exc.message}"
        ) from exc

    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    )
    for path in sorted((ROOT / "evidence").glob("*.yaml")):
        evidence = load_yaml(path)
        if evidence.get("skill") != path.stem:
            raise ValidationError(
                f"{path.relative_to(ROOT)}: skill must match the evidence filename"
            )
        errors = sorted(validator.iter_errors(evidence), key=lambda error: list(error.absolute_path))
        if errors:
            error = errors[0]
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            raise ValidationError(
                f"{path.relative_to(ROOT)}: schema error at {location}: {error.message}"
            )


def main() -> int:
    try:
        validate_catalogs()
        validate_public_boundary()
        validate_schema_files()
        validate_evidence()
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("OK: repository contract validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
