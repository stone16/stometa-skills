"""Promotion contracts for the public doc-steward package."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "doc-steward"


class DocStewardPromotionTest(unittest.TestCase):
    def test_evaluation_counts_match_promotion_evidence(self) -> None:
        evidence = yaml.safe_load(
            (ROOT / "evidence" / "doc-steward.yaml").read_text(encoding="utf-8")
        )
        expected = {
            "trigger": "trigger.yaml",
            "non_trigger": "non-trigger.yaml",
            "behavior": "behavior.yaml",
        }
        for evidence_key, filename in expected.items():
            evaluation = yaml.safe_load(
                (ROOT / "evals" / "doc-steward" / filename).read_text(encoding="utf-8")
            )
            cases = evaluation.get("cases")
            self.assertIsInstance(cases, list)
            self.assertEqual(len(cases), len({case["id"] for case in cases}))
            self.assertEqual(evidence["tests"][evidence_key], len(cases))

    def test_clean_copy_package_and_cli_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / ".agents" / "skills"
            installed = skills_root / "doc-steward"
            skills_root.mkdir(parents=True)
            shutil.copytree(SKILL, installed, symlinks=True)

            entrypoints = sorted(skills_root.glob("*/SKILL.md"))
            self.assertEqual(entrypoints, [installed / "SKILL.md"])
            frontmatter = entrypoints[0].read_text(encoding="utf-8").split("---", 2)[1]
            self.assertEqual(yaml.safe_load(frontmatter)["name"], "doc-steward")

            fixture = installed / "scripts" / "checks" / "fixtures" / "sample-repo"
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(installed / "scripts" / "checks" / "doc_lint.py"),
                    "--target",
                    str(fixture),
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertIn(result.returncode, (0, 1), result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(
                {"passed", "tier", "composite", "grade", "findings", "skipped"}
                <= payload.keys()
            )

    def test_recorded_python_test_counts_match_source_tree(self) -> None:
        """Prevent promotion evidence from silently drifting after new tests."""
        evidence = yaml.safe_load(
            (ROOT / "evidence" / "doc-steward.yaml").read_text(encoding="utf-8")
        )

        def count_tests(directory: Path) -> int:
            total = 0
            for path in directory.rglob("test_*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                total += sum(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name.startswith("test_")
                    for node in ast.walk(tree)
                )
            return total

        skill_count = count_tests(ROOT / "skills")
        repository_count = skill_count + count_tests(ROOT / "tests")
        self.assertEqual(evidence["tests"]["deterministic_unit"], skill_count)
        self.assertEqual(evidence["tests"]["repository_pytest"], repository_count)
        self.assertEqual(
            evidence["tests"]["promotion_unittest"],
            count_tests(ROOT / "tests"),
        )


if __name__ == "__main__":
    unittest.main()
