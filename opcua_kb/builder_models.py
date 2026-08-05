"""Data models used by the knowledge-base builder."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chapter:
    """A parsed specification section with source boundaries and linked records."""

    id: str
    section: str
    title: str
    level: int
    parent: str | None
    path: list[str]
    start_line: int
    end_line: int = 0
    text: str = ""
    tables: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


@dataclass
class Table:
    """A specification table in both source-preserving and normalized forms."""

    id: str
    number: str
    caption: str
    section: str | None
    table_kind: str
    target_entity: str | None
    start_line: int
    end_line: int
    raw_lines: list[str]
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)
    conformance_units: list[str] = field(default_factory=list)
