---
page_id: buildinfotype
kind: entity
entity_id: VariableType:BuildInfoType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "7.7", "table": "77", "lines": "1939-1954"}, {"section": "7.7", "lines": "1935-1937"}, {"section": "12.4", "table": "230", "lines": "4624-4632"}, {"section": "12.4", "table": "231", "lines": "4636-4643"}, {"section": "7.6", "table": "76", "lines": "1917-1933"}]
---

# BuildInfoType

**类型**：VariableType（复杂变量类型，`IsAbstract=False`）  
**父类型**：`BaseDataVariableType`  
**DataType**：`BuildInfo`（ValueRank = -1，标量）  
**规范位置**：OPC 10000-5 §7.7，Table 77；结构定义见 §12.4，Table 230、Table 231

## 用途

`BuildInfoType` 是 `ServerStatusType.BuildInfo` 子变量的类型，用来暴露服务器软件的构建信息。它把 `BuildInfo` 结构中的字段映射为六个 Mandatory 子 Variable，使客户端可以读取软件 URI、厂商、产品名、版本、构建号和构建日期。[§7.7 Table 77 L1939-L1954](../../source/OPC-10000-5-v1.05.06.md#L1939-L1954)

## 重要成员

Table 77 的六个子 Variable 都是 `HasComponent`、`BaseDataVariableType`、`Mandatory`：

| 地址空间成员 | 数据类型 | 对应 `BuildInfo` 字段 |
|---|---|---|
| `ProductUri` | `String` | `productUri` |
| `ManufacturerName` | `String` | `manufacturerName` |
| `ProductName` | `String` | `productName` |
| `SoftwareVersion` | `String` | `softwareVersion` |
| `BuildNumber` | `String` | `buildNumber` |
| `BuildDate` | `UtcTime` | `buildDate` |

地址空间的 BrowseName 使用 PascalCase，而 `BuildInfo` DataType 的结构字段在 §12.4 中使用 lowerCamelCase。两者是同一信息的不同表示层，不能把 `ProductUri` 和 `productUri` 当作两个不同的规范字段。[§12.4 Table 230 L4624-L4632](../../source/OPC-10000-5-v1.05.06.md#L4624-L4632)

## 结构语义

§12.4 对 `BuildInfo` 的字段给出简短定义：`productUri` 是标识软件的 URI，`manufacturerName` 是软件厂商名称，`productName` 是软件名称，`softwareVersion` 是软件版本，`buildNumber` 是构建号，`buildDate` 是构建日期时间。[§12.4 Table 230 L4624-L4632](../../source/OPC-10000-5-v1.05.06.md#L4624-L4632) `BuildInfo` 本身是 Structure DataType 的子类型；其地址空间表示由 Table 231 定义，BrowseName 为 `BuildInfo`、`IsAbstract=FALSE`、一致性单元为 `Base Info ServerType`。[§12.4 Table 231 L4636-L4643](../../source/OPC-10000-5-v1.05.06.md#L4636-L4643)

来源交叉引用异常：§7.7 正文 L1937 写 `BuildInfoType` 的 DataVariables 参照“12.3.15.1”的语义，但本地原文的 §12.3.15.1 实际是 `AnonymousIdentityToken`，`BuildInfo` 实际定义在 §12.4。本页按 §12.4 定位结构，并保留 §7.7 的原始表述作为异常记录，不修改原文。[§7.7 L1935-L1937](../../source/OPC-10000-5-v1.05.06.md#L1935-L1937) [§12.4 Table 230 L4624-L4632](../../source/OPC-10000-5-v1.05.06.md#L4624-L4632) [§12.4 Table 231 L4636-L4643](../../source/OPC-10000-5-v1.05.06.md#L4636-L4643)

`BuildInfoType` 在 Server 状态树中的位置是 `ServerStatus.BuildInfo`。`ServerStatusType` 的 Table 76 明确定义了 `BuildInfo` 子变量及其 DataType 为 `BuildInfo`、TypeDefinition 为 `BuildInfoType`、建模规则为 Mandatory。[§7.6 Table 76 L1917-L1933](../../source/OPC-10000-5-v1.05.06.md#L1917-L1933)

## 相关类型与边界

- 宿主变量见 [ServerStatusType](serverstatustype.md)。
- `BuildInfo` DataType 的字段名是 lowerCamelCase；本页成员表已标明映射关系。
- 本页不展开 Part 4 的 `ApplicationDescription` 或 Part 7 的 Profile 声明；构建信息与 Server Profile 是不同概念。
- 本页只保证 Part 5 的地址空间结构；这些字符串是否满足厂商特定的格式要求，不在 Part 5 的范围内。

## 相关页面

- [server-information-model](../topics/server-information-model.md)：Server 标准入口。
- [ServerStatusType](serverstatustype.md)：`BuildInfo` 的宿主变量类型。
- [ServerType](servertype.md)：标准 Server Object。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
