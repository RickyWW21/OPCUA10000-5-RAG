---
page_id: servercapabilitiestype
kind: entity
entity_id: ObjectType:ServerCapabilitiesType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.3.2", "table": "10", "lines": "307-339"}, {"section": "6.3.2", "lines": "342-345"}, {"section": "6.3.2", "lines": "348-401"}, {"section": "6.3.2", "lines": "372-378"}, {"section": "6.3.2", "lines": "401-408"}]
---

# ServerCapabilitiesType

**类型**：ObjectType（`IsAbstract=False`）  
**父类型**：`BaseObjectType`  
**规范位置**：OPC 10000-5 §6.3.2，Table 10

## 用途

`ServerCapabilitiesType` 是 `ServerType.ServerCapabilities` 的类型，用来声明 Server 支持的 Profile、Locale、采样率、连续点数量、数组/字符串长度、Session/Subscription/MonitoredItem 上限，以及可选的 `OperationLimits` 等能力。它回答的是“这个 Server 支持什么、限制是多少”，而不是“当前状态如何”。[§6.3.2 Table 10 L307-L339](../../source/OPC-10000-5-v1.05.06.md#L307-L339)

## 重要成员

Table 10 中多数成员是 Optional Property；只有少数为 Mandatory。典型成员包括：

- **Mandatory**：`ServerProfileArray`、`LocaleIdArray`、`MinSupportedSampleRate`、`MaxBrowseContinuationPoints`、`MaxQueryContinuationPoints`、`MaxHistoryContinuationPoints`、`SoftwareCertificates`。
- **Optional Property**：`MaxLogObjectContinuationPoints`、`MaxArrayLength`、`MaxStringLength`、`MaxByteStringLength`、`MaxSessions`、`MaxSubscriptions`、`MaxMonitoredItems`、`MaxSubscriptionsPerSession`、`MaxMonitoredItemsPerSubscription`、`MaxSelectClauseParameters`、`MaxWhereClauseParameters`、`MaxMonitoredItemsQueueSize`、`ConformanceUnits`。
- **Optional Object**：`OperationLimits`（类型 `OperationLimitsType`）、`RoleSet`（类型在 Part 18 中定义）。
- **Mandatory Object**：`ModellingRules` 和 `AggregateFunctions`，二者的 TypeDefinition 都是 `FolderType`。
- **OptionalPlaceholder**：`<VendorCapability>`（`BaseDataType`，类型 `ServerVendorCapabilityType`）。

`ServerProfileArray` 的每个字符串应是 Profile URI，且列表应只包含当前配置下支持的 Profile。`LocaleIdArray` 是 Server 已知支持的 LocaleId 数组，但 Server 可能通过底层系统提供自己并不完全知晓的 Locale。[§6.3.2 L342-L345](../../source/OPC-10000-5-v1.05.06.md#L342-L345)

## 能力限制的边界

`OperationLimits` 是访问操作限制的入口，例如一次 Read 调用中数组的最大长度；`ModellingRules` 和 `AggregateFunctions` 是浏览入口，分别让客户端找到 Server 支持的建模规则和聚合函数。[§6.3.2 L372-L378](../../source/OPC-10000-5-v1.05.06.md#L372-L378)

规范明确提出两条边界：当供应商无法确定某个可选组件的限制时，该组件不得提供（shall not be included）；当供应商要暴露自有能力时，应向标准 `ServerCapabilities` 实例添加额外节点。`ConformanceUnits` 是 `QualifiedName[]`，列出 Server 当前配置支持的 conformance unit。[§6.3.2 L401-L408](../../source/OPC-10000-5-v1.05.06.md#L401-L408)

从 `MinSupportedSampleRate` 开始，§6.3.2 正文随后逐项定义各 Max* 成员；这些值表示“正常情况下”的上限，不保证 Server 在任何时刻都能达到，例如 `MaxBrowseContinuationPoints` 的值 0 表示 Server 不限制客户端使用的并行连续点数。[§6.3.2 L348-L401](../../source/OPC-10000-5-v1.05.06.md#L348-L401) 规范的这些细节属于 Part 5 对成员语义的说明，不应被解释为 Part 4 服务调用的完整规则。

## 相关类型与边界

- `ServerCapabilities` 是 `ServerType` 的 Mandatory 组件；见 [ServerType](servertype.md)。
- 操作限制的具体成员和“非零”约束见 [OperationLimitsType](operationlimitstype.md)。
- `ModellingRules` 文件夹中放置 `ModellingRuleType` 实例；见 [ModellingRuleType](modellingruletype.md)。
- `RoleSet`、`ServerVendorCapabilityType` 以及一些上限的服务语义依赖 Part 18、Part 4 等；本项目未收录，不在此展开。

## 相关页面

- [server-information-model](../topics/server-information-model.md)：Server 标准入口的整体结构。
- [ServerType](servertype.md)：能力对象的宿主类型。
- [OperationLimitsType](operationlimitstype.md)：服务操作限制。
- [ModellingRuleType](modellingruletype.md)：建模规则类型。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
