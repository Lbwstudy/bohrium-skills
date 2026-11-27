---
name: paper-notes
description: 把学术论文转成结构化阅读笔记——按句挖出论断/方法/结果/限制四类笔记，每条带章节与页码归属，并附论文卡片、章节摘要、概念索引与覆盖度报告。用于「对得上、留得住、找得回、用得上」的文献精读任务。
---

# 文献总结与结构化笔记

## 这个 Skill 解决什么

读论文的笔记常坏在「写得好但找不回」。本 Skill 反过来做：先保证每条笔记能定位，再谈内容。

| 追问 | 本 Skill 的处置 |
|---|---|
| 对得上吗 | 每条笔记是原文整句的逐字引用，不转述；章节归属按**字符偏移**定位最深标题，不按页猜 |
| 留得住吗 | 固定十字段 schema，缺项写 `null` 并说明，不留空白让人脑补 |
| 找得回吗 | 每条带 `page`、`section`、`offset`；`concept_index` 给出概念到笔记号的倒排 |
| 用得上吗 | 输出 Markdown 版本，可直接进笔记软件；`note_kinds` 统计各类笔记分布，暴露偏科 |

## 什么时候用 / 不用

**用**：精读一篇论文并留下可检索的结构化笔记；为文献综述、复现、审稿准备素材。

**不用**：需要综述性散文（本 Skill 不写散文）；需要判断论文价值（那是评审）。

## 怎么调用

```
python run.py --topic 02-notes
```

本地调试用 `BSK_INPUT_DIR` / `BSK_OUTPUT_DIR` / `BSK_WORK_DIR`。

## 输入

`case.json`、`task.md`、文献文件（PDF / DOCX / HTML / MD / TXT）。

## 输出

`result.json` 七键。`result` 主要字段：

`notes`（每条含 `id`/`kind`/`text`/`page`/`section`/`offset`/`confidence`/`chapter`）`note_count` `note_kinds`（四类计数）`note_schema`（十字段定义）`paper_card`（题名/作者/年份/问题/方法/结论/局限）`section_summaries` `concepts` `concept_index` `coverage`（覆盖章节数 / 有正文章节数 / 未覆盖列表）`markdown` `page_map` `summary`

`kind` 取值：`claim` / `method` / `result` / `limitation`。
`confidence` 取值：`direct`（句子本身即陈述）/ `inferred`（由提示词推断）/ `unverified`（定位失败）。

## 契约字段怎么填

从 `case.json` 结构性发现契约键（12 别名），字段名归一化最长匹配到真实内容；匹配不上写 `{"value": null, "state": "not_reported"}` 并登记 `uncertainty`。

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

1. 抽取正文并切页，剔除跨页重复页眉页脚。
2. 章节切分后取每节 `body`；**不重新按页切段**——按页切会让同页多个标题下的笔记全挂到最后一个标题。
3. `CUES` 五类正则给每句打分：论断（we propose / this paper / we find）、方法（we use / we train / implemented with）、结果（outperform / achieve / improve）、限制（limitation / only / future work）、背景（recently / prior work）。
4. 命中即入候选，按 `\W+` 归一化去重，编号 N001…
5. `_section_at(text, offset)` 用字符偏移找最近的**已记录偏移**的标题，得到最深章节归属。
6. `_coverage()` 对比「有正文章节的集合」与「笔记实际覆盖的集合」，未覆盖的显式列出，不掩盖。
7. `_concepts()` 取术语频次与共现，生成概念索引。
8. `_markdown()` 输出可读版本。

## 异常处理

| 情况 | 行为 |
|---|---|
| 材料无法读取 | 按实际原因分别报告，不合并成一句「读取失败」。`unreadable_input = {file, code, reason}`，`code` 取 `encrypted`（有打开密码）/ `no_text_layer`（可开但无文字层，需 OCR）/ `not_a_pdf`（扩展名与内容不符）/ `damaged`（交叉引用表损坏）/ `backend_missing` / `backend_failed` / `extract_failed` 之一；此时 `status=cannot_determine`，`uncertainty` 同步写明该文件与下一步需要什么 |
| 未映射字符（连字、自定义编码、图片化字形） | 计入 `unmapped_char_count`；同时报 `unmapped_char_share`（占全文比例）。绝对值超 `max(20, 全文/2000)` 或占比超 `0.002` 即降级为 `partial` 并记 `state=uncertain`；不猜测替换，损坏字符原样保留 |
| 章节识别为空 | 退化为整篇单节，`section` 记为 `null` 并记 gap |
| 某类笔记为 0 | 如实报 0，不伪造；在 `uncertainty` 说明可能是章节标题不在常见命名内 |
| 句子定位失败 | `confidence=unverified`，整体降级 `partial` |
| 运行抛异常 | 捕获后仍写 `result.json` |

## 自检输出（`result.self_check`）

每次运行都会在 `result` 里附一块本机实测的审计，用于替代「本 Skill 效果很好」这类无法核对的说法。
它不是自评分数，是可以在同一份输出里复核的数：

| 轴 | 字段 | 读法 |
|---|---|---|
| 契约完成度 | `completion.ratio` | 契约要求的字段填了几个；填不出就登记，不编造 |
| 可核验性 | `verifiability` | 每条笔记的引文是否逐字来自原文；页码与章节是否对得上 |
| 覆盖率 | `coverage` | 原文有 13 页 / 91 条笔记（示例件）；本 Skill 报了几项 |
| 正确性 | `correctness.measured` | 恒为 `false`：本机没有评分方答案，正确性不自评 |
| 成本 | `cost` | 实际耗时、模型请求数、预算余量、每秒处理词数 |

`verifiability` 同时给出样本量（`quotes_checked` / `numbers_checked` / `anchored`），
避免「九十 个字段 100%」被读成「三百个字段 100%」。比率字段在没有样本时为 `null`，
不写成 `1.0`。

自检在开发期抓出过真实缺陷：00 的机构名曾把 `Google Brain` 与 `University of Toronto`
粘成 `Google Research University`；08 的引文曾把表格数字串进句子。这类问题人工读结果不易发现，
逐字回查才发现。

## 自查清单

- 每条笔记的 `text` 能在原文逐字找到
- `page` 与 `offset` 互不矛盾（页码由偏移换算，不是独立推断）
- 未覆盖章节出现在 `coverage.未覆盖` 里
- `status` 与实际完成度一致

- `self_check.axes.verifiability` 里 `quote_unverified` 为空，或每条都写明了为什么定位不到
- `cost.model_requests` 与实际相符（本 Skill 不调用模型，应为 0）
- 笔记里没有无法回查的句子

## 限制

- 只看句子表面提示词，不做语义理解；反讽、否定嵌套会误判
- 一条笔记不跨句合并，长论证会被拆成多条
- 图表内容与公式内部不产生笔记
- 中英文均支持，提示词表以英文为主，中文论文的命中率会低

## 最小调用示例

```
cd /app/submission
python run.py --topic 02-notes
```

以上为调用示例，结果以实际运行为准，不构成正式结果。
