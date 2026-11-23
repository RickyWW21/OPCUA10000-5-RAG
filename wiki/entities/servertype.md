---
page_id: servertype
kind: entity
entity_id: ObjectType:ServerType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.3.1", "table": "9", "lines": "225-250"}, {"section": "6.3.1", "lines": "253-260"}, {"section": "8.3.2", "table": "111", "lines": "2718-2725"}, {"section": "8.3.2", "table": "112", "lines": "2729-2910"}, {"section": "8.3.2", "lines": "2714-2717"}]
---

# ServerType

**类型**：ObjectType（`IsAbstract=False`）  
**父类型**：`BaseObjectType`  
**规范位置**：OPC 10000-5 §6.3.1，Table 9；Server Object 实例见 §8.3.2，Table 111

## 用途

`ServerType` 定义 OPC UA Server 对外声明其能力时使用的标准 ObjectType。标准地址空间中的 `Server` Object 以它为 TypeDefinition，因此客户端可以从 `Server` 浏览到服务器标识、状态、能力、诊断和冗余等标准入口。[§6.3.1 Table 9 L225-L250](../../source/OPC-10000-5-v1.05.06.md#L225-L250) [§8.3.2 Table 111 L2718-L2725](../../source/OPC-10000-5-v1.05.06.md#L2718-L2725)

§8.3.2 同时规定 `Server` Object 作为根 notifier：其 `EventNotifier` Attribute 应被设置为提供事件，Server 的所有事件都应能通过订阅该 Object 的事件访问。[§8.3.2 L2714-L2717](../../source/OPC-10000-5-v1.05.06.md#L2714-L2717)

## 重要成员

Table 9 中的关键组件如下。原表某些行末尾带脚注编号（例如 `ServerStatus1`、`ServerCapabilities1`、`ServerDiagnostics1`、`ServerRedundancy1`）；这些数字是脚注标记，不是 BrowseName 的一部分。Table 111 只给出 `Server` Object 的 BrowseName、`HasTypeDefinition`（`ServerType`）和一致性单元，不逐项列出成员名。[§8.3.2 Table 111 L2718-L2725](../../source/OPC-10000-5-v1.05.06.md#L2718-L2725) §8.3.2 的附加一致性单元表 Table 112 通过 BrowsePath 使用不带数字的 `ServerStatus`、`ServerCapabilities`、`ServerDiagnostics`、`ServerRedundancy` 等成员名，可作为命名依据。[§8.3.2 Table 112 L2729-L2910](../../source/OPC-10000-5-v1.05.06.md#L2729-L2910)

| 成员 | 节点类别 | 数据类型 / 类型定义 | 建模规则 |
|---|---|---|---|
| `ServerArray` | Variable | `String[]` / `PropertyType` | Mandatory |
| `NamespaceArray` | Variable | `String[]` / `PropertyType` | Mandatory |
| `ServerStatus` | Variable | `ServerStatusDataType` / `ServerStatusType` | Mandatory |
| `ServiceLevel` | Variable | `Byte` / `PropertyType` | Mandatory |
| `Auditing` | Variable | `Boolean` / `PropertyType` | Mandatory |
| `ServerCapabilities` | Object | `ServerCapabilitiesType` | Mandatory |
| `ServerDiagnostics` | Object | `ServerDiagnosticsType` | Mandatory |
| `VendorServerInfo` | Object | `VendorServerInfoType` | Mandatory |
| `ServerRedundancy` | Object | `ServerRedundancyType` | Mandatory |
| `UrisVersion` | Variable | `VersionTime` / `PropertyType` | Optional |
| `EstimatedReturnTime` | Variable | `DateTime` / `PropertyType` | Optional |
| `LocalTime` | Variable | `TimeZoneDataType` / `PropertyType` | Optional |
| `Namespaces` | Object | `NamespacesType` | Optional |
| `GetMonitoredItems` 等 | Method | §9 定义 | Optional |

`ServerArray` 是 Server URI 表，索引 0 保留给本地 Server；`NamespaceArray` 是命名空间 URI 表，索引 0 保留给 OPC UA 命名空间，索引 1 保留给本地 Server。规范要求 `ApplicationUri` 与 `ServerArray[0]`、`NamespaceArray[1]` 一致。客户端持有打开的 Session 时，Server 不得修改或删除这两张表的条目，但可以追加条目；对 `NamespaceArray`，规范还建议 Server 只追加条目而不改变已有索引，因为客户端可能缓存带索引的 NodeId，而 Server 并不总能避免改变索引，所以缓存 NamespaceIndex 的客户端应在启动 Session 时检查索引是否变化。[§6.3.1 L253-L260](../../source/OPC-10000-5-v1.05.06.md#L253-L260)

## 相关类型与边界

- `ServerStatus` 是复杂 Variable，类型为 `ServerStatusType`，其数据语义在 §12.10 的 `ServerStatusDataType` 中定义；本 Wiki 另有 [ServerStatusType](serverstatustype.md)。
- `ServerCapabilities` 承载 Profile、限制和可选能力，本 Wiki 另有 [ServerCapabilitiesType](servercapabilitiestype.md)。
- `ServerDiagnostics` 是诊断信息的根，本 Wiki 另有 [ServerDiagnosticsType](serverdiagnosticstype.md)。
- `VendorServerInfo`、`ServerRedundancy`、`Namespaces` 只在本页列出，尚未单独建页；其详细规则见 §6.3.6、§6.3.7 和 §6.3.14。
- `ServerType` 只规定标准入口和成员，不保证每个可选成员都出现；实际暴露内容取决于 Server 的能力与一致性单元。
- 本页不展开 Part 4 中 Session、Subscription 等服务语义，也不展开 Part 7 的 Profile 规则；本项目未收录这些部分。

## 相关页面

- [server-information-model](../topics/server-information-model.md)：从空 Server 地址空间到标准 Server Object 的整体视图。
- [BaseObjectType](baseobjecttype.md)：`ServerType` 的父类型。
- [ServerCapabilitiesType](servercapabilitiestype.md)：能力声明入口。
- [ServerDiagnosticsType](serverdiagnosticstype.md)：诊断入口。
- [ServerStatusType](serverstatustype.md)：状态变量类型。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。脚注编号已按原文上下文处理，但正式实现仍应以规范发布的 NodeSet 为准。
