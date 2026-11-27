---
name: introduce-related-work
description: 把论文的引言与相关工作章节拆成可核对的论证骨架——背景陈述及其引用密度、研究空白陈述及其是否给出原因、贡献陈述及其能否在正文找到支撑结果、相关工作是比较式组织还是罗列式组织，并指出哪条贡献没有支撑、哪句相关工作只列举不比较。不代写段落，只交出「立得住、分得清、说得实、对得上」四件事的现状与缺口。
---

# 引言与相关工作写作

## 这个 Skill 解决什么

引言与相关工作的问题不在文笔，在结构。本 Skill 不做润色，只把结构拆出来逐项核对：

| 追问 | 本 Skill 的处置 |
|---|---|
| 立得住 | 抽出背景陈述并统计其引用密度（`cited_ratio`）；无引用的背景断言单独标出，因为它多半是常识性铺陈而非有据立论 |
| 分得清 | 判定相关工作章节是 **grouped**（按方法族分组比较）还是 **listed**（逐篇罗列），并列出 `listed_only` 那些只提不比的句子 |
| 说得实 | 每条贡献陈述用内容词重叠对到正文结果句（阈值 0.28）；对不上的进 `unsupported`，不默认成立 |
| 对得上 | 引言的引用编号与文献表编号集合求差集，悬空编号列出；`reference_entries` 与 `cited_in_intro` 同时给出 |

## 什么时候用 / 不用

**用**：写引言前先摸清已有材料的论证完成度；审稿时快速判断贡献陈述是否有正文支撑；接手他人稿件定位「相关工作只是流水账」的具体句子。

**不用**：需要生成成段的中英文引言（本 Skill 给骨架与证据，行文由 agent 依据 `skeleton` 落笔）；需要检索新文献（不联网）。

## 怎么调用

```
python run.py --topic 07-intro
```

本地调试可用 `BSK_INPUT_DIR` / `BSK_OUTPUT_DIR` / `BSK_WORK_DIR` 覆盖路径。

## 输入

- `case.json`（含 `case_id`，可能含 `output_contract`）
- `task.md`
- 文献材料：PDF / DOCX / HTML / Markdown / TXT

引言章节按标题识别（`Introduction` / `1 Introduction`）；相关工作章节兼容 `Related Work` / `Related Works` / `Background and Related Work` / `Literature Review`。

## 输出

`result.json` 固定七键：`case_id` / `status` / `result` / `evidence` / `sources` / `uncertainty` / `changes` / `notes`。

`result` 主要字段：

| 字段 | 内容 |
|---|---|
| `introduction_section` / `introduction_paragraphs` | 命中的章节标题与段落数 |
| `background_moves` | `{found, moves[{index, quote, citations}]}`，背景陈述与各自引用数 |
| `gap_statements` | `{count, statements[{index, quote, explains_cause}]}`，研究空白陈述及其是否解释成因 |
| `contributions` | `{count, statements[{index, quote, has_number, numbers, supporting_result}]}`，支撑不到正文的进 `unsupported` |
| `related_work` | `{found, title, sentences, paragraphs, distinct_citations, citation_ids, comparative_sentences, listed_only, organisation, missing_comparison}` |
| `citation_audit` | `{cited_in_intro, reference_entries, dangling, dangling_note}` |
| `skeleton` | 汇总四块：`background` / `gap` / `contributions` / `related_work` / `paragraphs` |
| `page_map` / `quotes` / `summary` / `run` | 自动填充的定位与摘要 |

## 交给执行方的委托（`delegate_*`）

本题只搭论证骨架并核对每条陈述的支撑，不代写章节。三个键把骨架变成可直接执行的指令：

| 键 | 内容 |
| --- | --- |
| `delegate_prompt` | 完整提示词：已核对的背景陈述（带原文引用编号）、研究空白、标记为 supported 的贡献、相关工作的组织方式与规模 |
| `deliverable_contract` | 期望的回包形状 `{"introduction": "……", "related_work": "……"}` |
| `delegate_budget` | `1` 次模型请求 |

本 Skill 自身不调用模型。提示词要求：背景必带已有引用编号、空白须由已引文献推出、无支撑的贡献不写。回包写回 `result.delivered_text`。

### 写回路径

执行方把成稿写进 `<输出目录>/delivered.json` 即完成回填。写法随题目而异：

| 题目 | `delivered.json` 的形状 |
| --- | --- |
| 01 翻译 | `{"S001": "译文……", "S002": "……"}`，键是 `delegate_prompt` 里给出的段号 |
| 05 润色 | `{"polished_text": "……", "skipped": ["未采纳的编辑及原因"]}` |
| 07 引言 | `{"introduction": "……", "related_work": "……"}` |
| 08 方法 | `{"method": "……", "experiments": "……", "missing_for_reproduction": [...]}` |
| 09 LaTeX | `{"latex_source": "\\documentclass……"}` |

有该文件时，本次运行会：

- 把内容写进 `result.delivered_text`，`state` 记为 `delivered`，并写明「正文不是本 Skill 生成的」；
- 另外写出 `delivered_source`，标明来源是执行方；
- 做一次**数字一致性核对**：把交付文本里保有的数字与交给执行方的材料逐项比对，写进
  `delivered_number_check`（`scope` 说明是逐段比对还是比对了引用段）。

逐段比对的分母是**交给执行方的那几段**，不是整篇论文——97 段里只给了 40 段，另外 57 段的数字本来就不在要求范围内，算作缺失是错的。核对只在 `delivered.json` 存在时进行；没有该文件时不写这个键，也不报缺口。

数字核对不过（保有率 < 95%）会登记一条缺口，说明差了多少、举例几项，**但不改写交付内容**：本 Skill 没有原文之外的参照，能做的只是把差异摆出来。

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

1. **定位章节**：按标题正则找引言与相关工作；引言的正文取 `structure` 层已切好的 `body`，不从全文重新切段——重新切会丢掉章节边界信息。
2. **句级切分**：每句记起始偏移，偏移经 `_section_at` 换算出最深的所属章节，经页码表换算页码，因此列出的一句能指回「第几页的哪一节」。
3. **背景陈述**（`_background`）：认 `Convolutional networks have led to…`、`Deep networks naturally integrate…` 这类现在完成时／一般现在时的领域铺陈句；统计其含引用标记的比例。
4. **空白陈述**（`_gaps`）：认 `however`、`remains`、`has not been`、`little work`、`no prior`、`unclear`、`limitation`、`challenging` 等转折与否定线索；额外判定 `explains_cause`——句子是否说明**为什么**这个空白存在（认 `because`／`due to`／`as a result`／`attributed to`），只描述现象不算。
5. **贡献陈述**（`_contributions`）：认 `we propose`／`we present`／`this paper`／`our contribution`／`to the best of our knowledge`；对每条用内容词重叠对到正文结果句，`_best_match(threshold=0.28)` 取最高分，未达阈值即写入 `unsupported`。
6. **相关工作组织**（`_related`）：比较句数 ≥ `max(2, 句子总数/3)` 判为 `grouped`，否则 `listed`；`listed_only` 列出只出现方法名而无比较谓词的句子。
7. **引用审计**（`_citation_audit`）：引言内引用编号集合与文献表编号集合求差集；文献表缺失时 `if_no_references` 给出说明而不是空数组。
8. **汇总骨架**（`_skeleton`）：把上述四块的计数与判定收成一张表，`outline_markdown` 渲染成人可读版本。

## 异常处理

| 情况 | 行为 |
|---|---|
| 材料无法读取 | 按实际原因分别报告，不合并成一句「读取失败」。`unreadable_input = {file, code, reason}`，`code` 取 `encrypted`（有打开密码）/ `no_text_layer`（可开但无文字层，需 OCR）/ `not_a_pdf`（扩展名与内容不符）/ `damaged`（交叉引用表损坏）/ `backend_missing` / `backend_failed` / `extract_failed` 之一；此时 `status=cannot_determine`，`uncertainty` 同步写明该文件与下一步需要什么 |
| 未映射字符（连字、自定义编码、图片化字形） | 计入 `unmapped_char_count`；同时报 `unmapped_char_share`（占全文比例）。绝对值超 `max(20, 全文/2000)` 或占比超 `0.002` 即降级为 `partial` 并记 `state=uncertain`；不猜测替换，损坏字符原样保留 |
| 找不到引言章节 | `introduction_section=null`，`uncertainty` 写明未识别到引言，不把摘要当引言 |
| 找不到相关工作章节 | `related_work.found=false`，记 gap，不虚构比对结果 |
| 贡献陈述无支撑 | 进入 `unsupported` 列表，同时把状态降为 `partial`；不为了让数量好看而放宽阈值 |
| 引用编号悬空 | 列入 `dangling`；`reference_entries=0` 时注明文献表缺失，而非全部判为悬空 |
| 章节标题无编号 | 裸标题（`Introduction`）同样识别，层级由标题形态推断并记入 `notes` |
| 抽取后端非首选 | `notes` 记录实际后端名，供审计 |
| 运行抛异常 | 捕获后仍写 `result.json`，保留已完成部分与异常类型 |

## 自检输出（`result.self_check`）

每次运行都会在 `result` 里附一块本机实测的审计，用于替代「本 Skill 效果很好」这类无法核对的说法。
它不是自评分数，是可以在同一份输出里复核的数：

| 轴 | 字段 | 读法 |
|---|---|---|
| 契约完成度 | `completion.ratio` | 契约要求的字段填了几个；填不出就登记，不编造 |
| 可核验性 | `verifiability` | 贡献陈述的支撑句是否逐字来自结果章节；引文是否都在文献表内 |
| 覆盖率 | `coverage` | 原文有 13 页 / 7 段引言 / 25 处引用（示例件）；本 Skill 报了几项 |
| 正确性 | `correctness.measured` | 恒为 `false`：本机没有评分方答案，正确性不自评 |
| 成本 | `cost` | 实际耗时、模型请求数、预算余量、每秒处理词数 |

`verifiability` 同时给出样本量（`quotes_checked` / `numbers_checked` / `anchored`），
避免「二十五 个字段 100%」被读成「三百个字段 100%」。比率字段在没有样本时为 `null`，
不写成 `1.0`。

自检在开发期抓出过真实缺陷：00 的机构名曾把 `Google Brain` 与 `University of Toronto`
粘成 `Google Research University`；08 的引文曾把表格数字串进句子。这类问题人工读结果不易发现，
逐字回查才发现。

## 自查清单

- `result.json` 含 `case_id` 且与输入一致
- 每条 `moves`／`statements` 都带 `quote`，可回到原文核对
- `unsupported` 里的贡献陈述确实在正文找不到支撑句，不是阈值调得过严
- `related_work.organisation` 的判定依据（比较句数／总句数）可从 `comparative_sentences` 与 `sentences` 复算
- `citation_audit` 区分了「文献表缺失」与「编号悬空」两种情况
- `status` 与实际完成度一致（有 gap 就不是 `success`）

- `self_check.axes.verifiability` 里 `quote_unverified` 为空，或每条都写明了为什么定位不到
- `cost.model_requests` 与实际相符（本 Skill 不调用模型，应为 0）
- 每条贡献的 `support` 要么指向具体结果句，要么明确写「无结果支撑」

## 限制

- 不生成引言正文，只给骨架、证据与缺口
- 贡献与结果的匹配用内容词重叠，不是语义蕴含；改写幅度大的同义表述可能对不上，此时宁可报 `unsupported` 也不放宽
- 不认识「贡献在第 5 节以表格形式给出」这类跨模态支撑，只匹配正文句子
- 相关工作组织判定依赖比较谓词词表，领域特有比较表达（`outperforms in the low-data regime` 变体）可能漏判
- 不联网，不检索补充引用

## 最小调用示例

```
cd /app/submission
python run.py --topic 07-intro
# 产出 /app/output/result.json
```

以上为调用示例，结果以实际运行为准，不构成正式结果。
