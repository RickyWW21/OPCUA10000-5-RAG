import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from opcua_kb.embeddings import EmbeddingError
from opcua_kb.vector_index import VectorIndex
from tests.helpers import write_knowledge_base
from tools.evaluate_retrieval import EvaluationError, evaluate


class FakeProvider:
    """Deterministic local provider used by real-artifact evaluation tests."""

    model_name = "fake-model"
    dimension = 2

    def embed(self, texts):
        vectors = {"server metadata": [1.0, 0.0], "other metadata": [0.0, 1.0]}
        return [vectors.get(text, [1.0, 0.0]) for text in texts]


class BrokenProvider(FakeProvider):
    def embed(self, texts):
        raise EmbeddingError("broken local model")


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

            original = module.Part5Retriever
            fake = Mock()
            fake.last_mode = "fts"
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
            fake.last_mode = "fts"
            fake.retrieve.side_effect = [
                [Mock(id="a"), Mock(id="x")],
                [Mock(id="a")],
                [Mock(id="x"), Mock(id="c")],
            ]
            with patch.object(module, "Part5Retriever", Mock(return_value=fake)):
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

    def test_hybrid_uses_real_vector_artifact_and_reports_actual_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_knowledge_base(root)
            _write_manifest(root, "abc")
            provider = FakeProvider()
            VectorIndex(root, source_hash="abc").build(
                [
                    {
                        "id": "ObjectType:ServerType",
                        "type": "entity",
                        "title": "ServerType",
                        "text": "server metadata",
                        "doc": "OPC-10000-5",
                    }
                ],
                provider,
                source_hash="abc",
            )
            fixture = _write_fixture(
                root,
                [{"question": "ServerType", "expected_ids": ["ObjectType:ServerType"]}],
            )

            import tools.evaluate_retrieval as module

            with patch.object(
                module, "SentenceTransformerEmbeddingProvider", return_value=provider
            ):
                report = evaluate(root, fixture, retrieval_mode="hybrid")

            self.assertEqual(report["requested_mode"], "hybrid")
            self.assertEqual(report["actual_modes"], ["hybrid"])
            self.assertEqual(report["results"][0]["actual_mode"], "hybrid")
            self.assertEqual(report["results"][0]["requested_mode"], "hybrid")
            self.assertEqual(report["recall_at_1"], 1.0)
            self.assertEqual(
                report["provenance"]["retrieval"]["embedding_model"], "fake-model"
            )
            self.assertEqual(
                report["provenance"]["retrieval"]["vector_index"]["source_hash"], "abc"
            )

    def test_hybrid_errors_instead_of_accepting_actual_fts_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_knowledge_base(root)
            _write_manifest(root, "abc")
            VectorIndex(root, source_hash="abc").build(
                [
                    {
                        "id": "ObjectType:ServerType",
                        "type": "entity",
                        "title": "ServerType",
                        "text": "server metadata",
                        "doc": "OPC-10000-5",
                    }
                ],
                FakeProvider(),
                source_hash="abc",
            )
            fixture = _write_fixture(
                root,
                [{"question": "ServerType", "expected_ids": ["ObjectType:ServerType"]}],
            )

            import tools.evaluate_retrieval as module

            with patch.object(
                module,
                "SentenceTransformerEmbeddingProvider",
                return_value=BrokenProvider(),
            ):
                with self.assertRaisesRegex(EvaluationError, "hybrid|fallback"):
                    evaluate(root, fixture, retrieval_mode="hybrid")

    def test_hybrid_missing_artifacts_error_before_loading_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_knowledge_base(root)
            _write_manifest(root, "abc")
            fixture = _write_fixture(
                root,
                [{"question": "ServerType", "expected_ids": ["ObjectType:ServerType"]}],
            )

            import tools.evaluate_retrieval as module

            with patch.object(module, "SentenceTransformerEmbeddingProvider") as provider:
                with self.assertRaisesRegex(EvaluationError, "vector|index|embedding"):
                    evaluate(root, fixture, retrieval_mode="hybrid")
                provider.assert_not_called()

    def test_empty_vector_artifact_cannot_be_reported_as_hybrid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_knowledge_base(root)
            _write_manifest(root, "abc")
            VectorIndex(root).build([], FakeProvider(), source_hash="abc")
            fixture = _write_fixture(
                root, [{"question": "ServerType", "expected_ids": ["ObjectType:ServerType"]}]
            )
            with patch(
                "tools.evaluate_retrieval.SentenceTransformerEmbeddingProvider",
                return_value=FakeProvider(),
            ):
                with self.assertRaisesRegex(EvaluationError, "fallback"):
                    evaluate(root, fixture, retrieval_mode="hybrid")

    def test_hybrid_stale_source_hash_errors_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_knowledge_base(root)
            _write_manifest(root, "new-hash")
            VectorIndex(root, source_hash="old-hash").build(
                [
                    {
                        "id": "ObjectType:ServerType",
                        "type": "entity",
                        "title": "ServerType",
                        "text": "server metadata",
                        "doc": "OPC-10000-5",
                    }
                ],
                FakeProvider(),
                source_hash="old-hash",
            )
            fixture = _write_fixture(
                root,
                [{"question": "ServerType", "expected_ids": ["ObjectType:ServerType"]}],
            )

            import tools.evaluate_retrieval as module

            with patch.object(
                module, "SentenceTransformerEmbeddingProvider", return_value=FakeProvider()
            ):
                with self.assertRaisesRegex(EvaluationError, "source hash|stale"):
                    evaluate(root, fixture, retrieval_mode="hybrid")

    def test_fixture_validation_happens_before_loading_embedding_model(self):
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
                    with patch.object(module, "SentenceTransformerEmbeddingProvider") as provider:
                        with self.assertRaises(ValueError):
                            evaluate(root, fixture, retrieval_mode="hybrid")
                        provider.assert_not_called()

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
