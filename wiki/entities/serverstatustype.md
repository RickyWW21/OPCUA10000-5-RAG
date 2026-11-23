---
page_id: serverstatustype
kind: entity
entity_id: VariableType:ServerStatusType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "7.6", "table": "76", "lines": "1917-1933"}, {"section": "12.10", "table": "242", "lines": "4779-4787"}, {"section": "6.3.1", "lines": "266-266"}]
---

# ServerStatusType

**类型**：VariableType（复杂变量类型，`IsAbstract=False`）  
**父类型**：`BaseDataVariableType`  
**DataType**：`ServerStatusDataType`（ValueRank = -1，标量）  
**规范位置**：OPC 10000-5 §7.6，Table 76；结构定义见 §12.10，Table 242

## 用途

`ServerStatusType` 是 `ServerType.ServerStatus` 组件的 VariableType，用于以一组标准 DataVariables 暴露服务器状态。它把 `ServerStatusDataType` 结构中的字段映射为可单独浏览和读取的子 Variable，使客户端可以读取整个结构，也可以只读 `State`、`CurrentTime` 等单个字段。[§7.6 Table 76 L1917-L1933](../../source/OPC-10000-5-v1.05.06.md#L1917-L1933)

## 重要成员

Table 76 定义六个 Mandatory 子 Variable，均为 `HasComponent`，TypeDefinition 除 `BuildInfo` 外都是 `BaseDataVariableType`：

| 成员 | 数据类型 | TypeDefinition | 建模规则 |
|---|---|---|---|
| `StartTime` | `UtcTime` | `BaseDataVariableType` | Mandatory |
| `CurrentTime` | `UtcTime` | `BaseDataVariableType` | Mandatory |
| `State` | `ServerState` | `BaseDataVariableType` | Mandatory |
| `BuildInfo` | `BuildInfo` | `BuildInfoType` | Mandatory |
| `SecondsTillShutdown` | `UInt32` | `BaseDataVariableType` | Mandatory |
| `ShutdownReason` | `LocalizedText` | `BaseDataVariableType` | Mandatory |

`ServerStatus` 包含描述服务器状态的元素，其完整语义见 §12.10；`ServerStatusType` 只是把这些元素暴露为地址空间中的 DataVariables。[§6.3.1 L266-L266](../../source/OPC-10000-5-v1.05.06.md#L266-L266)

## 数据语义

`ServerStatusDataType` 在 §12.10 中定义如下：

- `startTime`：Server 启动的 UTC 时间；对某个 Server 实例是常量，Server 改变状态时不会重置。
- `currentTime`：Server 已知的当前 UTC 时间。
- `state`：当前 `ServerState`，其枚举值在 §12.6 中定义。
- `buildInfo`：`BuildInfo` 结构，描述构建信息。
- `secondsTillShutdown`：距离关机的近似秒数；只在状态进入 `SHUTDOWN` 后有意义。
- `shutdownReason`：关机的本地化原因；只在 `SHUTDOWN` 后有意义；没有具体原因时可为 null 或空。[§12.10 Table 242 L4779-L4787](../../source/OPC-10000-5-v1.05.06.md#L4779-L4787)

注意地址空间中的 BrowseName 使用 PascalCase（`StartTime`），而 DataType 结构字段使用 lowerCamelCase（`startTime`）。本页的成员表按 Table 76 的地址空间名称书写。

## 相关类型与边界

- 宿主是 `ServerType.ServerStatus`。Table 9 原行显示为 `ServerStatus1`，其中尾随数字是脚注标记，不是成员名；Server Object 的定义使用 `ServerStatus`。见 [ServerType](servertype.md)。
- `BuildInfo` 子变量使用 [BuildInfoType](buildinfotype.md)，其 DataType 为 `BuildInfo`。
- `ServerState` 枚举的取值在 §12.6 中定义；本 Wiki 尚未建页。
- 状态值的具体含义（例如 `RUNNING`、`SHUTDOWN`）由 Part 5 §12.6 定义，服务层如何改变状态由 Part 4 定义；本项目只展开 Part 5。
- 本页描述地址空间结构，不保证 Server 的所有状态变化都通过该变量可见。

## 相关页面

- [server-information-model](../topics/server-information-model.md)：Server 标准入口。
- [ServerType](servertype.md)：`ServerStatus` 的宿主。
- [BuildInfoType](buildinfotype.md)：构建信息 VariableType。
- [diagnostics](../topics/diagnostics.md)：诊断信息与状态信息的边界。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
