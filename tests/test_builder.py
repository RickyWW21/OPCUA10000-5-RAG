"""Builder behavior tests for table-to-entity enrichment."""

from __future__ import annotations

import unittest

from opcua_kb.builder import Chapter, Table, _apply_table_to_entity, _entity_kind
from opcua_kb.builder_models import Chapter as ModelChapter, Table as ModelTable


class BuilderTests(unittest.TestCase):
    """Protect emitted entity fields and relationship semantics."""

    @staticmethod
    def _entity(kind: str = "ObjectType") -> dict[str, object]:
        return {
            "id": "ObjectType:ServerType",
            "name": "ServerType",
            "kind": kind,
            "attributes": {},
            "components": [],
            "references": [],
            "fields": [],
            "enum_values": [],
        }

    def test_builder_reexports_table_model(self) -> None:
        self.assertIs(Chapter, ModelChapter)
        self.assertIs(Table, ModelTable)

    def test_reference_row_populates_component_and_edge(self) -> None:
        table = Table("table-1", "1", "Components", "6.3", "reference", None, 1, 3, [])
        table.rows = [
            {
                "References": "HasComponent",
                "BrowseName": "BuildInfo",
                "NodeClass": "Variable",
                "DataType": "BuildInfo",
                "TypeDefinition": "",
            }
        ]
        entity = self._entity()
        relationships: list[dict[str, object]] = []

        _apply_table_to_entity(entity, table, relationships)

        self.assertEqual("BuildInfo", entity["components"][0]["browse_name"])
        self.assertEqual("HAS_COMPONENT", relationships[0]["relation"])

    def test_structure_field_adds_field_and_datatype_edge(self) -> None:
        table = Table("table-2", "2", "Fields", "12.1", "structure", None, 1, 3, [])
        table.rows = [{"Name": "BuildDate", "Type": "DateTime", "Description": "date"}]
        entity = self._entity("DataType")
        relationships: list[dict[str, object]] = []

        _apply_table_to_entity(entity, table, relationships)

        self.assertEqual("BuildDate", entity["fields"][0]["name"])
        self.assertEqual(["HAS_FIELD", "USES_DATATYPE"], [edge["relation"] for edge in relationships])

    def test_enum_row_adds_value_without_relationship(self) -> None:
        table = Table("table-3", "3", "Enum", "12.1", "enum", None, 1, 3, [])
        table.rows = [{"Name": "Running", "Value": "1", "Description": "active"}]
        entity = self._entity("DataType")
        relationships: list[dict[str, object]] = []

        _apply_table_to_entity(entity, table, relationships)

        self.assertEqual({"name": "Running", "value": "1", "description": "active"}, entity["enum_values"][0])
        self.assertEqual([], relationships)

    def test_supertype_row_skips_other_row_processing(self) -> None:
        table = Table("table-4", "4", "Subtype", "6.3", "reference", None, 1, 3, [])
        table.rows = [
            {
                "References": "Subtype of the BaseObjectType defined",
                "BrowseName": "Ignored",
                "NodeClass": "Variable",
            }
        ]
        entity = self._entity()
        relationships: list[dict[str, object]] = []

        _apply_table_to_entity(entity, table, relationships)

        self.assertEqual("BaseObjectType", entity["supertype"])
        self.assertEqual(["HAS_SUBTYPE"], [edge["relation"] for edge in relationships])
        self.assertEqual([], entity["components"])

    def test_entity_kind_preserves_event_type_precedence(self) -> None:
        self.assertEqual("EventType", _entity_kind("6.4.2", "AlarmType"))

    def test_entity_kind_rules_preserve_each_section_family(self) -> None:
        cases = [
            ("6.3", "ServerType", "ObjectType"),
            ("7.2", "BaseVariableType", "VariableType"),
            ("8.4.1", "Mandatory", "ModellingRule"),
            ("8.2", "FolderType", "Object"),
            ("9.1", "GetMonitoredItems", "Method"),
            ("11.1", "HasComponent", "ReferenceType"),
            ("12.1", "BuildInfo", "DataType"),
            ("10.1", "Unrelated", None),
        ]

        for section, title, expected in cases:
            with self.subTest(section=section, title=title):
                self.assertEqual(expected, _entity_kind(section, title))
