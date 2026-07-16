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


if __name__ == "__main__":
    unittest.main()
