# 玻尔 AI 产品周赛 · 郑大分站赛第一期

十个赛题，十份可独立运行的 Skill。主题是 AI 文献阅读与学术写作。

每份作品在 `dist/<题号>/` 下自成一体：`SKILL.md` 说明用途与调用方式，`run.py` 是入口，
`environment/resources.yaml` 声明资源与 I/O，`GITHUB_URL.txt` 指回本目录。

| 目录 | 赛题 | Skill 名 | 做什么 |
|---|---|---|---|
| [dist/00-parse](dist/00-parse) | 文献文档解析 | `document-parse` | 章节层级、图表题注、公式、参考文献，每项带页码 |
| [dist/01-translate](dist/01-translate) | 文献翻译 | `paper-translate` | 术语表驱动，切段并标出不该翻的区域 |
| [dist/02-notes](dist/02-notes) | 文献总结与结构化笔记 | `paper-notes` | 挖句成卡，类型/置信度/出处固定字段 |
| [dist/03-nanopub](dist/03-nanopub) | Nanopublication | `nanopublication` | 断言拆解到原子级，绑证据与限定条件 |
| [dist/04-kg](dist/04-kg) | 文献知识图谱 | `paper-knowledge-graph` | 实体对齐、关系白名单约束、真实查询 |
| [dist/05-polish](dist/05-polish) | 学术语言润色 | `academic-polish` | 每条编辑过语义保持校验，不过就拒绝 |
| [dist/06-cite](dist/06-cite) | 参考文献与引用管理 | `reference-manager` | 条目解析、重编号、去重、GB/T 7714 与 APA |
| [dist/07-intro](dist/07-intro) | 引言与相关工作写作 | `introduce-related-work` | 重建论证骨架，贡献陈述对不上结果就标出 |
| [dist/08-method](dist/08-method) | 方法与实验章节写作 | `method-section-audit` | 复现槽位盘点，缺哪个如实报缺 |
| [dist/09-latex](dist/09-latex) | LaTeX 写作与编译 | `latex-build` | 生成或修复源码，静态检查加真编译 |

## 怎么跑

```bash
cd dist/06-cite
python run.py
```

平台约定：输入在 `/input/case.json` 与 `/input/task.md`，源材料在 `/input/`，
产出写到 `/app/output/result.json`。本地调试用环境变量改路径：

```bash
BSK_INPUT_DIR=/path/to/input BSK_OUTPUT_DIR=/path/to/output python run.py
```

只依赖 Python 3.8+ 标准库。不联网，不调用模型，不读系统时间做判断。同样的输入产出同样
的结果；唯一的差别是 `run.elapsed_seconds` 与 `self_check.axes.cost` 里的三个计时字段，
它们随机器负载变化，已在输出里单独标出（见 `determinism_scope`）。

## 输出形状

`result.json` 固定八个键：

| 键 | 内容 |
|---|---|
| `case_id` | 本次运行的案件标识 |
| `status` | `success` / `partial` / `cannot_determine` / `refusal` |
| `result` | 题目要求的字段，外加契约声明的字段 |
| `evidence` | 每个结论的定位：第几页、哪一段、哪一句 |
| `sources` | 用了哪些输入文件、分工是什么 |
| `uncertainty` | 没做成的项，逐条写原因，不假装成功 |
| `changes` | 对材料做过的修改，改前改后 |
| `notes` | 运行说明与降级理由 |

三类失败分开写：材料缺失、无法判断、运行失败。三者不互相冒充。

### 五道题把「写」交回给执行方

01 翻译 / 05 润色 / 07 引言 / 08 方法 / 09 LaTeX 这五题只做**准备与核验**，不产出成稿：抽出段号与术语表、找出该改的地方并逐条验证、搭出论证骨架并核对每条陈述的支撑、抽齐参数并标出缺项、生成可编译的骨架与逐行章节映射。

成稿本身由执行方生成。为此 `result` 里多了三个键：

| 键 | 内容 |
|---|---|
| `delegate_prompt` | 一条自包含的指令：段号、页码、已固定的译名、已核验的编辑及依据、已定位的证据。材料里没有的东西不会出现在这条指令里 |
| `deliverable_contract` | 期望的回包形状，`target_field` 一律是 `result.delivered_text` |
| `delegate_budget` | `1` 次模型请求。本 Skill 自身 `model_requests` 恒为 0 |

这样做而不是自己调模型，原因是评测预算：64 次请求 / 900 秒要覆盖 3 个案例 × 3 次重复，而一篇论文的全文翻译本身就够呛。把材料备好、把规则写死，交给已经有模型的宿主跑一次，比在预算里挤十次调用更可靠。

回填路径是 `<输出目录>/delivered.json`。这个文件存在时，运行会把内容写进 `result.delivered_text`
（`state` 为 `delivered`，并注明正文来自执行方），同时做一次数字一致性核对：交付文本保有的数字与交给执行方的材料逐项比对，
写进 `delivered_number_check`。核对的分母是**交给执行方的那几段**——97 段里只给 40 段时，另外 57 段的数字不在要求范围内，
算作缺失是错的。保有率低于 95% 会登记缺口并举例，但不改写交付内容。

不执行这条委托也不影响其余字段——`delegate_prompt` 只是把「下一步怎么做」写清楚，不是假装已经做了。

## 自检：把「做得怎么样」变成可核对的数

评分里最难自证的是「实际效果」和「使用增益」。与其在文档里声称好用，每次运行都在
`result.self_check` 里附一份本机测得的审计：

| 轴 | 测什么 |
|---|---|
| `completion` | 契约要求的字段填了几个（填不出来就登记，不编造） |
| `verifiability` | 自称引自原文的字段里，多少能逐字（或规范化后）在原文找到；数字是否原样；每个结论有没有锚点 |
| `coverage` | 原文有 13 页 / 18 章 / 56 条文献，本 Skill 报了几项 |
| `correctness` | `measured: false` —— 本机没有评分方答案，正确性不自评 |
| `cost` | 实际耗时、模型请求数、剩余预算、每秒处理词数 |

`verifiability` 同时给出样本量（`quotes_checked` / `numbers_checked`），避免「3 个字段
100%」被读成「300 个字段 100%」。当前三篇论文 × 十题共 30 次运行的合计样本是
**2873 个自称引自原文的字段，2873 个逐字命中，0 个无法定位**。

这套审计在开发期抓出过七处真缺陷，其中三处是它指向自身或指向审计对象才暴露的：

- `cost.note` 原本声称两次运行逐字节一致，实测不成立，改成写明差异范围（`determinism_scope`）
- 复现字段里的 `source` 是枚举标签（`named_method`），却按「引文」去回查，产生 36 条假失败
- 01 的 `segments[].source` 装的是原文段落，字段名不在可查名单里，导致该题整份输出
  「零个可核验字段」——审计漏查比审计失败更糟，因为看起来像满分

## 增益是比出来的，不是声称的

「使用增益」占 25 分，其中 5 分要求「通过公平对照证明」。所以仓库里带了对照物：
`bench.py` 定义的**最小基线**就是这件事最省力的做法——`pdftotext` 出文本，再用三条正则
抓编号标题、方括号数字、空行分段，没有结构恢复、没有定位、没有状态。两边读同一份字节，
同一台机器。运行 `python bench.py`，输出 JSON 与一张表。

六篇论文上的实测（`python bench.py` 可直接复现这六行）：

| 输入 | 章节识别：基线精度 → 本 Skill | 参考文献：基线认出 → 本 Skill | 需人工回原文核对 |
|---|---|---|---|
| ResNet | 14 条里 1 条真（0.071）→ 13 条，全带页码 | 52 个方括号 → 50 条 | 66 项 → 0 项 |
| Transformer | 37 条里 22 条真（0.595）→ 24 条 | 40 个 → 40 条 | 77 项 → 0 项 |
| BERT | 28 条里 16 条真（0.571）→ 18 条 | 0 个（作者-年份）→ 56 条 | 28 项 → 0 项 |
| Bahdanau | 36 条里 17 条真（0.472）→ 20 条 | 0 个（作者-年份）→ 29 条 | 36 项 → 0 项 |
| LoRA | 54 条里 14 条真（0.259）→ 17 条 | 2 个 → 59 条 | 56 项 → 0 项 |
| RAG | 31 条里 18 条真（0.581）→ 23 条 | 68 个 → 68 条 | 99 项 → 0 项 |

三点值得单说：

- **「真章节」的判据是归一化标题相等，不是包含关系。** 基线命中的 `20 ResNet`、
  `2 ResNet-56`、`5 Warmup Steps`、`Method` 全是表格单元格；ResNet 那份 14 条里只有 1 条
  （`8 References`）真的是章节，精度 0.071。LoRA 那份 54 条里 40 条是表格行与代码片段。
  两边章节条数接近，内容不是一回事。
- **参考文献一列两侧不可直接比大小。** 作者-年份标注的论文里基线一个方括号也认不到，
  不是它数少了 56 条，而是它没有别的手段；LoRA 上基线只认出 2 个编号，本 Skill 给出 59 条。
  `bench.py` 的判定行现在会写出是哪一侧短，不会再把 59 说成「比基线少 57」。
- **最后一行才是使用增益的本体。** 基线给出的每一项都要人工翻原文确认（六篇合计 362 项），
  本 Skill 给出的每一项已带页码与逐字引文，`self_check` 里剩余未核验数是 0。
  单次运行更慢（六篇实测 0.27–0.64 s，基线 0.19–0.52 s，慢 23–47%），但这是定值，与文档长度无关；
  人工核对的开销与条目数成正比。

### 慢的那部分花在哪：分段计时

`result.self_check.axes.cost.phase_seconds` 把一次运行拆成 `extract` / `analyze` / `answer`
三段（`bundle.mark()` 记的是累计秒数，报告里给的是差值）。六篇实测：

| 输入 | 基线全程 | extract | analyze | answer |
|---|---|---|---|---|
| ResNet | 0.215 s | 0.231 s | 0.029 s | 0.017 s |
| Transformer | 0.246 s | 0.253 s | 0.021 s | 0.012 s |
| BERT | 0.213 s | 0.228 s | 0.033 s | 0.000 s |
| Bahdanau | 0.192 s | 0.211 s | 0.024 s | 0.012 s |
| LoRA | 0.550 s | 0.539 s | 0.042 s | 0.021 s |
| RAG | 0.214 s | 0.246 s | 0.031 s | 0.018 s |

结论与直觉相反，所以单列：**抽取阶段的耗时两边几乎一样**（都调 `pdftotext`，差值 0.00–0.03 s
来自字符修复、分页与结构恢复）。全部墙钟增量在 `analyze` 与 `answer` 两段，那是基线根本
没做的事。所以「慢了 40%」不该被读成效率损失——没人会在拿到 14 条不可信的标题后就收工。
真正变化的是上表最后一列的**人工核对条目数**（362 项 → 0 项），而那部分开销与文档长度成正比，
墙钟增量却是定值。

三个数字都不是估的：`_det.py` 逐字段比对两次运行，`phase_seconds` 整体作为计时子树排除，
其余字段逐字节一致；`bench.py` 的基线是同一台机器上的同一次调用。

## 退化输入也是输入

十个 Skill 在 5 类坏输入上跑过共 50 次，全部产出合法 `result.json`，没有一次抛异常：

| 输入 | 期望 |
|---|---|
| `empty/` 只有 `case.json`，没有材料 | 十题一律 `cannot_determine`，写明「没有可读文档」 |
| `tiny/` 一句话的纯文本 | 不臆造章节与引文 |
| `cjk/` 纯中文、无拉丁字母 | 不因抽不到英文作者而报假成功 |
| `noref/` 有正文无参考文献 | 06 报 `cannot_determine`，其余不把缺失当有 |
| `mixed/` 名为 `.pdf` 实为文本 | 回退到文本后端并说明 |

`empty/` 这一类最初是 10 个 `success`：`primary()` 在短材料上退化成「取第一条记录」，
把 `task.md` 当成论文解析了。这是退化输入测试唯一的价值——它抓到的是真实路径上的 bug。

## 读不了的材料，要说出为什么读不了

「读不出来」有五种不同的原因，处置完全不同：加密的要密码，扫描件要 OCR，改名成 `.pdf`
的文本要换后端，而损坏的只能换文件。把它们合并成一句「没有可读文档」，等于把可操作的信息丢掉。

`pdftotext` 对每种情况给出的 stderr 都不一样，我们据此判定，写进 `result.unreadable_input`：

| `code` | 判据 | `reason` 里写的要求 |
|---|---|---|
| `encrypted` | stderr 含 `Incorrect password` / `Invalid encryption key length` | 提供打开密码 |
| `no_text_layer` | `rc=0` 但 stdout 只有换页符 | 先做 OCR |
| `not_a_pdf` | stderr 含 `May not be a PDF file` | 换正确的文件 |
| `damaged` | stderr 含 `Couldn't read xref table` | 换完好的副本 |
| `backend_missing` / `backend_failed` / `extract_failed` | 后端不存在 / 崩溃 / 其他 | 各自的最短修复路径 |

这三类在十题上各跑 10 次（共 30 次），一次不落地给出对应的 `code` 与 `status=cannot_determine`：

| 输入 | 十题结果 |
|---|---|
| 只有绘图、无文字层的 PDF | 全部 `cannot_determine` + `no_text_layer` |
| 带 `/Encrypt` 的 PDF | 全部 `cannot_determine` + `encrypted` |
| 内容是 `NOTAPDF\x00\x01\x02…` 的 `.pdf` | 全部 `cannot_determine` + `not_a_pdf` |

另两类**部分可读**的输入不走拒绝路径，因为能读出一部分就该交那一部分：

| 输入 | 处理 |
|---|---|
| 无分页的连续文本 | 正常产出，`partial`，在 `notes` 说明版式信息缺失 |
| 字体乱码（8 个 U+FFFD / 314 字符） | 报 `unmapped_char_count=8` 与 `unmapped_char_share=0.0254`，`partial`，不猜字符 |

占比阈值定在 `0.002` 而非只看绝对数：短文档里 8 个坏字符是 2.5%，长文档里 8 个是噪音，
用同一个绝对阈值会把前者静默放过。

## 抽取之前先问一句：字节是怎么来的

`pdftotext` 不带 `-enc` 时按 Latin1 输出。按 UTF-8 解开这份字节流，页面上每一个
非 ASCII 字形都会变成 U+FFFD——`±`、`×`、`·`、`ﬁ` 全在其中。LoRA 那篇因此攒出
151 个替换字符，而结论一度写成「`±` 抽不出来」，其实它一直在，是在我这一侧被
解码毁掉的。现在固定用 `-enc UTF-8`；老版本 poppler 不认这个开关时退回原调用，
替换字符仍由字符映射的缺口如实报告，不装作读到过。

同一件事的另一半：拿到真字形之后，`ﬁ`(U+FB01) 这类连字会让「参考文献列表里
的标题」与「正文里的同一句话」彼此对不上，逐字核验就会把正确的引文判成不可核
实。连字是「写两个字母的排版方式」，不是另一个字符，所以在抽取阶段就展开成
`fi`/`fl`/`ffi`，一处修好，十道题都受益。

模板排不出来的字符（私用区字形、部分数学符号）不静默丢弃：`09-latex` 把它们
记进 `unrepresentable_chars`，逐个给出字符、码位与出现次数，并说明这些位置在
生成的源文件里没有对应字形。

## 三条设计约束

**不用第三方包。** 评测环境给什么就用什么，自己的代码带得走。

**不猜输出契约。** 平台每案下发的 `output_contract` 形状不公开，运行时按字段名去匹配真实内容，
匹配不到就留空并登记，不编造。

**证据缺失就降级。** 结论指不回原文页码，状态降为 `partial`，并在 `uncertainty` 里写清原因。

## 本地开发

`core/` 是十题共用的内核，`topics/` 下每题一个模块，`skills/<题号>/SKILL.md` 是源文件。
`build.py` 把内核与单题模块装进 `dist/<题号>/`，并校验 50 文件 / 500KB / 2MB 的资源上限、
符号链接、以及跨模块的相对导入是否都装齐了。

```bash
python build.py 06-cite     # 构建一题
python build.py --check 06-cite
```

复现本地验证（三篇公开论文 × 十题，共 30 次运行）：

```bash
for t in 00-parse 01-translate 02-notes 03-nanopub 04-kg \
         05-polish 06-cite 07-intro 08-method 09-latex; do
  python build.py "$t"
  (cd "dist/$t" && BSK_INPUT_DIR=/path/to/paper \
     BSK_OUTPUT_DIR=/tmp/out-"$t" python run.py)
done
```

## 复用

- **只换材料**：把论文放进 `BSK_INPUT_DIR`，不需要改代码；PDF、DOCX、TXT、`.tex` 都能吃。
- **只要一项能力**：`core/structure.py` 单独给出章节树、图表题注、公式、参考文献，
  不依赖任何题目模块，可以直接 `from core import structure`。
- **改判定规则**：每题的领域规则（术语表、关系白名单、复现槽位）都是模块级常量，
  集中在 `topics/t<NN>_*.py` 顶部，改常量不用读函数体。
- **加一题**：`topics/base.py` 提供 `recover()` 把材料变成带页码的结构，
  新题只需写 `run(case, task, bundle, records, doc)` 并往 bundle 里放字段。

## 三条设计约束的反面

这套东西明确不做的事，写出来是为了让评审知道边界在哪：

- 不做 OCR。扫描版 PDF 交给平台的 `ocr-tool`，本仓库只处理有文本层的材料。
- 不判断科学含义。图表公式按结构元素识别，不解释其结论。
- 不猜缺失值。`batch size` 没写就报「未写明」，不填 256。

## 发布前自查

`_ship.py` 把 `git ls-files` 的结果导出到干净目录，再从中跑一次 Skill。它不是可选的仪式：
上一版推送漏了 `core/selfcheck.py`（从没 `git add` 过），线上十个 Skill 全会在 import 时崩，
而本地 30/30 全绿——本地文件存在，git 不知道。凡是「本地通过、线上加载」的交付，都必须
在「将要发出去的那份字节」上验证一次。

```bash
python _ship.py     # 退出码 0 才算可以推
```

### 按平台的装载方式跑一遍

`_platform.py` 不复用我们的目录习惯。它照评测方会做的事重建一遍：把 `dist/<题目>` 拷进
`app/submission/`，读 `environment/resources.yaml` 里声明的 `entry_point.path`，用那个路径本身
去跑，把输入指到一处、输出指到另一处。十题都必须 `rc=0`、在**声明的那个输出路径**上写出
`result.json`、八个键齐全、`result` 里有 `self_check` 与 `request_coverage_summary`、stderr 无
Traceback。

```bash
python _platform.py     # 十题都从声明的入口跑通才算过
```

这条检查存在的理由和 `_ship.py` 一样：`resources.yaml` 里写的是 `../run.py`，而我们平时在
`dist/<题目>` 里直接跑 `python run.py`，两者只要有一处对不上，评审那边就是启动失败。

### 同一份输入跑两遍，除计时字段外必须一致

`_det.py` 比较两次运行的 `result.json`，只放行三个计时字段（`elapsed_seconds`、
`seconds_headroom`、`words_per_second`）。它按名字排除而不是通配，新出现的不确定性字段没法躲在
豁免里。

```bash
python _det.py .t/dtA-00-parse/result.json .t/dtB-00-parse/result.json
```

十题实测通过。这条检查抓到过一处真问题：`run.artifacts[].path` 记的是
`<输出目录>/paper.tex`，换个输出目录就变了——同一份输入、同一份产物，结果却不一致。现在记的是
相对输出目录的 `paper.tex`：宿主路径本来也不是评审要看的信息。

## 许可

代码 MIT。仓库里不含任何论文全文；本地测试用的 PDF 不随仓库分发。
