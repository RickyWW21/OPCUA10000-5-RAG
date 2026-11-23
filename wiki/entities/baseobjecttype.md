---
page_id: baseobjecttype
kind: entity
entity_id: ObjectType:BaseObjectType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.2", "table": "8", "lines": "211-217"}, {"section": "6.2", "lines": "205-209"}, {"section": "6.1", "lines": "201-203"}]
---

# BaseObjectType

**类型**：ObjectType（`IsAbstract=False`）  
**规范位置**：OPC 10000-5 §6.2，Table 8

## 用途

`BaseObjectType` 是 OPC UA 对象类型层级的根基。当某个 Object 没有更具体的类型定义可用时，Server 可以用它作为类型；但规范建议 Server 在可能时使用更具体的类型。所有其他 ObjectType 都应直接或间接继承它。规范同时说明，Server 可能无法提供从 `BaseObjectType` 到全部子类型的 `HasSubtype` 引用，因此并不要求暴露完整的子类型关系。[§6.2 L205-L209](../../source/OPC-10000-5-v1.05.06.md#L205-L209)

Table 8 只给出 BrowseName、`IsAbstract` 和 Conformance Unit，没有列出任何组件（References 一栏为空）。因此它是一个纯粹的类型根基，而不是带有 `ServerStatus`、`ServerCapabilities` 之类成员的“服务器对象模板”；这些成员属于 `ServerType`。[§6.2 Table 8 L211-L217](../../source/OPC-10000-5-v1.05.06.md#L211-L217)

## 重要成员与关系

- **父类型**：无。它是 ObjectType 层级的根。
- **子类型**：其他所有 ObjectType，包括 `ServerType`、`ModellingRuleType`、`FolderType` 等，均直接或间接继承。
- **自有组件**：无。
- **建模规则**：Table 8 未为其自身定义 ModellingRule；它作为类型定义使用。
- **一致性单元**：`Base Info Base Types`。

## 相关类型与边界

Part 5 §6.1 允许通过子类型化扩展 ObjectType，也允许在每个 Object 实例上增加组件；但**不允许限制**本标准定义的 ObjectType 的组件。规范给出的例子是把 Part 3 定义的 `NodeVersion` Property 加到 `BaseObjectType` 上，表示 Server 中的每个 Object 都提供该属性。[§6.1 L201-L203](../../source/OPC-10000-5-v1.05.06.md#L201-L203)

需要注意的是，`BaseObjectType` 的“根类型”语义来自 Part 3 的地址空间模型；本项目只收录 Part 5，不展开 Part 3 中 ObjectType、继承和实例化规则的完整定义。阅读本页时应把“所有 ObjectType 继承它”理解为 Part 5 在 §6.2 中重申的约束，而不是本项目重新定义的规则。

## 相关页面

- [server-information-model](../topics/server-information-model.md)：Server 信息模型的整体结构。
- [ServerType](servertype.md)：最常用的 `BaseObjectType` 子类型。
- [ModellingRuleType](modellingruletype.md)：另一种直接或间接继承 `BaseObjectType` 的标准类型。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
