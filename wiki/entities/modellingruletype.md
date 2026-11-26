---
page_id: modellingruletype
kind: entity
entity_id: ObjectType:ModellingRuleType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.5", "table": "62", "lines": "1695-1702"}, {"section": "8.4.1", "table": "113", "lines": "2918-2924"}, {"section": "8.4.2", "table": "114", "lines": "2930-2936"}, {"section": "8.4.3", "table": "115", "lines": "2942-2948"}, {"section": "8.4.4", "table": "116", "lines": "2954-2960"}, {"section": "8.4.5", "table": "117", "lines": "2966-2972"}, {"section": "11.11", "table": "132", "lines": "3279-3288"}]
---

# ModellingRuleType

**类型**：ObjectType（`IsAbstract=False`）  
**父类型**：`BaseObjectType`  
**规范位置**：OPC 10000-5 §6.5，Table 62；标准实例见 §8.4；引用类型见 §11.11

## 用途

`ModellingRuleType` 是 OPC UA ModellingRule 对象的类型。ModellingRule 的语义在 Part 3 中定义；Part 5 规定它们在地址空间中的表示：每个标准 ModellingRule 是一个 Object，其 TypeDefinition 指向 `ModellingRuleType`。[§6.5 Table 62 L1695-L1702](../../source/OPC-10000-5-v1.05.06.md#L1695-L1702)

它本身没有定义额外组件；Table 62 只给出 BrowseName、`IsAbstract=False`、父类型和一致性单元。也就是说，`ModellingRuleType` 是“规则的规则类型”，其区分能力来自具体 ModellingRule Object 的 BrowseName（`Mandatory`、`Optional` 等），而不是来自该类型的内部字段。

## 标准实例

§8.4.1–§8.4.5 分别定义了以下标准 ModellingRule Objects，每个的 TypeDefinition 都是 `ModellingRuleType`：[§8.4.1 Table 113 L2918-L2924](../../source/OPC-10000-5-v1.05.06.md#L2918-L2924) [§8.4.2 Table 114 L2930-L2936](../../source/OPC-10000-5-v1.05.06.md#L2930-L2936) [§8.4.3 Table 115 L2942-L2948](../../source/OPC-10000-5-v1.05.06.md#L2942-L2948) [§8.4.4 Table 116 L2954-L2960](../../source/OPC-10000-5-v1.05.06.md#L2954-L2960) [§8.4.5 Table 117 L2966-L2972](../../source/OPC-10000-5-v1.05.06.md#L2966-L2972)

- `ExposesItsArray`
- `Mandatory`
- `Optional`
- `OptionalPlaceholder`
- `MandatoryPlaceholder`

以 `Mandatory` 为例（Table 114）：BrowseName 为 `Mandatory`，`HasTypeDefinition` 指向 `ObjectType` `ModellingRuleType`，一致性单元为 `Base Info Base Types`。其他四个标准实例的结构相同。它们通常位于 `ServerCapabilities.ModellingRules` 文件夹下，供客户端浏览 Server 支持的建模规则。该文件夹是 `ServerCapabilitiesType` 的 Mandatory 组件，类型为 `FolderType`；见 [ServerCapabilitiesType](servercapabilitiestype.md)。

## 与组件的关系

类型定义中的实例声明节点通过 `HasModellingRule` ReferenceType 指向对应的 ModellingRule Object，从而声明该实例声明是 Mandatory、Optional 还是 Placeholder。`HasModellingRule` 是非层次引用，`InverseName` 为 `ModellingRuleOf`，`Symmetric=False`，`IsAbstract=False`。[§11.11 Table 132 L3279-L3288](../../source/OPC-10000-5-v1.05.06.md#L3279-L3288)

因此，读取一个类型定义时，不能只看实例声明节点是否存在；还要看它通过 `HasModellingRule` 指向哪个规则对象。Part 5 只规定这些节点和引用的地址空间表示，规则在实例化时如何约束组件属于 Part 3 的建模规则语义，本项目未收录。

## 相关类型与边界

- 父类型见 [BaseObjectType](baseobjecttype.md)。
- `ModellingRuleType` 的实例不是“数据类型”，而是 Object；不要把它与 `DataType` 或 `VariableType` 混淆。
- 本页只覆盖 Part 5 的表示和 `HasModellingRule` 引用；不展开 Part 3 中 Mandatory/Optional/Placeholder 的完整实例化算法。
- 在 Table 9 等定义表中，`ModellingRule` 列写的是规则名称；在类型定义的地址空间中应通过 `HasModellingRule` 指向相应 Object，而不是把规则名称当作组件 BrowseName。

## 相关页面

- [server-information-model](../topics/server-information-model.md)：建模规则在标准地址空间中的位置。
- [BaseObjectType](baseobjecttype.md)：父类型。
- [ServerCapabilitiesType](servercapabilitiestype.md)：`ModellingRules` 文件夹的宿主。
- [ServerType](servertype.md)：大量组件使用 Mandatory/Optional 规则。
- [返回目录](../index.md)

> 本页由 LLM 根据上方引用的 Part 5 原文整理，状态为 draft，尚未经过人工语义审阅。
