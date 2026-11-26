---
page_id: diagnostics
kind: topic
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.3.3", "table": "11", "lines": "414-426"}, {"section": "6.3.3", "lines": "443-447"}, {"section": "6.3.4", "table": "12", "lines": "453-463"}, {"section": "6.3.4", "lines": "466-471"}, {"section": "6.3.5", "table": "13", "lines": "477-488"}, {"section": "6.3.5", "lines": "491-497"}, {"section": "8.3.1", "lines": "2704-2710"}]
---

# 服务器诊断（diagnostics）

本页综合 Part 5 §6.3.3–§6.3.5 和 §8.3.1，说明标准服务器诊断树的组织方式：服务器级摘要、Subscription 数组、按 Session 的汇总数组和对象，以及诊断开启/关闭对可用性的影响。它不讨论具体诊断计数器的完整字段（那些在 §12.8–§12.15 中定义），也不讨论 Part 4 的服务调用行为。

## 1. 诊断树的形状

标准路径是：

```
Server
└─ ServerDiagnostics (ServerDiagnosticsType)
   ├─ ServerDiagnosticsSummary (Mandatory)
   ├─ SamplingIntervalDiagnosticsArray (Optional)
   ├─ SubscriptionDiagnosticsArray (Mandatory)
   ├─ SessionsDiagnosticsSummary (Mandatory)
   │  ├─ SessionDiagnosticsArray (Mandatory)
   │  ├─ SessionSecurityDiagnosticsArray (Mandatory)
   │  └─ <ClientName> (OptionalPlaceholder, SessionDiagnosticsObjectType)
   │     ├─ SessionDiagnostics (Mandatory)
   │     ├─ SessionSecurityDiagnostics (Mandatory)
   │     ├─ SubscriptionDiagnosticsArray (Mandatory)
   │     └─ CurrentRoleIds (Optional)
   └─ EnabledFlag (Mandatory)
```

`ServerDiagnosticsType` 是 `ServerType.ServerDiagnostics` 的类型，提供 `ServerDiagnosticsSummary`、`SubscriptionDiagnosticsArray`、`SessionsDiagnosticsSummary` 和 `EnabledFlag` 等 Mandatory 成员，以及可选的 `SamplingIntervalDiagnosticsArray`。[§6.3.3 Table 11 L414-L426](../../source/OPC-10000-5-v1.05.06.md#L414-L426)

`SessionsDiagnosticsSummaryType` 为每个 Session 提供一个数组条目和一个 Object；数组存放 `SessionDiagnosticsDataType[]` 和 `SessionSecurityDiagnosticsDataType[]`，Object 的类型是 `SessionDiagnosticsObjectType`。[§6.3.4 Table 12 L453-L463](../../source/OPC-10000-5-v1.05.06.md#L453-L463) 该 Object 在 Table 12 中以 `<ClientName>` 作为 OptionalPlaceholder 的占位 BrowseName；它不是固定 BrowseName，实际 BrowseName 可由 CreateSession 的 `sessionName` 或其他 Server 特定机制派生。[§6.3.4 L466-L471](../../source/OPC-10000-5-v1.05.06.md#L466-L471)

`SessionDiagnosticsObjectType` 再提供单个 Session 的一般诊断、安全诊断、该 Session 的 Subscription 诊断数组，以及可选的 `CurrentRoleIds`。[§6.3.5 Table 13 L477-L488](../../source/OPC-10000-5-v1.05.06.md#L477-L488)

## 2. 摘要、数组和对象为什么同时存在

§8.3.1 解释了这种“三种视图并存”的设计：

- `SessionsDiagnosticsSummary` 有一个按 Session 的数组，适合一次读取或订阅全部条目。
- 同时为每个 Session 提供一个 Object，适合按 Session 浏览详细数据。
- Session Object 内部的复杂 Variable 与数组条目使用相同 DataType，并把同一信息进一步暴露为简单类型的 Variables。
- Subscription 诊断同理：Server 有一个全局数组，每个 Session Object 还有该 Session 的订阅数组。

这样不同需求的客户端可以选择批量读取、按对象浏览或按简单字段读取。[§8.3.1 L2704-L2710](../../source/OPC-10000-5-v1.05.06.md#L2704-L2710)

## 3. 可见性与安全边界

不同用户凭证可能看到不同条目，因此数组长度可能因连接而异；用户被 impersonation 后长度也可能变化。客户端如果订阅固定 index range，可能得到非预期结果。这是 Part 5 对诊断可见性差异的说明。[§8.3.1 L2704-L2710](../../source/OPC-10000-5-v1.05.06.md#L2704-L2710)

诊断数据的可见性与安全限制要分开看：

- `SessionsDiagnosticsSummaryType.SessionSecurityDiagnosticsArray`：规范建议（should）该安全相关数组不向所有用户开放，而只对经授权用户开放，并通过加密通道访问。[§6.3.4 L466-L471](../../source/OPC-10000-5-v1.05.06.md#L466-L471)
- `SessionDiagnosticsObjectType.SessionSecurityDiagnostics`：规范同样用 should，建议只对经授权用户开放。[§6.3.5 L491-L497](../../source/OPC-10000-5-v1.05.06.md#L491-L497)
- `CurrentRoleIds`：对不是当前 Session 的其他 Session，该信息 shall 只对经授权用户开放，例如具有 Part 18 中 `SecurityAdmin` Role 的用户。[§6.3.5 L491-L497](../../source/OPC-10000-5-v1.05.06.md#L491-L497)

这里 should 与 shall 的强度不同：前两项是建议，`CurrentRoleIds` 的跨 Session 访问限制是 shall。Part 18 的 Role 语义本项目未收录，本页只记录 Part 5 的访问限制。

## 4. 诊断关闭时会发生什么

`EnabledFlag` 控制诊断信息是否收集：

- `TRUE`：收集；把值设为 `TRUE` 会重置并启用收集。
- `FALSE`：不收集；把值设为 `FALSE` 会禁用收集但不重置已有值。

诊断关闭时，Server 可以对所有静态诊断节点（`EnabledFlag` 除外）返回 `Bad_NodeIdUnknown`；动态诊断节点（例如 Session 节点）不会出现在地址空间中。如果 Server 不支持收集诊断信息，`EnabledFlag` 是只读的。[§6.3.3 L443-L447](../../source/OPC-10000-5-v1.05.06.md#L443-L447)

因此，“类型定义了某个 Mandatory 组件”不等于“运行时一定能读到值”。诊断节点是否出现、是否可读，取决于 `EnabledFlag` 和 Server 的实现状态。

## 5. 状态、能力与诊断的区别

- `ServerStatus` 是服务器状态（启动时间、当前时间、State、构建信息），不是诊断计数器。
- `ServerCapabilities` 是能力声明（Profile、限制、Session 上限等），不是当前使用量。
- `ServerDiagnostics` 是运行时诊断信息（摘要、数组、Session/Subscription 计数等）。

三者都挂在 `Server` 下，但回答不同问题。把 `OperationLimits` 误当成诊断读数，或把 `EnabledFlag` 误当成 Server 是否支持其他服务/能力的开关，都会导致错误理解；`EnabledFlag` 为只读本身可能表明 Server 不支持诊断收集，而不是在声明某项其他能力。[§6.3.3 L443-L447](../../source/OPC-10000-5-v1.05.06.md#L443-L447)

## 6. 页面地图与边界

- 服务器级入口：[ServerDiagnosticsType](../entities/serverdiagnosticstype.md)
- Session 汇总：[SessionsDiagnosticsSummaryType](../entities/sessionsdiagnosticssummarytype.md)
- 单个 Session：[SessionDiagnosticsObjectType](../entities/sessiondiagnosticsobjecttype.md)
- 状态与构建：[ServerStatusType](../entities/serverstatustype.md)、[BuildInfoType](../entities/buildinfotype.md)
- 标准 Server 对象：[ServerType](../entities/servertype.md)、[server-information-model](server-information-model.md)
- 事件与审计（与诊断不同）：[events-and-auditing](events-and-auditing.md)

本页不展开 `ServerDiagnosticsSummaryDataType`（§12.9）、`SamplingIntervalDiagnosticsDataType`（§12.8）、`SessionDiagnosticsDataType`（§12.11）、`SessionSecurityDiagnosticsDataType`（§12.12）、`SubscriptionDiagnosticsDataType`（§12.15）的逐字段结构；这些 DataType 尚未单独建页。Part 4 如何维护 Subscription、Part 18 如何评估 Role，本项目未收录。

## 相关页面

- [ServerDiagnosticsType](../entities/serverdiagnosticstype.md)：诊断根对象。
- [SessionsDiagnosticsSummaryType](../entities/sessionsdiagnosticssummarytype.md)：Session 汇总。
- [SessionDiagnosticsObjectType](../entities/sessiondiagnosticsobjecttype.md)：单个 Session。
- [ServerStatusType](../entities/serverstatustype.md)：状态变量。
- [server-information-model](server-information-model.md)：整体结构。
- [返回目录](../index.md)

> 本页由 LLM 综合多个 Part 5 章节生成，状态为 draft，尚未经过人工语义审阅。
