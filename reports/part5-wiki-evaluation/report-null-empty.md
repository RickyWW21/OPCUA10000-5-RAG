# Part 5 Wiki＋原文 RAG：null 与 empty 区分复测（存档）

日期：2026-11-19（Asia/Hong_Kong）。沿用原来的 16 题、32 个金标准事实及评分规则。语义评分由 Codex 辅助复核，尚无独立人工签署。

## 结论

**Q09 的目标误译已在本轮两组真实输出中消除。** 原文组和混合组都明确保留 `null string`，说明它不同于 empty string（`""`），并且没有从“null 无效”推导出 empty 是否允许或禁止。BrowseName fallback 与 Severity 的范围、方向均正确，Q09 两组为 **2/2**，其中混合组由上轮 1.5/2 恢复。

**Q12 没有被误伤：** 对 shutdownReason，两组均按其原文保留“没有特定原因时可为 null 或 empty”，并区分两种表示。没有把 Message 的 null 禁止规则套到其他字段。

整体仍为原文组 **32/32、14/14 完整正向题**，混合组 **31.5/32、13/14**。混合组 Q09 恢复半分，但 Q06 本轮遗漏“每个当前采样率一个条目”，扣半分，故整体分数持平。没有用旧答案补齐本轮遗漏，也不能宣称混合检索优于纯原文组。

两组边界题均为 **2/2 严格通过**。195 项测试、267 项来源检查和 118 个去重 HTTP 内容目标全部通过，32 条回答无错误引用标签。前端及 HTTP API 未改，原文和 Wiki 引用链保留。

## 问题来源与改动

本地规范 v1.05.06 §6.4.2 L847 写的是 `A null string is not a valid value`；BaseEventType Wiki 页也写“Message 不能为 null”。上轮混合组上下文包含正确原文，但答案将其转述为“空字符串不是有效值”，因此问题位于生成表达阶段。

本轮产品代码仅修改 opcua_kb/rag.py 中的共享系统要求：

- 转述或翻译时保留技术字面量；解释 null-string 规则时，明确区分 null 与空字符串 `""`。
- 保留单词 `null`，不得把 null string 翻译为 empty string 或“空字符串”。
- 仅禁止 null 的条款不能单独证明 empty 允许或禁止；没有证据时不作这两种推断。

这项要求对两个检索组及既有 HTTP／CLI／TUI 问答入口共用。没有修改来源正文、Wiki、题目、检索排序、预算、引用格式或标签校验，没有事后替换模型答案，也没有增加模型重试。

它是生成约束，不是通用语义验证器；本轮通过不保证后续每次生成都不会误译。

## 实验设置

| 项目 | 设置 |
|---|---|
| 语料 | 本地 OPC-10000-5 v1.05.06 |
| 原文 SHA-256 | `c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf` |
| 题集 SHA-256 | `d742864eefaff15102757f52ab9d25c8d3b9d896f3372ca559e76984a81cd990` |
| 问题 | 同一组 16 题：14 道正向题、2 道边界题；32 个事实 |
| 检索／预算 | 原有精确匹配与 FTS；top_k=6，relationship_depth=0，12000 字符 |
| 模型 | 请求 deepseek-chat，temperature=0，workers=2 |
| 上轮结果 | run-boundary-final.jsonl，未覆盖 |
| 本轮结果 | run-null-empty.jsonl；一轮在线运行，32 条结果／模型响应，无重试 |
| 本轮 SHA-256 | `b0ffb498823f8c5ca5ce5dbbcaa2aaa5653c356346ed801e2db85b989597cd6b` |

原文、题集、Wiki 页面和 FTS 索引摘要与上轮完全相同。32 个题目／检索组组合的用户提示和证据上下文也逐条完全相同；冻结代码中仅 rag.py 改变，实际改动仅系统要求。

每个事实正确计 1、部分正确计 0.5、缺失或错误计 0。Wiki 草稿解释不能单独计为规范确认；原文支撑要求实际引用已提供且相关的原文。Q15、Q16 不进入正向事实分母，另计安全拒答和严格边界要求。

Q06 的第二个事实从首次评估起就同时要求“每个当前采样率一个条目”与“每条目一个 Variable”；本轮混合组只写后者，因此按原口径计 0.5，未调整金标准。

## 与上轮对比

| 指标 | 上轮原文组 | 上轮混合组 | 本轮原文组 | 本轮混合组 |
|---|---:|---:|---:|---:|
| 有原文引用支撑的事实／32 | 32 | 31.5 | 32 | 31.5 |
| 全部关键事实有原文支撑／14 题 | 14 | 13 | 14 | 13 |
| Q09／2 | 2 | 1.5 | 2 | 2 |
| Q06／3 | 3 | 3 | 3 | 2.5 |
| Q12／2 | 2 | 2 | 2 | 2 |
| 安全拒答／2 道边界题 | 2 | 2 | 2 | 2 |
| 严格边界要求通过／2 题 | 2 | 2 | 2 | 2 |
| 错误引用标签／16 次 | 0 | 0 | 0 | 0 |
| generated／16 次 | 16 | 16 | 16 | 16 |
| 包含 Wiki 正文的上下文／16 次 | 0 | 13 | 0 | 13 |
| 来源检查 | 70/70 | 197/197 | 70/70 | 197/197 |
| 平均证据字符数 | 9588.31 | 11940.38 | 9588.31 | 11940.38 |
| 平均管线耗时，ms | 2312.86 | 2679.83 | 3094.65 | 3489.42 |
| 中位管线耗时，ms | 2026.08 | 2371.52 | 2824.21 | 3031.39 |

原始内容、最终内容与原文支撑覆盖本轮分别都为 32/32、31.5/32。已覆盖事实均有有效支持引用；分母不含漏答，不能解释为每句附加说明都通过审核。

耗时含检索、请求与生成，不含后续来源审计。系统要求增加了提示长度，但没有记录 token 用量或费用，也未固定供应商模型快照，单次耗时不能推导稳定的性能变化。

## 逐题结果

下表为有原文引用支撑的覆盖；逐事实支持标签与理由保存在 review-null-empty.json。

| 题号／主题 | 原文组 | 混合组 | 核对结果 |
|---|---:|---:|---|
| Q01 BaseObjectType／HasSubtype | 2/2 | 2/2 | 核心用途、继承及无需完整引用图保持 |
| Q02 ServerType 成员 | 3/3 | 3/3 | 四个成员名称仍正确区分脚注；必选／可选项完整 |
| Q03 中文命名空间表 | 2/2 | 2/2 | 会话期间增删改及客户端启动校验保持 |
| Q04 MaxStringLength／未知上限 | 2/2 | 2/2 | 字节数、覆盖及省略条件保持 |
| Q05 EnabledFlag | 2/2 | 2/2 | 重置／启用、禁用不重置及只读保持 |
| Q06 采样间隔诊断 | 3/3 | 2.5/3 | 混合组漏“每个当前采样率一个条目”，仍写出每条目 Variable |
| Q07 会话诊断与权限 | 2/2 | 2/2 | 类型、BrowseName 与授权加密访问保持 |
| Q08 OperationLimitsType | 2/2 | 2/2 | 继承、Optional、非零及 nodesToRead 上限保持 |
| Q09 Message／Severity | 2/2 | 2/2 | null／empty 明确区分，不推导 empty 合法性；fallback 与 Severity 完整 |
| Q10 AuditEventType | 3/3 | 3/3 | 继承、默认 SourceNode 与额外 Property 建议保持 |
| Q11 BuildInfo 跨章节 | 3/3 | 3/3 | 六成员、六字段及本地交叉引用不一致保持 |
| Q12 ServerStatusDataType | 2/2 | 2/2 | 六字段、关闭规则及 null／empty 两种可选表示保持 |
| Q13 Part 5 范围 | 2/2 | 2/2 | §1 原文支持范围与不要求全部节点 |
| Q14 Annex C | 2/2 | 2/2 | 资料性、弃用、未来删除及剩余 shall 状态保持 |
| Q15 CreateSession／会话状态机 | 严格通过 | 严格通过 | 不编造完整参数／状态，明确请求 Part 4 |
| Q16 当前版本与上一版比较 | 严格通过 | 严格通过 | 不虚构具体变化，明确请求上一版或官方日志 |

## Q09、Q12 与引用定位

**Q09 原文组**实际使用 E1（EventType:BaseEventType）。答案保留 `A null string is not a valid value`，并说明证据未规定 empty string `""` 是否允许或禁止；没有描述时返回事件关联节点 BrowseName 的字符串部分。

**Q09 混合组**实际使用 C1 与 E1。C1 为 Wiki 带出的真实规范原文 `source:6.4.2:847-850`，provenance 保留 wiki/entities/baseeventtype.md 的来源链。回答明确说，null 规则本身不能确定 empty 的允许或禁止；不再把它们互译。Severity 仍为 1–1000，1 最低、1000 最高。

**Q12 两组**引用 §12.10 Table 242 的原文，正确说明 shutdownReason 在没有特定原因时可为 null 或 empty。混合组还使用 C3（`source:12.10:4779-4787`），即 Wiki 带出的规范范围。此处允许两种表示有直接证据，不是由 Q09 推断。

| 原文位置 | 内容 |
|---|---|
| 1.05.06，§6.4.2 L847 | Message 的 null string 无效及无描述时的 BrowseName fallback |
| 1.05.06，§6.4.2 L850 | Severity 的范围及方向 |
| 1.05.06，§12.10 Table 242 L4787 | shutdownReason 的状态、语义与 null／empty 表示 |
| 1.05.06，§6.3.3 L432 | Q06 每采样率条目及每条目 Variable 的双重要求 |

本轮未修改引用生成、版本、章节和行号映射。原文内容接口返回对应原始范围，Wiki 仍为 draft。

## 验证与复现

先对上轮 Q09 混合组真实输出执行保留 `null` 字面量的最小检查，观察到失败；原文输入包含 null，但输出只写“空字符串”。修改系统要求后，本轮两组均通过 null／empty 字面量检查，再逐句核对两者区别、empty 规则边界、fallback 和原文引用。字面量出现本身不能证明语义正确，未以此代替人工式语义复核。

本轮仅修改提示要求，没有增加对提示词源码文本的断言测试；继续用既有冻结题集的真实模型输出检验行为。32 条离线预检验证预算和来源；在线运行后，32 条真实响应全部读取并重新判分，未复用上一轮的事实评分。

| 检查 | 结果 |
|---|---|
| 全套测试 | `python -m unittest discover`：195 项通过 |
| 离线预检 | 32 条通过，证据预算不超 12000 字符 |
| 来源检查 | 267/267：原文组 70，混合组 197 |
| 去重 HTTP 目标 | 118/118 返回 200：15 个 Wiki 页面、103 个原文范围 |
| 版本与内容 | 1.05.06；Wiki 为 draft；原文逐行等于本地请求范围 |
| Wiki 检查 | 15 个内容页形式／来源检查通过 |
| 冻结检查 | 当前代码、语料、题集与元数据相符；上轮由匹配代码快照重新审计通过 |
| 前端／HTTP API | App.tsx、App.css、http_api.py 摘要与本轮开始前一致 |
| 空白检查 | `git diff --check` 通过 |

既有 Starlette TestClient 弃用提示和 Git CRLF 提示未导致失败。HTTP 来源检查通过既有 FastAPI TestClient 执行，未新增浏览器点击回归，不能称为前端端到端验收。

在线命令已完成，仅调用一次完整双组运行，无自动重试：

```powershell
python -X utf8 tools/evaluate_wiki_rag.py --online --workers 2 --output reports/part5-wiki-evaluation/run-null-empty.jsonl
```

仅复核本地结果的命令：

```powershell
python -X utf8 tools/check_wiki_evaluation.py --run run-null-empty.jsonl --review review-null-empty.json --output audit-null-empty.json
python -X utf8 tools/check_wiki_evaluation.py --run run-boundary-final.jsonl --review review-boundary-final.json --output audit-boundary-final-verified.json
python -m unittest discover
python -X utf8 tools/check_wiki.py
git diff --check
```

## 保留文件

以下文件位于 reports/part5-wiki-evaluation/，此前所有原始运行、元数据、评分和历史报告继续保留。

| 文件 | 用途 |
|---|---|
| report-boundary.md | 上轮脚注／边界修复报告存档 |
| run-boundary-final.jsonl、review-boundary-final.json 及运行元数据 | 未覆盖的上一轮结果 |
| run-boundary-final-code/ | 与上轮元数据匹配的八个代码文件快照 |
| audit-boundary-final-verified.json | 本轮重新核对上一轮结果 |
| preflight-null-empty.jsonl 及其元数据 | 本轮 32 条离线预检 |
| run-null-empty.jsonl、run-null-empty.meta.json | 本轮 32 条真实结果与代码／语料摘要 |
| review-null-empty.json | 绑定运行摘要的逐事实评分、引用标签及边界判定 |
| audit-null-empty.json | 当前摘要、来源、HTTP 审计及统计 |

评分文件绑定本轮运行摘要。审计检查过的运行、元数据和复核文件未包含环境中配置的 API 密钥。

## 局限与剩余问题

本轮是对已暴露问题的开发复测，不是独立未知题集。没有盲评、人工签署、重复采样或统计显著性分析；温度 0 不保证供应商输出完全可重复。上下文逐条相同有助于缩小变量，但不能从单次输出变化证明长期稳定收益。

必须保留以下限制：

- **Q06 混合组出现漏答：** 只写每条目对应 Variable，漏每个当前采样率一个条目，严格计半分。这解释了 Q09 修复后混合组总分仍为 31.5/32。
- **额外说明仍可能过多：** Q02 混合组追加与问题无关的 null／empty 说明；Q15 原文组对 SessionId 的 null 补充了没有必要的空字符串对比。没有由此宣称某字段允许或禁止 empty，但表达不够聚焦。
- **边界表述仍有细节限制：** Q15 混合组先说“仅在审计语义”提及 CreateSession，随后又列诊断 sessionName，前句范围过窄；Q16 原文组给出“例如 1.05.05 或更早版本”的多余示例，未断言上一版身份或虚构变化。按原诊断标准仍通过，不能称所有附加说明完美。
- **语言与引用精确率：** Q01 混合组仍以中文回答英文问题；Q11 混合组的额外命名解释单引 Wiki。核心事实均有原文支撑，但没有对所有附加句子做引用精确率穷举审核。
- **约束属于软要求：** 现有严格校验保证标签格式和成员关系，不验证所有事实蕴含。此次 null／empty 区分通过，不代表所有字段、语言和未来回答均能保证正确。

本轮可确认 Q09 的误译消失，null／empty 区别明确，Q12 的原文规则及来源引用保留。混合组整体分数持平，不能据此声称其准确性超过纯原文 RAG。
