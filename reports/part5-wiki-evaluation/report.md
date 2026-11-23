# Part 5 Wiki＋原文 RAG：数组条目覆盖规则复测

日期：2026-11-19（Asia/Hong_Kong）。沿用原来的 16 题、32 个金标准事实及评分规则。语义评分由 Codex 辅助复核，尚无独立人工签署。

## 结论

**Q06 混合组的漏答在最终整轮复测中得到修复。** 回答分别写出“Server 当前使用的每个采样率各有一个条目”和“数组每个条目提供一个 Variable”，再说明配置、数组长度与 NodeId 稳定性；关键结论实际引用包含 §6.3.3 L432 的规范原文。

混合组 Q06 从 **2.5/3 恢复到 3/3**，有原文引用支撑的事实覆盖从 **31.5/32 提升到 32/32**，完整正向题从 **13/14 提升到 14/14**。最终两组均为 **32/32、14/14**；两道边界题均严格通过。这里的满分限于本组金标准事实，不能解释为所有附加语句无误或未知问题上准确率为 100%。

最终 32 条结果全部为 generated，无错误标签或无引用回退。195 项测试、267 项来源检查和 118 个去重 HTTP 内容目标全部通过。前端及 HTTP API 未改，引用、版本、章节、行号与 Wiki 带出的原文来源链保留。

## 定位与修复

上一轮 Q06 混合组的 E2、C1、C2 中已经包含完整原文：

> There is one entry for each sampling rate currently used by the Server.

同一段接着规定 SamplingIntervalDiagnosticsArrayType 为每个数组条目提供一个 Variable。因此这次并非原文没有召回或被预算挤出，而是回答汇总时漏掉一种对应关系。旧答案只保留每条目 Variable 和配置／NodeId 稳定性，未保留每个当前采样率的覆盖要求。

本轮产品代码仅调整 opcua_kb/rag.py 的共享系统要求：

- 用户询问数组条目时，保留有来源支持的覆盖范围、数量关系和“当前使用”等限定词。
- “每个对象一个条目”与“每个条目一个 Variable”是不同映射；证据支持时分别陈述，不能用配置或 NodeId 稳定性代替。
- 针对候选复测发现的两个问题，补充明确：证据不足的拒答也要引用已检查记录；原文明确允许 null 或 empty 时，必须保留两种许可，不能随后声称 empty 的许可未知。

没有向系统指令注入 Q06 标准答案或固定引用标签；具体采样率规则仍来自检索出的规范。没有修改源文件、Wiki、索引、题集、检索算法或证据预算，也没有事后拼接漏掉的答案、替换标签、放宽校验或增加自动模型重试。

Wiki 页原有摘要未展开每采样率条目规则，但本轮未改写该页；最终规范回答引用的是已有原文，而非把 Wiki 摘要当作规范确认。

## 运行设置与候选记录

| 项目 | 设置 |
|---|---|
| 语料 | 本地 OPC-10000-5 v1.05.06 |
| 原文 SHA-256 | `c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf` |
| 题集 SHA-256 | `d742864eefaff15102757f52ab9d25c8d3b9d896f3372ca559e76984a81cd990` |
| 问题 | 同一组 16 题：14 道正向题、2 道边界题；32 个事实 |
| 检索／预算 | 既有精确匹配与 FTS；top_k=6，relationship_depth=0，12000 字符 |
| 模型 | 请求 deepseek-chat，temperature=0，workers=2 |
| 上轮结果 | run-null-empty.jsonl，未覆盖 |
| 本轮最终结果 | run-array-coverage-final.jsonl，32 条结果／模型响应 |
| 最终运行 SHA-256 | `af92a9551671675740fd64e9bbeddb45e1daac2a0cb3f41fc6a60d2a903aafc9` |

本次实际进行了 **两轮在线运行，共 64 条模型响应**，均无自动重试：

1. 第一候选 run-array-coverage.jsonl 完成 32 条。Q06 两组已写出两种映射；但 Q12 原文组先允许 null／empty、结尾又称 empty 许可未知，出现自相矛盾。Q16 原文组正确拒绝版本比较并请求材料，却未使用任何引用标签，严格校验将其回退为离线证据。检查“所有结果均为 generated”的断言因此失败，未忽略该结果。
2. 收紧上述引用和许可范围要求后，再执行完整双组运行，另存 run-array-coverage-final.jsonl。最终 Q12 两组明确保留两种许可，Q16 两组均保留引用并请求材料。统计只采用这一整轮，没有混选候选与最终答案。

第一候选 SHA-256 为 `3e87d824816f63a159f2c9f4050e95da7823edf7fb2b525ec881a16cbae1f36a`，原始输出、元数据及匹配代码快照保留。候选轮用于诊断，未另作完整逐事实总分；不能将其生成次数从运行记录中省略。

原文、题集、Wiki 和 FTS 摘要与上轮相同。最终运行中 **30/32** 个组合的用户提示及证据上下文与上轮逐字相同，包括 Q06 两组。Q01 两组的 HasSubtype 与 References 实体顺序交换，E2/E3 也相应交换；来源集合不变。未修改排序代码，不能声称全部 32 个上下文完全相同。

## 评分与上轮对比

每个事实正确计 1、部分正确计 0.5、缺失或错误计 0。Wiki 草稿解释不能单独计为规范确认；原文支撑要求实际引用已提供且相关的规范记录。Q15、Q16 不进入正向事实分母，另评安全拒答和严格边界要求。

Q06 第二个事实仍同时要求“每个当前采样率一个条目”与“每条目一个 Variable”，没有因本轮修复调整题目、标准答案或分值。

| 指标 | 上轮原文组 | 上轮混合组 | 本轮原文组 | 本轮混合组 |
|---|---:|---:|---:|---:|
| 有原文引用支撑的事实／32 | 32 | 31.5 | 32 | 32 |
| 全部关键事实有原文支撑／14 题 | 14 | 13 | 14 | 14 |
| Q06／3 | 3 | 2.5 | 3 | 3 |
| Q09／2 | 2 | 2 | 2 | 2 |
| Q12／2 | 2 | 2 | 2 | 2 |
| 安全拒答／2 道边界题 | 2 | 2 | 2 | 2 |
| 严格边界要求通过／2 题 | 2 | 2 | 2 | 2 |
| 错误引用标签／16 次 | 0 | 0 | 0 | 0 |
| generated／16 次 | 16 | 16 | 16 | 16 |
| 包含 Wiki 正文的上下文／16 次 | 0 | 13 | 0 | 13 |
| 来源检查 | 70/70 | 197/197 | 70/70 | 197/197 |
| 平均证据字符数 | 9588.31 | 11940.38 | 9588.31 | 11940.38 |
| 平均管线耗时，ms | 3094.65 | 3489.42 | 2856.00 | 3239.68 |
| 中位管线耗时，ms | 2824.21 | 3031.39 | 2609.79 | 3144.35 |

两组本轮原始内容、最终内容及原文支撑覆盖都为 32/32。事实分只覆盖题集金标准，未进行所有附加语句的引用精确率穷举审核；满分不等于每个排除说明、语言选择和措辞都准确。

耗时含检索、请求和生成，不含来源审计。未固定供应商模型快照，未记录 token 用量或费用；本次单轮结果不能证明稳定提速。新增要求增加系统提示长度，证据预算本身不变。

## 逐题最终结果

分数为有原文引用支撑的覆盖；逐事实引用标签与判分说明见 review-array-coverage-final.json。

| 题号／主题 | 原文组 | 混合组 | 核对结果 |
|---|---:|---:|---|
| Q01 BaseObjectType／HasSubtype | 2/2 | 2/2 | 用途、继承及不要求完整引用图保持 |
| Q02 ServerType 成员 | 3/3 | 3/3 | 四个脚注名称区分、必选／可选项保持 |
| Q03 中文命名空间表 | 2/2 | 2/2 | 会话内增删改规则与启动校验保持 |
| Q04 MaxStringLength／未知上限 | 2/2 | 2/2 | 字节数、覆盖与省略条件保持 |
| Q05 EnabledFlag | 2/2 | 2/2 | TRUE 重置启用、FALSE 禁用不重置及只读保持 |
| Q06 采样间隔诊断 | 3/3 | 3/3 | 两种条目映射分别答出，稳定性及适用范围完整 |
| Q07 会话诊断与权限 | 2/2 | 2/2 | 类型、BrowseName 与授权加密访问保持 |
| Q08 OperationLimitsType | 2/2 | 2/2 | 继承、Optional、非零与 nodesToRead 上限保持 |
| Q09 Message／Severity | 2/2 | 2/2 | 保留 null string，不误译为空字符串；fallback 与 Severity 完整 |
| Q10 AuditEventType | 3/3 | 3/3 | 继承、默认 SourceNode 与额外 Property 建议保持 |
| Q11 BuildInfo 跨章节 | 3/3 | 3/3 | 六成员、六字段及本地交叉引用不一致保持 |
| Q12 ServerStatusDataType | 2/2 | 2/2 | 六字段、关闭规则及 null／empty 两种许可完整 |
| Q13 Part 5 范围 | 2/2 | 2/2 | §1 支持范围与不要求全部节点 |
| Q14 Annex C | 2/2 | 2/2 | 资料性、弃用、未来删除、shall 状态与字段规则保持 |
| Q15 CreateSession／状态机 | 严格通过 | 严格通过 | 不编造完整参数／状态，引用已检查内容并请求 Part 4 |
| Q16 版本比较 | 严格通过 | 严格通过 | 不虚构变化，保留引用并请求上一版或官方日志 |

### Q06 引用与定位

原文 v1.05.06 的对应位置：

| 位置 | 规则 |
|---|---|
| §6.3.3 Table 11，L421 | SamplingIntervalDiagnosticsArray 为 Optional |
| §6.3.3，L432 | 每个当前使用的采样率一个条目；每条目一个 Variable |
| §6.3.3，L434 | 固定采样率适用范围、配置决定长度／变量集合、NodeId 稳定性与可不暴露条件 |
| §7.9 Table 79，L1987–1996 | SamplingIntervalDiagnosticsArrayType 的定义及 ExposesItsArray |

最终混合组明确引用 C2（`source:6.3.3:429-435`）、C1（§6.3.3 章节）和 E2（ServerDiagnosticsType）支持采样率到条目的映射；条目到 Variable 的映射还引用 E1（SamplingIntervalDiagnosticsArrayType）。

C2 是 Wiki 关联链接带出的真实规范段落，provenance 保留 wiki/entities/serverdiagnosticstype.md 的来源链；正文仍来自原文，具有版本、章节与行号。回答明确不以 W1 草稿确认规范规则。原文组则使用 E2/C1/T1 支持相同规则。

## 验证与复现

修复前先检查已保存的 Q06 混合组输出：确认用户证据包含每采样率条目原句，但答案未保留该覆盖要求，目标检查失败。最终两组实际输出都包含该规则和独立的每条目 Variable 规则，目标检查通过；随后完整阅读 32 条答案、核对语义和支持标签，不以字符串出现代替语义评分。

本轮只修改提示要求，未增加“提示源码包含某句话”的断言测试。消费者行为通过既有冻结题集的真实模型运行验证；没有新依赖、生成后修复或跳过引用校验。

| 检查 | 最终结果 |
|---|---|
| 全套测试 | `python -m unittest discover`：195 项通过 |
| 离线预检 | 32 条，预算和来源检查通过 |
| 最终来源检查 | 267/267：原文组 70，混合组 197 |
| HTTP 内容目标 | 118/118 返回 200：15 个 Wiki 页面、103 个原文范围 |
| 内容与版本 | 1.05.06；Wiki 为 draft；原文内容逐行等于请求的本地范围 |
| Wiki 检查 | 15 个内容页形式／来源检查通过 |
| 冻结审计 | 当前代码／语料／题集摘要通过；上轮由匹配快照重新审计通过 |
| 前端／HTTP API | App.tsx、App.css、http_api.py 摘要未变 |
| 空白检查 | `git diff --check` 通过 |

全套测试在候选修改后和最终修改后各通过一次，最终仍为 195 项。依赖的既有 Starlette TestClient 弃用提示、Git CRLF 提示不影响通过。

HTTP 内容核对通过既有 FastAPI TestClient 执行，没有新增浏览器点击验收，不能称为前端端到端验证。来源检查证明目标与内容正确，不能证明每个附加句子都由引用支持。

最终在线命令已完成：

```powershell
python -X utf8 tools/evaluate_wiki_rag.py --online --workers 2 --output reports/part5-wiki-evaluation/run-array-coverage-final.jsonl
```

仅复核本地结果的命令：

```powershell
python -X utf8 tools/check_wiki_evaluation.py --run run-array-coverage-final.jsonl --review review-array-coverage-final.json --output audit-array-coverage-final.json
python -X utf8 tools/check_wiki_evaluation.py --run run-null-empty.jsonl --review review-null-empty.json --output audit-null-empty-verified.json
python -m unittest discover
python -X utf8 tools/check_wiki.py
git diff --check
```

## 保留文件

下列运行文件均位于 reports/part5-wiki-evaluation/。此前各轮数据、元数据、评分及报告继续保留。

| 文件 | 用途 |
|---|---|
| report-null-empty.md | 上一轮报告存档 |
| run-null-empty.jsonl、review-null-empty.json 及运行元数据 | 上一轮结果，未覆盖 |
| run-null-empty-code/ | 与上一轮元数据匹配的八个代码文件快照 |
| audit-null-empty-verified.json | 本轮重新核对上一轮结果 |
| preflight-array-coverage.jsonl 及其元数据 | 第一候选离线预检 |
| run-array-coverage.jsonl 及其元数据、run-array-coverage-code/ | 第一在线候选及匹配代码，保留已发现的问题 |
| run-array-coverage-final.jsonl、run-array-coverage-final.meta.json | 最终整轮 32 条真实输出及代码／语料摘要 |
| review-array-coverage-final.json | 绑定最终运行摘要的逐事实评分和边界判定 |
| audit-array-coverage-final.json | 最终来源、HTTP 与统计审计 |

评分文件绑定运行摘要。已审计的运行、元数据和复核文件未包含环境中配置的 API 密钥。

## 局限

这仍是已用于定位问题的开发题集，不是独立未知测试集。候选结果用于调整提示后，再对完整题集复测；没有盲评、人工签署、统计显著性分析或重复随机采样。温度 0 不保证供应商输出完全可重复，候选顺序也存在已观察到的变化。

本轮同时收紧条目覆盖、拒答引用和明确许可的保留要求，没有逐项模型消融，不能精确归因各项收益，也不能从两组同为满分推导 Wiki 优于纯原文 RAG。

尚需注意：

- Q09 两组保留了 null string，未误译或推导 empty 合法性，但最终答案没有显式展开 null／empty 对比。不能把系统软要求写成每次都完整执行的保证。
- Q14 混合组末尾称 T1/C1 不涉及 shall，范围过宽：表格内实际存在 shall 例句，只是附录资料性状态由章节开头 C2 说明。核心状态与字段事实完整，附加排除措辞仍不严谨。
- Q01 两组以中文回答英文问题，语言跟随仍不稳定；Q06 原文组还追加了无需讨论的 null 边界句。事实分未因此扣减，但并非每处表达都最简。
- 当前严格校验只保证标签格式与成员关系，不验证所有语义蕴含；本次完整回答不等于未来生成都有覆盖保证。

可确认的是：最终整轮 Q06 两种映射均完整、都有原文引用；本组 14 道正向题的关键事实完整覆盖，边界题保留材料请求与引用，前端保持不变。
