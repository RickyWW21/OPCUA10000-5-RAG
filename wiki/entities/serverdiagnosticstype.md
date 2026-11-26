---
page_id: serverdiagnosticstype
kind: entity
entity_id: ObjectType:ServerDiagnosticsType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.3.3", "table": "11", "lines": "414-426"}, {"section": "6.3.3", "lines": "429-440"}, {"section": "6.3.3", "lines": "429-435"}, {"section": "6.3.3", "lines": "443-447"}]
---

# ServerDiagnosticsType

**类型**：ObjectType（`IsAbstract=False`）  
**父类型**：`BaseObjectType`  
**规范位置**：OPC 10000-5 §6.3.3，Table 11

## 用途

`ServerDiagnosticsType` 是 `ServerType.ServerDiagnostics` 的类型，定义服务器级诊断信息的标准入口。它把诊断信息组织成“摘要 + 数组 + 按 Session 的子树”：`ServerDiagnosticsSummary` 提供汇总，`SubscriptionDiagnosticsArray` 和 `SamplingIntervalDiagnosticsArray` 提供按订阅/采样间隔的数组，`SessionsDiagnosticsSummary` 进一步展开每个 Session。[§6.3.3 Table 11 L414-L426](../../source/OPC-10000-5-v1.05.06.md#L414-L426)

## 重要成员

| 成员 | 节点类别 | 数据类型 / 类型定义 | 建模规则 |
|---|---|---|---|
| `ServerDiagnosticsSummary` | Variable | `ServerDiagnosticsSummaryDataType` / `ServerDiagnosticsSummaryType` | Mandatory |
| `SamplingIntervalDiagnosticsArray` | Variable | `SamplingIntervalDiagnosticsDataType[]` / `SamplingIntervalDiagnosticsArrayType` | Optional |
| `SubscriptionDiagnosticsArray` | Variable | `SubscriptionDiagnosticsDataType[]` / `SubscriptionDiagnosticsArrayType` | Mandatory |
| `SessionsDiagnosticsSummary` | Object | `SessionsDiagnosticsSummaryType` | Mandatory |
| `EnabledFlag` | Variable | `Boolean` / `PropertyType` | Mandatory |

`ServerDiagnosticsSummary` 的语义在 §12.9 中定义；`SubscriptionDiagnosticsArray` 的每个条目对应 Server 中实际建立的 Notification channel，其语义在 §12.15 中定义；`SessionsDiagnosticsSummary` 的语义在 §6.3.4 中定义。[§6.3.3 L429-L440](../../source/OPC-10000-5-v1.05.06.md#L429-L440)

`SamplingIntervalDiagnosticsArray` 在 Table 11 中的建模规则固定为 Optional。只有使用固定采样间隔集合的 Server 才收集这类诊断；此时数组长度和所含 Variables 的集合由 Server 配置决定，并且分配给某个采样间隔诊断 Variable 的 NodeId 只要 Server 配置不变就不得改变。不使用固定采样率的 Server 可以不暴露该数组。[§6.3.3 L429-L435](../../source/OPC-10000-5-v1.05.06.md#L429-L435)

## EnabledFlag 与可用性边界

`EnabledFlag` 表示 Server 是否收集诊断信息；当 Server 支持诊断收集时，客户端也可以用它开启或关闭收集：

- `TRUE`：Server 收集诊断信息；把值设为 `TRUE` 会重置并启用收集。
- `FALSE`：不收集；把值设为 `FALSE` 会禁用收集，但不重置已有诊断值。

当诊断关闭时，除 `EnabledFlag` 外，Server 可以对所有静态诊断节点返回 `Bad_NodeIdUnknown`；动态诊断节点（例如 Session 节点）不会出现在地址空间中。如果 Server 不支持收集诊断信息，`EnabledFlag` 是只读的。[§6.3.3 L443-L447](../../source/OPC-10000-5-v1.05.06.md#L443-L447)

这条规则解释了为什么诊断页不能简单假定“节点存在就一定有可读值”：诊断关闭时，标准静态节点仍可能存在，但读取可能返回 `Bad_NodeIdUnknown`。

## 相关类型与边界

- 宿主对象是 `ServerType.ServerDiagnostics`；见 [ServerType](servertype.md)。
- 按 Session 的子树由 [SessionsDiagnosticsSummaryType](sessionsdiagnosticssummarytype.md) 定义，单个 Session 对象由 [SessionDiagnosticsObjectType](sessiondiagnosticsobjecttype.md) 定义。
- 诊断主题的综合说明见 [diagnostics](../topics/diagnostics.md)。
- 本页只覆盖服务器级诊断入口。Session/Subscription 的具体计数、时间戳和安全字段分别由 §12.11、§12.15、§12.12 等结构定义；本 Wiki 尚未为这些 DataType 单独建页。

## 相关页面

- [diagnostics](../topics/diagnostics.md)：诊断对象树与使用边界。
- [ServerType](servertype.md)：诊断对象的宿主。
- [SessionsDiagnosticsSummaryType](sessionsdiagnosticssummarytype.md)：Session 诊断数组和 Session 对象入口。
- [SessionDiagnosticsObjectType](sessiondiagnosticsobjecttype.md)：单个 Session 的诊断对象。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
