---
page_id: baseeventtype
kind: entity
entity_id: EventType:BaseEventType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.4.1", "lines": "796-799"}, {"section": "6.4.2", "table": "25", "lines": "804-824"}, {"section": "6.4.2", "lines": "827-841"}, {"section": "6.4.2", "lines": "847-861"}, {"section": "8.3.2", "lines": "2714-2717"}]
---

# BaseEventType

**类型**：EventType（在地址空间中表示为 ObjectType，`IsAbstract=True`）  
**父类型**：`BaseObjectType`  
**规范位置**：OPC 10000-5 §6.4.2，Table 25

## 用途

`BaseEventType` 是 OPC UA 标准事件类型的根基。Part 5 明确说明：标准 EventTypes 在地址空间中表示为 ObjectTypes；它们的类型语义在 Part 3 中定义，Part 5 规定其在地址空间中的表示。[§6.4.1 L796-L799](../../source/OPC-10000-5-v1.05.06.md#L796-L799)

`BaseEventType` 是抽象类型，不能直接实例化；具体事件类型从它继承。它定义了所有事件都应具备的公共字段，这些字段的地址空间表示由 Table 25 给出。[§6.4.2 Table 25 L804-L824](../../source/OPC-10000-5-v1.05.06.md#L804-L824)

## 重要成员

Table 25 中的 Property 使用 `HasProperty` 引用，TypeDefinition 为 `PropertyType`：

| 成员 | 数据类型 | 建模规则 | 含义摘要 |
|---|---|---|---|
| `EventId` | `ByteString` | Mandatory | Server 生成的唯一事件标识 |
| `EventType` | `NodeId` | Mandatory | 具体事件类型的 NodeId |
| `SourceNode` | `NodeId` | Mandatory | 事件来源节点；无具体来源时为 null |
| `SourceName` | `String` | Mandatory | 事件来源的描述 |
| `Time` | `UtcTime` | Mandatory | 事件发生时间 |
| `ReceiveTime` | `UtcTime` | Mandatory | Server 收到事件的时间 |
| `LocalTime` | `TimeZoneDataType` | Optional | 事件发生地点的本地时间偏移 |
| `Message` | `LocalizedText` | Mandatory | 可本地化的事件文本 |
| `Severity` | `UInt16` | Mandatory | 紧急程度，1–1000 |
| `ConditionClassId` | `NodeId` | Optional | 事件所属 ConditionClass |
| `ConditionClassName` | `LocalizedText` | Optional | ConditionClass 的显示名 |
| `ConditionSubClassId` | `NodeId[]` | Optional | 附加子类 |
| `ConditionSubClassName` | `LocalizedText[]` | Optional | 附加子类的显示名 |

`EventId` 必须唯一标识一次事件通知；Server 可以用 GUID 等方式生成，客户端可用它在冗余切换时减少缺口或重叠。`EventType`、`SourceNode`、`SourceName`、`Time`、`ReceiveTime` 等字段的语义在 §6.4.2 正文中逐项说明。[§6.4.2 L827-L841](../../source/OPC-10000-5-v1.05.06.md#L827-L841)

## 重要语义

- `Time` 应尽可能接近事件产生点设置；一旦设置，中间 OPC UA Server 不得修改。
- `ReceiveTime` 是当前 Server 收到事件的时间；同一事件经不同 Server 转发时，各 Server 可以给出不同的 `ReceiveTime`。
- `Message` 不能为 null；如果 Server 没有描述文本，必须（shall）返回事件关联节点 BrowseName 的字符串部分。
- `Severity` 范围为 1–1000，1 最低、1000 最高。规范预期很少有实现支持 1000 个不同等级，因此 Server 开发者负责把等级分布到 1–1000，使客户端可以假定线性分布；规范还建议把高紧急度事件映射到 667–1000、中紧急度到 334–666、低紧急度到 1–333。[§6.4.2 L847-L861](../../source/OPC-10000-5-v1.05.06.md#L847-L861)

## 相关类型与边界

- 审计事件从它派生，见 [AuditEventType](auditeventtype.md)。
- 综合说明见 [events-and-auditing](../topics/events-and-auditing.md)。
- `ConditionClassId` 等字段的名称来自 Part 9，后来被推广到一般 Event；Part 9 的 Condition/ Alarm 完整语义本项目未收录，本页不展开。
- Part 3 定义 EventType 的类型语义和事件模型，Part 4 定义订阅和 EventFilter 的服务行为；本项目只记录 Part 5 的地址空间表示。

## 相关页面

- [events-and-auditing](../topics/events-and-auditing.md)：事件与审计的整体视图。
- [AuditEventType](auditeventtype.md)：审计事件基类。
- [ServerType](servertype.md)：标准 `Server` Object 的类型；该 Object 同时是事件通知的根 notifier。[§8.3.2 L2714-L2717](../../source/OPC-10000-5-v1.05.06.md#L2714-L2717)
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
