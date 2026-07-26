from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_repo", ROOT / "scripts" / "validate_repo.py")
assert SPEC and SPEC.loader
validate_repo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_repo)


class RepositoryContractTest(unittest.TestCase):
    def test_current_checkout_is_valid(self) -> None:
        self.assertEqual(validate_repo.main(), 0)

    def test_skill_name_contract(self) -> None:
        self.assertIsNotNone(validate_repo.NAME_RE.fullmatch("skill-steward"))
        self.assertIsNone(validate_repo.NAME_RE.fullmatch("Skill_Steward"))

    def test_compatibility_vocabulary_is_closed(self) -> None:
        self.assertEqual(
            validate_repo.ALLOWED_COMPATIBILITY,
            {"verified", "expected", "unsupported"},
        )

    def test_promotion_evidence_schema_is_valid(self) -> None:
        validate_repo.validate_evidence()

    def test_every_stable_skill_is_collected(self) -> None:
        skills = validate_repo.load_yaml(ROOT / "catalog" / "skills.yaml")["skills"]
        collections = validate_repo.load_yaml(
            ROOT / "catalog" / "collections.yaml"
        )["collections"]
        stable = {
            name for name, entry in skills.items() if entry["lifecycle"] == "stable"
        }
        collected = {
            name for collection in collections.values() for name in collection["skills"]
        }
        self.assertLessEqual(stable, collected)

    def test_stable_skills_have_trigger_and_non_trigger_cases(self) -> None:
        skills = validate_repo.load_yaml(ROOT / "catalog" / "skills.yaml")["skills"]
        for name, entry in skills.items():
            if entry["lifecycle"] != "stable":
                continue
            for filename in ("trigger.yaml", "non-trigger.yaml"):
                evaluation = validate_repo.load_yaml(ROOT / "evals" / name / filename)
                cases = evaluation["cases"]
                self.assertTrue(cases)
                self.assertEqual(len(cases), len({case["id"] for case in cases}))


if __name__ == "__main__":
    unittest.main()
