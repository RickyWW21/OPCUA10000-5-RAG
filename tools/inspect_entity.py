from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb import KnowledgeBase


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect one OPC UA 10000-5 entity.")
    parser.add_argument("name")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()

    kb = KnowledgeBase(args.root)
    entity = kb.get_entity(args.name)
    if not entity:
        print(f"未找到实体: {args.name}")
        raise SystemExit(1)

    print(f"名称: {entity['name']}")
    print(f"类型: {entity['kind']}")
    print(f"章节: {entity.get('section')}")
    print(f"表格: {', '.join(entity.get('related_tables', []))}")
    if entity.get("supertype"):
        print(f"父类型: {entity['supertype']}")
    print(f"中文摘要: {entity.get('summary_zh', '')}")
    print(f"English summary: {entity.get('summary_en', '')}")
    if entity.get("attributes"):
        print("\n属性:")
        for key, value in entity["attributes"].items():
            print(f"  - {key}: {value}")
    if entity.get("components"):
        print("\n组件/引用:")
        for item in entity["components"][:80]:
            print(
                f"  - {item.get('reference_type')} {item.get('node_class')} "
                f"{item.get('browse_name')} [{item.get('data_type')} / {item.get('type_definition')}] "
                f"{item.get('modelling_rule')}"
            )
    if entity.get("fields"):
        print("\n字段:")
        for item in entity["fields"][:80]:
            print(f"  - {item.get('name')}: {item.get('type')} - {item.get('description')}")
    if entity.get("enum_values"):
        print("\n枚举值:")
        for item in entity["enum_values"][:80]:
            print(f"  - {item.get('name')}={item.get('value')} - {item.get('description')}")


if __name__ == "__main__":
    main()
