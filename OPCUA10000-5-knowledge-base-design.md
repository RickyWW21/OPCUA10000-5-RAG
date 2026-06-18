# OPC UA 10000-5 本地知识库设计

来源文件：`C:\Users\admin\Downloads\OPC-10000-5-v1.05.06.md`

规范：OPC-10000-5: OPC Unified Architecture - Part 5: Information Model

版本：1.05.06

发布时间：2025-10-22

## 1. 框架内容简述

OPC UA 10000-5 定义的是 OPC UA 的 Information Model，即信息模型。它描述一个 OPC UA Server 地址空间中标准化的节点、类型、实例、引用关系、数据类型、事件类型、诊断对象和建模规则。可以理解为：它定义了一个“空的标准 OPC UA Server”应当具备的基础地址空间框架，但并不要求每个 Server 暴露所有节点；实际暴露内容取决于 Server 支持的功能和一致性单元。

该规范主要覆盖以下方面：

1. 范围、引用标准与术语
   - 说明 Part 5 与 OPC UA 其他部分的关系。
   - 引用 Part 1、Part 3、Part 4、Part 6、Part 7、Part 8、Part 9、Part 11、Part 18、Part 20 等规范。
   - 定义术语、缩略语和节点描述表的阅读规则。

2. NodeId、BrowseName 与通用属性
   - 说明标准节点如何使用 NodeId 和 BrowseName。
   - 定义 Object、Variable、VariableType、Method 等节点类别的通用属性。

3. 标准 ObjectTypes
   - 包含 `BaseObjectType`、Server 相关对象类型、诊断对象类型、冗余对象类型、命名空间元数据对象类型等。
   - 包含事件类型体系，例如 `BaseEventType`、`AuditEventType`、证书审计事件、Session 审计事件、模型变更事件、系统事件、进度事件等。
   - 包含 `FolderType`、`ModellingRuleType`、`AggregateFunctionType`、接口类型、列表类型、数据类型细化与子类型限制相关类型。

4. 标准 VariableTypes
   - 包含 `BaseVariableType`、`PropertyType`、`BaseDataVariableType`。
   - 包含 Server 状态、构建信息、诊断数组、Session 诊断、安全诊断、订阅诊断等变量类型。
   - 包含选项集、选择列表、音频变量、向量、坐标、姿态、坐标系、位域等变量类型。

5. 标准 Objects 与地址空间组织
   - 定义标准地址空间的入口与组织节点，例如 `Root`、`Objects`、`Types`、`Views`、`ObjectTypes`、`VariableTypes`、`ReferenceTypes`、`DataTypes`、`EventTypes`、`InterfaceTypes`、`Server` 等。
   - 定义标准建模规则对象，例如 `Mandatory`、`Optional`、`MandatoryPlaceholder`、`OptionalPlaceholder`、`ExposesItsArray`。

6. 标准 Methods
   - 包含 `GetMonitoredItems`、`ResendData`、`SetSubscriptionDurable`、`RequestServerStateChange` 等方法的地址空间定义。

7. 标准 ReferenceTypes
   - 定义 OPC UA 地址空间中节点之间的标准引用关系。
   - 包含层次引用、非层次引用、组件关系、属性关系、类型定义关系、子类型关系、事件源关系、接口关系、数据类型细化关系等。

8. 标准 DataTypes
   - 包含基础数据类型、枚举、结构体、字符串派生类型、数字类型、NodeId、QualifiedName、LocalizedText 等。
   - 包含服务相关数据类型，例如 `ApplicationDescription`、`DataValue`、`StatusCode`、`UserIdentityToken` 等。
   - 包含 Part 5 自身定义的数据结构，例如 Server 状态、诊断、订阅、模型变更、语义变更、网络组、端点 URL、向量、坐标、姿态、帧、数据类型描述、语义版本、位域定义等。

9. 附录
   - Annex A 给出 Server 信息建模的设计决策。
   - Annex B 说明 DataTypeDictionary。
   - Annex C 说明 OPC Binary Type Description System。
   - Annex D 涉及几何参考。

## 2. 本地知识库目标

该知识库的目标不是简单保存整篇 Markdown，而是把 OPC UA 10000-5 中的实体、章节、表格和关系拆成可检索、可引用、可组合回答的本地资料库。它应支持以下本地调用场景：

1. 按章节问答
   - 例：`6.3.1 ServerType 是什么？`
   - 例：`标准 Server Object 包含哪些组件？`

2. 按实体查询
   - 例：`BaseEventType 的字段有哪些？`
   - 例：`HasComponent 和 HasProperty 的区别是什么？`
   - 例：`SessionDiagnosticsDataType 结构包含哪些字段？`

3. 按节点类别查询
   - ObjectType、VariableType、ReferenceType、DataType、Method、Object、ModellingRule。

4. 按关系查询
   - 某类型的父类型、子类型、组件、属性、引用类型、TypeDefinition、ModellingRule。

5. 按实现任务查询
   - 例：`我要实现 Server Diagnostics，需要哪些 ObjectTypes、VariableTypes 和 DataTypes？`
   - 例：`实现事件审计需要哪些 Audit EventTypes？`

6. 按一致性与规范定位查询
   - 查询某节点所属章节、表格、Conformance Units、原文片段位置。

## 3. 推荐本地目录结构

建议将知识库放在本项目目录下：

```text
OPCUA10000-5/
  source/
    OPC-10000-5-v1.05.06.md
    source_manifest.json
  kb/
    chapters.jsonl
    entities.jsonl
    tables.jsonl
    relationships.jsonl
    glossary.jsonl
    chunks.jsonl
    aliases.json
  indexes/
    fts.sqlite
    vector.index
    embeddings.jsonl
  exports/
    opcua10000-5.summary.md
    opcua10000-5.entity-catalog.md
  tools/
    build_kb.py
    query_kb.py
    inspect_entity.py
  README.md
```

说明：

- `source/` 保存原始规范文件和来源元数据。
- `kb/` 保存结构化知识库数据，使用 JSONL 方便增量写入和本地脚本读取。
- `indexes/` 保存全文索引、向量索引和 embedding 结果。
- `exports/` 保存面向人阅读的派生文档。
- `tools/` 保存构建和查询脚本。

## 4. 数据分层设计

### 4.1 章节层：`chapters.jsonl`

每个章节一条记录，用于按规范结构定位内容。

字段建议：

```json
{
  "id": "sec-6.3.1",
  "doc": "OPC-10000-5",
  "version": "1.05.06",
  "section": "6.3.1",
  "title": "ServerType",
  "level": 3,
  "parent": "sec-6.3",
  "path": ["6 Standard ObjectTypes", "6.3 ObjectTypes for the Server Object", "6.3.1 ServerType"],
  "start_line": 0,
  "end_line": 0,
  "text": "...",
  "tables": ["table-9"],
  "entities": ["ObjectType:ServerType"]
}
```

用途：

- 回答章节级问题。
- 保留上下文层级。
- 支持从实体回溯到原文。

### 4.2 实体层：`entities.jsonl`

每个 OPC UA 标准实体一条记录。实体是本知识库的核心。

实体类型建议：

- `ObjectType`
- `VariableType`
- `Object`
- `Variable`
- `Method`
- `ReferenceType`
- `DataType`
- `EventType`
- `ModellingRule`
- `ConformanceUnit`
- `Term`
- `AnnexTopic`

字段建议：

```json
{
  "id": "ObjectType:ServerType",
  "name": "ServerType",
  "kind": "ObjectType",
  "section": "6.3.1",
  "title": "ServerType",
  "summary": "Defines the type for the standard Server Object.",
  "node_id": null,
  "browse_name": "ServerType",
  "supertype": "BaseObjectType",
  "attributes": {
    "IsAbstract": false
  },
  "components": [
    {
      "browse_name": "ServerStatus",
      "node_class": "Variable",
      "data_type": "ServerStatusDataType",
      "type_definition": "ServerStatusType",
      "modelling_rule": "Mandatory"
    }
  ],
  "references": [
    {
      "reference_type": "HasSubtype",
      "target": "ServerType",
      "direction": "forward"
    }
  ],
  "related_tables": ["table-9"],
  "source_ref": {
    "file": "source/OPC-10000-5-v1.05.06.md",
    "section": "6.3.1"
  }
}
```

用途：

- 精确查询某个类型、方法、引用类型或数据类型。
- 构建本地知识图谱。
- 生成“某实体定义卡片”。

### 4.3 表格层：`tables.jsonl`

规范中大量定义在表格内，表格应作为单独知识对象保存。

字段建议：

```json
{
  "id": "table-9",
  "number": 9,
  "caption": "ServerType definition",
  "section": "6.3.1",
  "table_kind": "type_definition",
  "target_entity": "ObjectType:ServerType",
  "columns": ["References", "NodeClass", "BrowseName", "DataType", "TypeDefinition", "ModellingRule"],
  "rows": [
    {
      "References": "HasComponent",
      "NodeClass": "Variable",
      "BrowseName": "ServerStatus",
      "DataType": "ServerStatusDataType",
      "TypeDefinition": "ServerStatusType",
      "ModellingRule": "Mandatory"
    }
  ],
  "notes": [],
  "conformance_units": []
}
```

用途：

- 保留规范定义表的结构。
- 支持字段级查询。
- 避免只做纯文本切片导致表格信息丢失。

### 4.4 关系层：`relationships.jsonl`

把表格和文字中的关系抽成边，方便图查询。

关系类型建议：

- `HAS_SUBTYPE`
- `HAS_COMPONENT`
- `HAS_PROPERTY`
- `HAS_TYPE_DEFINITION`
- `HAS_MODELLING_RULE`
- `HAS_ENCODING`
- `GENERATES_EVENT`
- `HAS_EVENT_SOURCE`
- `USES_DATATYPE`
- `USES_REFERENCETYPE`
- `DEFINED_IN_SECTION`
- `DEFINED_BY_TABLE`
- `HAS_CONFORMANCE_UNIT`

字段建议：

```json
{
  "source": "ObjectType:ServerType",
  "relation": "HAS_COMPONENT",
  "target": "Variable:ServerType.ServerStatus",
  "properties": {
    "reference_type": "HasComponent",
    "node_class": "Variable",
    "data_type": "ServerStatusDataType",
    "type_definition": "ServerStatusType",
    "modelling_rule": "Mandatory"
  },
  "source_ref": {
    "section": "6.3.1",
    "table": "table-9"
  }
}
```

用途：

- 回答“某类型有哪些组件/属性/引用”。
- 回答“哪些类型使用了某 DataType”。
- 支持可视化地址空间关系。

### 4.5 术语层：`glossary.jsonl`

保存术语、缩略语、规范内特殊定义。

字段建议：

```json
{
  "id": "term-ClientUserId",
  "term": "ClientUserId",
  "kind": "term",
  "definition": "String that identifies the user of the client requesting an action.",
  "section": "3.1.1",
  "aliases": []
}
```

用途：

- 快速解释术语。
- 作为问答系统中的优先召回内容。

### 4.6 文本切片层：`chunks.jsonl`

用于向量检索和全文检索。切片不应替代结构化实体层，而是作为补充。

切片策略：

- 按章节切片，保留章节号和标题。
- 表格单独切片，表格行不要与上下文混在一个长文本里。
- 每个切片建议 500 到 1200 中文字符或 300 到 800 英文 token。
- 对定义表，可以一张表一个切片；若表过长，则按逻辑行分块。
- 每个切片带上 `entity_ids`、`table_ids`、`section`、`heading_path`。

字段建议：

```json
{
  "id": "chunk-sec-6.3.1-001",
  "doc": "OPC-10000-5",
  "version": "1.05.06",
  "section": "6.3.1",
  "heading_path": ["6 Standard ObjectTypes", "6.3 ObjectTypes for the Server Object", "6.3.1 ServerType"],
  "chunk_type": "section_text",
  "text": "...",
  "entity_ids": ["ObjectType:ServerType"],
  "table_ids": ["table-9"],
  "keywords": ["ServerType", "Server Object", "ServerStatus", "ServiceLevel"]
}
```

用途：

- 本地 RAG 问答。
- 模糊问题召回。
- 结合实体层做精确回答。

## 5. 检索设计

建议采用三路混合检索：

1. 精确实体检索
   - 输入中识别实体名，如 `ServerType`、`BaseEventType`、`HasComponent`、`DataValue`。
   - 先查 `entities.jsonl` 和 `aliases.json`。
   - 适合规范实体定义查询。

2. 全文检索
   - 使用 SQLite FTS5 建立 `chunks`、`entities`、`tables` 的全文索引。
   - 适合关键词检索、章节定位、英文规范原文检索。

3. 向量检索
   - 对 `chunks.jsonl` 和实体摘要生成 embedding。
   - 适合中文自然语言问题、概念性问题和跨章节问题。

推荐排序策略：

```text
final_score =
  0.45 * exact_entity_score +
  0.30 * full_text_score +
  0.20 * vector_score +
  0.05 * section_priority_score
```

优先级建议：

- 如果问题中出现精确实体名，实体检索优先。
- 如果问题问“有哪些字段/组件/引用/父类型”，优先返回结构化实体和关系。
- 如果问题问“为什么这样建模/设计原因”，优先召回 Annex A 和相关章节说明。
- 如果问题问“实现某功能需要什么”，先召回实体关系，再补充章节切片。

## 6. 查询接口设计

### 6.1 命令行接口

建议提供以下本地命令：

```powershell
python tools/query_kb.py "ServerType 包含哪些组件？"
python tools/inspect_entity.py ServerType
python tools/query_kb.py "HasComponent 和 HasProperty 的区别"
python tools/query_kb.py "实现审计事件需要哪些 EventType？"
```

### 6.2 Python API

建议暴露一个轻量 API：

```python
from opcua_kb import KnowledgeBase

kb = KnowledgeBase("D:/Users/admin/My Document/OPCUA10000-5")

entity = kb.get_entity("ServerType")
refs = kb.get_relationships("ObjectType:ServerType", relation="HAS_COMPONENT")
answer = kb.ask("Server Diagnostics 相关的标准对象有哪些？")
```

### 6.3 本地 Agent 调用

可给本地 Agent 暴露三个工具：

```text
search_opcua_kb(query, top_k=8)
get_opcua_entity(name)
trace_opcua_relationships(entity, relation=None, depth=1)
```

工具职责：

- `search_opcua_kb`：混合检索，返回章节、实体、表格和片段。
- `get_opcua_entity`：返回某实体结构化定义。
- `trace_opcua_relationships`：返回实体之间的引用、继承、组件、属性、数据类型关系。

## 7. 构建流程

推荐构建步骤：

1. 复制源文件
   - 将 `C:\Users\admin\Downloads\OPC-10000-5-v1.05.06.md` 复制到 `source/`。
   - 生成 `source_manifest.json`，记录版本、发布时间、文件哈希。

2. 解析章节
   - 使用正则识别 `1 Scope`、`6.3.1 ServerType`、`12.2.12.1 Argument`、`Annex A ...` 等标题。
   - 生成 `chapters.jsonl`。

3. 解析表格
   - 识别 `Table N - caption`。
   - 根据表格标题判断表格类型，如 `definition`、`Structure`、`values`、`ReferenceType`、`example`。
   - 生成 `tables.jsonl`。

4. 抽取实体
   - 从章节标题和表格标题抽取实体名。
   - 根据章节归属判断实体类型：
     - 第 6 章：ObjectType/EventType。
     - 第 7 章：VariableType。
     - 第 8 章：Object/Variable/ModellingRule Object。
     - 第 9 章：Method。
     - 第 11 章：ReferenceType。
     - 第 12 章：DataType。
   - 生成 `entities.jsonl`。

5. 抽取关系
   - 从定义表中的 `References`、`NodeClass`、`BrowseName`、`DataType`、`TypeDefinition`、`ModellingRule` 列抽取关系。
   - 从 ReferenceType 表抽取父子关系、对称性、反向名等。
   - 从 DataType Structure 表抽取结构字段关系。
   - 生成 `relationships.jsonl`。

6. 生成文本切片
   - 按章节和表格生成 `chunks.jsonl`。
   - 每个 chunk 保留实体 ID、表格 ID 和章节路径。

7. 建立索引
   - SQLite FTS5：索引章节标题、实体名、实体摘要、表格标题、chunk 文本。
   - 向量索引：索引 chunk 文本和实体摘要。

8. 验证
   - 检查所有表格是否挂到章节。
   - 检查所有实体是否能回溯到章节或表格。
   - 检查关系中的 source/target 是否能解析到实体或局部节点。

## 8. 推荐问答生成规则

回答时应遵循：

1. 先给结论，再给规范定位。
2. 对实体类问题，优先使用结构化实体定义。
3. 对表格字段问题，保留表格字段名，不要只做自然语言概括。
4. 对不确定或跨规范内容，明确指出 Part 5 只定义信息模型，服务行为可能属于 Part 4，编码映射可能属于 Part 6，Profile/Conformance 可能属于 Part 7。
5. 输出中引用章节号和表格号，例如：`见 6.3.1, Table 9 - ServerType definition`。

## 9. 知识库最小可用版本

如果先做一个可用的 MVP，建议范围如下：

1. 必做数据
   - `chapters.jsonl`
   - `tables.jsonl`
   - `entities.jsonl`
   - `chunks.jsonl`
   - SQLite FTS5 全文索引

2. 必做查询
   - 按实体名查询。
   - 按章节号查询。
   - 按关键词全文检索。
   - 返回章节号、表格号、原文片段。

3. 第二阶段增强
   - `relationships.jsonl`
   - 向量检索。
   - 中文问题意图分类。
   - 图关系追踪。

4. 第三阶段增强
   - 多 OPC UA Part 联合知识库。
   - UANodeSet XML 对照解析。
   - ConformanceUnit 到节点的覆盖查询。
   - 可视化地址空间关系图。

## 10. 适合本规范的核心标签体系

建议为每个实体和 chunk 打标签：

```text
information-model
address-space
object-type
variable-type
reference-type
data-type
event-type
audit-event
server-object
server-diagnostics
session-diagnostics
subscription-diagnostics
redundancy
namespace-metadata
modelling-rule
method
conformance-unit
datatype-structure
datatype-enum
geometry
binary-type-description
```

## 11. 典型查询到数据源映射

| 用户问题类型 | 优先数据源 | 辅助数据源 |
| --- | --- | --- |
| 某实体是什么 | `entities.jsonl` | `chapters.jsonl`, `chunks.jsonl` |
| 某类型有哪些组件 | `relationships.jsonl` | `tables.jsonl` |
| 某 DataType 有哪些字段 | `tables.jsonl` | `entities.jsonl` |
| 某 ReferenceType 用途 | `entities.jsonl` | `relationships.jsonl`, `chunks.jsonl` |
| 某功能需要哪些节点 | `relationships.jsonl` | `entities.jsonl`, `chunks.jsonl` |
| 某章节讲什么 | `chapters.jsonl` | `chunks.jsonl` |
| 设计原因/建模建议 | Annex A chunks | 相关实体 |
| 编码/TypeDictionary | Annex B/C chunks | DataType entities |

## 12. 结论

OPC UA 10000-5 的知识库应以“实体 + 表格 + 关系 + 章节切片”为核心，而不是只做普通文档向量化。原因是该规范大量信息存在于结构化定义表中，关键问题通常是“某个节点、类型、引用或数据类型如何定义以及与谁相关”。因此，最佳本地知识库形态是混合型：

- 章节层保留规范上下文。
- 实体层支撑精确查询。
- 表格层保留定义细节。
- 关系层支撑地址空间和类型系统追踪。
- 切片层支撑自然语言问答和模糊检索。

这样设计后，本地工具、脚本或 Agent 都可以可靠地调取 OPC UA 10000-5 中的标准信息模型内容，并且能给出可追溯到章节和表格的回答。
