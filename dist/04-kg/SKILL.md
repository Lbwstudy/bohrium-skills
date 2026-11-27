---
name: paper-knowledge-graph
description: 从论文构建可查询的实体关系图谱——五类实体（指标/数据集/方法/任务/架构）、七类带家族白名单的关系、别名归并，并附至少三个真实查询（结果子图＋支撑证据＋无法确定的关系）。用于「抽得准、连得对、对得齐、查得到回得去」的知识图谱任务。
---

# 文献知识图谱构建

## 这个 Skill 解决什么

自动抽取的图谱最容易出两类假边：自反边（VGG 与 VGG-19 互指）和非法边（指标包含数据集）。本 Skill 用家族白名单和长标签优先匹配把这两类按死。

| 追问 | 本 Skill 的处置 |
|---|---|
| 抽得准吗 | 五类实体的封闭词表 + 别名归一（`ResNet-50` / `resnet 50` / `ResNet50` 合一） |
| 连得对吗 | 七类关系各带 `(from_family, to_family)` 白名单，家族不匹配不建边；同句实体按 label 长度降序匹配并遮蔽已占用 span，短标签抢不到长标签的位置 |
| 对得齐吗 | `alias_table` 明示哪些标签被并到一个节点，合并是记录在案的动作而非隐式 |
| 查得到回得去吗 | 四个内置查询各自输出 `answer` + `subgraph` + `evidence[{page, quote}]` + `uncertain[]` |

## 什么时候用 / 不用

**用**：从一篇或几篇论文建可查的关系图谱；为文献调研找「谁在哪个数据集上比谁好」。

**不用**：需要跨论文大规模对齐（本 Skill 单篇内工作）；需要实体消歧到外部知识库（如 Wikidata）。

## 怎么调用

```
python run.py --topic 04-kg
```

## 输入

`case.json`、`task.md`、文献文件（可多篇）。

## 输出

`result.json` 七键。`result` 主要字段：

`nodes`（含 `id`/`label`/`family`/`mentions`/`pages`）`node_count` `edges`（含 `source`/`target`/`relation`/`page`/`quote`）`edge_count` `alias_table`（合并组）`graph_format`（实体家族与关系白名单定义）`queries`（查询定义）`query_results`（每个查询的 `method`/`answer`/`subgraph`/`evidence`/`uncertain`）`query_count` `unresolved_relations`（抽到动词但没建成边的句子，**显式列出而不是丢掉**）`markdown` `page_map` `summary`

四个内置查询：`_q_datasets`（数据集及其证据页）、`_q_improvements`（谁优于谁，附原句）、`_q_methods_by_task`（方法服务哪个任务）、`_q_evidence_for`（高频实体出现在哪些章节）。

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
2. 实体识别：按 `FAMILIES` 五类词表匹配；`_build_alias_index()` 用 `re.sub(r"[^a-z0-9]", "", alias)` 归一所有别名，`_key()` 得到稳定节点 id。
3. 句内实体匹配：**按 label 长度降序**遍历，命中后用 `"\0" * len(label)` 遮蔽该 span。这一步是自反边的唯一有效解法——按长度升序匹配时 `VGG` 会先占住 `VGG-16` 的位置。
4. 关系抽取：`RELATION_RULES` 七类，每条带 `allowed` 的家族对白名单；同句内家族匹配的实体对才连边。
5. 边去重：`(source, target, relation)` 三元唯一，同一边在多句出现时保留首个页码并在 `mentions` 累加。
6. `_unresolved()` 收集命中关系动词却未能建边的句子，附原因（家族不匹配 / 实体缺失）。
7. 查询执行：四个函数各自遍历节点与边，返回子图与证据，无法确定的进 `uncertain`。

## 异常处理

| 情况 | 行为 |
|---|---|
| 材料无法读取 | 按实际原因分别报告，不合并成一句「读取失败」。`unreadable_input = {file, code, reason}`，`code` 取 `encrypted`（有打开密码）/ `no_text_layer`（可开但无文字层，需 OCR）/ `not_a_pdf`（扩展名与内容不符）/ `damaged`（交叉引用表损坏）/ `backend_missing` / `backend_failed` / `extract_failed` 之一；此时 `status=cannot_determine`，`uncertainty` 同步写明该文件与下一步需要什么 |
| 未映射字符（连字、自定义编码、图片化字形） | 计入 `unmapped_char_count`；同时报 `unmapped_char_share`（占全文比例）。绝对值超 `max(20, 全文/2000)` 或占比超 `0.002` 即降级为 `partial` 并记 `state=uncertain`；不猜测替换，损坏字符原样保留 |
| 实体为 0 | `status=cannot_determine`，说明可能材料不是实验类论文 |
| 边为 0 但节点 > 0 | 如实报，`unresolved_relations` 说明关系词未命中或家族不匹配 |
| 别名合并冲突 | 记录在 `alias_table`，不静默丢弃 |
| 查询结果为空 | 每个查询的 `answer` 写「本图谱内未找到」，不返回空对象 |
| 运行抛异常 | 捕获后仍写 `result.json` |

## 自检输出（`result.self_check`）

每次运行都会在 `result` 里附一块本机实测的审计，用于替代「本 Skill 效果很好」这类无法核对的说法。
它不是自评分数，是可以在同一份输出里复核的数：

| 轴 | 字段 | 读法 |
|---|---|---|
| 契约完成度 | `completion.ratio` | 契约要求的字段填了几个；填不出就登记，不编造 |
| 可核验性 | `verifiability` | 实体的首次出现位置与引文是否真实；每条关系的证据是否指向真实句子 |
| 覆盖率 | `coverage` | 原文有 13 页 / 41 实体 / 62 关系（示例件）；本 Skill 报了几项 |
| 正确性 | `correctness.measured` | 恒为 `false`：本机没有评分方答案，正确性不自评 |
| 成本 | `cost` | 实际耗时、模型请求数、预算余量、每秒处理词数 |

`verifiability` 同时给出样本量（`quotes_checked` / `numbers_checked` / `anchored`），
避免「四十一 个字段 100%」被读成「三百个字段 100%」。比率字段在没有样本时为 `null`，
不写成 `1.0`。

自检在开发期抓出过真实缺陷：00 的机构名曾把 `Google Brain` 与 `University of Toronto`
粘成 `Google Research University`；08 的引文曾把表格数字串进句子。这类问题人工读结果不易发现，
逐字回查才发现。

## 自查清单

- 无自反边（`source != target`）
- 每条边的关系在其家族的 `allowed` 白名单内
- 每个节点至少一条 `mentions`，能追回原文
- 四个查询都有 `answer`、`subgraph`、`evidence`、`uncertain` 四段
- 被合并的别名都在 `alias_table` 里有记录

- `self_check.axes.verifiability` 里 `quote_unverified` 为空，或每条都写明了为什么定位不到
- `cost.model_requests` 与实际相符（本 Skill 不调用模型，应为 0）
- 每个查询的 `evidence` 里都是原文句子，不是说明文字

## 限制

- 实体词表封闭，跨领域新术语需扩展 `FAMILIES`
- 关系只在单句内建边，跨句推理（前提在前文、结论在后文）不覆盖
- 不做实体消歧到外部知识库
- 数值比较不做大小判断，只记「优于」这一关系

## 最小调用示例

```
cd /app/submission
python run.py --topic 04-kg
```

以上为调用示例，结果以实际运行为准，不构成正式结果。
