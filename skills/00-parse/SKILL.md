---
name: document-parse
description: 把学术 PDF 还原成可核验的结构化骨架（标题、作者、摘要、章节层级、图表题注、公式、参考文献、页码映射），每个结果都带页码出处。用于需要「提得全、排得对、拆得清、核得回」的文献解析任务，也作为其他文献类 Skill 的解析底座。
---

# 文献文档解析

## 这个 Skill 解决什么

把一篇学术文献拆成机器可用的结构化结果，并且**每一条都能指回原文位置**。它不理解论文的科学含义，只回答四个问题：

| 追问 | 本 Skill 的处置 |
|---|---|
| 提得全吗 | 正文、图表题注、公式、参考文献、脚注分别抽取，各自计数；抽不到的显式报缺口，不省略 |
| 排得对吗 | 先做跨页重复行剔除（页眉页脚），再按编号序列的单调性校验章节顺序，表格行不会被当成标题 |
| 拆得清吗 | 章节按 `1 / 1.1 / 1.1.1` 推出层级；图、表、公式、参考文献各自结构化，不混进正文 |
| 核得回吗 | 每条记录带页码；引文用逐字定位，定位不到就降级标注，不假装找到 |

## 什么时候用 / 不用

**用**：给一篇（或几篇）PDF、DOCX、Markdown 论文做结构化抽取；要建索引；要给下游写作/翻译/综述提供干净的输入。

**不用**：需要判断论文结论对不对（那是审稿，不是解析）；需要重排双栏版面像素（那是渲染工具的事）。

## 怎么调用

平台侧入口固定：`/input/case.json` 与 `/input/task.md` 进，`/app/output/result.json` 出。

```
python run.py --topic 00-parse
```

可用环境变量覆盖路径（本地调试用）：`BSK_INPUT_DIR`、`BSK_OUTPUT_DIR`、`BSK_WORK_DIR`。

## 输入

- `case.json`：含 `case_id`，可能含 `output_contract`（字段名由平台决定，形状不公开）
- `task.md`：本题的自然语言要求
- 同目录下的文献文件：PDF / DOCX / HTML / Markdown / TXT / JSON

## 输出

`result.json` 固定含：

| 键 | 含义 |
|---|---|
| `case_id` | 原样回传 |
| `status` | `success` / `partial` / `cannot_determine` / `refusal` |
| `result` | 主结果，含本题字段 + `run` 运行信息 |
| `evidence` | 每条结论的定位（页码、段落、字符位置） |
| `sources` | 用到的材料清单 |
| `uncertainty` | 未报告项、不确定项及原因 |
| `changes` | 修改记录（本题通常为空） |
| `notes` | 运行说明与限制 |

`result` 里主要字段：

`title` `authors` `affiliations` `doi` `arxiv_id` `abstract` `sections`（含 `heading`/`level`/`page`/`chars`/`words`）`figures` `tables` `equations` `references`（含 `index`/`text`/`page`）`page_count` `document_stats` `unmapped_char_count` `layout_probe` `extraction_backend`

## 契约字段怎么填

平台的 `output_contract` 形状不固定。本 Skill 不猜它的结构，而是在运行时：

1. 从 `case.json` 里结构性搜索契约键（`output_contract` / `result_contract` / `expected_output` / `output_fields` 等 12 个别名，含嵌套 JSON-Schema `properties`）；
2. 取其字段名列表；
3. 逐名做归一化匹配（去掉大小写与分隔符后最长匹配）到**已抽出的真实内容**；
4. 匹配不上的，写 `{"value": null, "state": "not_reported", ...}` 并登记到 `uncertainty`。

所以 `summary`、`quotes`、`page_map` 这类没预料到的字段名也能拿到材料支撑的答案；确实没有依据的字段宁可留空。

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

1. **抽取后端链**：`pdf-text-tool`（平台首选）→ `pdftotext`（原始模式优先，避免 `-layout` 把双栏压平）→ `pymupdf` → `pypdf` → 内置纯 stdlib 解析器。实际用到的后端写进 `extraction_backend`，供审计。
2. **页分割**：按 `\f` 切页，失败时回退页脚页码正则。
3. **页眉页脚剔除**：统计每页首尾两行，跨页重复率 ≥50% 的短行判为 running head。
4. **标题与作者**：候选行按大写词比例、长度、是否有冒号问号打分；作者行（≥3 个人名，或 ≥2 人名带逗号，或「人名+机构」）不参与标题竞争；机构名不当人名。
5. **章节**：`SECTION_RE` 取编号标题，`BARE_SECTION_RE` 取无编号标准标题；再用**状态机单调性校验**（当前顶级编号只能延续或 +1，子标题必须挂在当前顶级下）剔除表格行。
6. **图表公式**：题注正则取标签与题注文本，带偏移量以便换算页码。
7. **参考文献**：从 References 段落起，按 `[n]` 标记切条目。
8. **可核验性**：结构字段的锚点是「从版式读出」；摘要等引文类字段做逐字定位，失败即降级。

## 异常处理

| 情况 | 行为 |
|---|---|
| 材料无法读取 | 按实际原因分别报告，不合并成一句「读取失败」。`unreadable_input = {file, code, reason}`，`code` 取 `encrypted`（有打开密码）/ `no_text_layer`（可开但无文字层，需 OCR）/ `not_a_pdf`（扩展名与内容不符）/ `damaged`（交叉引用表损坏）/ `backend_missing` / `backend_failed` / `extract_failed` 之一；此时 `status=cannot_determine`，`uncertainty` 同步写明该文件与下一步需要什么 |
| 抽取后端全失败 | 同上，且 `extraction_backend` 记录为 `none` |
| 未映射字符（连字、自定义编码、图片化字形） | 计入 `unmapped_char_count`；同时报 `unmapped_char_share`（占全文比例）。绝对值超 `max(20, 全文/2000)` 或占比超 `0.002` 即降级为 `partial` 并记 `state=uncertain`；不猜测替换，损坏字符原样保留 |
| 章节识别为空 | 报 `not_reported`，不伪造层级 |
| 单条引文定位失败 | 值仍记录，标 `unverified`，整体降级为 `partial` |
| 运行抛异常 | 捕获后仍写 `result.json`，把已完成部分与异常类型一并留下 |

## 自检输出（`result.self_check`）

每次运行都会在 `result` 里附一块本机实测的审计，用于替代「本 Skill 效果很好」这类无法核对的说法。
它不是自评分数，是可以在同一份输出里复核的数：

| 轴 | 字段 | 读法 |
|---|---|---|
| 契约完成度 | `completion.ratio` | 契约要求的字段填了几个；填不出就登记，不编造 |
| 可核验性 | `verifiability` | 自称引自原文的字段里多少能逐字（或规范化后）在原文找到；数字是否原样出现；每条结论有没有页码锚点 |
| 覆盖率 | `coverage` | 原文有 13 页 / 18 章 / 56 条文献（示例件）；本 Skill 报了几项 |
| 正确性 | `correctness.measured` | 恒为 `false`：本机没有评分方答案，正确性不自评 |
| 成本 | `cost` | 实际耗时、模型请求数、预算余量、每秒处理词数 |

`verifiability` 同时给出样本量（`quotes_checked` / `numbers_checked` / `anchored`），
避免「三 个字段 100%」被读成「三百个字段 100%」。比率字段在没有样本时为 `null`，
不写成 `1.0`。

自检在开发期抓出过真实缺陷：00 的机构名曾把 `Google Brain` 与 `University of Toronto`
粘成 `Google Research University`；08 的引文曾把表格数字串进句子。这类问题人工读结果不易发现，
逐字回查才发现。

## 自查清单

- `result.json` 有 `case_id`，且与输入一致
- 每个结构字段都能在 `evidence` 或 `sources` 找到出处
- 抽不到的字段出现在 `uncertainty`，不是被悄悄省略
- `status` 与实际完成度相符（有缺口就不是 `success`）
- 输入为空/不可读时仍有合法 JSON 输出
- `self_check.axes.verifiability` 里 `quote_unverified` 为空，或每条都写明了为什么定位不到
- `cost.model_requests` 与实际相符（本 Skill 不调用模型，应为 0）
- 机构列表逐条可比，不是整串拼接

## 限制

- 纯文本层无法还原栏数与精确排版；本 Skill 只报告「行内宽间隙」这一线索，不假装测得栏数
- 图表只到题注级别，不含单元格与像素内容
- 公式只识别独立成行且带编号的，行内公式不单独抽取
- 参考文献按 `[n]` 编号切分；纯作者-年份制（无编号）会记为缺口

## 最小调用示例

```
cd /app/submission
python run.py --topic 00-parse
# 产出 /app/output/result.json
```

本地指定输入输出：

```
cd dist/00-parse
BSK_INPUT_DIR=/path/to/input BSK_OUTPUT_DIR=/tmp/out python run.py
```

预期：`status` 为 `success` 或 `partial`；`result.sections` 每项带 `page`，
`result.references` 每项带 `index` 与 `page`，`self_check.axes.verifiability.quote_ratio`
给出本次逐字回查的比例与样本量。

以上为调用示例，结果以实际运行为准，不构成正式结果。

## 资源配置

见 `environment/resources.yaml`。本 Skill 不需要额外下载资源；所有逻辑在随附 Python 文件中，只用标准库。
