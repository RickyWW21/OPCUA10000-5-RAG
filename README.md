# OPC UA 10000-5 结构化实体知识库

数据源：`C:\Users\admin\Downloads\OPC-10000-5-v1.05.06.md`

版本：1.05.06

发布时间：2025-10-22

## 统计

- Chapters: 301
- Tables: 323
- Entities: 262
- Relationships: 2537

## 常用命令

```powershell
python tools/query_kb.py "ServerType 包含哪些组件？" --top-k 8
python tools/inspect_entity.py ServerType
python tools/trace_entity.py ServerType --relation HAS_COMPONENT --depth 1
```
