---
page_id: auditeventtype
kind: entity
entity_id: EventType:AuditEventType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.4.2", "table": "25", "lines": "804-824"}, {"section": "6.4.3", "table": "26", "lines": "905-923"}, {"section": "6.4.3", "lines": "924-928"}, {"section": "6.4.3", "lines": "931-942"}]
---

# AuditEventType

**类型**：EventType（在地址空间中表示为 ObjectType，`IsAbstract=True`）  
**父类型**：`BaseEventType`  
**规范位置**：OPC 10000-5 §6.4.3，Table 26

## 用途

`AuditEventType` 是审计事件的标准基类。它继承 `BaseEventType` 的全部 Property，并增加审计所需的“谁、何时、对什么动作、结果如何”等字段。它本身是抽象类型；具体审计事件通过其子类型区分连接、Session、证书、节点管理、历史访问、写入和方法调用等场景。[§6.4.2 Table 25 L804-L824](../../source/OPC-10000-5-v1.05.06.md#L804-L824) [§6.4.3 Table 26 L905-L923](../../source/OPC-10000-5-v1.05.06.md#L905-L923)

## 重要成员

Table 26 新增的 Property 如下，均使用 `HasProperty` 和 `PropertyType`：

| 成员 | 数据类型 | 建模规则 | 含义摘要 |
|---|---|---|---|
| `ActionTimeStamp` | `UtcTime` | Mandatory | 用户发起动作的时间 |
| `Status` | `Boolean` | Mandatory | 动作是否成功 |
| `ServerId` | `String` | Mandatory | 生成事件的 Server 的唯一标识 |
| `ClientAuditEntryId` | `String` | Mandatory | 客户端提供的可读 AuditEntryId |
| `ClientUserId` | `String` | Mandatory | 发起动作的用户标识 |
| `ClientApplicationUri` | `String` | Optional | 客户端应用的 URI |

这些事件类型对应的 Conformance Units 包括 `Auditing Connections`、`Auditing NodeManagement`、`Auditing History Services`、`Auditing Write` 和 `Auditing Method`。[§6.4.3 Table 26 L905-L923](../../source/OPC-10000-5-v1.05.06.md#L905-L923)

## 语义与边界

`AuditEventType` 继承 `BaseEventType` 的全部 Property，`BaseEventType` 的字段用于描述事件来源。若子类型没有另行规定 `SourceNode`，则该 Property 必须（shall）设为 Server 节点；`SourceName` 通常提供更多来源信息，例如方法调用事件可以是 `"Method/"` 加被调用方法名。[§6.4.3 L924-L928](../../source/OPC-10000-5-v1.05.06.md#L924-L928)

几个容易混淆的字段：

- `ActionTimeStamp` 是**用户发起动作**的时间；`BaseEventType.Time` 是 Server 生成审计事件（记录动作）的时间，两者含义不同。
- `Status=TRUE` 表示请求的动作可以执行；`FALSE` 表示未执行/失败。
- `ServerId` 即使在多个 Server 共用同一 URI 的透明冗余场景中，也应能唯一标识生成事件的 Server。
- `ClientAuditEntryId` 是人类可读的审计条目 ID；若因证书检查失败无法解密，应使用客户端 IP、端口、MAC、DNS 名等可识别信息替代。
- `ClientUserId` 的具体取值依赖身份令牌：UserName 令牌取用户名，X509 令牌取证书 Subject Name，Issued/JWT 令牌按规范规则组合 issuer/subject，Anonymous 令牌则为 null。[§6.4.3 L931-L942](../../source/OPC-10000-5-v1.05.06.md#L931-L942)

规范建议新的 `AuditEventType` 子类型不要增加核心 UA 规范已定义字段之外的额外 Property，以便通用审计客户端用一组核心 EventFields 收集所有相关审计事件。子类型的主要作用是让 `EventType` 可用于排序和分类。[§6.4.3 L924-L928](../../source/OPC-10000-5-v1.05.06.md#L924-L928)

## 相关类型与边界

- 父类型见 [BaseEventType](baseeventtype.md)，综合说明见 [events-and-auditing](../topics/events-and-auditing.md)。
- 具体子类型（如 `AuditSessionEventType`、`AuditCertificateEventType`、`AuditNodeManagementEventType`、`AuditUpdateMethodEventType`）在 §6.4.4–§6.4.27 中定义；本 Wiki 尚未为它们单独建页。
- 身份令牌、Session 和审计配置的服务语义属于 Part 4；Role 语义属于 Part 18；本项目未收录，不展开。
- 本页仅记录 Part 5 的地址空间表示和字段语义，不对审计实现是否满足安全策略作判断。

## 相关页面

- [events-and-auditing](../topics/events-and-auditing.md)：事件与审计的整体视图。
- [BaseEventType](baseeventtype.md)：审计事件的父类型。
- [ServerType](servertype.md)：`Auditing` Property 表示 Server 是否生成审计事件。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
