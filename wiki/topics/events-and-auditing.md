---
page_id: events-and-auditing
kind: topic
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.4.1", "lines": "796-799"}, {"section": "6.4.2", "table": "25", "lines": "804-824"}, {"section": "6.4.2", "lines": "827-841"}, {"section": "6.4.2", "lines": "847-850"}, {"section": "6.4.3", "table": "26", "lines": "905-923"}, {"section": "6.4.3", "lines": "924-928"}, {"section": "6.4.3", "lines": "931-944"}, {"section": "8.3.2", "lines": "2714-2717"}]
---

# 事件与审计（events-and-auditing）

本页综合 Part 5 §6.4 和 §8.3.2，说明标准事件类型如何在地址空间中表示、`BaseEventType` 提供哪些公共字段、`AuditEventType` 在此基础上增加什么，以及 Server Object 在事件通知中的位置。审计的“记录什么、保留多久、如何防篡改”等策略不属于 Part 5，本页不展开。

## 1. EventType 在地址空间中的表示

Part 5 规定，标准 EventTypes 在地址空间中表示为 **ObjectTypes**。事件类型的语义已经在 Part 3 中定义；Part 5 的 §6.4 只规定它们在地址空间中的表示。[§6.4.1 L796-L799](../../source/OPC-10000-5-v1.05.06.md#L796-L799)

因此，阅读 Part 5 的 EventType 表时，应把它当作 ObjectType 定义：`IsAbstract`、父类型、`HasProperty` 组件和 ModellingRule 都是地址空间层面的信息。事件实例本身不是这些 ObjectType 的 Object 实例，而是通过事件通知机制传递的字段集合；具体订阅和 EventFilter 行为由 Part 4 定义。

## 2. BaseEventType：公共字段

`BaseEventType` 是抽象类型，父类型为 `BaseObjectType`。它的 Mandatory Property 包括 `EventId`、`EventType`、`SourceNode`、`SourceName`、`Time`、`ReceiveTime`、`Message` 和 `Severity`；`LocalTime`、`ConditionClassId`、`ConditionClassName`、`ConditionSubClassId`、`ConditionSubClassName` 为 Optional。[§6.4.2 Table 25 L804-L824](../../source/OPC-10000-5-v1.05.06.md#L804-L824)

这些字段解决四个问题：

1. **身份**：`EventId` 唯一标识一次事件通知，可用于冗余切换时减少缺口/重叠；`EventType` 给出具体事件类型的 NodeId。
2. **来源**：`SourceNode` 指向事件来源节点，无具体来源时为 null；`SourceName` 提供可读描述。
3. **时间**：`Time` 是事件发生时间，应尽量接近事件产生点设置，中间 Server 不得修改；`ReceiveTime` 是当前 Server 收到事件的时间，同一事件经不同 Server 转发时可能不同。[§6.4.2 L827-L841](../../source/OPC-10000-5-v1.05.06.md#L827-L841)
4. **内容**：`Message` 是可本地化文本，不能为 null；`Severity` 为 1–1000，1 最低、1000 最高。[§6.4.2 L847-L850](../../source/OPC-10000-5-v1.05.06.md#L847-L850)

`ConditionClassId` 等四个字段的名称来自 Part 9 的 ConditionClass 概念，后来被推广到一般 Event；Part 9 的完整 Condition/Alarm 语义本项目未收录。

## 3. AuditEventType：审计专用字段

`AuditEventType` 是抽象类型，父类型为 `BaseEventType`，继承后者的全部 Property。它增加的字段包括：

- `ActionTimeStamp`（`UtcTime`，Mandatory）：用户发起动作的时间。
- `Status`（`Boolean`，Mandatory）：动作是否成功。
- `ServerId`（`String`，Mandatory）：生成事件的 Server 的唯一标识，即使在透明冗余中也要唯一。
- `ClientAuditEntryId`（`String`，Mandatory）：人类可读的审计条目 ID。
- `ClientUserId`（`String`，Mandatory）：发起动作的用户标识。
- `ClientApplicationUri`（`String`，Optional）：客户端应用 URI。

这些字段与 `BaseEventType` 的字段配合：`BaseEventType` 描述事件来源，`AuditEventType` 描述“谁在何时对什么动作、结果如何”。[§6.4.3 Table 26 L905-L923](../../source/OPC-10000-5-v1.05.06.md#L905-L923)

`ActionTimeStamp` 和 `Time` 容易混淆：前者是用户发起动作的时间，后者是 Server 生成审计事件（记录动作）的时间。`Status=TRUE` 表示动作可以执行，`FALSE` 表示未执行/失败。子类型没有另行规定时，`SourceNode` 必须（shall）设为 Server 节点；方法调用审计的 `SourceName` 通常是 `"Method/"` 加方法名。[§6.4.3 L924-L928](../../source/OPC-10000-5-v1.05.06.md#L924-L928)

`ClientUserId` 的取值依赖身份令牌：UserName 取用户名，X509 取证书 Subject Name，Issued/JWT 按 issuer/subject 规则组合，Anonymous 为 null。上述 `ActionTimeStamp`、`Status`、`ClientAuditEntryId`、`ClientUserId` 等字段的语义见 §6.4.3 正文。[§6.4.3 L931-L944](../../source/OPC-10000-5-v1.05.06.md#L931-L944) 身份令牌的服务层语义属于 Part 4，本项目未收录。

## 4. Server Object 作为根 notifier

标准 `Server` Object 是服务器信息的浏览入口，其内容由 `ServerType` 定义。它同时是**根 notifier**：`EventNotifier` Attribute 应被设置为允许事件通知，Server 的所有事件都应能通过订阅该 Object 的事件访问。[§8.3.2 L2714-L2717](../../source/OPC-10000-5-v1.05.06.md#L2714-L2717)

这意味着客户端通常可以从 `Server` 这一入口发现事件，而不必先知道具体事件源。事件源节点与 `Server` 之间通过事件源/notifier 引用组织；具体引用类型和订阅行为属于 Part 3/Part 4，本页只记录 Part 5 对 Server Object 的定位。

## 5. 审计事件的分类与扩展边界

`AuditEventType` 的 Conformance Units 包括 Auditing Connections、Auditing NodeManagement、Auditing History Services、Auditing Write 和 Auditing Method。具体子类型（如 `AuditSessionEventType`、`AuditCertificateEventType`、`AuditNodeManagementEventType`、`AuditUpdateMethodEventType`）用于让 `EventType` 可排序和分类。[§6.4.3 Table 26 L905-L923](../../source/OPC-10000-5-v1.05.06.md#L905-L923)

规范建议新的审计子类型不要增加核心 UA 规范已定义字段之外的额外 Property，以便通用审计客户端用一组核心 EventFields 收集所有相关审计事件。这是互操作性建议，不表示所有审计事件都只包含这些字段。[§6.4.3 L924-L928](../../source/OPC-10000-5-v1.05.06.md#L924-L928)

## 6. 页面地图与边界

- 事件基类：[BaseEventType](../entities/baseeventtype.md)
- 审计基类：[AuditEventType](../entities/auditeventtype.md)
- 宿主入口：[ServerType](../entities/servertype.md)
- 服务器整体视图：[server-information-model](server-information-model.md)
- 诊断（与事件不同）：[diagnostics](diagnostics.md)

本项目未收录 Part 3（事件模型）、Part 4（订阅/EventFilter）、Part 9（Alarms and Conditions）和 Part 18（Role-Based Security）。因此本页不解释事件实例如何被订阅、Condition 状态机如何工作，也不对审计合规性作判断。

## 相关页面

- [BaseEventType](../entities/baseeventtype.md)：事件公共字段。
- [AuditEventType](../entities/auditeventtype.md)：审计事件基类。
- [ServerType](../entities/servertype.md)：Server Object 与根 notifier。
- [server-information-model](server-information-model.md)：标准 Server 地址空间。
- [返回目录](../index.md)

> 本页由 LLM 综合多个 Part 5 章节生成，状态为 draft，尚未经过人工语义审阅。
