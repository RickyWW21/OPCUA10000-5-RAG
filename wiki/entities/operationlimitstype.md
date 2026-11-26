---
page_id: operationlimitstype
kind: entity
entity_id: ObjectType:OperationLimitsType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.3.11", "table": "20", "lines": "605-624"}, {"section": "6.3.11", "lines": "626-626"}, {"section": "6.3.11", "lines": "628-648"}, {"section": "6.3.11", "lines": "650-658"}]
---

# OperationLimitsType

**类型**：ObjectType（`IsAbstract=False`）  
**父类型**：`FolderType`  
**规范位置**：OPC 10000-5 §6.3.11，Table 20

## 用途

`OperationLimitsType` 是 `ServerCapabilities.OperationLimits` 的类型，用来集中暴露 Server 在一次服务调用中允许的数组规模。它不是会话或订阅的数量上限（那些在 `ServerCapabilitiesType` 的 `MaxSessions`、`MaxSubscriptions` 等 Property 中），而是**单个服务请求中各数组参数的最大长度**。[§6.3.11 Table 20 L605-L624](../../source/OPC-10000-5-v1.05.06.md#L605-L624)

## 重要成员

Table 20 列出的 Property 全部是 Optional，DataType 均为 `UInt32`，TypeDefinition 均为 `PropertyType`：

- `MaxNodesPerRead`
- `MaxNodesPerHistoryReadData`
- `MaxNodesPerHistoryReadEvents`
- `MaxNodesPerWrite`
- `MaxNodesPerHistoryUpdateData`
- `MaxNodesPerHistoryUpdateEvents`
- `MaxNodesPerMethodCall`
- `MaxNodesPerBrowse`
- `MaxNodesPerRegisterNodes`
- `MaxNodesPerTranslateBrowsePathsToNodeIds`
- `MaxNodesPerNodeManagement`
- `MaxMonitoredItemsPerCall`

规范要求：任何已提供的操作限制 Property 都必须具有**非零值**。[§6.3.11 L626-L626](../../source/OPC-10000-5-v1.05.06.md#L626-L626)

## 成员语义

这些值分别约束对应服务调用的数组长度，例如：

- `MaxNodesPerRead` 约束 `Read` 的 `nodesToRead` 数组。
- `MaxNodesPerWrite` 约束 `Write` 的 `nodesToWrite` 数组。
- `MaxNodesPerMethodCall` 约束 `Call` 的 `methodsToCall` 数组。
- `MaxNodesPerBrowse` 约束 `Browse` 的 `nodesToBrowse` 数组，或 `BrowseNext` 的 `continuationPoints` 数组。
- `MaxNodesPerRegisterNodes` 约束 `RegisterNodes` 的 `nodesToRegister` 和 `UnregisterNodes` 的 `nodesToUnregister`。
- `MaxNodesPerTranslateBrowsePathsToNodeIds` 约束 `browsePaths` 数组。
- `MaxNodesPerNodeManagement` 约束 AddNodes、AddReferences、DeleteNodes、DeleteReferences 的相关数组。
- `MaxMonitoredItemsPerCall` 约束 CreateMonitoredItems、ModifyMonitoredItems、SetMonitoringMode、DeleteMonitoredItems 和 SetTriggering 的相关数组。[§6.3.11 L628-L648](../../source/OPC-10000-5-v1.05.06.md#L628-L648) [§6.3.11 L650-L658](../../source/OPC-10000-5-v1.05.06.md#L650-L658)

## 相关类型与边界

- `OperationLimits` 是 `ServerCapabilitiesType` 的 Optional Object；见 [ServerCapabilitiesType](servercapabilitiestype.md)。
- `OperationLimitsType` 继承 `FolderType`，因此也具备 Folder 的组织语义；`FolderType` 本身不是本 Wiki 的独立页面。
- 本页只描述限制值的地址空间表示和 Part 5 明示的数组含义。服务调用失败、Bad 状态码和分页/连续点行为由 Part 4 定义，本项目未收录。
- 不要把 `OperationLimitsType` 与 `ServerCapabilitiesType` 上的 `MaxSessions`、`MaxSubscriptions`、`MaxMonitoredItems` 等“全局数量上限”混淆：前者约束单次请求的数组规模，后者约束 Server 能维持的对象数量。

## 相关页面

- [server-information-model](../topics/server-information-model.md)：能力声明的整体位置。
- [ServerCapabilitiesType](servercapabilitiestype.md)：`OperationLimits` 的宿主。
- [ServerType](servertype.md)：标准 Server Object。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
