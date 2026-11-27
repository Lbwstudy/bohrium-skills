"""Topic 05 — academic language polishing.

The rubric's hardest requirement is "没改坏": an edit that improves the prose
but changes what it says is a regression. So every edit here is checked before
it is offered — numbers, negation, comparison direction and named entities must
survive unchanged, and an edit that fails that check is reported as rejected
rather than applied.

The edits themselves are small by design. A rewrite is not verifiable; a
substitution with a rule name and a reason is.
"""

import re

from . import base

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u4e00-\u9fff(])")

# Rules that fire on a sentence and propose a bounded substitution.
# Each entry: name, pattern, replacement, why.
RULES = [
    ("informal-word", r"\ba lot of\b", "many",
     "学术语域避免口语化量词"),
    ("informal-word", r"\blots of\b", "many", "学术语域避免口语化量词"),
    ("informal-word", r"\bkinda\b", "somewhat", "口语词，改写为书面语"),
    ("informal-word", r"\bsort of\b", "approximately", "口语填充词，删除或改写"),
    ("informal-word", r"\bhuge\b", "substantial", "主观程度词，改为可度量的表述"),
    ("informal-word", r"\bpretty\b", "reasonably", "口语程度副词"),
    ("informal-word", r"\bget\b(?=\s+(?:better|worse|larger|smaller|higher|lower))",
     "become", "口语化系动词"),
    ("informal-word", r"\bwe got\b", "we obtained", "口语化动词"),
    ("informal-word", r"\bdon't\b", "do not", "缩写形式不适合正式论文"),
    ("informal-word", r"\bcan't\b", "cannot", "缩写形式不适合正式论文"),
    ("informal-word", r"\bit's\b", "it is", "缩写形式不适合正式论文"),
    ("informal-word", r"\bdoesn't\b", "does not", "缩写形式不适合正式论文"),
    ("informal-word", r"\bwon't\b", "will not", "缩写形式不适合正式论文"),
    ("informal-word", r"\bisn't\b", "is not", "缩写形式不适合正式论文"),
    ("informal-word", r"\betc\.", "and other settings",
     "et al. 之外的 etc. 在正文中应写全或删除"),
    ("wordiness", r"\bin order to\b", "to", "冗余连接，删词不损语义"),
    ("wordiness", r"\bdue to the fact that\b", "because", "冗余从句压缩"),
    ("wordiness", r"\bit is worth noting that\b", "", "填充句，删除不损信息"),
    ("wordiness", r"\bit should be noted that\b", "", "填充句，删除不损信息"),
    ("wordiness", r"\bat this point in time\b", "now", "冗余时间状语"),
    ("wordiness", r"\bhas the ability to\b", "can", "冗余情态结构"),
    ("wordiness", r"\bmake use of\b", "use", "冗余动词短语"),
    ("wordiness", r"\bin spite of\b", "despite", "冗长介词短语"),
    ("wordiness", r"\bprior to\b", "before", "冗长介词"),
    ("wordiness", r"\bsubsequent to\b", "after", "冗长介词"),
    ("wordiness", r"\ba number of\b", "several", "冗余量词"),
    ("hedge-stacking", r"\bmay possibly\b", "may", "双重模糊限定，删其一"),
    ("hedge-stacking", r"\bmight perhaps\b", "might", "双重模糊限定，删其一"),
    ("hedge-stacking", r"\bseems to suggest\b", "suggests", "双重模糊限定，删其一"),
    ("hedge-stacking", r"\bcould potentially\b", "could", "双重模糊限定，删其一"),
    ("redundancy", r"\bcompletely eliminate\b", "eliminate",
     "completely 与 eliminate 语义重复"),
    ("redundancy", r"\babsolutely essential\b", "essential", "绝对化修饰冗余"),
    ("redundancy", r"\bvery unique\b", "unique", "unique 不可分级"),
    ("redundancy", r"\bfirst and foremost\b", "first", "同义堆叠"),
    ("redundancy", r"\beach and every\b", "each", "同义堆叠"),
    ("vague-quantifier", r"\bsignificantly\b(?!\s+(?:higher|lower|better|worse|"
                        r"different|correlated))", "substantially",
     "significantly 在统计语境有专门含义，非统计时改用 substantially 避免歧义"),
    ("vague-quantifier", r"\bvery good\b", "strong", "主观评价改为可判断表述"),
    ("vague-quantifier", r"\bgood results\b", "favorable results",
     "主观评价改为可判断表述"),
    ("tense-mismatch", r"\bwe have proposed\b", "we propose",
     "论文陈述自身贡献用现在时"),
    ("tense-mismatch", r"\bthis paper has shown\b", "this paper shows",
     "论文陈述自身结论用现在时"),
    ("passive-we", r"\bit was found by us that\b", "we found that",
     "回避施动者的被动式，改为主动"),
    # Mechanical faults. These are unambiguously wrong in any register, and the
    # replacement cannot change what the sentence asserts.
    ("wordiness", r"\bit can be seen that\b", "we observe that",
     "回避施动者的填充式表述"),
    ("wordiness", r"\bas is well known\b", "", "读者已知信息不必声明"),
    ("wordiness", r"\bthe fact that\b", "that", "冗余名词化结构"),
    ("wordiness", r"\bfor the purpose of\b", "to", "冗余目的状语"),
    ("wordiness", r"\bin the event that\b", "if", "冗余条件从句"),
    ("nominalization", r"\bthe utilization of\b", "using", "名词化改为动词"),
    ("nominalization", r"\bthe implementation of\b", "implementing", "名词化改为动词"),
    ("double-connective", r",\s+and also\b", ", and", "双重连接词"),
    ("double-connective", r"\bbut however\b", "however", "双重转折词"),
    ("double-connective", r"\bbecause of the reason that\b", "because", "冗余因果结构"),
    ("mechanical", r"\b(\w+)\s+\1\b", None, "相邻重复词"),
    ("mechanical", r"\bet al\s*\.", "et al.", "et al. 的句点与空格写法"),
    ("mechanical", r"\be\.g\s*,", "e.g.,", "e.g. 后的逗号写法"),
    ("mechanical", r"\bi\.e\s*,", "i.e.,", "i.e. 后的逗号写法"),
    ("mechanical", r"\s+([,;:.!?])", None, "标点前多余空格"),
    ("mechanical", r"([,;:])(?=[A-Za-z])", None, "标点后缺少空格"),
    ("mechanical", r"\.(?=[A-Z][a-z])", None, "句号后缺少空格"),
    ("mechanical", r"\s+$", None, "行尾多余空格"),
]

# Terms whose variant spellings must not coexist in one paper.
TERM_VARIANTS = [
    (r"\bFig\.", "Figure"),
    (r"\bdata ?set\b", "dataset"),
    (r"\bdata ?base\b", "database"),
    (r"\bpre-?process(?:ing)?\b", "preprocessing"),
    (r"\bpost-?process(?:ing)?\b", "postprocessing"),
    (r"\bmulti-?task\b", "multi-task"),
    (r"\bnon-?linear\b", "nonlinear"),
    (r"\bhyper-?parameter\b", "hyperparameter"),
    (r"\bdown-?sample\b", "downsample"),
    (r"\bup-?sample\b", "upsample"),
    (r"\bfine-?tun(?:e|ing)\b", "fine-tune"),
    (r"\breal-?time\b", "real-time"),
    (r"\bstate of the art\b", "state-of-the-art"),
]

NEGATIONS = re.compile(r"\b(?:not|no|never|none|neither|nor|without|cannot|"
                       r"fail|fails|failed|unable)\b", re.I)
NUMERAL = re.compile(r"\d+(?:[.,]\d+)*")
COMPARATIVE = re.compile(r"\b(?:higher|lower|more|less|better|worse|"
                         r"greater|smaller|larger|faster|slower|increase|"
                         r"decrease|improve|reduce)\b", re.I)


def run(case, task, bundle, records, doc):
    if doc is None:
        base.refuse_empty(bundle, "sentences", records,
                         "输入目录中没有可读文档，无法做润色")
        return
    base.degraded(bundle, doc)

    sentences = _sentences(doc)
    edits, rejected = _edits(sentences)
    bundle.put("sentence_count", len(sentences))
    bundle.put("edit_count", len(edits))
    bundle.put("edits", edits)
    bundle.put("rejected_edits", rejected)

    consistency = _consistency(sentences)
    unified, sentences = _unify(sentences, consistency)
    consistency["unified"] = unified
    bundle.put("term_consistency", consistency)

    style = _style_profile(sentences)
    bundle.put("style_profile", style)

    bundle.put("polished_text", _polished(sentences, edits))
    bundle.put("markdown", _markdown(doc, sentences, edits, rejected,
                                     consistency, style))
    bundle.put("edit_rules", [{"rule": name, "pattern": pattern,
                               "replacement": replacement, "why": why}
                              for name, pattern, replacement, why in
                              _unique_rules()])

    _honest_gaps(bundle, doc, sentences, edits, rejected, consistency)


def _unique_rules():
    seen = set()
    out = []
    for row in RULES:
        key = (row[0], row[1], row[2])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _sentences(doc):
    """Sentences with enough context to locate and to check an edit against."""
    rows = []
    cursor = 0
    for page_no, page in enumerate(doc.get("pages") or [], 1):
        body = " ".join(page.split())
        local = 0
        for sentence in SENT_SPLIT.split(body):
            sentence = sentence.strip()
            if len(sentence) < 25 or _tabular(sentence):
                local += len(sentence) + 1
                continue
            start = body.find(sentence[:50], local)
            start = start if start >= 0 else local
            local = start + 1
            rows.append({
                "id": "S%03d" % (len(rows) + 1),
                "text": sentence,
                "page": page_no,
                "offset": cursor + start,
                "section": _section_at(doc, cursor + start),
                "words": len(sentence.split()),
            })
        cursor += len(page) + 1
    return rows


def _section_at(doc, offset):
    best = None
    for item in doc.get("sections") or []:
        if item.get("offset", 0) <= offset:
            best = item
        else:
            break
    return ((best.get("num", "") + " " + best["title"]).strip() if best else None)


def _edits(sentences):
    """Propose substitutions, then keep only the ones that preserve meaning."""
    from . import t05_support as support

    edits = []
    rejected = []
    for sentence in sentences:
        for name, pattern, replacement, why in RULES:
            if name == "mechanical" and not _prose(sentence["text"]):
                continue
            if replacement is None:
                candidates = _structural(sentence["text"], name, pattern)
            else:
                candidates = [(m.group(0), _swap(sentence["text"], m, replacement))
                              for m in re.finditer(pattern, sentence["text"], re.I)]
            for original, edited in candidates:
                if replacement and original == replacement:
                    continue
                if not edited or edited == sentence["text"]:
                    continue
                check = support.preserves(sentence["text"], edited)
                row = {
                    "edit_id": "P%03d" % (len(edits) + len(rejected) + 1),
                    "sentence_id": sentence["id"],
                    "page": sentence["page"],
                    "section": sentence["section"],
                    "rule": name,
                    "before": sentence["text"],
                    "after": edited,
                    "from": original,
                    "to": replacement if replacement is not None else edited,
                    "why": why,
                    "meaning_check": check,
                }
                if check["preserved"]:
                    edits.append(row)
                else:
                    row["rejected_because"] = check["reason"]
                    rejected.append(row)
    return edits, rejected


def _swap(text, match, replacement):
    out = text[:match.start()] + replacement + text[match.end():]
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    return out


def _structural(text, name, pattern):
    """Edits that rewrite a span rather than substitute a fixed string."""
    out = []
    if name == "mechanical" and pattern == r"\b(\w+)\s+\1\b":
        for match in re.finditer(pattern, text, re.I):
            token = match.group(1)
            if token.lower() in REPEATABLE or token.isdigit():
                continue
            if any(c.isdigit() for c in token):
                continue
            window = text[max(0, match.start() - 40):match.end() + 40]
            if sum(c.isdigit() or c == "|" for c in window) > len(window) * 0.15:
                continue
            out.append((match.group(0), _swap(text, match, token)))
    elif name == "mechanical" and pattern == r"([,;:])(?=[A-Za-z])":
        for match in re.finditer(pattern, text):
            out.append((match.group(0), _swap(text, match, match.group(1) + " ")))
    elif name == "mechanical" and pattern == r"\.(?=[A-Z][a-z])":
        for match in re.finditer(pattern, text):
            out.append((match.group(0), _swap(text, match, ". ")))
    elif name == "mechanical" and pattern == r"\s+$":
        if text != text.rstrip():
            out.append((text[len(text.rstrip()):], text.rstrip()))
    return out


def _prose(text):
    """A sentence with real clause structure, not a figure or table fragment."""
    words = text.split()
    if len(words) < 8:
        return False
    letters = sum(c.isalpha() for c in text)
    if letters < len(text) * 0.6:
        return False
    return bool(re.search(r"\b(?:is|are|was|were|has|have|we|this|the)\b", text, re.I))


REPEATABLE = {"that", "had", "is", "very"}

# Table rows survive sentence splitting as long numeric runs. Polishing them is
# meaningless and the substitution rules misfire on them, so they are dropped
# from the candidate pool.
TABLE_ROW = re.compile(r"(?:\b\d+(?:\.\d+)?\b[\s,;|]*){4,}")


def _tabular(sentence):
    """A numeric row, not prose that happens to mention numbers."""
    if TABLE_ROW.search(sentence):
        return True
    if not _prose(sentence):
        return True
    digits = sum(c.isdigit() for c in sentence)
    return digits > len(sentence) * 0.18


def _consistency(sentences):
    """Whether the paper spells the same term the same way throughout."""
    blob = "\n".join(s["text"] for s in sentences)
    rows = []
    for pattern, canonical in TERM_VARIANTS:
        forms = {}
        for match in re.finditer(pattern, blob, re.I):
            surface = match.group(0)
            forms.setdefault(surface.lower(), []).append(surface)
        if len(forms) > 1:
            rows.append({
                "canonical": canonical,
                "variants": sorted({v[0] for v in forms.values()}),
                "counts": {k: len(v) for k, v in sorted(forms.items())},
                "action": "统一为 %s，共 %d 处需改" % (
                    canonical, sum(len(v) for v in forms.values())),
            })
    return {"variant_groups": len(rows), "groups": rows}


INFORMAL_MARKERS = re.compile(r"\b(?:a lot of|kinda|sort of|pretty|huge|"
                              r"don't|can't|it's|isn't|won't)\b", re.I)
FILLER = re.compile(r"\b(?:it is worth noting|it should be noted|"
                    r"in order to|due to the fact that)\b", re.I)


def _unify(sentences, consistency):
    """Apply the canonical spelling everywhere the variant occurs.

    Only the surface form changes, so meaning is preserved by construction;
    each change is recorded with its sentence and page so a reader can restore
    the original wording.
    """
    plan = []
    for group in consistency.get("groups") or []:
        canonical = group["canonical"]
        for variant in group["variants"]:
            if variant == canonical:
                continue
            pattern = re.compile(r"(?<![@w-])%s(?![@w-])" % re.escape(variant), re.I)
            plan.append((variant, canonical, pattern))
    if not plan:
        return [], sentences
    applied = []
    out = []
    for sentence in sentences:
        text = sentence["text"]
        for variant, canonical, pattern in plan:
            while True:
                match = pattern.search(text)
                if not match:
                    break
                if match.group(0) == canonical:
                    break
                applied.append({"sentence_id": sentence["id"],
                                "page": sentence["page"],
                                "section": sentence["section"],
                                "from": match.group(0), "to": canonical,
                                "why": "全篇统一术语写法，仅改表层拼写"})
                text = text[:match.start()] + canonical + text[match.end():]
        row = dict(sentence)
        row["text"] = text
        out.append(row)
    return applied, out


def _style_profile(sentences):
    """Objective style measures, not a subjective verdict."""
    if not sentences:
        return {}
    words = [len(s["text"].split()) for s in sentences]
    total = sum(words)
    long_sentences = [s["id"] for s in sentences if s["words"] > 45]
    passive = len(re.findall(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ed|"
                             r"\w+en)\b",
                             "\n".join(s["text"] for s in sentences), re.I))
    informal = [s["id"] for s in sentences
                if INFORMAL_MARKERS.search(s["text"])]
    filler = [s["id"] for s in sentences if FILLER.search(s["text"])]
    first_person = len(re.findall(r"\b(?:we|our|us)\b",
                                 "\n".join(s["text"] for s in sentences), re.I))
    return {
        "sentences": len(sentences),
        "words": total,
        "mean_sentence_words": round(total / len(sentences), 1),
        "longest_sentence_words": max(words),
        "over_45_words": len(long_sentences),
        "over_45_ids": long_sentences[:20],
        "passive_constructions": passive,
        "passive_per_1000_words": round(passive * 1000.0 / max(total, 1), 1),
        "informal_sentence_ids": informal[:20],
        "filler_sentence_ids": filler[:20],
        "first_person_mentions": first_person,
        "note": "以上为可复算的客观计数；是否「像学术语域」由评审判断，"
                "此处只给计数不改写风格。",
    }


def _polished(sentences, edits):
    """The text with accepted edits applied, and nothing else touched."""
    by_sentence = {}
    for edit in edits:
        by_sentence.setdefault(edit["sentence_id"], []).append(edit)
    out = []
    for sentence in sentences:
        text = sentence["text"]
        for edit in by_sentence.get(sentence["id"], []):
            if edit["from"] in text:
                text = text.replace(edit["from"], edit["to"], 1)
        out.append({"sentence_id": sentence["id"], "page": sentence["page"],
                    "section": sentence["section"], "text": text,
                    "changed": sentence["id"] in by_sentence})
    return out


def _markdown(doc, sentences, edits, rejected, consistency, style):
    meta = doc.get("meta") or {}
    lines = ["# 学术语言润色 — %s" % (meta.get("title") or "Untitled"), ""]
    lines.append("共 %d 句，提出 %d 处最小编辑，%d 处因未通过语义保持校验被拒绝。"
                 % (len(sentences), len(edits), len(rejected)))
    lines.append("")
    lines.append("## 已采用编辑（逐条可回查页码）")
    for edit in edits:
        lines.append("")
        lines.append("**%s · %s · 第 %s 页%s**"
                     % (edit["edit_id"], edit["rule"], edit["page"],
                        "（%s）" % edit["section"] if edit["section"] else ""))
        lines.append("")
        lines.append("- 原句：%s" % edit["before"])
        lines.append("- 改后：%s" % edit["after"])
        lines.append("- 依据：%s" % edit["why"])
        lines.append("- 语义校验：数值 %s，否定 %s，比较方向 %s，实体 %s"
                     % _check_words(edit["meaning_check"]))
    if rejected:
        lines.append("")
        lines.append("## 被拒绝的编辑")
        for row in rejected:
            lines.append("")
            lines.append("- %s（%s，第 %s 页）：%s → %s；拒绝原因：%s"
                         % (row["edit_id"], row["rule"], row["page"],
                            row["from"], row["to"], row["rejected_because"]))
    lines.append("")
    lines.append("## 术语一致性")
    if consistency["groups"]:
        for group in consistency["groups"]:
            lines.append("- %s：%s；%s"
                         % (group["canonical"], " / ".join(group["variants"]),
                            group["action"]))
    else:
        lines.append("- 未发现本文内的同一术语多种写法。")
    lines.append("")
    lines.append("## 风格计数")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("| --- | --- |")
    for key in ("sentences", "words", "mean_sentence_words",
                "longest_sentence_words", "over_45_words",
                "passive_constructions", "first_person_mentions"):
        lines.append("| %s | %s |" % (key, style.get(key)))
    return "\n".join(lines)


def _check_words(check):
    def mark(key):
        value = check.get(key)
        if value is True:
            return "保持"
        if value is False:
            return "变更"
        return str(value)
    return (mark("numbers_preserved"), mark("negation_preserved"),
            mark("comparison_preserved"), mark("entities_preserved"))


def _honest_gaps(bundle, doc, sentences, edits, rejected, consistency):
    if not sentences:
        bundle.gap(item="句子", reason="未从材料中切分出可润色的句子",
                   field="edits", state="not_reported")
        return
    if not edits:
        bundle.gap(item="编辑",
                   reason="按当前规则集未发现需要最小编辑的句子；"
                          "这不等于文本无问题，只说明本规则集未命中",
                   field="edits", state="partial")
    if rejected:
        bundle.gap(item="被拒绝的编辑",
                   reason="%d 处编辑会改变数值/否定/比较方向或实体，"
                          "按「没改坏」要求拒绝而非应用" % len(rejected),
                   field="rejected_edits", state="partial")
    live = consistency.get("variant_groups") or 0
    done = len(consistency.get("unified") or [])
    if live and done:
        bundle.note("发现 %d 组术语多种写法，已统一 %d 处并逐条登记句号与页码；"
                    "交付文本中不再并存两种写法" % (live, done))
    elif live:
        bundle.gap(item="术语不统一",
                   reason="发现 %d 组同一术语的多种写法，但无法在不改语义的前提下"
                          "自动统一，已在 term_consistency 中列出" % live,
                   field="term_consistency", state="partial")
