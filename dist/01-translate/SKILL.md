---
name: paper-translate
description: 为学术论文生成可核验的翻译工作台——分段单元、术语表（含论文自有多词术语）、数字与引用索引、双语对照骨架、译后审计表。不代替译者下笔，而是保证「术语稳、段落全、关系准、可核验」四项约束在翻译过程中不被破坏。
---

# 文献翻译

## 这个 Skill 解决什么

机器翻译论文最容易坏在四处，本 Skill 对应给出四件工具：

| 追问 | 本 Skill 的处置 |
|---|---|
| 术语稳吗 | 从论文自身统计多词术语，与约 90 条学科种子词表合并成术语表；同词不同译会被审计表抓出来 |
| 段落全吗 | 按段落切分而非按字符切分，编号 S001…；参考文献、邮箱行、`[n]` 开头行标为「非正文区」，明确不计入待译范围 |
| 关系准吗 | 把原文里的 `[n]`、`\cite{}` 抽取成引用映射，译文里引用编号错位能被发现 |
| 可核验吗 | 每条术语、每段原文、每个数字都带页码；译后审计表逐段核对术语、数字、引用三项 |

## 什么时候用 / 不用

**用**：把一篇英文学术论文译成中文（或反向），且要求术语统一、可回溯原文；作为人工译者或下游模型的翻译前置。

**不用**：需要最终译文的成品（本 Skill 给的是脚手架与审计表，译文由执行 Skill 的 agent 按 `translation_brief` 落笔）；专利、法律文本等术语体系完全不同的材料。

## 怎么调用

```
python run.py --topic 01-translate
```

本地调试可用 `BSK_INPUT_DIR` / `BSK_OUTPUT_DIR` / `BSK_WORK_DIR` 覆盖路径。

## 输入

- `case.json`（含 `case_id`，可能含 `output_contract`）
- `task.md`
- 文献文件：PDF / DOCX / HTML / Markdown / TXT

## 输出

`result.json` 固定七键：`case_id` / `status` / `result` / `evidence` / `sources` / `uncertainty` / `changes` / `notes`。

`result` 主要字段：

`segments`（每段 `id`/`page`/`text`/`chars`/`region`）`segment_count` `untranslated_regions`（被排除的区及原因）`glossary`（`term`/`count`/`rendering`；`rendering` 为 `null` 表示待译者确定，不预设）`glossary_size` `translation_units`（按 2000 字符打包的翻译批次）`citation_map`（`marker`/`page`/`context`）`numbers_index`（数字与其所在段）`translation_brief`（七条翻译规则）`audit_template`（逐段核对表）`page_map` `summary`

## 交给执行方的委托（`delegate_*`）

本题只做译前准备，不替你写字。`result` 里的三个键把「拿这些材料写译文」变成一条可直接执行的指令：

| 键 | 内容 |
| --- | --- |
| `delegate_prompt` | 完整提示词：段号与原页码、已固定译名的术语表、公式与 `[n]` 原样保留的要求、译不出时标 `[待核]` |
| `deliverable_contract` | 期望的回包形状 `{"S001": "……", ...}`，键是段号 |
| `delegate_budget` | `1` 次模型请求 |

本 Skill 自身不调用模型（`self_check.axes.cost.model_requests` 恒为 0）。把 `delegate_prompt` 交给宿主 Agent 执行一次，把回答写回 `result.delivered_text` 即可；不执行也不影响其余字段的完整性。

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

1. 抽取正文，切页，剔除跨页重复的页眉页脚。
2. `_segment()` 按段落边界切分，每段记录起始偏移，偏移换算页码。
3. `_region()` 判定区属：以 `[n]` 开头、含邮箱、位于 References 章节内、或长度极短的标签行 → 非正文区，记入 `untranslated_regions` 并说明原因。
4. `_glossary()` 两路合并：种子词表命中（约 90 条英中对照，`rendering` 已给）+ 论文自有多词短语（出现 ≥3 次，`rendering` 留 `null` 交由译者定）。频率降序。
5. `_citation_map()` 抽 `[n]`（含 `[n-m]`、`[n,m]`）与 `\cite{}`，记页码与上下文句。
6. `_numbers_index()` 抽全部数字与单位，标出所在段号，供译后核对「数字未走样」。
7. `_translation_units()` 把段落按 2000 字符打包，避免超出单次调用预算。
8. `_audit_template()` 生成逐段审计行：术语一致性、数字一致性、引用完整性三项待勾。

## 异常处理

| 情况 | 行为 |
|---|---|
| 材料无法读取 | 按实际原因分别报告，不合并成一句「读取失败」。`unreadable_input = {file, code, reason}`，`code` 取 `encrypted`（有打开密码）/ `no_text_layer`（可开但无文字层，需 OCR）/ `not_a_pdf`（扩展名与内容不符）/ `damaged`（交叉引用表损坏）/ `backend_missing` / `backend_failed` / `extract_failed` 之一；此时 `status=cannot_determine`，`uncertainty` 同步写明该文件与下一步需要什么 |
| 未映射字符（连字、自定义编码、图片化字形） | 计入 `unmapped_char_count`；同时报 `unmapped_char_share`（占全文比例）。绝对值超 `max(20, 全文/2000)` 或占比超 `0.002` 即降级为 `partial` 并记 `state=uncertain`；不猜测替换，损坏字符原样保留 |
| 章节识别失败 | 退化为整篇按段落切分，`region` 全部标 `body`，并记录该降级 |
| 术语表为空 | `glossary_size=0` 并记 gap，不臆造术语 |
| 参考文献无编号制 | `citation_map` 为空 → 记 gap，说明作者-年份制未被本 Skill 覆盖 |
| 抽取后端非首选 | `notes` 记录实际后端名，供审计 |
| 运行抛异常 | 捕获后仍写 `result.json`，保留已完成部分与异常类型 |

## 自检输出（`result.self_check`）

每次运行都会在 `result` 里附一块本机实测的审计，用于替代「本 Skill 效果很好」这类无法核对的说法。
它不是自评分数，是可以在同一份输出里复核的数：

| 轴 | 字段 | 读法 |
|---|---|---|
| 契约完成度 | `completion.ratio` | 契约要求的字段填了几个；填不出就登记，不编造 |
| 可核验性 | `verifiability` | 术语表每条是否在原文出现；译文段落与原文段落的对应关系是否可定位 |
| 覆盖率 | `coverage` | 原文有 13 页 / 44 条术语（示例件）；本 Skill 报了几项 |
| 正确性 | `correctness.measured` | 恒为 `false`：本机没有评分方答案，正确性不自评 |
| 成本 | `cost` | 实际耗时、模型请求数、预算余量、每秒处理词数 |

`verifiability` 同时给出样本量（`quotes_checked` / `numbers_checked` / `anchored`），
避免「十二 个字段 100%」被读成「三百个字段 100%」。比率字段在没有样本时为 `null`，
不写成 `1.0`。

自检在开发期抓出过真实缺陷：00 的机构名曾把 `Google Brain` 与 `University of Toronto`
粘成 `Google Research University`；08 的引文曾把表格数字串进句子。这类问题人工读结果不易发现，
逐字回查才发现。

## 自查清单

- `result.json` 含 `case_id` 且与输入一致
- 每个 `segments[i]` 都有页码，`region` 已分类
- `untranslated_regions` 的排除是显式的，不是静默丢段
- 术语表的 `rendering=null` 项未被擅自填成某个译法
- `status` 与实际完成度一致（有 gap 就不是 `success`）

- `self_check.axes.verifiability` 里 `quote_unverified` 为空，或每条都写明了为什么定位不到
- `cost.model_requests` 与实际相符（本 Skill 不调用模型，应为 0）
- 未定术语数为 0，或每条都给了为什么不译

## 限制

- 不产出译文正文；译文由 agent 依据 `translation_brief` 与 `glossary` 生成
- 术语表是统计结果，不判断两个术语是否同义
- 公式内部不翻译，行内公式按原样保留并计入数字索引
- 双向翻译均支持，但种子词表以英中为主

## 最小调用示例

```
cd /app/submission
python run.py --topic 01-translate
# 产出 /app/output/result.json
```

以上为调用示例，结果以实际运行为准，不构成正式结果。
