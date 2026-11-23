# OPC UA Part 5 LLM Wiki

这是 `OPC-10000-5-v1.05.06.md`（OPC Unified Architecture - Part 5: Information Model）的持久 Wiki。首版由 LLM 阅读原文和现有 `kb/` 记录后手动整理，**未经过人工语义审阅**；所有内容页状态均为 `draft`。

- 原文版本：`1.05.06`（2025-10-22），SHA-256：`c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf`
- 内容页：12 个实体页 + 3 个主题页，共 15 页（目录、日志、维护规则不计入）
- 来源引用：正文使用“§章节 Table 表号 L起-L止”形式的永久引用，并指向本地原文对应行锚点；每页 frontmatter 的 `sources` 列出同一组来源。引用格式（包括目录页的相对路径例外）见 [AGENTS.md](AGENTS.md) 的 §1.2
- 维护方式：手动 Agent 维护，不做增量编译器；导入/更新/查询/检查流程见 [AGENTS.md](AGENTS.md)
- 变更记录：[log.md](log.md)
- 校验：`python tools/check_wiki.py`（形式/出处检查，不进行语义审阅）

## 实体页（12）

| 页面 | 类型 | 规范位置 | 说明 |
|---|---|---|---|
| [BaseObjectType](entities/baseobjecttype.md) | ObjectType | §6.2 / Table 8 | 所有 ObjectType 的根类型，无自有组件 |
| [ServerType](entities/servertype.md) | ObjectType | §6.3.1 / Table 9 | 标准 Server Object 的类型与入口 |
| [ServerCapabilitiesType](entities/servercapabilitiestype.md) | ObjectType | §6.3.2 / Table 10 | Profile、Locale、上限和能力声明 |
| [ServerDiagnosticsType](entities/serverdiagnosticstype.md) | ObjectType | §6.3.3 / Table 11 | 服务器级诊断入口 |
| [SessionsDiagnosticsSummaryType](entities/sessionsdiagnosticssummarytype.md) | ObjectType | §6.3.4 / Table 12 | Session 诊断数组与 Session 对象入口 |
| [SessionDiagnosticsObjectType](entities/sessiondiagnosticsobjecttype.md) | ObjectType | §6.3.5 / Table 13、14 | 单个 Session 的诊断对象 |
| [OperationLimitsType](entities/operationlimitstype.md) | ObjectType | §6.3.11 / Table 20 | 单次服务调用的数组规模限制 |
| [BaseEventType](entities/baseeventtype.md) | EventType | §6.4.2 / Table 25 | 事件公共字段与 Severity 等语义 |
| [AuditEventType](entities/auditeventtype.md) | EventType | §6.4.3 / Table 26 | 审计事件基类与审计字段 |
| [ServerStatusType](entities/serverstatustype.md) | VariableType | §7.6 / Table 76 | 服务器状态变量与 `ServerStatusDataType` |
| [BuildInfoType](entities/buildinfotype.md) | VariableType | §7.7 / Table 77 | 构建信息变量与 `BuildInfo` 结构 |
| [ModellingRuleType](entities/modellingruletype.md) | ObjectType | §6.5 / Table 62 | ModellingRule 对象的类型 |

## 主题页（3）

| 页面 | 综合章节 | 说明 |
|---|---|---|
| [server-information-model](topics/server-information-model.md) | §1、§4.1、§6.1、§6.2、§6.3.1、§8.3.2 | 从空 Server 地址空间到标准 Server Object 的整体结构 |
| [events-and-auditing](topics/events-and-auditing.md) | §6.4、§8.3.2 | EventType 表示、BaseEvent/AuditEvent 字段、根 notifier |
| [diagnostics](topics/diagnostics.md) | §6.3.3–§6.3.5、§8.3.1 | 诊断树、Session 视图、可见性与 EnabledFlag |

## 使用建议

1. 先读本页确认页面范围和状态。
2. 查某个类型时，从实体页的“重要成员”和“相关类型与边界”入手，再按正文引用回到原文行。
3. 查跨类型问题（例如“Server 信息模型包含什么”“事件和审计如何区分”“诊断树如何组织”）时，从主题页入手。
4. 修改任何页面后运行 `python tools/check_wiki.py`；失败信息会指出过时 hash、缺失章节/表格、越界行号、缺失链接或重复 `page_id`。

## 边界声明

- 只引用 Part 5（`OPC-10000-5` v1.05.06）。涉及 Part 3、Part 4、Part 6、Part 7、Part 9、Part 18 等的内容只注明“本项目未收录”，不根据它们推导规则。
- 校验器只验证形式、出处和互链，**不验证语义正确性**。LLM 生成内容仍可能误读原文。
- 原文中的脚注编号（如 `ServerStatus1`）不等同于规范成员名；实体页已按原文上下文和 Server Object 表核对。
