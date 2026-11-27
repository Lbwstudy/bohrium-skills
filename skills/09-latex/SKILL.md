---
name: latex-build
description: 双入口的 LaTeX 交付工具——输入是坏掉的 .tex/.bib 时做定点修复（只转义必须转义的字符、跳过数学环境与 tabular 对齐符），输入是 PDF 时生成可编译的完整 .tex 工程；两种情况都给出行号级的 lint（未转义字符、括号失衡、环境未闭合、未定义 \ref 与 \cite、缺宏包）、宏包需求清单与可重复构建命令。编译不了就如实报 static-only，不把静态检查冒充编译通过。
---

# LaTeX 写作与编译

## 这个 Skill 解决什么

LaTeX 的问题分两类：源文件本身有错，和根本没有源文件。本 Skill 两条路都走：

| 追问 | 本 Skill 的处置 |
|---|---|
| 编译得通 | `_lint` 给出**行号级**诊断：未转义 `_`／`&`／`%`／`#`、花括号失衡（记录未闭合的开括号行号）、`\begin` 未闭合、未定义 `\ref`、未定义 `\cite`、缺失宏包。每条都能定位到具体文件与行，而不是停在「Undefined control sequence」 |
| 改得对 | `_autofix` 只改必须改的：文本参数里的 `_`／`&`／`%` 转义，**数学环境内与 `\ref`／`\cite`／`\label` 内跳过**，tabular 的 `&` 保持原样 |
| 交得可用 | 产出的是可编译的 `.tex`（PDF 入路）或修好的源文件（源文件入路），不是截图或片段；`structure_mapping` 逐条给出「章节标题 → 用的命令 → 在 tex 里的行号 → 原始页码」 |
| 复现得了 | `package_requirements` 给出 loaded／needed／missing 三列表；`reproduce_commands` 给本地 latexmk、Overleaf、清理、验证四条命令；`compile_result` 如实报是否真编译过 |

## 什么时候用 / 不用

**用**：投稿前跑一遍源文件找编译隐患；把 PDF 论文转成可编辑的 LaTeX 工程；接手他人的 `.tex` 与 `.bib` 对账引用；定位「第一条报错之后的连带报错」。

**不用**：需要排版级精修（字体、间距、模板微调）；需要真正的 PDF 视觉比对（本 Skill 只在环境有 TeX 时真编译，否则明确报 `static-only`）。

## 怎么调用

```
python run.py --topic 09-latex
```

本地调试可用 `BSK_INPUT_DIR` / `BSK_OUTPUT_DIR` / `BSK_WORK_DIR` 覆盖路径。

## 输入

- `case.json`（含 `case_id`，可能含 `output_contract`）
- `task.md`
- 二选一：`.tex`（可带 `.bib`）或 PDF／DOCX／HTML／Markdown／TXT

入路自动判定：材料里有 `.tex`／`.latex`／`.bib` 走**修复路径**，否则走**生成路径**。

## 输出

`result.json` 固定七键：`case_id` / `status` / `result` / `evidence` / `sources` / `uncertainty` / `changes` / `notes`。

`result` 主要字段：

| 字段 | 内容 |
|---|---|
| `latex_file` / `latex_source` | 生成或修复后的主文件名与全文 |
| `structure_mapping` | `{heading, level, command, tex_line, source_page}` 逐条 |
| `lint_issues` | `{issues[], packages{loaded,needed,missing}, ...}`；`lint_issue_count` 为条数 |
| `package_requirements` | `{loaded, needed, missing}` |
| `compile_result` | `{compiled, checked, reason, note}`；`checked ∈ full / static-only` |
| `reproduce_commands` | `{local, overleaf, clean, verify}` |
| `page_map` / `quotes` / `summary` / `run` | 自动填充的定位与摘要；生成的 `.tex` 作为 artifact 列出 |

## 交给执行方的委托（`delegate_*`）

本题交付可编译的骨架与逐行章节映射，不代写正文。三个键把骨架变成可直接执行的指令：

| 键 | 内容 |
| --- | --- |
| `delegate_prompt` | 完整提示词：`structure_mapping` 的逐行清单（LaTeX 行号、章节命令、标题、层级、原文页码）、转义规则、宏包与表格约定 |
| `deliverable_contract` | 期望的回包形状 `{"latex_source": "……"}`（完整文件内容） |
| `delegate_budget` | `1` 次模型请求 |

本 Skill 自身不调用模型。提示词要求不新增宏包、特殊字符按 `SPECIALS` 转义（反斜杠写 `\textbackslash{}`）、公式保留编号、表格用 `booktabs`。回包写回 `result.delivered_text` 后可再走一遍 `compile_result`。

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

### 修复路径（`_repair`）

1. **分类行**：`SYNTAX`（`\begin` `\end` `\usepackage` `\documentclass` `\newcommand` `\label` `\ref` `\eqref` `\cite` `\includegraphics` `\input` `\bibliography` `\url` `\href` …）整行跳过；`TEXT_ARG`（`\title` `\author` `\section` `\caption` `\footnote` `\item` …）只处理第一个花括号参数。
2. **数学保护**（`_math_span_end`）：遇到 `$` 整段跳到配对处，数学里的 `_` 与 `^` 一律不转义。
3. **tabular 保护**：维护 `in_tabular` 状态，`&` 是对齐符不是待转义字符。
4. **定点转义**（`_escape_line`）：只转义 `&` `%` `#` `_` 四个真会炸的字符；`\` 已由分类跳过。
5. **诊断**（`_lint`）：未转义 specials、花括号平衡（含未闭合开括号的行号）、环境未闭合、`\ref` 目标是否存在、`\cite` key 是否在 `.bib` 里。lint 自身也过一遍 `_strip_math` 与 `_in_tabular`，避免把保护好的内容报成错。
6. **对账**（`_bib_keys`／`_cross_check`）：`.bib` 的 key 集合与 `\cite` 需求集合求差，未定义引用的 key 直接列出。

### 生成路径（`_build_tex`）

1. 从 `structure` 层取 chapter 目录与正文，按层级映射成 `\section`／`\subsection`／`\subsubsection`，记 `tex_line` 与原始页码。
2. 正文逐段转义（同上的保护规则），公式段转成 `equation` 环境。
3. 参考文献用 `thebibliography` 内联，避免依赖缺失的 `.bst`。
4. 按正文实际用到的命令推导宏包集（`_required_packages`），与 `BASE_PACKAGES` 合并后写进导言区。

### 共同

7. **真编译**（`_compile`）：用 `tempfile.TemporaryDirectory` 隔离工作目录，按 `latexmk` → `pdflatex` 顺序真跑；两者都不在 PATH 时**如实**返回 `{"compiled": false, "checked": "static-only"}`，不把静态检查说成编译通过。
8. **给命令**（`_commands`）：`latexmk -pdf`、Overleaf 操作步骤、`latexmk -C` 清理、编译后查 `paper.log` 里 `There were undefined references` 的验证命令。

## 异常处理

| 情况 | 行为 |
|---|---|
| 材料无法读取 | 按实际原因分别报告，不合并成一句「读取失败」。`unreadable_input = {file, code, reason}`，`code` 取 `encrypted`（有打开密码）/ `no_text_layer`（可开但无文字层，需 OCR）/ `not_a_pdf`（扩展名与内容不符）/ `damaged`（交叉引用表损坏）/ `backend_missing` / `backend_failed` / `extract_failed` 之一；此时 `status=cannot_determine`，`uncertainty` 同步写明该文件与下一步需要什么 |
| 未映射字符（连字、自定义编码、图片化字形） | 计入 `unmapped_char_count`；同时报 `unmapped_char_share`（占全文比例）。绝对值超 `max(20, 全文/2000)` 或占比超 `0.002` 即降级为 `partial` 并记 `state=uncertain`；不猜测替换，损坏字符原样保留 |
| 环境无 TeX 发行版 | `compile_result.checked="static-only"`，`compiled=false`，`reason` 写明缺 latexmk 与 pdflatex；不声称编译通过 |
| 缺宏包 | `package_requirements.missing` 列出，并在 `uncertainty` 记「需安装后编译才能确认」 |
| 缺字体 | 同上，进 `missing`；模板类文件缺失时记「需模板文件就位后才能编译」 |
| 报错级联 | lint 一次列出全部问题并各带行号，不模拟 TeX 的「首错即停」 |
| 未定义 `\ref` / `\cite` | 分别列出目标名与所在行，指明是标签缺失还是引用 key 在 `.bib` 里不存在 |
| 权限不足无法写临时目录 | 捕获异常，保留已完成诊断，`notes` 说明写入失败位置 |
| 运行抛异常 | 捕获后仍写 `result.json`，保留已完成部分与异常类型 |

## 自检输出（`result.self_check`）

每次运行都会在 `result` 里附一块本机实测的审计，用于替代「本 Skill 效果很好」这类无法核对的说法。
它不是自评分数，是可以在同一份输出里复核的数：

| 轴 | 字段 | 读法 |
|---|---|---|
| 契约完成度 | `completion.ratio` | 契约要求的字段填了几个；填不出就登记，不编造 |
| 可核验性 | `verifiability` | 结构映射的每一条是否指向原文的真实章节；编译日志是否原样回传 |
| 覆盖率 | `coverage` | 原文有 13 页 / 12 条结构映射（示例件）；本 Skill 报了几项 |
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
- 每条 `lint_issues.issues[i]` 都带行号与问题类型
- 数学环境内与 tabular 内的字符没有被误转义（抽查 `$a_b$` 与 `a & b \\` 两处）
- `compile_result.checked` 如实反映是否真编译过
- `structure_mapping` 的 `tex_line` 能在 `latex_source` 对应行找到该标题
- `status` 与实际完成度一致（`static-only` 时不是 `success`）

- `self_check.axes.verifiability` 里 `quote_unverified` 为空，或每条都写明了为什么定位不到
- `cost.model_requests` 与实际相符（本 Skill 不调用模型，应为 0）
- `compile_result.checked` 是 `real-build` 还是 `static-only`，二者不能混说

## 限制

- 只在环境提供 `latexmk` 或 `pdflatex` 时真编译；否则为静态检查
- 不做视觉比对与排版微调
- 公式只做转义与结构搬移，不还原复杂公式的原始写法
- 生成路径产出的是可编译骨架，不是原论文的排版复刻
- `\newcommand` 定义的宏不展开分析，自定义宏内部的特殊字符需人工复核

## 最小调用示例

```
cd /app/submission
python run.py --topic 09-latex
# 产出 /app/output/result.json（生成路径还会写出 paper.tex）
```

以上为调用示例，结果以实际运行为准，不构成正式结果。
