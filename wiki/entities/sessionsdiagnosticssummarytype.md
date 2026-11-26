---
page_id: sessionsdiagnosticssummarytype
kind: entity
entity_id: ObjectType:SessionsDiagnosticsSummaryType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.3.4", "table": "12", "lines": "453-463"}, {"section": "6.3.4", "lines": "466-471"}, {"section": "8.3.1", "lines": "2704-2710"}]
---

# SessionsDiagnosticsSummaryType

**类型**：ObjectType（`IsAbstract=False`）  
**父类型**：`BaseObjectType`  
**规范位置**：OPC 10000-5 §6.3.4，Table 12

## 用途

`SessionsDiagnosticsSummaryType` 是 `ServerDiagnosticsType.SessionsDiagnosticsSummary` 的类型，用来汇总 Server 上所有 Session 的诊断信息。它提供两条并行路径：一条是按 Session 排列的数组，另一条是为每个 Session 提供一个 `SessionDiagnosticsObjectType` Object，便于客户端按 Session 浏览详细数据。[§6.3.4 Table 12 L453-L463](../../source/OPC-10000-5-v1.05.06.md#L453-L463)

## 重要成员

| 成员 | 节点类别 | 数据类型 / 类型定义 | 建模规则 |
|---|---|---|---|
| `SessionDiagnosticsArray` | Variable | `SessionDiagnosticsDataType[]` / `SessionDiagnosticsArrayType` | Mandatory |
| `SessionSecurityDiagnosticsArray` | Variable | `SessionSecurityDiagnosticsDataType[]` / `SessionSecurityDiagnosticsArrayType` | Mandatory |
| `<ClientName>` | Object | `SessionDiagnosticsObjectType` | OptionalPlaceholder |

`SessionDiagnosticsArray` 为每个 Session 提供一个条目，承载一般诊断信息；`SessionSecurityDiagnosticsArray` 为每个活动 Session 提供一个条目，承载安全相关诊断信息。由于后者涉及安全，规范建议（should）不把它开放给所有用户，而只通过加密通道开放给经授权用户。[§6.3.4 L466-L471](../../source/OPC-10000-5-v1.05.06.md#L466-L471)

`<ClientName>` 是 OptionalPlaceholder：Server 为每个 Session 提供一个 Object，其 BrowseName 可以由 `CreateSession` 中的 `sessionName` 派生，也可以由服务器特有机制生成；其类型为 `SessionDiagnosticsObjectType`。[§6.3.4 L466-L471](../../source/OPC-10000-5-v1.05.06.md#L466-L471)

## 数组与对象的关系

§8.3.1 说明了设计意图：`SessionsDiagnosticsSummary` 同时提供“每个 Session 一个 Object”和“每个 Session 一个数组条目”。Session Object 内部的复杂 Variable 与数组中条目使用相同 DataType，并把同一信息进一步暴露为简单类型的 Variables。Subscription 诊断也采用类似模式：Server 有一个全局数组，每个 Session Object 还有该 Session 的订阅数组。[§8.3.1 L2704-L2710](../../source/OPC-10000-5-v1.05.06.md#L2704-L2710)

由于不同用户凭证可能看到不同条目，数组长度可能因连接而异；用户被 impersonation 后长度也可能变化。因此客户端如果订阅固定 index range，可能得到非预期结果。这是 Part 5 对可见性差异的说明，不展开 Part 4 的 impersonation 服务细节。

## 相关类型与边界

- 宿主路径：`Server` → `ServerDiagnostics` → `SessionsDiagnosticsSummary`。
- 单个 Session 对象由 [SessionDiagnosticsObjectType](sessiondiagnosticsobjecttype.md) 定义。
- 服务器级诊断入口见 [ServerDiagnosticsType](serverdiagnosticstype.md)，综合说明见 [diagnostics](../topics/diagnostics.md)。
- 本页不展开 `SessionDiagnosticsDataType`、`SessionSecurityDiagnosticsDataType` 的逐字段结构；它们分别在 §12.11、§12.12 中定义，本 Wiki 尚未单独建页。

## 相关页面

- [diagnostics](../topics/diagnostics.md)：诊断对象的整体组织。
- [ServerDiagnosticsType](serverdiagnosticstype.md)：上层诊断对象。
- [SessionDiagnosticsObjectType](sessiondiagnosticsobjecttype.md)：单个 Session 的诊断对象。
- [ServerType](servertype.md)：诊断树的根。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
