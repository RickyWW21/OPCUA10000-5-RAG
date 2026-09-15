import subprocess
import sys
import unittest
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class AskCliTests(unittest.TestCase):
    def test_ask_cli_prints_answer_mode_and_citations(self) -> None:
        result = run_cli_script("tools/ask_kb.py", "What is ServerType?", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("offline", result.stdout)
        self.assertIn("引用", result.stdout)
        self.assertIn("[E1]", result.stdout)

    def test_ask_cli_rejects_empty_question_without_traceback(self) -> None:
        result = run_cli_script("tools/ask_kb.py", "   ")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_ask_cli_reports_missing_api_key_without_traceback(self) -> None:
        env = os.environ.copy()
        env.pop("DEEPSEEK_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        result = subprocess.run(
            [sys.executable, "tools/ask_kb.py", "What is ServerType?"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LLM API key is required", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
