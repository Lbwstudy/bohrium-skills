---
name: reference-manager
description: 把一篇论文的参考文献表变成可核验的引用台账——逐条拆出作者/题名/刊名/年/卷期/页码/DOI，解析正文与 LaTeX 里每一处引用标记，检出悬空引用与未被引用条目，给出按首次引用顺序的重编号映射，并同时输出 GB/T 7714—2015 与 APA 两种格式。不改稿，只交出「挂得对、编得顺、收得净、对得上」四件事的证据与待办。
---

# 参考文献与引用管理

## 这个 Skill 解决什么

参考文献出错的方式是固定的四种，本 Skill 对每一种给一条可核验的产物：

| 追问 | 本 Skill 的处置 |
|---|---|
| 挂得对 | 解析正文 `[n]`／`\cite{}` 每一处标记，与文献表编号比对，列出 **悬空引用**（引了但表里没有）与 **未被引用条目**（表里有但没人引） |
| 编得顺 | 按首次引用顺序生成 `renumber_map`（旧号→新号），并逐条记入 `changes`，编号与正文的错位成为可执行的改写指令 |
| 收得净 | 以 DOI 优先、题名归一化次之做去重，产出 `duplicate_groups`（保留哪条、合并哪条、依据是什么），不做静默删除 |
| 对得上 | 每条文献给出 GB/T 7714—2015 与 APA 两种成品字符串，缺字段的条目进 `format_blocked` 说明缺哪一项，而不是补一个猜的值 |

## 什么时候用 / 不用

**用**：投稿前自查引文；接手别人的稿子要摸清引用状况；论文格式转换（期刊要 GB/T，会议要 APA）；LaTeX 工程的 `\cite` 与 `.bib` 对账；参考文献表要从 PDF 里恢复成可编辑结构。

**不用**：需要真实检索并补全缺失文献的元数据（本 Skill 不联网，缺字段只登记不填充）；需要按作者-年份（Harvard／Chicago author-date）制式输出（当前只实现顺序编码制 `[n]` 与 APA 两套）。

## 怎么调用

```
python run.py --topic 06-cite
```

本地调试可用 `BSK_INPUT_DIR` / `BSK_OUTPUT_DIR` / `BSK_WORK_DIR` 覆盖路径。

## 输入

- `case.json`（含 `case_id`，可能含 `output_contract`）
- `task.md`
- 文献材料：PDF / DOCX / HTML / Markdown / TXT，或 LaTeX 源文件（`.tex` + `.bib`）

LaTeX 工程在读入时按源文件解析，不经 PDF 文本层——`\cite{key}` 的 key 与 `.bib` 的 `@entry` 直接对账，避免中间层损失。

## 输出

`result.json` 固定七键：`case_id` / `status` / `result` / `evidence` / `sources` / `uncertainty` / `changes` / `notes`。

`result` 主要字段：

| 字段 | 内容 |
|---|---|
| `reference_count` | 文献表条目数 |
| `references` | 每条 `index` / `raw` / `authors` / `author_parts` / `title` / `venue` / `volume_issue` / `year` / `pages` / `doi` |
| `in_text_citation_count` | 正文引用标记出现次数 |
| `dangling_citations` | 正文引用了但文献表里不存在的编号 |
| `uncited_entries` | 文献表里有但正文从未引用的编号 |
| `citation_order` | 按首次出现排出的编号序列 |
| `renumber_map` | `{old, new}` 逐条映射，`renumber_changes` 为条目数 |
| `duplicate_groups` | `{keep, drop, reason, title}`，`duplicate_count` 为组数 |
| `gbt7714` / `apa` | 两种格式的成品字符串，各 `{index, text}` |
| `format_blocked` | `{index, missing}`，缺哪些格式必需字段 |
| `missing_field_totals` | 各字段在全表缺失的条目数 |
| `page_map` / `quotes` / `summary` / `run` | 自动填充的定位与摘要 |

## 契约字段怎么填

从 `case.json` 结构性发现契约键（12 个别名，含嵌套 JSON-Schema `properties`），取字段名后做归一化最长匹配到已抽出的真实内容；匹配不上的写 `{"value": null, "state": "not_reported"}` 并登记 `uncertainty`。不猜测契约结构。

## 回应案件真正问的问题（`result.request_*`）

`task.md` 里写的是这个案件要什么，不是一般性的「解析这篇论文」。运行时把它拆成若干条询问，逐条对着产出核对，三个键写进 `result`：

| 键 | 内容 |
|---|---|
| `request_summary` | `asks` 条询问、`targets` 点名的小节/表/图/公式、`language` 目标语言、`format` 要求的输出格式 |
| `request_coverage` | 每条询问一行：`state` 为 `answered` / `partially_answered` / `not_answered` / `present` / `absent_from_material`，并给出命中的字段名与匹配度 |
| `request_coverage_summary` | `{asks, targets, answered, total, ratio}` |

判定不放宽：字段名与询问词干要对上才算命中，正文长文本只有在字段名已命中时才补充匹配。所以「摘要里提到 learning rate」不会被算成回答了超参数问题——那条会如实记为 `not_answered`。案件点名的小节/表/图若材料里不存在，记为 `absent_from_material` 并单独登记，不拿别的对象顶替。

没提供 `task.md` 时三个键仍然写出，`ratio` 为 `null`，并注明「无逐条询问可对照」，不留空。

## 方法

1. **取文献表**：从 References／Bibliography 章节切条目。多栏 PDF 会把多条压在同一行，所以按 `[n]` 编号**升序游走**收条目——只有编号等于「上一个 + 1」才收，这样正文里指向后方的行内引用不会被误当条目起点。
2. **拆字段**（`_parse_entry`）：DOI 与年份用锚点正则先行；作者走 `_author_blob`——按 `\.\s+` 逐段试探，每段若仍读作人名列表则继续，读到题名则止（`Y. Bengio` 的首字母自带句点，不能用首个句点截断）。
3. **切题名与刊名**：`_title_span` 给出题名在原始串里的起止偏移，`_venue` 从该偏移之后按逗号分段，遇到纯数字／`pages?`／等于年份的段就停。题名要单独返回偏移，因为连字修复（`hier- archies` → `hierarchies`）会改写字符串本身，事后再按题名去原文里找位置会找不到。
4. **清尾部噪声**：题名或刊名末尾常粘着年份（`In ECCV. 2014`），停用后会在两种格式里重复出现，逐字段剥掉。
5. **去正文泄漏**：文献表不是文末时（附录在其后），最后一条会把附录正文整段吞进来。判据是「句子里出现三个以上功能词」——引用尾是名字、刊名、数字与页码范围，连续散文才说明越界了。
6. **解析引用**（`_in_text`）：`[n]`／`[n-m]`／`[n,m]` 与 `\cite{a,b}` 全部展开，与文献表编号集合求差集，得悬空与被未引两组。
7. **重编号**（`_renumber`）：按首次引用顺序给新号，逐条 `bundle.change("renumber", 旧号, 新号, ...)`。正文改写交给编辑工具或人工，本 Skill 只交映射。
8. **去重**（`_dedupe`）：DOI 相同优先，其次题名去除非字母数字后完全相同。
9. **双格式渲染**（`_gbt7714` / `_apa`）：GB/T 7714—2015 为「主要责任者. 题名[文献类型标志]. 出版项, 年, 卷(期): 页码.」，责任者最多 3 人后接「等」并姓前名后缩写；APA 7 为「Surname, I., & Surname, I. (Year). Title. Venue, 卷(期), 页码.」，最多 20 人，末位前加 `&`。
10. **登记缺口**（`_field_gaps`）：逐字段统计缺失条目数，有缺失即记 `uncertainty` 并把状态保持为 `partial`。

## 异常处理

| 情况 | 行为 |
|---|---|
| 材料无法读取 | 按实际原因分别报告，不合并成一句「读取失败」。`unreadable_input = {file, code, reason}`，`code` 取 `encrypted`（有打开密码）/ `no_text_layer`（可开但无文字层，需 OCR）/ `not_a_pdf`（扩展名与内容不符）/ `damaged`（交叉引用表损坏）/ `backend_missing` / `backend_failed` / `extract_failed` 之一；此时 `status=cannot_determine`，`uncertainty` 同步写明该文件与下一步需要什么 |
| 未映射字符（连字、自定义编码、图片化字形） | 计入 `unmapped_char_count`；同时报 `unmapped_char_share`（占全文比例）。绝对值超 `max(20, 全文/2000)` 或占比超 `0.002` 即降级为 `partial` 并记 `state=uncertain`；不猜测替换，损坏字符原样保留 |
| 无参考文献章节 | `reference_count=0`，`uncertainty` 写明未找到文献表，不臆造条目 |
| 文献表无 `[n]` 编号（作者-年份制） | 条目抽取退化，`citation_order` 与 `renumber_map` 为空，记录「编号制未被覆盖」 |
| PDF 文本层吃掉重音字符（`Montúfar` → `Montu�far`） | 该字符按字母处理，作者串不整体丢弃；损坏原样保留并在引文中可见，不悄悄替换成别的名字 |
| 悬空引用 | 列入 `dangling_citations` 并记 gap；不把不存在的编号补成某条真文献 |
| 字段缺失（刊名/页码/DOI） | 进 `format_blocked` 与 `missing_field_totals`，按可得字段输出，留空不猜 |
| 抽取后端非首选 | `notes` 记录实际后端名，供审计 |
| 运行抛异常 | 捕获后仍写 `result.json`，保留已完成部分与异常类型 |

## 自检输出（`result.self_check`）

每次运行都会在 `result` 里附一块本机实测的审计，用于替代「本 Skill 效果很好」这类无法核对的说法。
它不是自评分数，是可以在同一份输出里复核的数：

| 轴 | 字段 | 读法 |
|---|---|---|
| 契约完成度 | `completion.ratio` | 契约要求的字段填了几个；填不出就登记，不编造 |
| 可核验性 | `verifiability` | 文献条目的题名/作者/年份是否逐字来自原文；正文引用号是否都在文献表范围内 |
| 覆盖率 | `coverage` | 原文有 13 页 / 50 条文献 / 227 处引用（示例件）；本 Skill 报了几项 |
| 正确性 | `correctness.measured` | 恒为 `false`：本机没有评分方答案，正确性不自评 |
| 成本 | `cost` | 实际耗时、模型请求数、预算余量、每秒处理词数 |

`verifiability` 同时给出样本量（`quotes_checked` / `numbers_checked` / `anchored`），
避免「五十 个字段 100%」被读成「三百个字段 100%」。比率字段在没有样本时为 `null`，
不写成 `1.0`。

自检在开发期抓出过真实缺陷：00 的机构名曾把 `Google Brain` 与 `University of Toronto`
粘成 `Google Research University`；08 的引文曾把表格数字串进句子。这类问题人工读结果不易发现，
逐字回查才发现。

## 自查清单

- `result.json` 含 `case_id` 且与输入一致
- `references[i].raw` 保留原文，可与 `title`／`venue` 对照复核
- `dangling_citations` 与 `uncited_entries` 都有明确来源，不是「解析失败」的兜底
- `duplicate_groups` 的每组都写了 `reason`，没有静默删除任何条目
- `format_blocked` 里每条都说明缺哪个字段，而不是整条报失败
- `status` 与实际完成度一致（有 gap 就不是 `success`）

- `self_check.axes.verifiability` 里 `quote_unverified` 为空，或每条都写明了为什么定位不到
- `cost.model_requests` 与实际相符（本 Skill 不调用模型，应为 0）
- `fields_absent_from_source` 与 `gaps` 不混：前者是论文没印，后者是没做

## 限制

- 不联网，不检索、不补全缺失的元数据（DOI、页码、刊名缺失只登记）
- 只实现顺序编码制与 APA 两套格式；Harvard／Chicago／MLA／IEEE 未覆盖
- 重编号会改写正文里的 `[n]`，但只覆盖方括号数字引用；`\cite{}` 形式的键不动，需要人工替换
- 条目拆分依赖 `[n]` 编号制；纯作者-年份制的文献表条目不保证切准
- 去重按 DOI 与题名精确归一，不做模糊匹配，宁可漏合并也不误合并

## 最小调用示例

```
cd /app/submission
python run.py --topic 06-cite
# 产出 /app/output/result.json
```

以上为调用示例，结果以实际运行为准，不构成正式结果。
