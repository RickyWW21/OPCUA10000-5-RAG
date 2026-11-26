# Wiki 维护规则（Agent 入口）

本文件是后续 Agent 维护 `wiki/` 的操作说明。它是流程文档，不是规范内容页，也不计入 15 个知识页。

## 0. 状态与不可越过的边界

- 首版 Wiki 由 LLM 在 2026-11-18 阅读 `source/OPC-10000-5-v1.05.06.md`、`kb/chapters.jsonl`、`kb/tables.jsonl`、`kb/entities.jsonl` 后手动生成。
- 所有内容页 `status: draft`，**未经过人工语义审阅**。不要把 LLM 的聊天结论、摘要或推断自动提升为规范结论。
- 只引用 Part 5。涉及 Part 3、Part 4、Part 6、Part 7、Part 9、Part 18 等的内容，只能注明“本项目未收录”，不得展开或据此推导规则。
- 原文中的脚注标记（例如 `ServerStatus1`、`ServerCapabilities1`）不是规范成员名的一部分。写成员名前必须回到原文表格和上下文核对；本 Wiki 已在 `ServerType` 页说明这一点。
- 不新增实体 id：`entity_id` 必须能在 `kb/entities.jsonl` 中找到。没有实体记录的主题只能写 topic 页。
- 不伪造来源、行号、hash、章节号或表号。没有把握的内容不写，或明确标注为待核对。
- 首版是**手动 Agent 维护**，不建增量编译器、不引入 YAML 库、不调用外部 API。校验只覆盖形式/出处。

## 1. 目录与格式

```
wiki/
  index.md                  # 目录，必须链接全部内容页
  log.md                    # 生成/更新日志
  AGENTS.md                 # 本文件
  entities/<page_id>.md     # 12 个实体页
  topics/<page_id>.md       # 3 个主题页
```

### 1.1 Frontmatter

每页以 `---` 开始和结束。`sources` 使用 JSON 数组（YAML flow 形式，单行）：

```yaml
---
page_id: servertype
kind: entity
entity_id: ObjectType:ServerType
source_doc: OPC-10000-5
source_version: 1.05.06
source_sha256: c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf
status: draft
updated: 2026-11-18
sources: [{"section": "6.3.1", "table": "9", "lines": "225-250"}, {"section": "6.3.1", "lines": "253-257"}]
---
```

- `page_id`：小写字母、数字、连字符，全 Wiki 唯一。
- `kind`：`entity` 或 `topic`。
- `entity_id`：仅实体页；必须与 `kb/entities.jsonl` 的 `id` 完全一致。
- `source_doc`：固定 `OPC-10000-5`。
- `source_version`：固定 `1.05.06`，并与 `source/source_manifest.json` 一致。
- `source_sha256`：manifest 的 `sha256`，必须等于当前原文文件的实际 SHA-256。
- `status`：首版为 `draft`；人工审阅机制建立前不要改成其他值。
- `updated`：`YYYY-MM-DD`。
- `sources`：非空 JSON 数组。每项有 `section`、可选的 `table`、`lines`（`起-止`）。正文必须逐项引用，不能只放在 frontmatter 里。

### 1.2 正文引用（唯一格式）

```markdown
[§6.3.1 Table 9 L225-L250](../../source/OPC-10000-5-v1.05.06.md#L225-L250)
```

- 从 `wiki/entities/` 或 `wiki/topics/` 到原文都是 `../../source/...`；从 `wiki/index.md` 则是 `../source/...`（目录页目前不必引用原文）。
- 标签必须写清章节和表号（无表时省略 `Table n`），行范围必须与链接 fragment 完全一致。
- 同一组 `section/table/lines` 必须出现在该页 `sources` 中；正文引用与 `sources` 双向对应。
- 行号是原文从 1 开始的行号。表号是 `Table n` 中的数字，不是 `table-9` 这类 kb 内部 id。
- 引用是永久定位，不使用“本次问答 [E1]”之类的临时证据标记。

## 2. 导入新实体页

1. 在 `kb/entities.jsonl` 中找到目标实体，记录 `id`、`kind`、`section`、`related_tables`。找不到记录就不要新建实体页；可写主题页或暂不建页。
2. 在 `kb/chapters.jsonl` 找到该 `section` 的 `start_line`/`end_line`；在 `kb/tables.jsonl` 找到 `related_tables` 对应记录的 `number`、`section`、`start_line`/`end_line`。
3. 打开原文对应章节，核对定义表、正文、脚注和建模规则。不要只根据 `summary_zh` 写页面；`summary_zh` 是生成的线索，不是规范原文。
4. 新建 `wiki/entities/<page_id>.md`，写 frontmatter 和正文。正文至少包含：用途、重要成员（可用表格）、相关类型与边界、相关页面、返回目录。
5. 正文每个关键结论附近放符合 §1.2 的永久引用；`sources` 列出实际用到的全部范围。
6. 更新 `wiki/index.md`，加入页面链接和一行说明。
7. 在 `wiki/log.md` 追加一条记录：日期、操作者（LLM/Agent）、新增页面、核对的章节/表格、校验命令。
8. 运行 §5 的校验命令；全部通过后才算完成导入。

## 3. 更新已存在页面

1. 先读目标页和它的 `sources`，再读当前原文范围；不要凭记忆改动。
2. 如果只是补充说明：新增正文引用时同步在 `sources` 增加完全相同的条目；删除正文引用时同步删除 `sources` 条目。校验器会拒绝“只在一边存在”的情况。
3. 如果原文版本/内容发生变化：
   - 先核对 `source/source_manifest.json` 的 `doc`、`version`、`sha256` 与当前原文。
   - 更新 manifest 后，**所有页面**的 `source_sha256` 都会变成过时值，校验器会逐页报错。必须逐页确认引用范围仍然有效，再更新 hash；不得为了让校验通过而盲目替换 hash。
   - 章节、表格、行号发生移动时，重新从 `kb/chapters.jsonl`/`kb/tables.jsonl` 和原文定位，更新正文引用与 `sources`。
   - 原文删除或重命名章节/表格时，校验器会报“unknown section/table”；应删除或改写相应结论，而不是保留失效引用。
4. 更新 `updated` 日期和 `wiki/log.md`；如果页面范围变化，同步更新 `index.md` 的说明。
5. 再次运行校验。来源更新后，过时 hash、失效章节/表格、越界行号都会导致非零退出码，这是预期行为，不是校验器故障。

## 4. 查询流程

1. 先读 `wiki/index.md` 选择实体页或主题页。
2. 实体页优先看“用途”“重要成员”“相关类型与边界”；主题页优先看章节导览和页面地图。
3. 需要规范原文时，按正文引用跳到 `source/OPC-10000-5-v1.05.06.md` 的对应行；不要只引用 Wiki 自身的结论。
4. 需要机器可读的实体详情时，查 `kb/entities.jsonl`、`kb/tables.jsonl`、`kb/chapters.jsonl`；Wiki 不复制全部字段，也不替代 kb。
5. 回答用户时区分：
   - “Part 5 原文写了什么”；
   - “LLM Wiki 如何整理”；
   - “本项目未收录的其他 Part 规则”。
6. 不要把 Wiki 的 `draft` 内容说成“已审阅”或“规范保证”。校验通过只表示形式/出处检查通过。

## 5. 校验命令与预期失败

在项目根目录运行：

```powershell
python tools/check_wiki.py
python -m unittest tests.test_wiki
python -m unittest discover
```

`tools/check_wiki.py` 的 `--root` 默认是项目根，也可以显式指定：

```powershell
python tools/check_wiki.py --root .
```

退出码 0 表示形式/出处检查通过；非 0 表示至少一项失败，错误逐条打印到 stderr。它会检查：

- 10–20 个内容页（首版 15 个：12 实体 + 3 主题）；
- frontmatter 必需字段、`page_id` 唯一、kind/entity_id 规则；
- manifest 的 doc/version/hash 与当前原文一致，页面 hash 与 manifest 一致；
- `sources` 的章节/表格/行范围存在于 `kb/` 和原文，并与正文引用逐项对应；
- 实体页的 `entity_id` 存在于 `kb/entities.jsonl`，来源包含实体 section，且至少一个引用表匹配 `related_tables`；
- 内部 Markdown 链接存在、不逃出项目 root、行锚点范围有效；
- 每页至少链接另一个知识页，`index.md` 覆盖全部内容页，每页至少有一个来自内容页或目录的入链；
- `wiki/AGENTS.md`、`wiki/log.md` 存在。

它**不检查**语义正确性、事实一致性、审计合规性或翻译质量。

常见预期失败：

| 现象 | 原因 | 修复 |
|---|---|---|
| `sha256` 报错 | manifest 或页面 hash 过时 | 核对原文后更新 manifest 和所有页面 hash |
| `unknown section` / `unknown table` | kb 中没有该章节/表，或写错编号 | 从 kb 记录重新定位，不硬编码猜测 |
| `outside section/table` / `beyond end of source` | 行范围错误 | 重新读原文行号并修正 |
| `no matching frontmatter source` | 正文引用与 `sources` 不一致 | 两边同步 |
| `link target does not exist` | 页面互链或原文路径错误 | 修正相对路径 |
| `duplicate page_id` | 两个页面用了同一 id | 改唯一 id 并更新 index |
| `no link to another knowledge page` | 页面只链回目录或原文 | 增加至少一个实体/主题页链接 |

## 6. 日志格式

`wiki/log.md` 每条至少包含：

```markdown
## 2026-11-18 — 首版生成（LLM）
- 操作者：LLM/Agent（未人工审阅）
- 范围：12 实体 + 3 主题
- 核对：source v1.05.06、kb/chapters、kb/tables、kb/entities
- 校验：`python tools/check_wiki.py` → <实际结果>
- 备注：只做形式/出处检查；语义未审阅
```

不要写“已审阅”“已验证语义”之类结论，除非有明确的人工审阅记录。不要提交 git；提交由用户决定。
