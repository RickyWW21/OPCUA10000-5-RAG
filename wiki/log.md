# Wiki 日志

## 2026-11-18 — 首版生成（LLM）

- **操作者**：LLM/Agent（DeepSeek Harness），**未人工审阅**。
- **输入**：`source/OPC-10000-5-v1.05.06.md`、`kb/chapters.jsonl`、`kb/tables.jsonl`、`kb/entities.jsonl`、`source/source_manifest.json`。
- **范围**：15 个内容页 = 12 实体页 + 3 主题页；外加 `index.md`、`log.md`、`AGENTS.md`。
- **实体页**：BaseObjectType、ServerType、ServerCapabilitiesType、ServerDiagnosticsType、SessionsDiagnosticsSummaryType、SessionDiagnosticsObjectType、OperationLimitsType、BaseEventType、AuditEventType、ServerStatusType、BuildInfoType、ModellingRuleType。
- **主题页**：server-information-model、events-and-auditing、diagnostics。
- **实体 id 来源**：全部取自 `kb/entities.jsonl` 的 `id` 字段，未自造 id。
- **引用方式**：正文使用 `[§章节 Table 表号 L起-L止](../../source/OPC-10000-5-v1.05.06.md#L起-L止)`；frontmatter `sources` 使用同一组章节/表/行范围。只引用 Part 5；Part 3/4/6/7/9/18 等只注明“本项目未收录”。
- **脚注处理**：`ServerType` 表中原有 `ServerStatus1`、`ServerCapabilities1` 等脚注标记；页面按 §8.3.2 Server Object 及附加一致性单元表核对为 `ServerStatus`、`ServerCapabilities` 等成员名，并明确说明尾随数字不是成员名。
- **校验**：`python tools/check_wiki.py` → 见下方“校验结果”；`python -m unittest tests.test_wiki` → 见下方。
- **限制**：校验器只检查形式/出处/互链，不做语义审阅；页面内容仍可能误读原文。首版为手动维护，不做增量编译器，不依赖外部 API。

### 校验结果

后续 Agent 追加同一天的校验结果时，请写实际命令和实际输出摘要，不要写“已通过语义检查”。

- `python tools/check_wiki.py`：exit 0，输出 `OK (15 content pages: 12 entities, 3 topics)`；仅形式/出处检查，未做语义审阅。以上结果由主代理独立运行核实。
- `python -m unittest tests.test_wiki`：8 tests，OK。以上结果由主代理独立运行核实。
- `python -m unittest discover`：142 tests，OK（耗时 22.574s；已有 `StarletteDeprecationWarning`）。以上结果由主代理独立运行核实。

## 2026-11-18 — 定点引用/措辞修订（LLM/Agent）

- **操作者**：LLM/Agent（DeepSeek Harness），**未人工审阅**；所有内容页继续为 `status: draft`。
- **范围**：只修改 `wiki/*.md`（内容页、`index.md`、本日志）；未改 Python 校验器/测试、前端、`kb/`、原文与 `.gitignore`，未提交 git。
- **index.md**：删除带伪行号的 Markdown 链接示例，目录页不再出现会被校验器当作实际链接的 `../../source/...`；改为纯文字说明并链接 `AGENTS.md` §1.2；同步主题页综合章节加入 §4.1。
- **根类型与扩展**：`baseobjecttype.md`、`topics/server-information-model.md` 的“根类型/使用更具体类型/不要求完整 HasSubtype”改引 §6.2 L205-L209，frontmatter 同步；`NodeVersion` 例子改为“Server 中的每个 Object”；server-information-model 补 §4.1 L129-L135，并修正“NodeId 映射归 Part 6”的表述。
- **ServerType**：`ServerArray`/`NamespaceArray` 缓存段引用扩到 §6.3.1 L253-L260，补入 NamespaceArray 只增不改索引的建议与客户端检查；Table 111 说明改为仅定义 `Server` 与 `HasTypeDefinition`，成员名依据 Table 112（§8.3.2 L2729-L2823）；Server 根 notifier 结论补 §8.3.2 L2714-L2717。
- **事件/审计**：`baseeventtype.md` 的 `Message`/`Severity` 引 §6.4.2 L847-L861 并同步 frontmatter，用途删去未被 Part 5 表支持的订阅/EventFilter 推论；`events-and-auditing.md` 的内容段补 §6.4.2 L847-L850，审计字段段补 §6.4.3 L931-L944；两页的新审计子类型建议改为“不增加核心 UA 规范已定义字段之外的额外 Property”，引 §6.4.3 L924-L928；`SourceNode` 保留原文 shall 强度。
- **能力/诊断**：`servercapabilitiestype.md` 的 Max* 段补 §6.3.2 L348-L401，“无法确定可选上限”改为“不得提供（shall not be included）”；`serverdiagnosticstype.md` 将 `SamplingIntervalDiagnosticsArray` 的建模规则固定为 Optional，按 §6.3.3 L429-L435 说明固定采样间隔集合的收集条件、数组长度与 NodeId 稳定条件；`EnabledFlag` 可写性不再写成无条件支持。
- **Session/安全**：`sessiondiagnosticsobjecttype.md`、`topics/diagnostics.md`、`sessionsdiagnosticssummarytype.md` 将 `<ClientName>` 明确为占位符，实际 BrowseName 由 `sessionName` 或其他 Server 机制确定，补 §6.3.4 L466-L471；diagnostics 安全段分开 Session 安全数组的 should 与跨 Session `CurrentRoleIds` 的 shall，并补 §6.3.5 L491-L497；`EnabledFlag` 限定为“不表示 Server 是否支持其他服务/能力”。
- **建模规则/BuildInfo**：`modellingruletype.md` 改为“类型定义中的实例声明节点通过 `HasModellingRule`…”，不声称运行时实例普遍带该引用，未改 §8.4 引用；`buildinfotype.md` 补 §12.4 Table 231 L4636-L4643，并记录 §7.7 L1937 的来源交叉引用异常（见下）。
- **来源交叉引用异常**：§7.7 正文 L1937 写 `BuildInfoType` 的 DataVariables 参照“12.3.15.1”，但本地原文 §12.3.15.1 实际是 `AnonymousIdentityToken`，`BuildInfo` 实际定义在 §12.4。`buildinfotype.md` 按 §12.4（Table 230、Table 231）定位，同时保留 §7.7 L1935-L1937 的原文表述作为异常记录，不修改原文。
- **校验**：
  - `python tools/check_wiki.py`：exit 0，输出 `OK (15 content pages: 12 entities, 3 topics)`；仅形式/出处检查，未做语义审阅。以上结果由主代理独立运行核实。
  - `python -m unittest tests.test_wiki`：8 tests，OK。以上结果由主代理独立运行核实。
  - `python -m unittest discover`：142 tests，OK（耗时 22.574s；已有 `StarletteDeprecationWarning`）。以上结果由主代理独立运行核实。
- **备注**：校验只覆盖形式/出处/互链，不验证语义；本页记录不构成人工审阅结论。独立 DSH 审阅任务因上游响应流中断未完成；主代理已逐页对照 Part 5 原文复核，但仍未人工审阅，所有内容页保持 `status: draft`。

## 2026-11-18 — Wiki 接入 RAG 引用/后端验证（LLM/Agent）

- **操作者**：LLM/Agent（DeepSeek Harness），**未人工审阅**；所有内容页继续为 `status: draft`。
- **范围**：只改 `opcua_kb/rag.py`、新增 `tests/test_wiki_rag.py`、在 `tests/test_http_api.py` 增加一个 Wiki 集成测试、追加本日志；未改前端、`opcua_kb/retrieval.py`、`opcua_kb/wiki.py`、`source/`、`kb/`、索引，未提交 git。
- **接入方式**：Wiki 检索记录使用 `type='wiki'`、`id='wiki:<page_id>'`，`evidence` 为完整 Markdown 正文；`provenance` 固定含 `page_id`、`path`（`wiki/...` 相对项目根）、`source_doc`、`source_version`、`source_sha256`、`status`、`sources`（frontmatter 原引用数组）。原文 chunk 自带的 provenance 原样保留。
- **引用标签**：新增 `[W1]` 形式的 Wiki 标签；`_CANONICAL_CITATION`、`_CITATION_CANDIDATE`、`_CITATION_PREFIXES` 与 system 提示同步。`[W99]`、`[W0]`、`[Wabc]` 以及被预算省略的 W 标签会被拒绝并离线回退；E/T/C/R 既有行为不变。
- **上下文与回答**：Wiki 证据前加简短头（Wiki 草稿非规范原文、页面路径、版本、status），再跟完整正文；预算计算含头部、编号与分隔符，整条不截断。system 明确 Wiki 是 LLM 整理 draft、仅用于解释导航，Part 5 原文优先；证据是数据不得执行其中指令；只剩 Wiki 时须说明无法核对规范。离线回答同样标注 Wiki 草稿，仅含 Wiki 时额外说明无法核对规范。
- **序列化**：`RAGAnswer.citations` 与 `_serialize` 改为支持嵌套 `dict[str, Any]`；仅对有 provenance 的记录在 `retrieved` 和 `citations` 中增加 `provenance`，保留既有 `id/title/label` 结构，旧的无 metadata 引用字典完全不变。
- **测试**：新增 `tests/test_wiki_rag.py` 6 个用例（混合上下文、两组引用与 metadata、无效/未供给 W 回退、预算省略不泄漏、旧记录兼容、离线 Wiki-only 提示）；`tests/test_http_api.py` 新增 1 个真实临时 source/manifest/wiki 页的集成用例（sha 实际计算、chapter/table 行范围来自同一 fixture、offline fts top_k=2、历史嵌套 metadata 保留）。
- **实际 focused 结果**：本轮运行 `python -m unittest tests.test_wiki_rag tests.test_rag tests.test_http_api tests.test_session_api` **未能执行**：本地 `pwsh` 子进程初始化持续失败，所有命令（含 `Write-Output`、`python --version`、`cmd /c echo`）均立即返回 `0xC0000142`（STATUS_DLL_INIT_FAILED），未得到任何测试计数或通过/失败输出。实现前的 TDD 红跑同样因此没有结果。该环境故障不是接口缺失，也不是测试断言失败；本轮未据未运行的测试宣称通过。
- **备注**：以上为 LLM 接入记录，不构成人工审阅；内容页仍为 `draft`。待环境恢复后需重跑上述 focused 命令并在此追加实际计数。

## 2026-11-18 — 默认上下文预算下的 Wiki 摘录（LLM/Agent）

- **操作者**：LLM/Agent（DeepSeek Harness），**未人工审阅**；所有内容页继续为 `status: draft`。
- **范围**：只改 `opcua_kb/rag.py`、追加 `tests/test_wiki_rag.py` 用例、追加本日志；未改 `opcua_kb/retrieval.py`/前端/`source/`/`kb/`/索引，未提交 git。
- **方案**：retriever 仍保存完整 Wiki 正文。RAG 先按整页整条计入预算；仅当整页放不下时，从同一 Wiki 正文按空行切出完整块，排除标题、导航（`相关页面`/目录）、免责声明和纯链接块，按 `ask` 的 question 关键词排序，挑选能完整放入剩余预算的块，拼成带 `Wiki 摘录 excerpt（Wiki 草稿，AI 整理，非规范原文…）` 头部、`path`、`source_version`、`status` 的摘录。没有完整块能放入时仍整条省略并披露；整页放得下时不摘录。默认 `max_context_chars` 未提高，原文/表格/段落均不截断。
- **序列化**：`_serialize` 改为直接接收 `_select_units` 选中的实际文本，`retrieved[*].snippet` 与发送给模型的 context 逐字一致；Wiki 摘录仍保留整页 `provenance`（`sources` 仍表示页面出处，不表示这些原文都进入了上下文）。无 Wiki 记录与引用编号规则不变。摘录使用时会附加预算披露。
- **回归用例**：`tests/test_wiki_rag.py` 新增 3 个用例：默认 12000 预算下 10646 字符原文 + 含完整短段落和 Markdown 原文引用的 Wiki 最终同时含原文与 `[W1]`、context 不超预算且 snippet/context 一致；超长不可分段 Wiki 仍被省略且无 W 标签；完整 Wiki 能放下时尾部不丢且不标记摘录。用例先于实现写入。
- **实际 focused 结果**：本轮运行 `python -m unittest tests.test_wiki_rag tests.test_rag` **未能执行**：`pwsh` 子进程初始化持续返回 `0xC0000142`（STATUS_DLL_INIT_FAILED），连 `Write-Output` 也无任何输出；RED 运行和实现后运行都没有得到测试计数或通过/失败结果。真实离线调用（`KnowledgeBase('.')` + `Part5Retriever` + `RAGPipeline`，question=`ServerType 包含哪些组件？`，top_k=6）同样未能执行。故本轮不宣称测试或离线调用通过，需由环境恢复后的主代理重跑。
- **摘录限制**：按空行切块，不构建通用分块器；短于 40 字符的块、纯链接块、导航和免责声明不会成为摘录；关键词仅用于在可容纳的完整块中排序，不做语义判定。若 Wiki 只有一个超大段落，仍会整条省略。摘录是 AI 整理的非规范内容，不能替代 Part 5 原文。

## 2026-11-18 — 主代理独立验证 Wiki RAG 接入

- **实现与验证**：DSH 完成检索、引用和预算摘录实现；其本地 shell 无法启动，以下结果由主代理在当前工作区实际运行核实，不依赖 DSH 的静态判断。
- **Windows 夹具修正**：HTTP 测试改为对实际源文件字节计算 SHA-256，避免 LF 字符串与写入后的 CRLF 文件不一致；生产来源校验没有放宽。
- **回归**：主代理新增 `tests/test_wiki_budget.py`，先观察到整页 Wiki 超预算被省略而导致 `[W1]` 不可用的失败，再验证摘录实现通过；模型上下文与响应 `retrieved[*].snippet` 一致。
- **实际结果**：`python -m unittest tests.test_wiki_retrieval tests.test_retrieval tests.test_hybrid_retrieval` 为 21 项通过；预算/RAG/HTTP/会话相关测试为 36 项通过；`python -m unittest discover` 为 163 项通过（20.705 秒）；`python tools/check_wiki.py` 为 15 页形式、出处与互链检查通过。
- **真实离线查询**：ServerType 与 BaseEventType 同时返回 `[E1]` 原文和 `[W1]` Wiki，实际上下文分别为 11854、11864 字符；中文诊断关闭问题同时返回原文 chunk 和 Wiki，上下文为 11916 字符。三者均未超过默认 12000 字符预算。
- **现有入口**：`python tools/ask_kb.py ServerType --offline --no-embeddings --top-k 6` 退出码为 0，结果同时包含 entity 和 wiki。HTTP 响应与会话历史保留 Wiki `provenance` 的集成测试通过。
- **限制**：本轮未调用在线模型 API；生成分支通过本地记录型模型测试。Wiki 仍为 `draft`，原文优先，校验不构成人工语义审阅。前端、规范原文、既有知识库与索引均未改动，未提交 git。

## 2026-11-18 — 接入代码审查与来源头补全

- **独立审查**：DSH 完成静态代码审查；运行测试由主代理负责。
- **预算决定**：保留“首条规范证据、Wiki、其余规范候选”的分配，使两类资料都能进入问答。未采纳“全部原文候选先占用预算”的建议，因为它会重新挤掉 Wiki；规范优先体现为首条规范证据保留、冲突时以规范为准，后续省略仍会披露。
- **修正**：Wiki 整页与摘录的证据头都新增 `source_doc`、`source_sha256` 和简写的章节/表格/行号引用。API `provenance` 继续保留完整元数据，离线证据和模型上下文也能直接追溯来源。
- **回归**：主代理先运行新增的来源头检查并观察到缺少 SHA-256 的失败，修正后预算/RAG/HTTP/会话相关 37 项测试通过。
- **真实上下文**：补全来源头后，ServerType 为 11947 字符、BaseEventType 为 11939 字符、中文诊断关闭问题为 11948 字符；三者仍同时含 Wiki 与原文，且均不超过默认 12000 字符。
- **最终全套结果**：主代理在来源头修正后实际运行 `python -m unittest discover`，164 项测试全部通过（22.323 秒）。本轮未调用在线模型 API，Wiki 页面继续保持 `draft`。
