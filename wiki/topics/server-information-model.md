---
page_id: server-information-model
kind: topic
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "1", "lines": "9-11"}, {"section": "4.1", "lines": "129-135"}, {"section": "6.1", "lines": "201-203"}, {"section": "6.2", "lines": "205-209"}, {"section": "6.2", "table": "8", "lines": "211-217"}, {"section": "6.3.1", "table": "9", "lines": "225-250"}, {"section": "8.3.2", "table": "111", "lines": "2718-2725"}, {"section": "8.3.2", "table": "112", "lines": "2729-2910"}, {"section": "8.3.2", "lines": "2714-2717"}]
---

# Server 信息模型（server-information-model）

本页把 Part 5 中与“标准 Server 地址空间”相关的章节串起来：从 Part 5 的范围，到类型根基 `BaseObjectType`，再到标准 `Server` Object 及其 `ServerType` 组件。它回答的是“一个标准 OPC UA Server 在信息模型层面应提供哪些标准入口”，而不是“某个厂商实际实现了哪些功能”。

## 1. Part 5 定义的地址空间

Part 5 定义 OPC UA Information Model，描述 Server 地址空间中的标准化 Nodes。这些 Nodes 既包括标准化类型，也包括用于诊断或作为服务器特定节点入口的标准化实例。规范因此定义了“一个空 OPC UA Server”的地址空间；但它并不预期每个 Server 都提供所有这些 Nodes。[§1 L9-L11](../../source/OPC-10000-5-v1.05.06.md#L9-L11)

这句话有两个重要含义：

1. **标准地址空间是模板，不是强制全量清单。** 某些节点是由功能、Profile 或一致性单元触发的；未实现某项能力时，相关节点可以不存在。
2. **“标准”不等于“固定实例树”。** Part 5 定义类型和标准入口；本 Part 的 §4.1 给出 NodeId 的符号名与 NamespaceIndex 规则。其他部分本项目未收录，本页不展开。[§4.1 L129-L135](../../source/OPC-10000-5-v1.05.06.md#L129-L135)

## 2. 类型根基与扩展边界

`BaseObjectType` 是所有 ObjectType 的直接或间接根类型。它本身没有定义组件；当 Object 没有更具体的类型定义时可以使用它，但 Server 应尽量使用更具体的类型。Server 可能无法提供从它到所有子类型的 `HasSubtype` 引用，因此不要求暴露完整子类型图。[§6.2 L205-L209](../../source/OPC-10000-5-v1.05.06.md#L205-L209) [§6.2 Table 8 L211-L217](../../source/OPC-10000-5-v1.05.06.md#L211-L217)

Part 5 允许通过子类型化扩展标准 ObjectType，也允许在每个 Object 实例上增加组件；但**不允许限制**标准 ObjectType 的组件。规范用 `NodeVersion` 加到 `BaseObjectType` 的例子说明：可以在类型层表达“Server 中的每个 Object 都提供某属性”。[§6.1 L201-L203](../../source/OPC-10000-5-v1.05.06.md#L201-L203)

这意味着标准类型提供的是“最小公共结构 + 可扩展点”，而不是封闭的最终结构。扩展时不能删除或收窄标准组件的建模规则。

## 3. ServerType 与 Server Object

`ServerType` 定义标准 Server Object 的能力与服务入口。它的 Mandatory 成员包括 `ServerArray`、`NamespaceArray`、`ServerStatus`、`ServiceLevel`、`Auditing`、`ServerCapabilities`、`ServerDiagnostics`、`VendorServerInfo` 和 `ServerRedundancy`；`UrisVersion`、`EstimatedReturnTime`、`LocalTime`、`Namespaces` 以及若干 Method 是 Optional。[§6.3.1 Table 9 L225-L250](../../source/OPC-10000-5-v1.05.06.md#L225-L250)

Table 9 的原文有些行显示为 `ServerStatus1`、`ServerCapabilities1`、`ServerDiagnostics1`、`ServerRedundancy1`。这些尾随数字是脚注标记，不是 BrowseName。Table 111 只给出 `Server` Object 的 BrowseName、`HasTypeDefinition`（`ServerType`）和一致性单元，不逐项列出成员名。[§8.3.2 Table 111 L2718-L2725](../../source/OPC-10000-5-v1.05.06.md#L2718-L2725) §8.3.2 的附加一致性单元表 Table 112 通过 BrowsePath 引用不带数字的 `ServerStatus`、`ServerCapabilities`、`ServerDiagnostics`、`ServerRedundancy` 等成员名，因此应以这些名称为准。[§8.3.2 Table 112 L2729-L2910](../../source/OPC-10000-5-v1.05.06.md#L2729-L2910)

标准 `Server` Object 是浏览服务器信息的入口，其内容由 `ServerType` 定义，而不是在实例上重新定义一遍；§8.3.2 还规定它是根 notifier：其 `EventNotifier` Attribute 应被设置为提供事件，Server 的所有事件都应能通过订阅该 Object 的事件访问。[§8.3.2 L2714-L2717](../../source/OPC-10000-5-v1.05.06.md#L2714-L2717)

```
Server (Object, TypeDefinition=ServerType)
├─ ServerArray / NamespaceArray / UrisVersion
├─ ServerStatus (ServerStatusType)
│  └─ BuildInfo (BuildInfoType)
├─ ServiceLevel / Auditing / EstimatedReturnTime / LocalTime
├─ ServerCapabilities (ServerCapabilitiesType)
│  ├─ OperationLimits (OperationLimitsType)
│  └─ ModellingRules / AggregateFunctions
├─ ServerDiagnostics (ServerDiagnosticsType)
│  └─ SessionsDiagnosticsSummary (SessionsDiagnosticsSummaryType)
└─ VendorServerInfo / ServerRedundancy / Namespaces
```

## 4. 能力、状态与诊断的分工

- **能力**由 `ServerCapabilities` 表达：Profile、Locale、采样率、连续点、数组/字符串长度、Session/Subscription/MonitoredItem 上限等。它回答“支持什么”。见 [ServerCapabilitiesType](../entities/servercapabilitiestype.md)。
- **状态**由 `ServerStatus` 表达：启动时间、当前时间、ServerState、构建信息、关机倒计时和原因。它回答“现在怎样”。见 [ServerStatusType](../entities/serverstatustype.md) 和 [BuildInfoType](../entities/buildinfotype.md)。
- **诊断**由 `ServerDiagnostics` 表达：服务器摘要、订阅数组、按 Session 的数组和对象、采样间隔诊断。它回答“运行得如何”。见 [ServerDiagnosticsType](../entities/serverdiagnosticstype.md)、[SessionsDiagnosticsSummaryType](../entities/sessionsdiagnosticssummarytype.md) 和 [SessionDiagnosticsObjectType](../entities/sessiondiagnosticsobjecttype.md)。
- **事件**由 EventTypes 表达，`Server` Object 是根 notifier。见 [events-and-auditing](events-and-auditing.md)。

这三类信息不应混用：`OperationLimits` 中的 `MaxNodesPerRead` 不是当前读数，`ServerStatus.State` 不是诊断计数器，`ServerDiagnostics.EnabledFlag` 也不表示 Server 是否支持其他服务/能力。

## 5. 与其他部分的关系

Part 5 只定义信息模型和标准节点的表示。以下内容明确不在本页范围内：

- **Part 3**：地址空间模型、NodeClass、引用和建模规则的完整语义。
- **Part 4**：服务、Session、Subscription、Read/Write/Browse 等的调用行为。
- **Part 6**：本项目未收录；本页不据此推导实例或编码规则，也不额外断言 NodeId 具体映射的归属。Part 5 自身的 NodeId 规则见 §4.1。
- **Part 7**：Profiles 与一致性单元的组合规则。
- **Part 18**：Role-Based Security 的 Role 和权限语义。

本项目未收录这些部分，因此本页只注明边界，不根据它们推导额外规则。

## 6. 页面地图

- 类型根基：[BaseObjectType](../entities/baseobjecttype.md)
- 服务器对象：[ServerType](../entities/servertype.md)
- 能力声明：[ServerCapabilitiesType](../entities/servercapabilitiestype.md)、[OperationLimitsType](../entities/operationlimitstype.md)
- 状态与构建：[ServerStatusType](../entities/serverstatustype.md)、[BuildInfoType](../entities/buildinfotype.md)
- 诊断：[ServerDiagnosticsType](../entities/serverdiagnosticstype.md)、[SessionsDiagnosticsSummaryType](../entities/sessionsdiagnosticssummarytype.md)、[SessionDiagnosticsObjectType](../entities/sessiondiagnosticsobjecttype.md)
- 事件与审计：[BaseEventType](../entities/baseeventtype.md)、[AuditEventType](../entities/auditeventtype.md)、[events-and-auditing](events-and-auditing.md)
- 建模规则：[ModellingRuleType](../entities/modellingruletype.md)
- [返回目录](../index.md)

> 本页由 LLM 综合多个 Part 5 章节生成，状态为 draft，尚未经过人工语义审阅。
