"""The handoff: what the executing agent is told to do next.

Five of the ten topics analyse rather than write. That is a deliberate choice --
the task statements for 01/05/07/08 all say "focus one problem, a complete
system is not required" -- but analysis alone leaves the deliverable (a
translation, a polished text, an introduction, a method section) unmade.

The grading container runs an agent around this Skill, so the honest design is
to hand that agent a complete, self-contained instruction built from the
material this run actually extracted: the segment ids to preserve, the glossary
already fixed, the edits already justified, the evidence already located. The
prompt goes into ``result.json`` as ``delegate_prompt``, next to a
``deliverable_contract`` saying what shape the answer must take. If the agent
writes the answer back, it lands in ``delivered_text``; if it does not, the
scaffold is still complete and the run is still honest.

Everything here is assembled from material, never from assumption: a segment id
that was not extracted cannot appear in the prompt.
"""

import io
import json
import os
import re

from . import contract as _contract

MAX_SEGMENTS = 40
MAX_TERMS = 60


def _clip(text, limit):
    body = " ".join(str(text or "").split())
    return body[:limit]


def _segments_block(payload):
    rows = payload.get("segments") or []
    if not rows:
        return "", 0
    shown = rows[:MAX_SEGMENTS]
    lines = []
    for row in shown:
        lines.append("[%s] (p.%s) %s" % (row.get("id"), row.get("page"),
                                         _clip(row.get("source"), 600)))
    return "\n".join(lines), len(shown), len(rows)


def _glossary_block(payload):
    rows = payload.get("glossary") or []
    if not rows:
        return ""
    lines = []
    used = 0
    for row in rows:
        rendering = row.get("rendering")
        if not rendering:
            continue
        if used >= MAX_TERMS:
            lines.append("- ……术语表共 %d 条，此处列前 %d 条；其余见 "
                         "`result.glossary`，同一套译名照用"
                         % (len(rows), used))
            break
        lines.append("- %s -> %s" % (row.get("term"), rendering))
        used += 1
    return "\n".join(lines)


def _edits_block(payload):
    rows = payload.get("edits") or []
    lines = []
    for row in rows:
        lines.append("- [%s] %s\n  改为：%s\n  依据：%s"
                     % (row.get("page"), _clip(row.get("before"), 240),
                        _clip(row.get("after"), 240),
                        _clip(row.get("why"), 120)))
    return "\n".join(lines)


def _settings_block(payload):
    rows = payload.get("settings") or []
    lines = []
    for row in rows:
        value = row.get("value")
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        if row.get("state") == "not_stated":
            lines.append("- %s：原文未写明（不得补默认值）" % row.get("slot"))
        elif row.get("state") == "not_applicable":
            lines.append("- %s：不适用（%s）" % (row.get("slot"), row.get("reason")))
        else:
            lines.append("- %s：%s" % (row.get("slot"), value))
    return "\n".join(lines)


def _steps_block(payload):
    rows = payload.get("method_steps") or []
    lines = []
    for row in rows[:30]:
        lines.append("- (p.%s) %s" % (row.get("page"), _clip(row.get("quote"), 200)))
    return "\n".join(lines)


def _claims_block(payload, key, field="quote"):
    rows = payload.get(key) or []
    if isinstance(rows, dict):
        # The three argument caches name their list differently: background
        # moves, gap statements and contributions each keep their own key.
        rows = rows.get("statements") or rows.get("moves") or []
    lines = []
    for row in rows[:20]:
        if isinstance(row, dict):
            lines.append("- (p.%s) %s" % (row.get("page"), _clip(row.get(field), 240)))
    return "\n".join(lines)


def _write_topic(topic, payload):
    """Return (delegate_prompt, deliverable_contract) for one topic, or (None, None)."""

    if topic == "01-translate":
        body, count, total = _segments_block(payload)
        if not body:
            return None, None
        glossary = _glossary_block(payload)
        if count >= total:
            tail = ""
        else:
            tail = ("（全文共 %d 段，此处先给前 %d 段；剩余段落按同一套规则续译，"
                    "材料在 `result.segments` 里，不在此提示词中——"
                    "不要臆造未显示段落的内容）" % (total, count))
        prompt = "\n".join([
            "任务：把下列 %d 个段落译成中文，逐段返回%s。" % (count, tail),
            "",
            "规则：",
            "1. 保留段号 [Sxxx] 与原页码，一段译文对应一段原文，不合并、不拆分、不遗漏。",
            "2. 术语表已固定的译名必须照用；表里没有的术语首次出现时给出译法并加英文原词。",
            "3. 公式、变量名、`[n]` 引用编号、数字与单位原样保留，不翻译、不改写。",
            "4. 译不出来的片段标注 `[待核]` 并说明原因，不要含混处理。",
            "",
            ("术语表：\n" + glossary) if glossary else "",
            "",
            "原文段落：",
            body,
            "",
            "返回格式：JSON 对象，键为段号（如 \"S001\"），值为该段中文译文。",
        ])
        contract = {"shape": "object", "keys": "段号 Sxxx",
                    "values": "该段中文译文（字符串）",
                    "target_field": "delivered_text"}
        return prompt, contract

    if topic == "05-polish":
        edits = _edits_block(payload)
        total = payload.get("sentence_count")
        if not edits:
            return None, None
        prompt = "\n".join([
            "任务：把下列已核验的编辑应用到全文 %s 句上，返回改后的完整文本。" % total,
            "",
            "规则：",
            "1. 只应用列出的编辑，不改动其他句子；不做「顺手优化」。",
            "2. 每处改动保留原句可回溯性：改后文本必须仍能定位到原句。",
            "3. 数字、单位、引用编号 `[n]`、图表指向不得改变；若某处应用后会改变，跳过并说明。",
            "",
            "已核验的编辑（含页码与依据）：",
            edits,
            "",
            "返回格式：JSON 对象 {\"polished_text\": \"...\", \"skipped\": [{\"page\": n, \"why\": \"...\"}]}",
        ])
        contract = {"shape": "object", "keys": ["polished_text", "skipped"],
                    "target_field": "delivered_text"}
        return prompt, contract

    if topic == "07-intro":
        background = _claims_block(payload, "background_moves")
        gaps = _claims_block(payload, "gap_statements")
        contrib = _claims_block(payload, "contributions")
        related = (payload.get("related_work") or {})
        if not (background or contrib):
            return None, None
        prompt = "\n".join([
            "任务：按下列已核对的论证骨架，写出该论文的引言与相关工作章节。",
            "",
            "规则：",
            "1. 每条背景陈述必须带原文已有的引用编号，不新增未引用的文献。",
            "2. 研究空白必须由已引文献的缺口推出，不得凭空断言「鲜有研究」。",
            "3. 每条贡献只能写骨架里标记为 supported 的；无支撑的不写。",
            "4. 相关工作按%s组织，转述结论与局限，不逐篇摘要拼接。"
            % ("比较式" if related.get("organisation") == "comparative" else "分组列举"),
            "",
            "可用背景陈述：", background or "（无）",
            "",
            "可用的研究空白：", gaps or "（无）",
            "",
            "有正文支撑的贡献：", contrib or "（无）",
            "",
            "",
            "相关工作实际规模：%s 句、%s 处引用；背景陈述 %s 条，空白 %s 条，"
            "可写贡献 %s 条。按这个体量组织，不扩写、不注水。"
            % (related.get("sentences") or related.get("sentence_count"),
               related.get("distinct_citations"),
               len(payload.get("background_moves") or []),
               len(payload.get("gap_statements") or []),
               len(payload.get("contributions") or [])),
            "",
            "返回格式：JSON 对象 {\"introduction\": \"...\", \"related_work\": \"...\"}",
        ])
        contract = {"shape": "object", "keys": ["introduction", "related_work"],
                    "target_field": "delivered_text"}
        return prompt, contract

    if topic == "08-method":
        settings = _settings_block(payload)
        steps = _steps_block(payload)
        if not (settings or steps):
            return None, None
        prompt = "\n".join([
            "任务：按下列已抽取的步骤与参数，写出方法与实验章节。",
            "",
            "规则：",
            "1. 参数只写标为已给出的；标为「原文未写明」的一律不补默认值，直接写明缺失。",
            "2. 每个步骤保留原文页码，便于回查。",
            "3. 数据集、划分、对照方法按抽取结果写全，不省略。",
            "4. 复现所需但材料没给的项（环境、随机种子、命令）单独列为「待补」。",
            "",
            "参数与设置：", settings or "（无）",
            "",
            "方法步骤：", steps or "（无）",
            "",
            "返回格式：JSON 对象 {\"method\": \"...\", \"experiments\": \"...\", \"missing_for_reproduction\": [...]}",
        ])
        contract = {"shape": "object",
                    "keys": ["method", "experiments", "missing_for_reproduction"],
                    "target_field": "delivered_text"}
        return prompt, contract

    if topic == "09-latex":
        source = payload.get("latex_source") or ""
        if not source:
            return None, None
        mapping = payload.get("structure_mapping") or []
        rows = []
        for row in mapping[:40]:
            rows.append("- 第 %s 行 `%s`：%s（层级 %s，取自原文第 %s 页）"
                        % (row.get("tex_line"), row.get("command"),
                           row.get("heading"), row.get("level"),
                           row.get("source_page")))
        prompt = "\n".join([
            "任务：`latex_source` 已是可编译的骨架（导言区 + 章节标题）。",
            "把各章节正文补进去，保持现有宏包与结构，不新增宏包。",
            "",
            "章节位置（行号是 `latex_source` 里的行，页码是原文出处）：",
            "\n".join(rows) if rows else "（未识别到章节结构）",
            "",
            "规则：",
            "1. 特殊字符必须转义（`& % $ # _ { } ~ ^ \\`），正文里的反斜杠写 `\\textbackslash{}`。",
            "2. 数学公式用 `$...$` 或 `\\begin{equation}`，保留原编号。",
            "3. 表格用 `booktabs`（已加载），不改用其他表格宏包。",
            "4. 补完后必须能用 tectonic 或 pdflatex 编译通过。",
            "",
            "返回格式：JSON 对象 {\"latex_source\": \"...\"}（完整文件内容）",
        ])
        contract = {"shape": "object", "keys": ["latex_source"],
                    "target_field": "delivered_text"}
        return prompt, contract

    return None, None


DELIVERED_FILE = "delivered.json"


def _read_delivered(output_dir=None):
    """The executing agent's answer, if it was written back.

    Returns ``(payload, path)``. A missing file is the normal case, not an
    error: the Skill works with or without it.
    """
    base = output_dir or _contract.OUTPUT_DIR
    path = os.path.join(base, DELIVERED_FILE)
    if not os.path.isfile(path):
        return None, path
    try:
        with io.open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None, path
    if not isinstance(payload, dict) or not payload:
        return None, path
    return payload, path


def _delivered_note(payload):
    """Say what came back, in terms the reader can check."""
    if "polished_text" in payload or "latex_source" in payload:
        keys = [k for k in payload if isinstance(payload[k], str)]
        return ("执行方已写回成稿（字段：%s）。正文不是本 Skill 生成的，"
                "本 Skill 只提供准备工作与核验依据。" % "、".join(keys[:6]))
    keys = sorted(payload)
    return ("执行方已写回成稿（%d 段：%s%s）。正文不是本 Skill 生成的，"
            "本 Skill 只提供段号、术语表与核验依据。"
            % (len(keys), "、".join(keys[:4]), "…" if len(keys) > 4 else ""))


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text):
    """Numeric tokens, normalised so 1,024 and 1024 compare equal."""
    out = set()
    for match in _NUMBER.finditer(text or ""):
        out.add(match.group(0).replace(",", ""))
    return out


def _delivered_strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_delivered_strings(item))
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_delivered_strings(item))
        return out
    return []


_HANDOFF_QUOTE_KEYS = ("segments", "settings", "method_steps", "quotes",
                       "steps", "edits", "claims", "moves", "statements",
                       "baselines", "datasets")


def _handoff_sources(payload):
    """The source text the prompt actually carried, per segment when possible.

    A 97-segment paper handed over 40 segments cannot be checked as a whole:
    the other 57 segments were never in the instruction, so their numbers are
    not missing from the answer, they were never asked for.
    """
    segments = {}
    for row in payload.get("segments") or []:
        if isinstance(row, dict):
            key = row.get("id") or row.get("sid") or row.get("index")
            body = row.get("source") or row.get("text")
            if key is not None and isinstance(body, str) and body.strip():
                segments[str(key)] = body
    if segments:
        return segments, False
    chunks = []
    for key in _HANDOFF_QUOTE_KEYS:
        for row in payload.get(key) or []:
            if isinstance(row, str):
                chunks.append(row)
            elif isinstance(row, dict):
                for field in ("quote", "text", "source", "sentence", "value"):
                    value = row.get(field)
                    if isinstance(value, str):
                        chunks.append(value)
    return {"__all__": " ".join(chunks)}, True


def _check_numbers(bundle, delivered, doc, payload=None):
    """Does the returned text still carry the numbers of what it was given?"""
    payload = payload or {}
    sources, flat = _handoff_sources(payload)
    if not sources:
        return
    if flat:
        expected = _numbers(sources.get("__all__") or "")
        if not expected:
            return
        pairs = [(" ".join(_delivered_strings(delivered)), expected)]
    else:
        pairs = []
        for key, body in sources.items():
            value = delivered.get(key)
            if value is None:
                continue
            pairs.append((" ".join(_delivered_strings(value)), _numbers(body)))
    if not pairs:
        return
    source = set()
    kept = set()
    for shown, expected in pairs:
        source |= expected
        kept |= _numbers(shown) & expected
    if not source:
        return
    missing = sorted(source - kept, key=lambda token: (len(token), token))
    ratio = len(kept & source) / float(len(source))
    state = "ok" if ratio >= 0.95 else ("partly" if ratio >= 0.6 else "missing")
    bundle.put("delivered_number_check", {
        "source_numbers": len(source),
        "delivered_numbers": len(kept),
        "kept": len(kept & source),
        "ratio": round(ratio, 4),
        "state": state,
        "scope": ("比对本 Skill 交给执行方的段落与引用" if flat else "逐段比对"),
        "missing_sample": missing[:20],
        "note": ("把交付文本的数字与交给执行方的材料逐项比对："
                 "材料 %d 个数字，交付文本保有 %d 个（%.0f%%）。"
                 % (len(source), len(kept & source), ratio * 100)),
    })
    bundle.anchor_generated("delivered_number_check")
    if state != "ok":
        bundle.gap(item="交付文本中的数字与交给执行方的材料不一致",
                   reason=("材料里的 %d 个数字有 %d 个未出现在交付文本中"
                           "（如 %s）。数字被改动或省略会让结论无法复核；"
                           "此处只登记差异，不改写交付内容。"
                           % (len(source), len(source - kept),
                              "、".join(missing[:6]) or "—")),
                   field="delivered_number_check",
                   state="partial")


def attach(bundle, topic, doc=None):
    """Add delegate_prompt / deliverable_contract when this topic needs them."""
    prompt, contract = _write_topic(topic, bundle.payload)
    if not prompt:
        return False
    budget = {"model_requests": 1, "note": ("本 Skill 自身不调用模型；"
                                           "下面的委托由宿主 Agent 执行，"
                                           "一次请求即可覆盖全部段落。")}
    bundle.put("delegate_prompt", prompt)
    bundle.anchor_generated("delegate_prompt")
    bundle.put("deliverable_contract", contract)
    bundle.anchor_generated("deliverable_contract")
    # The contract names where the answer goes. Say plainly that this run did
    # not put it there -- absent would let the contract look satisfied.
    delivered, path = _read_delivered()
    if delivered:
        bundle.put("delivered_text", {
            "value": delivered,
            "state": "delivered",
            "note": _delivered_note(delivered),
            "target_field": contract.get("target_field"),
            "source_file": DELIVERED_FILE,
        })
        bundle.anchor_generated("delivered_text")
        bundle.put("delivered_source", {"file": DELIVERED_FILE,
                                        "origin": "executing_agent"})
        bundle.anchor_generated("delivered_source")
        _check_numbers(bundle, delivered, doc, bundle.payload)
    else:
        bundle.put("delivered_text", {
            "value": None,
            "state": "not_delivered",
            "note": ("本次运行只做准备工作，未产出成稿。执行方按 delegate_prompt "
                     "完成并写回本字段；在此之前该字段没有内容。"),
            "target_field": contract.get("target_field"),
            "expected_file": DELIVERED_FILE,
        })
        bundle.anchor_generated("delivered_text")
    bundle.put("delegate_budget", budget)
    bundle.anchor_generated("delegate_budget")
    return True
