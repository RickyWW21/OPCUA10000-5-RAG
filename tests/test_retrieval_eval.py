import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tests.helpers import write_knowledge_base
from tools.evaluate_retrieval import evaluate


def _write_manifest(root: Path, sha256: str = "abc") -> None:
    (root / "source").mkdir(parents=True, exist_ok=True)
    (root / "source" / "source_manifest.json").write_text(
        json.dumps({"doc": "OPC-10000-5", "sha256": sha256}), encoding="utf-8"
    )


def _write_fixture(root: Path, cases: list[dict]) -> Path:
    fixture = root / "eval.json"
    fixture.write_text(json.dumps(cases), encoding="utf-8")
    return fixture


class RetrievalEvaluationTests(unittest.TestCase):
    def test_evaluate_reports_recall_at_one_and_three(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "eval.json"
            fixture.write_text(
                json.dumps(
                    [
                        {"question": "one", "expected_ids": ["a"]},
                        {"question": "two", "expected_ids": ["b"]},
                    ]
                ),
                encoding="utf-8",
            )
            root = Path(directory) / "root"
            (root / "source").mkdir(parents=True)
            (root / "source" / "source_manifest.json").write_text(
                json.dumps({"doc": "OPC-10000-5"}), encoding="utf-8"
            )

            import tools.evaluate_retrieval as module

            fake = Mock()
            fake.mode = "fts"
            fake.retrieve.side_effect = [
                [Mock(id="a"), Mock(id="x")],
                [Mock(id="x"), Mock(id="b")],
            ]
            with patch.object(module, "create_retriever", return_value=fake):
                report = evaluate(root, fixture)

            self.assertEqual(report["queries"], 2)
            self.assertEqual(report["recall_at_1"], 0.5)
            self.assertEqual(report["recall_at_3"], 1.0)
            self.assertEqual(report["requested_mode"], "fts")
            self.assertEqual(report["actual_modes"], ["fts"])

    def test_true_recall_hit_and_mrr_distinguish_multiple_expected_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            fixture = temporary / "eval.json"
            fixture.write_text(
                json.dumps(
                    [
                        {"question": "one", "expected_ids": ["a", "b"]},
                        {
                            "question": "unanswerable",
                            "expected_ids": [],
                            "category": "out_of_scope",
                        },
                        {"question": "two", "expected_ids": ["c", "d"]},
                    ]
                ),
                encoding="utf-8",
            )
            root = temporary / "root"
            _write_manifest(root)

            import tools.evaluate_retrieval as module

            fake = Mock()
            fake.mode = "fts"
            fake.retrieve.side_effect = [
                [Mock(id="a"), Mock(id="x")],
                [Mock(id="a")],
                [Mock(id="x"), Mock(id="c")],
            ]
            with patch.object(module, "create_retriever", return_value=fake):
                report = evaluate(root, fixture)

            self.assertEqual(report["queries"], 2)
            self.assertEqual(report["case_count"], 3)
            self.assertEqual(report["recall_at_1"], 0.25)
            self.assertEqual(report["recall_at_3"], 0.5)
            self.assertEqual(report["hit_at_1"], 0.5)
            self.assertEqual(report["hit_at_3"], 1.0)
            self.assertEqual(report["mrr"], 0.75)
            self.assertEqual(
                [result["question"] for result in report["results"]],
                ["one", "two"],
            )
            self.assertEqual(report["diagnostics"]["out_of_scope"]["queries"], 1)
            diagnostic = report["diagnostics"]["out_of_scope"]["results"][0]
            self.assertEqual(diagnostic["retrieved_ids"], ["a"])
            self.assertTrue(diagnostic["retrieved_nonempty"])
            self.assertNotIn("success", diagnostic)
            self.assertNotIn("hit_at_1", diagnostic)

    def test_fixture_validation_happens_before_building_retriever(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_knowledge_base(root)
            _write_manifest(root, "abc")
            invalid_cases = [
                [{"question": "q", "expected_ids": ["a", "a"]}],
                [{"question": "q", "expected_ids": ["a"], "category": "nonsense"}],
                [{"question": "q", "expected_ids": []}],
                [{"question": "q", "expected_ids": ["a"], "top_k": True}],
                [{"question": "q", "expected_ids": ["a"], "relationship_depth": -1}],
                [{"question": "q", "expected_ids": [1]}],
            ]

            import tools.evaluate_retrieval as module

            for cases in invalid_cases:
                with self.subTest(cases=cases):
                    fixture = _write_fixture(root, cases)
                    with patch.object(module, "create_retriever") as factory:
                        with self.assertRaises(ValueError):
                            evaluate(root, fixture)
                        factory.assert_not_called()

    def test_diagnostic_category_requires_empty_expected_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_manifest(root)
            fixture = _write_fixture(
                root,
                [
                    {
                        "question": "What is its data type?",
                        "expected_ids": ["ObjectType:ServerType"],
                        "category": "context_dependent",
                    }
                ],
            )
            with self.assertRaises(ValueError):
                evaluate(root, fixture)


if __name__ == "__main__":
    unittest.main()
