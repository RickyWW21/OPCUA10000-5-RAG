import unittest

from streamlit_app import format_answer_metadata, format_citation_label, format_retrieved_record


class StreamlitAppTests(unittest.TestCase):
    def test_format_answer_metadata_reports_generation_and_retrieval_modes(self) -> None:
        self.assertEqual(
            "生成模式：generated · 检索模式：hybrid",
            format_answer_metadata("generated", "hybrid"),
        )

    def test_format_citation_label_keeps_title_and_id(self) -> None:
        citation = {"label": "[E1]", "title": "ServerType", "id": "ObjectType:ServerType"}
        self.assertEqual("[E1] ServerType (`ObjectType:ServerType`)", format_citation_label(citation))

    def test_format_retrieved_record_includes_type_and_section(self) -> None:
        record = {"type": "entity", "title": "ServerType", "section": "6.3.1", "snippet": "Defines a server."}
        self.assertEqual("entity · ServerType · 6.3.1\nDefines a server.", format_retrieved_record(record))


if __name__ == "__main__":
    unittest.main()
