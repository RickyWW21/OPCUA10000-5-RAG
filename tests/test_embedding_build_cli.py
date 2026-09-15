import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from opcua_kb.builder import build


class FakeProvider:
    model_name = "fake-model"
    dimension = 2

    def embed(self, texts):
        return [[1.0, float(index + 1)] for index, _ in enumerate(texts)]


class EmbeddingBuildTests(unittest.TestCase):
    def test_embedding_build_is_opt_in_and_base_build_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            source = Path(directory) / "source.md"
            source.write_text("1 Scope\n\nPart 5 information model.\n", encoding="utf-8")
            stats = build(root, source)
            self.assertNotIn("embeddings", stats)
            self.assertFalse((root / "indexes" / "embeddings.jsonl").exists())

            build(root, source, embeddings=True, embedding_provider=FakeProvider())
            self.assertTrue((root / "indexes" / "embeddings.jsonl").exists())

    def test_ask_cli_can_disable_vector_retrieval(self):
        project_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(project_root / "tools" / "ask_kb.py"), "What is ServerType?", "--offline", "--no-embeddings"],
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fts", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
