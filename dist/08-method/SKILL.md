---
name: method-section-audit
description: 把论文的方法与实验章节拆成复现者真正需要的零件——16 个训练设置槽位逐项判定「原文写明」还是「原文未写」，25 步方法流程带上所属章节与页码，数据集、对照基线、评价指标分别成表，再按权重算出可复现性得分并列出缺哪几块。缺失的批大小是结论不是失败：留空并计入缺口的清单，绝不填一个看起来合理的默认值。
---

# 方法与实验章节写作

## 这个 Skill 解决什么

方法章的读者只有一种：想复现的人。本 Skill 按这个人的需求拆材料：

| 追问 | 本 Skill 的处置 |
|---|---|
| 写得全 | 16 个槽位（数据集／划分／批大小／学习率／优化器／动量／权重衰减／epoch／调度／数据增强／初始化／硬件／训练时长／评价指标／对照基线／重复次数）逐项判定 `stated` 或 `not_stated` |
| 写得准 | 每个取值带原文引文；量级记号被文本层吃掉时（`60 ✕ 10⁴` 读成 `60  104`）不报数值，标 `suspect` 并说明理由 |
| 做得着 | 方法步骤带章节与页码，复现者能按顺序照做；顺序线索（first／then／1)／2)）一并记录 |
| 说得住 | 加权算出 `reproducibility.score`（满分 100）与 `missing_slots`，限制条件单独成表 |

## 什么时候用 / 不用

**用**：投稿前自查方法章是否写全；复现他人论文前先摸清哪些参数必须猜；审稿时判断可复现性；把散落在正文、图表题注、附录里的超参汇总成一张表。

**不用**：需要从代码仓库或补充材料里对账（本 Skill 只读本次提供的文献材料）；需要判断方法本身是否正确（只做信息完整性检查，不做科学审查）。

## 怎么调用

```
python run.py --topic 08-method
```

本地调试可用 `BSK_INPUT_DIR` / `BSK_OUTPUT_DIR` / `BSK_WORK_DIR` 覆盖路径。

## 输入

- `case.json`（含 `case_id`，可能含 `output_contract`）
- `task.md`
- 文献材料：PDF / DOCX / HTML / Markdown / TXT

方法章按标题识别；当章节名不含 `method`／`approach`／`architecture` 等词（例如叫 `3 Deep Residual Learning`）时，退化为「所有非框架章、非实验章」——否则会把方法步骤全部漏掉。

## 输出

`result.json` 固定七键：`case_id` / `status` / `result` / `evidence` / `sources` / `uncertainty` / `changes` / `notes`。

`result` 主要字段：

| 字段 | 内容 |
|---|---|
| `settings` | 16 槽逐项 `{slot, state, values, quotes, suspect}`，`state ∈ stated / not_stated` |
| `setting_count` | 已写明的槽位数 |
| `reproducibility` | `{score, max_score, weighted_earned, weighted_total, missing_slots, checklist_version, note, assumption}` |
| `method_steps` | `{index, text, section, page, order_cue}`，`step_count` 为条数 |
| `datasets` | 数据集名列表（含划分信息时附在 `dataset_use`） |
| `baselines` | 对照方法名与其所在页 |
| `metrics` | 评价指标名（`top-1` / `top-5` / `mAP` / `IoU` / `accuracy` …） |
| `limitations` | 原文自陈的限制与未来工作句 |
| `checklist` | 复现者要填的空表与 `blank_fields` |
| `page_map` / `quotes` / `summary` / `run` | 自动填充的定位与摘要 |

权重（总 120，归一化到 100）：dataset 15, split 10, batch-size 10, learning-rate 10, optimizer 8, momentum 5, weight-decay 5, epochs 8, schedule 6, augmentation 6, initialization 5, hardware 6, training-time 3, metric 10, baseline 8, repetition 5。

## 交给执行方的委托（`delegate_*`）

本题只抽取参数、步骤与缺项，不代写章节。三个键把抽取结果变成可直接执行的指令：

| 键 | 内容 |
| --- | --- |
| `delegate_prompt` | 完整提示词：参数逐项状态（已给出 / 原文未写明 / 不适用）、方法步骤原文与页码、数据集与对照 |
| `deliverable_contract` | 期望的回包形状 `{"method": "……", "experiments": "……", "missing_for_reproduction": [...]}` |
| `delegate_budget` | `1` 次模型请求 |

本 Skill 自身不调用模型。**「原文未写明」的项在提示词里明确禁止补默认值**，只能写进 `missing_for_reproduction`。回包写回 `result.delivered_text`。

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

1. **选章节**（`_method_rows`）：先试方法章词表；命中为空则取所有非框架章（排除 abstract／introduction／related work／references／acknowledg／appendix），保证方法散落在命名不规范的章节时仍能取到。
2. **扫槽位**（`_settings`）：每槽一个正则族。调度槽认 `divided by 10 when the error plateaus`、`drop the learning rate` 这类非常规写法；重复次数槽认 `we run it 5 times`、`mean±std`、`best (mean±std)`；硬件槽认 `one/two/four/eight GPUs`。
3. **取值清洗**（`_clean_value`）：剥掉尾部 `.,;:)]`，`0.9.` → `0.9`。
4. **量级防伪**（`_mangled_magnitude`）：数值前 14 字符内出现 `×`／`·`／`^`／`*`／`±`／`~` 或被替换字符（U+FFFD）时，判定为「乘号或幂次记号未进文本层」，不报数值，标 `suspect=True` 并保留引文。宁可报缺，不可报错。
5. **算分**（`_reproducibility`）：按权重累加已写明槽位，归一化到 100，输出 `missing_slots`。
6. **抽步骤**（`_steps`）：从方法章抽含施动者的步骤句，`offset` 经 `_section_at` 换算最深章节、经页码表换算页码；`order_cue` 记录 first／then／next／finally／1)／2)。
7. **抽实体**：`_dataset_use`／`_baselines`／`_metrics`／`_limitations`。指标分两趟匹配——`\b(?:mAP|IoU|MAP)\b` 大小写敏感单独跑，避免普通词 "map" 误命中；其余指标（top-1／top-5／error rate／accuracy／BLEU／F1／perplexity）才用忽略大小写。
8. **生成填空表**（`_checklist`）：把未写明的槽位转成复现者需要向作者索取的问题清单。

## 异常处理

| 情况 | 行为 |
|---|---|
| 材料无法读取 | 按实际原因分别报告，不合并成一句「读取失败」。`unreadable_input = {file, code, reason}`，`code` 取 `encrypted`（有打开密码）/ `no_text_layer`（可开但无文字层，需 OCR）/ `not_a_pdf`（扩展名与内容不符）/ `damaged`（交叉引用表损坏）/ `backend_missing` / `backend_failed` / `extract_failed` 之一；此时 `status=cannot_determine`，`uncertainty` 同步写明该文件与下一步需要什么 |
| 未映射字符（连字、自定义编码、图片化字形） | 计入 `unmapped_char_count`；同时报 `unmapped_char_share`（占全文比例）。绝对值超 `max(20, 全文/2000)` 或占比超 `0.002` 即降级为 `partial` 并记 `state=uncertain`；不猜测替换，损坏字符原样保留 |
| 章节名不规范（`3 Deep Residual Learning`） | 退化为「非框架非实验章」，并在 `notes` 记录该决策 |
| 数值量级记号被吃掉（`60  104` 实为 60×10⁴） | `value=null`，`suspect=True`，`uncertainty` 说明「原文给出但量级记号未被文本层保留」，附引文 |
| 训练时长全文未写 | 计为 `not_stated` 并进 `missing_slots`，不按同类论文的常见值填充 |
| 找不到方法章 | `step_count=0`，记 gap，不把引言当方法 |
| 数据集名与普通名词同形（`map`） | 大小写敏感单独匹配，避免误收 |
| 抽取后端非首选 | `notes` 记录实际后端名，供审计 |
| 运行抛异常 | 捕获后仍写 `result.json`，保留已完成部分与异常类型 |

## 自检输出（`result.self_check`）

每次运行都会在 `result` 里附一块本机实测的审计，用于替代「本 Skill 效果很好」这类无法核对的说法。
它不是自评分数，是可以在同一份输出里复核的数：

| 轴 | 字段 | 读法 |
|---|---|---|
| 契约完成度 | `completion.ratio` | 契约要求的字段填了几个；填不出就登记，不编造 |
| 可核验性 | `verifiability` | 超参值的引文是否逐字来自原文；数据集名是否原样出现 |
| 覆盖率 | `coverage` | 原文有 13 页 / 16 个复现槽位（示例件）；本 Skill 报了几项 |
| 正确性 | `correctness.measured` | 恒为 `false`：本机没有评分方答案，正确性不自评 |
| 成本 | `cost` | 实际耗时、模型请求数、预算余量、每秒处理词数 |

`verifiability` 同时给出样本量（`quotes_checked` / `numbers_checked` / `anchored`），
避免「十六 个字段 100%」被读成「三百个字段 100%」。比率字段在没有样本时为 `null`，
不写成 `1.0`。

自检在开发期抓出过真实缺陷：00 的机构名曾把 `Google Brain` 与 `University of Toronto`
粘成 `Google Research University`；08 的引文曾把表格数字串进句子。这类问题人工读结果不易发现，
逐字回查才发现。

## 自查清单

- `result.json` 含 `case_id` 且与输入一致
- 每个 `stated` 槽位都有 `quotes` 与页码，可回原文核对
- `suspect=True` 的项确实没有报出可能错误的数值
- `reproducibility.score` 可由 `settings` 的状态与权重表复算
- `missing_slots` 里的每一项在 `checklist.blank_fields` 都有对应的索取问题
- `status` 与实际完成度一致（有 `not_stated` 槽位时不是 `success`）

- `self_check.axes.verifiability` 里 `quote_unverified` 为空，或每条都写明了为什么定位不到
- `cost.model_requests` 与实际相符（本 Skill 不调用模型，应为 0）
- `not_applicable` 与 `not_reported` 分开：前者是该项不适用，后者是论文没写

## 限制

- 只读本次提供的材料，不查代码仓库、补充材料或论文附带配置
- 只做信息完整性检查，不判断方法正确性、实验设计是否公平
- 槽位词表以深度学习／视觉类论文为主，其他领域的超参命名可能漏检
- 步骤抽取依赖施动者与顺序线索，纯公式推导不算步骤
- 「原文未写」是结论而非失败；本 Skill 从不填入默认值

## 最小调用示例

```
cd /app/submission
python run.py --topic 08-method
# 产出 /app/output/result.json
```

以上为调用示例，结果以实际运行为准，不构成正式结果。
