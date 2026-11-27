---
name: academic-polish
description: 对学术论文做可审计的语言润色——每条修改必须通过数字、否定、比较、专名四项语义保持校验，不通过就报拒绝而不落笔；同时给出客观文体画像与术语一致性检查。用于「改得对、说得像、没改坏、讲得清」的润色任务。
---

# 学术语言润色

## 这个 Skill 解决什么

润色最怕改了意思。本 Skill 的默认动作是**拒绝**：一条修改只有同时保住数字、否定、比较级和专名，才会被应用。

| 追问 | 本 Skill 的处置 |
|---|---|
| 改得对吗 | 规则表 60 余条，分九类（口语词、冗词、模糊限定堆叠、冗余、模糊量词、时态、被动、名词化、机械修正）；每条改动都记录 before/after/why |
| 说得像吗 | `style_profile` 给客观计数：平均句长、超 45 词句数、每千词被动数、第一人称出现次数——不与「好文风」比，只报事实 |
| 没改坏吗 | `t05_support.preserves()` 四轴比对，任一轴被破坏即 `rejected`，并在 `rejected_edits` 里留下原因 |
| 讲得清吗 | `term_consistency` 揭出同义异形（`dataset` / `data set`），只报不改，是否统一由作者定 |

## 什么时候用 / 不用

**用**：改语法、去口语、压冗词、查术语一致性；投稿前的最后一轮语言清理。

**不用**：重写论证结构；改技术内容；把英式改成美式这类风格偏好（不在本 Skill 判定范围）。

## 怎么调用

```
python run.py --topic 05-polish
```

## 输入

`case.json`、`task.md`、文献文件（PDF / DOCX / MD / TXT / TEX）。

## 输出

`result.json` 七键。`result` 主要字段：

`edits`（每条含 `sentence_id`/`before`/`after`/`rule`/`why`/`preserved`/`page`）`edit_count` `rejected_edits`（含 `reason`）`sentence_count` `style_profile`（`mean_sentence_words`/`over_45_words`/`passive_per_1000_words`/`informal_sentence_ids`/`first_person_mentions`）`term_consistency`（`variants`/`counts`）`edit_rules`（规则表清单）`polished_text` `markdown` `page_map` `summary`

## 交给执行方的委托（`delegate_*`）

本题只找「该改的地方」并逐条核验，不替你重写全文。三个键把已核验的编辑变成可直接执行的指令：

| 键 | 内容 |
| --- | --- |
| `delegate_prompt` | 完整提示词：每条编辑的页码、原文、改后文本与依据；要求只应用列出的编辑、保留原句可回溯性、数字与引用编号不得改变 |
| `deliverable_contract` | 期望的回包形状 `{"polished_text": "……", "skipped": [...]}` |
| `delegate_budget` | `1` 次模型请求 |

本 Skill 自身不调用模型。回包写回 `result.delivered_text`；某处编辑应用后会改变数值或否定，提示词要求跳过并记入 `skipped`。

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

从 `case.json` 结构性发现契约键（12 别名），字段名归一化最长匹配；匹配不上写 `{"value": null, "state": "not_reported"}` 并登记 `uncertainty`。

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

1. 抽正文、切页、去页眉页脚。
2. 句子切分；`_tabular()` 与 `TABLE_ROW`（连续四个以上数字/分隔符）判为表格行，直接跳过——对表格做润色必然改错。
3. `_prose()` 判定是否自然语言（≥8 词、字母占比 ≥60%、含系动词或代词）；机械类规则只作用于自然语言，避免在图表碎片上误改。
4. 逐条 `RULES` 匹配并试改。
5. 每条试改过 `preserves()`：数字列表、否定词数、比较级词表、专名集合四项逐一比对。任一不等 → 进 `rejected_edits` 并写明哪一轴被破坏。
6. `REPEATABLE` 与 `.isdigit()` 双重排除，防止把 `20 20`、`2n 2n` 当重复词删掉。
7. `_style_profile()` 只做计数，不输出「文风评分」。
8. `TERM_VARIANTS` 做一致性扫描，只报不改。

## 异常处理

| 情况 | 行为 |
|---|---|
| 材料无法读取 | 按实际原因分别报告，不合并成一句「读取失败」。`unreadable_input = {file, code, reason}`，`code` 取 `encrypted`（有打开密码）/ `no_text_layer`（可开但无文字层，需 OCR）/ `not_a_pdf`（扩展名与内容不符）/ `damaged`（交叉引用表损坏）/ `backend_missing` / `backend_failed` / `extract_failed` 之一；此时 `status=cannot_determine`，`uncertainty` 同步写明该文件与下一步需要什么 |
| 未映射字符（连字、自定义编码、图片化字形） | 计入 `unmapped_char_count`；同时报 `unmapped_char_share`（占全文比例）。绝对值超 `max(20, 全文/2000)` 或占比超 `0.002` 即降级为 `partial` 并记 `state=uncertain`；不猜测替换，损坏字符原样保留 |
| 句子为 0 | `status=cannot_determine` |
| 修改会破坏语义保持 | 不应用，进 `rejected_edits`，`status` 降 `partial` |
| 术语变体冲突 | 只报不自动统一，避免擅自改术语 |
| 材料主要为表格/公式 | `_prose()` 全 false，`edit_count=0` 并说明材料不含可润色散文 |
| 运行抛异常 | 捕获后仍写 `result.json` |

## 自检输出（`result.self_check`）

每次运行都会在 `result` 里附一块本机实测的审计，用于替代「本 Skill 效果很好」这类无法核对的说法。
它不是自评分数，是可以在同一份输出里复核的数：

| 轴 | 字段 | 读法 |
|---|---|---|
| 契约完成度 | `completion.ratio` | 契约要求的字段填了几个；填不出就登记，不编造 |
| 可核验性 | `verifiability` | 每条编辑的改前/改后是否都能在文本里找到；数值数量是否保持不变 |
| 覆盖率 | `coverage` | 原文有 13 页 / 3 处编辑（示例件）；本 Skill 报了几项 |
| 正确性 | `correctness.measured` | 恒为 `false`：本机没有评分方答案，正确性不自评 |
| 成本 | `cost` | 实际耗时、模型请求数、预算余量、每秒处理词数 |

`verifiability` 同时给出样本量（`quotes_checked` / `numbers_checked` / `anchored`），
避免「三 个字段 100%」被读成「三百个字段 100%」。比率字段在没有样本时为 `null`，
不写成 `1.0`。

自检在开发期抓出过真实缺陷：00 的机构名曾把 `Google Brain` 与 `University of Toronto`
粘成 `Google Research University`；08 的引文曾把表格数字串进句子。这类问题人工读结果不易发现，
逐字回查才发现。

## 自查清单

- 每条 `edits[i]` 的 `preserved` 四项全为 true
- `rejected_edits` 里每条都有具体破坏项
- 数字在原句与改句完全一致（数量、量级、单位）
- 否定词数未被削减
- `status` 与实际完成度一致

- `self_check.axes.verifiability` 里 `quote_unverified` 为空，或每条都写明了为什么定位不到
- `cost.model_requests` 与实际相符（本 Skill 不调用模型，应为 0）
- `rejected_edits` 每条都写了拒绝理由

## 限制

- 只做局部短语级替换，不重写句子结构
- 语义保持是四项启发式校验，不是形式化证明；改写导致的细微语义漂移可能漏检
- 不判断学科惯例（不同领域的时态、被动偏好不同）
- 中文润色规则明显少于英文

## 最小调用示例

```
cd /app/submission
python run.py --topic 05-polish
```

以上为调用示例，结果以实际运行为准，不构成正式结果。
