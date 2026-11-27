---
name: nanopublication
description: 把论文正文拆成可独立核对的最小科学断言（nanopublication 风格），每条带主语、关系、限定条件、逐字证据与来源元数据，并给出原子性与待复核标记。用于「拆得细、对得上、追得回、读得懂」的断言级拆解任务。
---

# Nanopublication

## 这个 Skill 解决什么

一句论文里常塞着三四个断言，引用时就会失真。本 Skill 把句子拆到不能再拆，并让每条都能单独核对。

| 追问 | 本 Skill 的处置 |
|---|---|
| 拆得细吗 | 按并列谓词、分号、因果连接词切分；**只有当两半各自含动词时才拆**，避免拆出残缺残句 |
| 对得上吗 | 每条断言保留逐字引文，页码与章节由偏移换算，不二次推断 |
| 追得回吗 | `provenance` 记论文标题、DOI、arXiv 编号、源文件名；`evidence` 记引文+页码+章节 |
| 读得懂吗 | 强制给出 `subject`/`relation`/`object` 三元，主体抽不到就标 `needs_review`，不让「它」「本文」混过去 |

## 什么时候用 / 不用

**用**：把论文结论做成可引用、可核对、可入库的断言集合；给知识图谱、事实核查、系统综述提供原料。

**不用**：需要论文级摘要（那是 02 的活）；需要判断断言真假（本 Skill 只做拆解与溯源）。

## 怎么调用

```
python run.py --topic 03-nanopub
```

## 输入

`case.json`、`task.md`、文献文件。

## 输出

`result.json` 七键。`result` 主要字段：

`assertions`（每条含 `assertion_id`/`text`/`subject`/`relation`/`object`/`qualifiers`/`evidence`/`provenance`/`atomicity`/`needs_review`）`assertion_count` `sample_20`（**等距抽样的 20 条样例**）`triples`（`subject`/`predicate`/`object`/`page`）`quality`（见下）`nanopub_format`（字段定义与关系词表）`provenance`（论文级来源）`markdown` `page_map` `summary`

`quality` 字段：`total` / `standalone` / `standalone_ratio` / `with_subject` / `with_relation` / `with_numbers` / `needs_review` / `review_ids` / `relation_histogram`。

关系词表 11 类：`achieves` `proposes` `shows` `outperforms` `reduces` `increases` `causes` `uses` `compares` `differs` `supports`；无法归类记 `unresolved`。

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
2. `NOISE_RE` 剔除 arXiv 页眉、DOI 行、版权声明、预印本声明；开头六词命中文献标题前缀的行一律丢弃——否则第一页页眉会被当成断言。
3. `CLAIM_CUES` 五组正则识别可断言句（达成 / 提出 / 比较 / 指示 / 因果）。
4. `_atomize()` 按 `,` `;` `and` `while` `whereas` 试探切分，只有两半都含动词才采纳，否则保留整句。
5. `_subject()` 先剥 1–2 层前置从句（`Solely due to X, we obtain Y` 的 `X` 是状语不是主语），再找名词短语；找不到退到 `we` / `our <noun>`。
6. `_relation()` 按词表匹配；只声称差异不声称因果的（`higher training error`）归 `differs` 而非 `causes`。
7. `_qualifiers()` 抽范围、条件、数据集、指标、模糊限定五类。
8. `_atomicity()` 三条扣分：超过 60 词、含并列谓词、句首回指代词；扣分项进 `needs_review`。
9. `_sample()` 按 `total/20` 等距抽样，避免二十条全落在同一节。

## 异常处理

| 情况 | 行为 |
|---|---|
| 材料无法读取 | 按实际原因分别报告，不合并成一句「读取失败」。`unreadable_input = {file, code, reason}`，`code` 取 `encrypted`（有打开密码）/ `no_text_layer`（可开但无文字层，需 OCR）/ `not_a_pdf`（扩展名与内容不符）/ `damaged`（交叉引用表损坏）/ `backend_missing` / `backend_failed` / `extract_failed` 之一；此时 `status=cannot_determine`，`uncertainty` 同步写明该文件与下一步需要什么 |
| 未映射字符（连字、自定义编码、图片化字形） | 计入 `unmapped_char_count`；同时报 `unmapped_char_share`（占全文比例）。绝对值超 `max(20, 全文/2000)` 或占比超 `0.002` 即降级为 `partial` 并记 `state=uncertain`；不猜测替换，损坏字符原样保留 |
| 断言数 < 20 | 如实报实际条数并降级，说明需换更长材料，不重复填充凑数 |
| 主语抽不到 | `subject` 置 `null`，`needs_review=true`，不填「本文」蒙混 |
| 关系未命中词表 | `relation="unresolved"`，计入 `quality` 分母 |
| 运行抛异常 | 捕获后仍写 `result.json` |

## 自检输出（`result.self_check`）

每次运行都会在 `result` 里附一块本机实测的审计，用于替代「本 Skill 效果很好」这类无法核对的说法。
它不是自评分数，是可以在同一份输出里复核的数：

| 轴 | 字段 | 读法 |
|---|---|---|
| 契约完成度 | `completion.ratio` | 契约要求的字段填了几个；填不出就登记，不编造 |
| 可核验性 | `verifiability` | 断言三元组的主语/关系/宾语是否都取自原句；每条断言的引文能否定位 |
| 覆盖率 | `coverage` | 原文有 13 页 / 71 条断言（示例件）；本 Skill 报了几项 |
| 正确性 | `correctness.measured` | 恒为 `false`：本机没有评分方答案，正确性不自评 |
| 成本 | `cost` | 实际耗时、模型请求数、预算余量、每秒处理词数 |

`verifiability` 同时给出样本量（`quotes_checked` / `numbers_checked` / `anchored`），
避免「七十一 个字段 100%」被读成「三百个字段 100%」。比率字段在没有样本时为 `null`，
不写成 `1.0`。

自检在开发期抓出过真实缺陷：00 的机构名曾把 `Google Brain` 与 `University of Toronto`
粘成 `Google Research University`；08 的引文曾把表格数字串进句子。这类问题人工读结果不易发现，
逐字回查才发现。

## 自查清单

- 每条 `evidence.quote` 能在原文逐字找到
- `page` 由偏移换算，与引文位置一致
- `sample_20` 是等距抽样，不是前 20 条
- 主语缺失的条目都在 `review_ids` 里，没有被静默补全

- `self_check.axes.verifiability` 里 `quote_unverified` 为空，或每条都写明了为什么定位不到
- `cost.model_requests` 与实际相符（本 Skill 不调用模型，应为 0）
- `needs_review` 的条目都写明了缺主语还是缺关系

## 限制

- 只按句法线索拆解，不做逻辑推理；一个句子里的隐含前提不会被显式化
- 图表数值不进入断言（只进 `with_numbers` 计数）
- 关系词表是封闭的 11 类，跨领域论文可能需要扩展
- 中文论文的提示词覆盖弱于英文

## 最小调用示例

```
cd /app/submission
python run.py --topic 03-nanopub
```

以上为调用示例，结果以实际运行为准，不构成正式结果。
