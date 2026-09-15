import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from tools.evaluate_retrieval import evaluate


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

            original = module.Part5Retriever
            fake = Mock()
            fake.retrieve.side_effect = [
                [Mock(id="a"), Mock(id="x")],
                [Mock(id="x"), Mock(id="b")],
            ]
            module.Part5Retriever = Mock(return_value=fake)
            try:
                report = evaluate(root, fixture)
            finally:
                module.Part5Retriever = original

            self.assertEqual(report["queries"], 2)
            self.assertEqual(report["recall_at_1"], 0.5)
            self.assertEqual(report["recall_at_3"], 1.0)


if __name__ == "__main__":
    unittest.main()
