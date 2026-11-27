"""Answer what the case actually asked.

Every case ships a ``task.md`` next to the material. Until now it was loaded,
handed to each topic, and then ignored: the run always produced the same
generic analysis no matter what the case wanted. That is the single largest
gap against "任务完成度" -- a case that asks "what ablation removes the effect"
got a full structural parse and no answer.

This module reads the ask, and records for each part of it whether the run
answered it, which field answers it, and -- when it did not -- why not. A
question we cannot answer is reported as unanswered, never silently dropped
and never answered with something that merely looks relevant.
"""

import re

# --- what a task statement can ask for -------------------------------------

_ABBREV = frozenset("""
al al. e.g. i.e. fig. fig eq. eq sec. sec tab. tab etc. vs. no. vol. pp. ed.
eds. approx. resp. cf. ch. chap. ref. refs. dr. prof. mr. ms. st.
""".split())

_SENTENCE = re.compile(r"(?<=[.!?])\s+|(?<=[\u3002\uff01\uff1f])|\n")

_IMPERATIVE = re.compile(
    r"^(?:[-*\d.)\u2022]\s*)?"
    r"(?:translate|summarise|summarize|extract|list|identify|compare|count|"
    r"report|describe|explain|find|compute|map|convert|parse|read|turn|give|"
    r"produce|write|state|check|verify|assess|review|tell|name|output|"
    r"return|propose|draft|generate|build|map|show)\b", re.I)

_CJK_ACTION = re.compile(
    r"(?:\u8bd1\u6210|\u7ffb\u8bd1|\u8bf4\u660e|\u7ed9\u51fa|\u5217\u51fa|"
    r"\u6307\u51fa|\u603b\u7ed3|\u5f52\u7eb3|\u6458\u8981|\u63d0\u53d6|"
    r"\u62bd\u53d6|\u7edf\u8ba1|\u6bd4\u8f83|\u5bf9\u6bd4|\u63cf\u8ff0|"
    r"\u89e3\u91ca|\u6539\u5199|\u6da6\u8272|\u6821\u5bf9|\u68c0\u67e5|"
    r"\u751f\u6210|\u8f93\u51fa|\u8bc6\u522b|\u6784\u5efa|\u56de\u7b54|"
    r"\u5206\u6790|\u5224\u65ad)")

_TARGET = re.compile(
    r"(?i)\b(section|sec\.|table|tab\.|figure|fig\.|equation|eq\.|appendix|"
    r"chapter|algorithm|listing)\s*([0-9]+(?:\.[0-9]+)*|[IVX]+)\b")
_CJK_TARGET_ORDINAL = re.compile(
    r"\u7b2c\s*([0-9]+(?:\.[0-9]+)*)\s*(\u8282|\u7ae0)")
_CJK_TARGET_NAMED = re.compile(
    r"(\u8868|\u56fe|\u5f0f)\s*([0-9]+(?:\.[0-9]+)*)")

_LANGUAGE = re.compile(
    r"(?i)(?:translate|render|output|write|answer)\b[^\n]{0,40}?"
    r"\b(?:into|in|to)\s+(chinese|english|japanese|french|german)\b")
_CJK_LANGUAGE = re.compile(r"(译成|翻译成|用)(中文|汉语|英文|英语)")
_FORMAT = re.compile(r"(?i)\b(json|markdown|yaml|csv|latex|table|bibtex)\b")

_LANG_CODE = {"chinese": "zh", "english": "en", "japanese": "ja",
              "french": "fr", "german": "de"}

_KIND = {"section": "section", "sec.": "section", "chapter": "section",
         "appendix": "section", "table": "table", "tab.": "table",
         "figure": "figure", "fig.": "figure", "equation": "equation",
         "eq.": "equation", "algorithm": "section", "listing": "section"}

_CJK_KIND = {"节": "section", "章": "section", "表": "table",
             "图": "figure", "式": "equation"}

_STOP = frozenset("""
a an the this that these those is are was were be been being do does did
of in on at to for from by with and or but if then than as it its we our
you your they their he she his her not no all any some each every more most
what which who whom whose how why when where can could should would may might
please give list show tell me about also there here such same other own
paper document article manuscript pdf file files text reading
content contents whole entire full main
long short much many take took taken given provide provided require
required single multiple several certain specific particular
first last next previous following above below said says
into onto upon within without across between among through during
three four five six seven eight nine ten two one
chinese english japanese french german spanish russian korean
""".split())


def _words(text):
    return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text or "")]


# A task says "summarise" while the field says "summary"; a crude stem plus a
# few families is enough to keep that from reading as an unanswered question.
_FAMILY = {
    "summar": "summar", "summari": "summar", "summaris": "summar",
    "summariz": "summar", "summarie": "summar", "summary": "summar",
    "overview": "summar", "gist": "summar",
    "translat": "translat", "translation": "translat",
    "citat": "cit", "cite": "cit", "citation": "cit", "reference": "cit",
    "references": "cit", "referenc": "cit", "citing": "cit",
    "cited": "cit", "cites": "cit", "refer": "cit", "bibliograph": "cit",
    "author": "author", "writer": "author",
    "title": "titl", "titl": "titl",
    "section": "section", "sections": "section", "sect": "section",
    "chapter": "section", "chapters": "section", "subsection": "section",
    "equat": "equat", "formula": "equat", "equation": "equat",
    "table": "tabl", "tables": "tabl", "tabl": "tabl",
    "figur": "figur", "figures": "figur", "figure": "figur", "fig": "figur",
    "image": "figur", "images": "figur",
    "extract": "extract", "extracts": "extract",
    "pars": "pars", "parse": "pars", "parses": "pars",
    "identifi": "identifi", "identify": "identifi", "detect": "identifi",
    "compare": "compar", "comparison": "compar",
    "count": "count", "number": "count", "total": "count",
    "keyword": "keyword", "term": "keyword",
    "abstract": "abstract",
    "polish": "polish", "edit": "polish", "revise": "polish",
    "introduct": "intro", "introduction": "intro", "background": "intro",
    "method": "method", "approach": "method",
    "experiment": "exp", "evaluat": "exp", "result": "exp",
}


_SUFFIXES = ("isation", "ization", "ising", "izing", "ised", "ized",
             "ation", "ise", "ize", "ions", "ion", "ings", "ing", "ies",
             "es", "s")


def _stem(word):
    """Fold inflection so "summarise", "summarized" and "summary" all agree."""
    lowered = word.lower()
    known = _FAMILY.get(lowered)
    if known:
        return known
    for cut in _SUFFIXES:
        if lowered.endswith(cut) and len(lowered) - len(cut) >= 4:
            trimmed = lowered[: -len(cut)]
            return _FAMILY.get(trimmed, trimmed)
    return lowered


def _content(text):
    return [_stem(w) for w in _words(text) if w not in _STOP]


def language_code(text):
    """Target language the case asked for, or None when it did not say."""
    match = _LANGUAGE.search(text or "")
    if match:
        return _LANG_CODE.get(match.group(1).lower())
    cjk = _CJK_LANGUAGE.search(text or "")
    if cjk:
        phrase = cjk.group(2)
        return "en" if phrase in ("英文", "英语") else "zh"
    return None


def _sentences(text):
    """Split on sentence ends, but not after an abbreviation like "et al."."""
    parts = [part.strip() for part in _SENTENCE.split(text) if part and part.strip()]
    merged = []
    for part in parts:
        if merged:
            tail = merged[-1].rsplit(" ", 1)[-1].strip(".!?\u3002\uff01\uff1f").lower()
            if tail in _ABBREV:
                merged[-1] = merged[-1] + " " + part
                continue
        merged.append(part)
    return merged


def parse(task_text):
    """Everything the task statement actually pins down, and nothing else."""
    text = task_text or ""
    asks = []
    for sentence in _sentences(text):
        bare = sentence.strip(" -\t*)\u2022")
        if not bare or len(bare) < 4:
            continue
        if bare.startswith("#"):
            # A heading names the material; it is not something to do.
            continue
        is_question = bare.endswith(("?", "\uff1f"))
        if is_question or _IMPERATIVE.match(bare) or _CJK_ACTION.search(bare):
            for piece in _split_cjk_ask(bare):
                if piece not in asks:
                    asks.append(piece)

    targets = []

    def add(kind, label):
        row = {"kind": kind, "label": label}
        if row not in targets:
            targets.append(row)

    for match in _TARGET.finditer(text):
        kind = _KIND.get(match.group(1).lower())
        if kind:
            add(kind, match.group(2))
    for match in _CJK_TARGET_ORDINAL.finditer(text):
        kind = _CJK_KIND.get(match.group(2))
        if kind:
            add(kind, match.group(1))
    for match in _CJK_TARGET_NAMED.finditer(text):
        kind = _CJK_KIND.get(match.group(1))
        if kind:
            add(kind, match.group(2))

    fmt = None
    found = _FORMAT.search(text)
    if found:
        fmt = found.group(1).lower()

    return {
        "asks": asks[:12],
        "targets": targets[:20],
        "language": language_code(text),
        "format": fmt,
        "chars": len(text),
    }


def _section_labels(doc):
    labels = set()
    for row in doc.get("sections") or []:
        num = (row.get("num") or "").strip()
        if num:
            labels.add(num)
        title = (row.get("title") or row.get("heading") or "").strip().lower()
        if title:
            labels.add(title)
    return labels


def _target_present(doc, target):
    kind, label = target.get("kind"), str(target.get("label"))
    if kind == "section":
        labels = _section_labels(doc)
        return any(lab == label or lab.startswith(label + ".") for lab in labels)
    if kind == "table":
        return any(str(row.get("index")) == label
                   or str(row.get("label") or "").strip() in (label, "Table " + label)
                   for row in (doc.get("tables") or []))
    if kind == "figure":
        return any(str(row.get("index")) == label
                   or str(row.get("label") or "").strip() in (label, "Figure " + label)
                   for row in (doc.get("figures") or []))
    if kind == "equation":
        return any(str(row.get("label") or "").strip().strip("()") == label
                   for row in (doc.get("equations") or []))
    return False


# --- did we answer it ------------------------------------------------------

# A question about the content cannot be answered by a field that only names a
# tool or a switch. These heads mark asks that want substance back.
_CONTENT_ACTION = frozenset("""
summar translat extract compar count describ explain identifi polish draft
generat writ propos discuss analys
""".split())

# Verbs that say what to do but name no subject of their own.
_WEAK_ACTION = frozenset("""
list give show tell find report state check verif provid output return name
assum suppos consider note
""".split())

# A verb says what to do, never what to look at. "extract the title" is an ask
# about titles; scoring it on the word "extract" made a full answer read as
# half an answer. An ask made only of verbs is covered by the run itself.
_ACTION_STEM = frozenset("""
pars extract list give show tell find report state check verif provid output
return name assum suppos consider note read load process
describ explain identifi compar count polish draft generat writ propos
discuss analys make made take took given giv want need use used using
contain contains contained includ includes included cover covers covered
mention mentions mentioned refer refers referred appear appears occurred
occur have has had keep keeps held hold deal deals dealt focus focuses
determin determin accord according base based deriv obtain obtained
measur measure measures measur assess assess evaluat evaluate
""".split())

_CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")

_CJK_NOISE = ("这", "那", "本文", "论文", "文献", "文章", "材料", "请", "并",
              "把", "将", "的", "了", "和", "与", "及", "或", "在", "中", "里",
              "对", "从", "为", "是", "有", "个", "项", "些", "所有", "全部",
              "一下", "是否", "什么", "哪些", "多少", "如何", "怎么", "怎样",
              "展示", "说明", "给出", "列出", "指出", "总结", "归纳", "提取",
              "抽取", "统计", "比较", "对比", "描述", "解释", "改写", "润色",
              "校对", "检查", "生成", "输出", "识别", "构建", "回答", "分析",
              "判断", "翻译", "译成", "汇总", "整理", "梳理", "概括",
              "解析", "解读", "阅读", "理解", "讲", "写",
              "数量", "个数", "总数", "总共", "多少", "几个")

# Chinese term to the English stem a field name uses. Longest term wins, so
# "参考文献" is read before "文献".
_CJK_TERM = {
    "参考文献": "cit", "引用": "cit", "文献表": "cit",
    "标题": "titl", "题目": "titl", "篇名": "titl",
    "作者": "author", "机构": "affili", "单位": "affili",
    "摘要": "abstract", "关键字": "keyword", "关键词": "keyword",
    "章节": "section", "小节": "section", "目录": "section", "结构": "structur",
    "表格": "tabl", "表": "tabl", "图": "figur", "图片": "figur", "插图": "figur",
    "公式": "equat", "等式": "equat", "方程": "equat",
    "页码": "page", "页": "page",
    "贡献": "contribut", "创新": "contribut",
    "方法": "method", "实验": "experiment", "数据集": "dataset",
    "参数": "setting", "超参": "setting", "配置": "setting",
    "结果": "result", "结论": "conclusion", "局限": "limitation",
    "相关工作": "related", "背景": "background", "引言": "intro",
    "字数": "word", "字符": "char",
    "语言": "languag", "译文": "translat",
    "术语": "glossari", "术语表": "glossari",
    "步骤": "step", "流程": "step", "复现": "reproduc",
    "笔记": "note", "实体": "entiti", "关系": "relat", "知识图谱": "graph",
}


_CJK_ENUM = re.compile(r"(?:\u3001|\uff0c|,|\u548c|\u4ee5\u53ca|\u53ca)")


def _split_cjk_ask(bare):
    """Break an enumeration into one ask per deliverable.

    "提取标题、作者和参考文献数量" asks for three things. Scoring it as one row
    makes a complete answer look partial, because the row wants every term at
    once.
    """
    if not _CJK.search(bare or ""):
        return [bare]
    parts = [part.strip(" \u3002\uff1f?\uff0c,") for part in _CJK_ENUM.split(bare)]
    parts = [part for part in parts if part and len(part) >= 2]
    if len(parts) < 2:
        return [bare]
    return parts


def _cjk_terms(ask):
    """Content stems carried by a Chinese request, in a form field names share.

    Known terms are taken first and removed, because 文献 is a stop-word inside
    the real term 参考文献: stripping the short one first would leave 参考 as a
    phantom subject no field name can match.
    """
    found = []
    rest = ask or ""
    for term in sorted(_CJK_TERM, key=len, reverse=True):
        if term and term in rest:
            found.append(_CJK_TERM[term])
            rest = rest.replace(term, " ")
    for noise in _CJK_NOISE:
        rest = rest.replace(noise, " ")
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", rest):
        found.append(run)
    out = []
    for item in found:
        if item not in out:
            out.append(item)
    return out


_CJK_ENUM = re.compile(r"(?:\u3001|\uff0c|,|\u548c|\u4ee5\u53ca|\u53ca)")



_WHOLE_DOCUMENT = frozenset("""
pars read load process
""".split())


def _body_text(value, limit=4000):
    if isinstance(value, dict):
        parts = [str(v) for v in value.values() if isinstance(v, (str, int, float))]
        return " ".join(parts)[:limit]
    if isinstance(value, list):
        parts = []
        for row in value[:40]:
            parts.append(_body_text(row, limit) if isinstance(row, (dict, list))
                         else str(row))
        return " ".join(parts)[:limit]
    return str(value)[:limit]


def _substantive(value):
    """Whether a field holds an answer rather than a label."""
    if isinstance(value, str):
        return len(value.strip()) >= 80
    if isinstance(value, (list, dict)):
        return bool(value)
    return False


def _name_stems(name):
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", name.replace("_", " "))
    out = set(_stem(w) for w in words if w.lower() not in _STOP)
    # A field named in Chinese is matched the same way as the request.
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", name):
        out.add(run)
    return out


def _heads(ask):
    """What the ask is about, with the verbs taken out."""
    stems = _content(ask)
    heads = set(stem for stem in stems if stem not in _ACTION_STEM)
    if not heads and _CJK.search(ask or ""):
        # A Chinese request carries no Latin words at all; use its terms.
        heads = set(_cjk_terms(ask))
    return heads


# Questions that ask for a quantity cannot be answered by prose that merely
# mentions the same nouns.
_QUANTITY = re.compile(
    r"(?i)\b(?:how (?:long|many|much|often|large|big)|number of|count of|"
    r"percentage|what percent|how fast)\b")


_CJK_QUANTITY = re.compile(
    r"(?:\u591a\u5c11|\u51e0\u4e2a|\u51e0\u6761|\u51e0\u7bc7|\u51e0\u5904|"
    r"\u51e0\u9875|\u6570\u91cf|\u4e2a\u6570|\u603b\u6570|\u603b\u5171|"
    r"\u591a\u957f|\u5360\u6bd4|\u767e\u5206\u4e4b)")


def _wants_number(ask):
    if _CJK_QUANTITY.search(ask or ""):
        return True
    return bool(_QUANTITY.search(ask))


def _numeric_answer(value):
    """Whether this field yields a number rather than a description."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, list):
        return bool(value) and all(
            not isinstance(row, (dict, list)) for row in value)
    if isinstance(value, dict):
        return False
    return bool(re.search(r"\d", str(value)[:60]))


def _coverage(ask, payload):
    """Which fields answer this ask, and how much of it they cover.

    A part of the ask counts as covered only if some field matches it, and the
    verdict is "answered" only when every content head is covered -- one shared
    noun ("table") must not stand in for the rest of the question ("ablation").
    """
    heads = _heads(ask) - _WHOLE_DOCUMENT
    if not heads and _heads(ask):
        # Chinese has no whole-document particles to strip.
        heads = set(_heads(ask))
    if not heads:
        return None, 0.0, []
    wants_substance = bool(heads & _CONTENT_ACTION)
    quantity = _wants_number(ask)
    matched = set()
    names = []
    for name in payload:
        if name.startswith("request_") or name in ("run", "self_check"):
            continue
        value = payload.get(name)
        if wants_substance and not _substantive(value):
            continue
        if quantity and not _numeric_answer(value):
            continue
        # A structured field answers through its name. Only a prose field can
        # also answer through what it says -- otherwise one reference title
        # containing the word "summarize" would answer "summarise the paper".
        have = _name_stems(name)
        # Prose may only complete an answer for a field that is already about
        # the question. Letting any long string contribute heads is how the
        # abstract came to answer a question about the learning rate.
        named_heads = heads & have
        if isinstance(value, str) and named_heads:
            have |= set(s for s in _content(value[:4000]) if s not in _STOP)
        got = heads & have
        if got:
            matched |= got
            named = heads & _name_stems(name)
            names.append((bool(named), len(got), name))
    if not names:
        return None, 0.0, []
    names.sort(reverse=True)
    score = len(matched) / float(len(heads))
    return names[0][2], score, sorted(matched)


def attach(bundle, doc, task_text):
    """Record the ask, and for each part of it whether this run answered it."""
    request = parse(task_text)
    if not (task_text or "").strip():
        # Nothing to answer is a fact worth stating: otherwise a reader cannot
        # tell a case that asked nothing from one this run failed to read.
        request = {"asks": [], "targets": [], "language": None,
                   "format": None, "chars": 0}
        bundle.put("request_summary", request)
        bundle.anchor_generated("request_summary")
        bundle.put("request_coverage", [])
        bundle.anchor_generated("request_coverage")
        bundle.put("request_coverage_summary",
                   {"asks": 0, "targets": 0, "answered": 0, "total": 0,
                    "ratio": None,
                    "note": "本案件未提供 task.md，按整体解析执行，无逐条询问可对照"})
        bundle.anchor_generated("request_coverage_summary")
        bundle.note("本案件没有 task.md，未提出逐条询问；本结果按整体解析执行。")
        return False
    if not request["asks"] and not request["targets"]:
        return False

    bundle.put("request_summary", request)
    bundle.anchor_generated("request_summary")

    payload = bundle.payload
    coverage = []
    format_heads = set(["json", "markdown", "yaml", "csv", "latex", "tabl",
                        "bibtex"])
    for ask in request["asks"]:
        heads = _heads(ask)
        fmt = request.get("format")
        if fmt and heads and heads <= (format_heads | set([_stem(fmt)])):
            coverage.append({
                "kind": "ask",
                "request": ask,
                "state": "answered",
                "field": "run",
                "match": 1.0,
                "matched_terms": sorted(heads),
                "note": "该问只限定输出格式；result.json 本身即为该格式，"
                        "无需另设字段",
            })
            continue
        # A Chinese ask yields no ASCII heads at all; excusing it as "the
        # whole document" would mark an unanswered translation as answered.
        bare_ask = (not heads or heads <= _WHOLE_DOCUMENT) and (
        not _CJK.search(ask) or not _cjk_terms(ask))
        if bare_ask:
            coverage.append({
                "kind": "ask",
                "request": ask,
                "state": "answered",
                "field": "document_stats",
                "match": 1.0,
                "matched_terms": sorted(heads),
                "note": "该问未点名材料的任何局部（或只要求解析整篇）；"
                        "本次运行的解析结果本身即为答案，明细见文档统计与各结构字段",
            })
            continue
        field, score, matched = _coverage(ask, payload)
        if score >= 0.5 and _wants_number(ask):
            body = _body_text(payload.get(field)) if field else ""
            if not re.search(r"\d", body):
                coverage.append({
                    "kind": "ask",
                    "request": ask,
                    "state": "partially_answered",
                    "field": field,
                    "match": round(score, 3),
                    "matched_terms": matched,
                    "note": "该问要的是数量，命中字段 %s 里没有数值；"
                            "不以文字描述充数" % field,
                })
                bundle.gap(item="案件问题只部分回答：%s" % ask[:80],
                           reason="该问要数量，字段 %s 中无数值可引，未凭空给出" % field,
                           field="request_coverage", state="partial")
                continue
        if score >= 1.0 - 1e-9:
            state = "answered"
        elif score > 0:
            state = "partially_answered"
        else:
            state = "not_answered"
        coverage.append({
            "kind": "ask",
            "request": ask,
            "state": state,
            "field": field,
            "match": round(score, 3),
            "matched_terms": matched,
            "note": (None if state == "answered" else
                     "本次运行的产出只覆盖该问的一部分（命中 %s），"
                     "未命中部分如实标出，不以相近字段充数" % "、".join(matched)
                     if state == "partially_answered" else
                     "本次运行的产出没有对应这一问的字段，已如实标为未回答"),
        })
        if state != "answered":
            bundle.gap(item="案件问题%s：%s" % ("只部分回答" if state == "partially_answered"
                                                else "未回答", ask[:80]),
                       reason=("材料可抽取的字段覆盖不到该问的全部要求（命中 %s）；"
                               "未用相近字段充数，需人工或由委托方补答"
                               % ("、".join(matched) or "无")),
                       field="request_coverage", state="partial")

    for target in request["targets"]:
        present = _target_present(doc, target)
        coverage.append({
            "kind": target["kind"],
            "request": "%s %s" % (target["kind"], target["label"]),
            "state": "present" if present else "absent_from_material",
            "field": None,
            "match": None,
            "note": (None if present else
                     "案件点名该%s，但材料里没有识别到它；"
                     "不臆造内容，按缺失登记" % target["kind"]),
        })
        if not present:
            bundle.gap(item="案件点名的 %s %s 未在材料中找到"
                            % (target["kind"], target["label"]),
                       reason="材料中不存在该对象（或未能识别），未以相近对象替代",
                       field="request_coverage", state="partial")

    answered = sum(1 for row in coverage if row["state"] in ("answered", "present"))
    bundle.put("request_coverage", coverage)
    bundle.anchor_generated("request_coverage")
    summary = {
        "asks": len(request["asks"]),
        "targets": len(request["targets"]),
        "answered": answered,
        "total": len(coverage),
        "ratio": round(answered / float(len(coverage)), 4) if coverage else None,
    }
    bundle.put("request_coverage_summary", summary)
    bundle.anchor_generated("request_coverage_summary")
    bundle.note("案件诉求覆盖 %d/%d：逐条登记在上表，未回答与材料缺失分别标明。"
                % (answered, len(coverage)))
    return True
