---
page_id: sessiondiagnosticsobjecttype
kind: entity
entity_id: ObjectType:SessionDiagnosticsObjectType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.3.4", "lines": "466-471"}, {"section": "6.3.5", "table": "13", "lines": "477-488"}, {"section": "6.3.5", "lines": "491-497"}, {"section": "6.3.5", "table": "14", "lines": "501-504"}]
---

# SessionDiagnosticsObjectType

**类型**：ObjectType（`IsAbstract=False`）  
**父类型**：`BaseObjectType`  
**规范位置**：OPC 10000-5 §6.3.5，Table 13、Table 14

## 用途

`SessionDiagnosticsObjectType` 表示**单个** OPC UA Session 的诊断信息。`SessionsDiagnosticsSummaryType` 为每个 Session 提供一个该类型的 Object，原文用 `<ClientName>` 作为占位符；它不是固定的 BrowseName，实际 BrowseName 可由 CreateSession 的 `sessionName` 或其他 Server 特定机制派生。客户端因此可以从某个具体 Session 出发读取其一般诊断、安全诊断和订阅诊断。[§6.3.4 L466-L471](../../source/OPC-10000-5-v1.05.06.md#L466-L471) [§6.3.5 Table 13 L477-L488](../../source/OPC-10000-5-v1.05.06.md#L477-L488)

## 重要成员

| 成员 | 节点类别 | 数据类型 / 类型定义 | 建模规则 |
|---|---|---|---|
| `SessionDiagnostics` | Variable | `SessionDiagnosticsDataType` / `SessionDiagnosticsVariableType` | Mandatory |
| `SessionSecurityDiagnostics` | Variable | `SessionSecurityDiagnosticsDataType` / `SessionSecurityDiagnosticsType` | Mandatory |
| `SubscriptionDiagnosticsArray` | Variable | `SubscriptionDiagnosticsDataType[]` / `SubscriptionDiagnosticsArrayType` | Mandatory |
| `CurrentRoleIds` | Variable | `NodeId[]` / `PropertyType` | Optional |

`SessionDiagnostics` 提供一般诊断信息，`SessionSecurityDiagnostics` 提供安全相关诊断信息。由于后者涉及安全，规范建议（should）它只对经授权的用户开放，而不是对所有用户可见。[§6.3.5 L491-L497](../../source/OPC-10000-5-v1.05.06.md#L491-L497)

`SubscriptionDiagnosticsArray` 是该 Session 已打开 Subscription 的诊断数组；它的每个条目对应一个 Subscription，并同样通过 `SubscriptionDiagnosticsArrayType` 暴露为 Variables。

`CurrentRoleIds` 是可选数组，给出 Server 授予当前 Session 的每个 Role 的 NodeId。它是安全相关信息：对于不是当前 Session 的其他 Session，该信息 shall 只对经授权的用户（例如具有 Part 18 中 `SecurityAdmin` Role 的用户）开放。[§6.3.5 L491-L497](../../source/OPC-10000-5-v1.05.06.md#L491-L497)

## 附加一致性单元

Table 14 为 `CurrentRoleIds` 定义了附加一致性单元：当暴露该 BrowsePath 时，相关一致性单元为 `Security Role Server Base 2`。[§6.3.5 Table 14 L501-L504](../../source/OPC-10000-5-v1.05.06.md#L501-L504)

这说明 `CurrentRoleIds` 不仅是一个可选字段，还与 Role-Based Security 的一致性声明相关。`SecurityAdmin` 和 Role 的完整语义在 Part 18 中定义，本项目未收录，因此本页只记录 Part 5 中的地址空间与访问限制说明。

## 相关类型与边界

- 父级汇总对象见 [SessionsDiagnosticsSummaryType](sessionsdiagnosticssummarytype.md)。
- 上层诊断入口见 [ServerDiagnosticsType](serverdiagnosticstype.md)，综合主题见 [diagnostics](../topics/diagnostics.md)。
- `SessionDiagnosticsDataType` 的字段（SessionId、SessionName、各类计数器等）在 §12.11 中定义；`SessionSecurityDiagnosticsDataType` 在 §12.12 中定义。本 Wiki 尚未为这两个 DataType 建页。
- 本页只描述地址空间类型和 Part 5 明示的访问边界，不展开 Part 4 的 Session 生命周期或 Part 18 的 Role 评估算法。

## 相关页面

- [diagnostics](../topics/diagnostics.md)：诊断树的组织方式。
- [SessionsDiagnosticsSummaryType](sessionsdiagnosticssummarytype.md)：Session 对象的上层汇总。
- [ServerDiagnosticsType](serverdiagnosticstype.md)：服务器级诊断入口。
- [ServerType](servertype.md)：标准 Server Object。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
