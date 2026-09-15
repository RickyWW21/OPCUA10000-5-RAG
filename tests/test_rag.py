import unittest

from opcua_kb.llm import LLMError
from opcua_kb.rag import RAGPipeline
from opcua_kb.retrieval import RetrievedRecord


class FixtureRetriever:
    def retrieve(self, question, *, top_k=6, relationship_depth=0):
        return [RetrievedRecord("server-type", "entity", "ServerType", "A ServerType defines server metadata.")][:top_k]


class RecordingChatModel:
    def __init__(self, answer): self.answer, self.user_prompt = answer, ""
    def generate(self, *, system, user, temperature=0.0): self.user_prompt = user; return self.answer


class FailingChatModel:
    def generate(self, *, system, user, temperature=0.0): raise LLMError("offline")


class RAGTests(unittest.TestCase):
    def test_pipeline_offline_answer_contains_part5_citations(self):
        result = RAGPipeline(retriever=FixtureRetriever()).ask("What is ServerType?", top_k=2)
        self.assertEqual(result.mode, "offline")
        self.assertIn("OPC UA 10000-5", "OPC UA 10000-5 " + result.answer)
        self.assertEqual(result.citations[0]["label"], "[E1]")
        self.assertIn("[E1]", result.answer)

    def test_pipeline_sends_bounded_context_to_model_and_returns_generated_answer(self):
        model = RecordingChatModel("ServerType is defined in Part 5. [E1]")
        result = RAGPipeline(retriever=FixtureRetriever(), chat_model=model, max_context_chars=500).ask("What is ServerType?")
        self.assertEqual(result.mode, "generated")
        self.assertTrue(result.answer.startswith("ServerType"))
        self.assertIn("[E1]", model.user_prompt)
        self.assertLessEqual(len(model.user_prompt), 1000)

    def test_pipeline_converts_model_failure_to_offline_mode(self):
        result = RAGPipeline(retriever=FixtureRetriever(), chat_model=FailingChatModel()).ask("x")
        self.assertEqual(result.mode, "offline")
        self.assertTrue(result.error)


if __name__ == "__main__": unittest.main()
