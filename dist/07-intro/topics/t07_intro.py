"""Topic 07 — introduction and related-work writing.

The rubric asks whether the opening stands up: is the background real, is prior
work grouped rather than listed, is the gap stated as a gap and not as an
insult, and does every claim point at a citation or at the paper itself.

So this module does not write prose. It recovers the argumentative skeleton the
paper already has — what problem, what others did, what was left open, what this
paper claims — and checks the skeleton for the faults that make an introduction
fail: a citation that is claimed but missing from the reference list, a related
work section that is a flat list, a contribution with no corresponding result,
a gap statement that never names a gap.
"""

import re

from . import base

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u4e00-\u9fff(])")

GAP_CUES = [
    r"\bhowever\b", r"\bnevertheless\b", r"\bremains? (?:un|open|a challenge)",
    r"\bhas not been\b", r"\bhave not been\b", r"\blimited\b", r"\black(?:s|ing)?\b",
    r"\bdifficult(?:y|ies)?\b", r"\bchalleng\w*\b", r"\bsuffer\w*\b",
    r"\bdegrad\w*\b", r"\bbottleneck\b", r"\bnot well\b", r"\bunclear\b",
]
GAP_RE = [re.compile(p, re.I) for p in GAP_CUES]

CONTRIB_CUES = [
    r"\bwe (?:propose|present|introduce|develop|show|demonstrate|find|"
    r"provide|contribute)\b",
    r"\bthis (?:paper|work|study)\b",
    r"\bour (?:contribution|approach|method|work|results?|main)\b",
    r"\bto the best of our knowledge\b",
]
CONTRIB_RE = [re.compile(p, re.I) for p in CONTRIB_CUES]

BACKGROUND_CUES = [
    r"\b(?:recent|previous|prior|earlier|existing)\b",
    r"\bhas (?:been )?(?:attracted|advanced|progressed|improved)\b",
    r"\bstate[- ]of[- ]the[- ]art\b",
    r"\b(?:deep|convolutional|neural) networks?\b",
]
BACKGROUND_RE = [re.compile(p, re.I) for p in BACKGROUND_CUES]

# Verbs that move a related-work group from "listed" to "compared".
COMPARE_VERBS = re.compile(r"\b(?:outperform\w*|improv\w*|differ\w*|"
                           r"unlike|in contrast|whereas|while|but|"
                           r"similar\w*|share\w*|extend\w*|generaliz\w*|"
                           r"fail\w*|suffer\w*|limited to)\b", re.I)

CITATION = re.compile(r"\[(\d{1,3}(?:\s*[,\u2013-]\s*\d{1,3})*)\]")


def run(case, task, bundle, records, doc):
    if doc is None:
        base.refuse_empty(bundle, "sections", records,
                         "输入目录中没有可读文档，无法重建引言结构")
        return
    base.degraded(bundle, doc)

    intro = _intro(doc)
    related = _related(doc)
    contributions = _contributions(doc, intro)
    gaps = _gaps(intro)
    background = _background(intro)

    bundle.put("introduction_section", intro.get("title"))
    bundle.put("introduction_paragraphs", intro.get("paragraphs", 0))
    bundle.put("background_moves", background)
    bundle.put("gap_statements", gaps)
    bundle.put("contributions", contributions)
    bundle.put("related_work", related)
    bundle.put("citation_audit", _citation_audit(doc, intro))
    bundle.put("skeleton", _skeleton(intro, background, gaps, contributions,
                                     related))
    bundle.put("outline_markdown", _markdown(doc, intro, background, gaps,
                                             contributions, related))

    _honest_gaps(bundle, doc, intro, related, contributions, gaps)


AUTHOR_YEAR = re.compile(r"\(([^()]{2,120}?)\)")
AUTHOR_YEAR_PART = re.compile(
    r"([A-Z][\w\u00c0-\u024f'\-]+(?:\s+[A-Z][\w\u00c0-\u024f'\-]+)?"
    r"(?:\s+(?:et\s+al\.?|and\s+[A-Z][\w\u00c0-\u024f'\-]+))?)"
    r"[,\s]\s*((?:19|20)\d{2})[a-z]?")


def _section_rows(doc):
    return doc.get("sections") or []


def _with_children(doc, row):
    """One section plus every subsection beneath it, in document order."""
    num = (row.get("num") or "").strip()
    if not num:
        return row
    rows = [row]
    for other in _section_rows(doc):
        other_num = (other.get("num") or "").strip()
        if other_num and other_num != num and other_num.startswith(num + "."):
            rows.append(other)
    if len(rows) == 1:
        return row
    rows.sort(key=lambda r: r.get("offset") or 0)
    merged = dict(row)
    merged["body"] = "\n\n".join((r.get("body") or "") for r in rows)
    return merged


def _section_text(doc, row):
    """Body of one section.

    The structure pass already carved each section's own text, so re-cutting it
    from the joined document would reintroduce the child-section bleed that
    carving was meant to stop.
    """
    return row.get("body") or ""


def _find(doc, pattern):
    for row in _section_rows(doc):
        title = row.get("title") or ""
        if re.search(pattern, title, re.I):
            return row
    return None


_FOOTNOTE = re.compile(r"^[\u2217*\u2020\u2021\u00a7\u00b6]\s*\S")
_PAGE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")


_URL = re.compile(r"https?://\S+")


def _tidy_quote(sentence, limit=240, source=""):
    """Drop page furniture and keep only what the source really contains."""
    if not sentence:
        return sentence
    cut = sentence.split("\x0c")[0]
    kept = []
    for line in cut.split("\n"):
        bare = line.strip()
        if not bare:
            continue
        if _PAGE_NUMBER.match(bare) or _FOOTNOTE.match(bare):
            continue
        kept.append(bare)
    tidied = _URL.sub(" ", " ".join(kept))
    tidied = " ".join(tidied.split())[:limit]
    if not source:
        return tidied
    flat = " ".join(source.split())
    if tidied in flat:
        return tidied
    # The sentence carries something the page interleaved; publish the longest
    # prefix that is genuinely on the page rather than a string of our own.
    for cut_at in range(len(tidied) - 1, 39, -1):
        head = tidied[:cut_at].rstrip(" ,;:")
        if head and head in flat:
            return head
    return tidied[:40].rstrip(" ,;:")


def _intro(doc):
    row = _find(doc, r"^(?:introduction|background)$") or _find(doc, r"introduction")
    if not row:
        return {}
    body = _section_text(doc, row)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if len(p.strip()) > 60]
    return {
        "title": ((row.get("num") or "") + " " + row["title"]).strip(),
        "body": body,
        "paragraphs": len(paragraphs),
        "page": _page_of(doc, row.get("offset") or 0),
        "sentences": [_tidy_quote(s, source=doc.get("text") or "")
                      for s in SENT_SPLIT.split(body) if len(s.strip()) >= 30],
    }


def _related(doc):
    row = _find(doc, r"related work|prior work|literature review|background and")
    if not row:
        return {"found": False,
                "state": "not_applicable",
                "reason": "该稿件没有独立的 Related Work 章节；相关工作并入引言"
                          "或其他章节，属结构选择而非抽取失败"}
    row = _with_children(doc, row)
    body = _section_text(doc, row)
    sentences = [_tidy_quote(s, source=doc.get("text") or "")
                 for s in SENT_SPLIT.split(body) if len(s.strip()) >= 30]
    cited = set()
    author_year = set()
    for sentence in sentences:
        for match in CITATION.finditer(sentence):
            for part in re.split(r"[,\u2013-]", match.group(1)):
                part = part.strip()
                if part.isdigit():
                    cited.add(int(part))
        for match in AUTHOR_YEAR.finditer(sentence):
            for part in AUTHOR_YEAR_PART.finditer(match.group(1)):
                author_year.add((part.group(1).lower(), part.group(2)))
    comparing = [s for s in sentences if COMPARE_VERBS.search(s)]
    # Grouping: a related-work paragraph that names several works and then says
    # how they relate is a group; one that only lists is a list.
    groups = []
    for index, sentence in enumerate(sentences):
        names = CITATION.findall(sentence)
        if not names:
            continue
        groups.append({
            "index": index + 1,
            "citations": len(names),
            "comparative": bool(COMPARE_VERBS.search(sentence)),
            "quote": sentence[:200],
            "page": _page_of(doc, (row.get("offset") or 0) + body.find(sentence[:40])),
        })
    flat = [g for g in groups if not g["comparative"]]
    return {
        "found": True,
        "title": ((row.get("num") or "") + " " + row["title"]).strip(),
        "sentences": len(sentences),
        "paragraphs": len([p for p in re.split(r"\n\s*\n", body) if len(p.strip()) > 60]),
        "distinct_citations": len(cited) + len(author_year),
        "citation_ids": sorted(cited)[:60],
        "author_year_citations": sorted("%s %s" % (a, y)
                                        for a, y in author_year)[:60],
        "comparative_sentences": len(comparing),
        "listed_only": len(flat),
        "organisation": "grouped" if len(comparing) >= max(2, len(groups) // 3)
                        else "listed",
        "groups": groups[:25],
        "missing_comparison": [g["quote"] for g in flat][:10],
    }


def _background(intro):
    """The opening moves: what the field looks like before this paper."""
    sentences = intro.get("sentences") or []
    hits = []
    for index, sentence in enumerate(sentences[:12]):
        if any(p.search(sentence) for p in BACKGROUND_RE):
            hits.append({"index": index + 1, "quote": sentence[:220],
                         "citations": len(CITATION.findall(sentence))})
    return {
        "found": len(hits),
        "moves": hits,
        "cited_ratio": round(len([h for h in hits if h["citations"]])
                             / max(len(hits), 1), 3),
        "note": "背景陈述若无引用，读者无法核对该陈述是否成立。",
    }


def _gaps(intro):
    sentences = intro.get("sentences") or []
    hits = []
    for index, sentence in enumerate(sentences):
        for pattern in GAP_RE:
            if pattern.search(sentence):
                hits.append({"index": index + 1, "quote": sentence[:240],
                             "cue": pattern.pattern.strip("\\b")[:40],
                             "page": intro.get("page")})
                break
    named = [h for h in hits if re.search(r"\b(?:because|since|due to|"
                                          r"caused by|as a result)\b",
                                          h["quote"], re.I)]
    return {
        "count": len(hits),
        "statements": hits[:15],
        "explains_cause": len(named),
        "note": "只陈述「存在困难」而未说明成因的空白陈述，读者无法判断"
                "本文是否真的填上了它。",
    }


_FRAGMENT = re.compile(r"^(?:\(\w*\d{4}[a-z]?\)|[A-Z]\.)[,;:]")
# A pointer to where something is shown is not a statement of what the paper
# contributes, however much it looks like one.
_POINTER = re.compile(r"\b(?:we (?:provide|give|show|refer|point|describe|list)"
                      r"[^.]{0,60}?(?:appendix|supplementar|footnote|"
                      r"the supplementary material)|see (?:appendix|section)|"
                      r"(?:is|are) (?:given|shown|listed|described) in "
                      r"(?:appendix|the appendix|supplementar))\b", re.I)

_ROADMAP = re.compile(r"\b(?:the )?contributions? of (?:our|this) (?:paper|work)"
                      r"\b|\bour contributions? (?:are|can be summarized)\b", re.I)


_BULLET_SPLIT = re.compile(r"\n\s*[\u2022\u00b7\u25cf\u25aa\u2023-]\s*")


def _claims(sentence):
    """Split a contribution sentence into independently checkable claims.

    Contribution lists are written as bullets and survive extraction as one
    run of text headed by a roadmap line, so splitting here is what lets each
    bullet be checked against the body on its own.
    """
    parts = _BULLET_SPLIT.split(sentence)
    out = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # the header asserts nothing on its own
        part = _ROADMAP.sub("", part).strip(" :\n")
        if len(part) < 30 or _FRAGMENT.match(part) or _POINTER.search(part):
            continue
        out.append(part)
    return out


def _add_claim(sentence, ordinal, doc, results, hits, intro):
    numbers = re.findall(r"\d+(?:\.\d+)?\s*%?", sentence)
    support = (_best_match(sentence, results)
               or _comparative_support(sentence, results)
               or _artifact_support(sentence, doc))
    hits.append({
        "index": ordinal,
        "quote": sentence[:240],
        "has_number": bool(numbers),
        "numbers": numbers[:5],
        "supporting_result": support,
        "supported": bool(support),
        "page": intro.get("page"),
    })


def _contributions(doc, intro):
    """Claims of contribution, paired with the result that would support each."""
    sentences = intro.get("sentences") or []
    hits = []
    results = _result_sentences(doc)
    for index, sentence in enumerate(sentences):
        bulleted = bool(_BULLET_SPLIT.search(sentence))
        for claim in _claims(sentence):
            # A bullet inherits its status from the list header; a plain
            # sentence has to announce itself.
            if not bulleted and not any(p.search(claim) for p in CONTRIB_RE):
                continue
            _add_claim(claim, index + 1, doc, results, hits, intro)
    return {
        "count": len(hits),
        "statements": hits[:15],
        "unsupported": [h["quote"] for h in hits if not h["supported"]][:10],
        "note": "贡献陈述若在正文中找不到对应结果，评审无法核验其成立。",
    }


def _result_sentences(doc):
    out = []
    body = doc.get("text") or ""
    for sentence in SENT_SPLIT.split(body):
        sentence = sentence.strip()
        if len(sentence) < 30:
            continue
        if re.search(r"\d+(?:\.\d+)?\s*%|\b(?:error rate|accuracy|top-1|top-5|"
                     r"BLEU|F1|mAP|perplexity|IoU|AUC)\b", sentence, re.I):
            if sentence not in out:
                out.append(sentence)
    return out


# A contribution is supported when the body reports the thing the claim named,
# not when the prose happens to share common words with it. "We present
# comprehensive experiments on ImageNet" shares almost no vocabulary with
# "achieves 3.57% error on the 152-layer ResNet", yet that number is exactly
# what makes the claim checkable.
METRIC_RE = re.compile(
    r"\b(?:error rate|top-1|top-5|accuracy|BLEU|F1|mAP|perplexity|IoU|AUC|"
    r"mismatch rate|word error rate)\b", re.I)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
DATASET_RE = re.compile(
    r"\b(?:ImageNet|CIFAR(?:-10|-100)?|COCO|MNIST|PASCAL VOC|"
    r"GLUE|SuperGLUE|MNLI|SNLI|SQuAD|WMT|CoNLL|SWAG|BooksCorpus|"
    r"PTB|WikiText|One Billion Word)\b", re.I)


_SYSTEM_STOP = frozenset("""The This These Those Our We It Its They Their In On For With
A An As At By From However Moreover Furthermore Therefore Thus Hence Although
While When Where What Which That There Here Table Figure Section Appendix
Algorithm Equation Model Models Method Methods Approach Approaches Paper Work
Study Result Results Experiment Experiments Training Data Set Dataset Task Tasks
Neural Deep Language Natural Learning Machine Computer Vision Image Images
Network Networks Layer Layers Attention Word Words Sentence Sentences
Baseline Baselines State Art Architecture Architectures""".split())
_SYSTEM = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*\b")


def _named_systems(sentence):
    """Capitalised system or model names, minus sentence-initial English."""
    return {m.group(0) for m in _SYSTEM.finditer(sentence)
            if m.group(0) not in _SYSTEM_STOP and len(m.group(0)) >= 2}


def _evidence(sentence):
    """What a sentence makes checkable: metrics, numbers, datasets."""
    return {"metric": {m.group(0).lower() for m in METRIC_RE.finditer(sentence)},
            "dataset": {m.group(0).lower() for m in DATASET_RE.finditer(sentence)},
            "numbers": {n.group(0).replace(" ", "") for n in NUMBER_RE.finditer(sentence)},
            "systems": _named_systems(sentence)}


_DEFINE_CUE = re.compile(
    r"\b(?:consists? of|comprised? of|composes? of|is (?:a|an|the)|are (?:a|an|the)|"
    r"architecture|framework|structure|formulat|defined as|we (?:describe|detail|"
    r"introduce|present|design|build|stack|compose))\b", re.I)


def _artifact_support(claim, doc, need=3):
    """A body sentence that defines the thing the claim says it introduces.

    A claim about a method needs the method, not a score. Requiring a number
    from every contribution reported the paper's own framework as unsupported.
    """
    words = _content(claim)
    if not words:
        return None
    for sentence in SENT_SPLIT.split(doc.get("text") or ""):
        sentence = sentence.strip()
        if len(sentence) < 40 or not _DEFINE_CUE.search(sentence):
            continue
        if len(words & _content(sentence)) >= need:
            return {"quote": sentence[:240], "kind": "artifact"}
    return None


_COMPARATIVE_CUE = re.compile(
    r"\b(?:outperform\w*|surpass\w*|better than|exceed\w*|improv\w*|"
    r"higher than|lower than|more accurate|gain\w*)\b", re.I)


def _comparative_support(claim, results):
    """A results sentence that makes a comparison and reports a quantity.

    A qualitative finding ("X outperforms previous approaches") carries no
    number, so scoring it against numbers alone reports every such finding as
    unsupported even when the results table is right there.
    """
    if not _COMPARATIVE_CUE.search(claim):
        return None
    for sentence in results:
        if isinstance(sentence, dict):
            text = sentence.get("quote") or ""
            page = sentence.get("page")
        else:
            text = sentence or ""
            page = None
        if not _COMPARATIVE_CUE.search(text):
            continue
        if not NUMBER_RE.search(text):
            continue
        return {"quote": text[:240], "kind": "comparison",
                "page": page, "score": 0.5}
    return None


def _best_match(claim, results, threshold=0.28):
    """The result sentence that carries the evidence the claim needs.

    Three signals, in decreasing order of how much they prove:
      * a numeric result the claim itself already stated (the strongest, since
        the paper says the same figure twice);
      * the same metric or dataset named in both;
      * content-word overlap, used only as a tie-breaker so two unrelated
        sentences cannot be paired on shared filler.
    """
    claim_ev = _evidence(claim)
    claim_words = _content(claim)
    best, best_score = None, 0.0
    for sentence in results:
        ev = _evidence(sentence)
        score = 0.0
        if claim_ev["numbers"] & ev["numbers"]:
            score += 0.6
        if claim_ev["metric"] & ev["metric"]:
            score += 0.25
        if claim_ev["dataset"] & ev["dataset"]:
            score += 0.2
        # Naming the same system in a sentence that reports a figure is what
        # makes a claim checkable when the claim itself carries no number.
        if claim_ev["systems"] & ev["systems"] and (ev["numbers"] or ev["metric"]):
            score += 0.5
        words = _content(sentence)
        if words and claim_words:
            score += 0.4 * len(claim_words & words) / len(claim_words)
        if score > best_score:
            best_score, best = score, sentence
    if best and best_score >= threshold:
        return {"quote": best[:240], "score": round(best_score, 3)}
    return None


def _content(text):
    stop = {"the", "a", "an", "of", "and", "to", "in", "for", "on", "with",
            "we", "our", "this", "that", "is", "are", "be", "as", "by", "it",
            "from", "at", "or", "which", "can", "has", "have", "been", "not"}
    return {w.lower() for w in re.findall(r"[A-Za-z]{3,}", text)
            if w.lower() not in stop}


def _citation_audit(doc, intro):
    """Every citation the introduction makes, checked against the reference list."""
    refs = doc.get("references") or []
    known = {r["index"] for r in refs}
    used = set()
    for sentence in intro.get("sentences") or []:
        for match in CITATION.finditer(sentence):
            for part in re.split(r"[,\u2013-]", match.group(1)):
                part = part.strip()
                if part.isdigit():
                    used.add(int(part))
    dangling = sorted(used - known) if known else []
    return {
        "cited_in_intro": len(used),
        "reference_entries": len(refs),
        "dangling": dangling,
        "dangling_note": ("引言引用了不存在的编号：%s" % dangling) if dangling
                         else "引言所用的编号均能在参考文献表中找到",
        "if_no_references": "参考文献为空时无法判断编号是否有效，"
                            "此处不给出「全部有效」的结论" if not known else None,
    }


def _skeleton(intro, background, gaps, contributions, related):
    return {
        "background": {"sentences": background.get("found"),
                       "cited_ratio": background.get("cited_ratio")},
        "gap": {"statements": gaps.get("count"),
                "explains_cause": gaps.get("explains_cause")},
        "contributions": {"statements": contributions.get("count"),
                          "supported": contributions.get("count", 0)
                                       - len(contributions.get("unsupported") or [])},
        "related_work": {"found": related.get("found"),
                         "organisation": related.get("organisation"),
                         "distinct_citations": related.get("distinct_citations")},
        "paragraphs": intro.get("paragraphs"),
    }


def _markdown(doc, intro, background, gaps, contributions, related):
    meta = doc.get("meta") or {}
    lines = ["# 引言与相关工作结构审计 — %s" % (meta.get("title") or "Untitled"), ""]
    if not intro:
        lines.append("未找到引言章节，无法重建结构。")
        return "\n".join(lines)
    lines.append("引言：%s，%d 段，%d 句。"
                 % (intro["title"], intro["paragraphs"], len(intro["sentences"])))
    lines.append("")
    lines.append("## 背景")
    lines.append("")
    lines.append("背景陈述 %d 句，其中带引用 %s 比例。"
                 % (background["found"], background["cited_ratio"]))
    for move in background["moves"][:5]:
        lines.append("- %s" % move["quote"])
    lines.append("")
    lines.append("## 研究空白")
    lines.append("")
    lines.append("空白陈述 %d 处，其中说明成因 %d 处。"
                 % (gaps["count"], gaps["explains_cause"]))
    for gap in gaps["statements"][:5]:
        lines.append("- %s" % gap["quote"])
    lines.append("")
    lines.append("## 贡献")
    lines.append("")
    lines.append("贡献陈述 %d 处，能在正文找到对应结果 %d 处。"
                 % (contributions["count"],
                    contributions["count"] - len(contributions["unsupported"])))
    for item in contributions["statements"][:6]:
        mark = "有" if item["supported"] else "未找到"
        lines.append("- %s（支撑：%s）" % (item["quote"], mark))
        if item["supported"]:
            lines.append("  - 对应结果：%s" % item["supporting_result"]["quote"])
    lines.append("")
    lines.append("## 相关工作")
    lines.append("")
    if related.get("found"):
        lines.append("章节：%s；%d 句，%d 条不同引用；组织方式：%s。"
                     % (related["title"], related["sentences"],
                        related["distinct_citations"], related["organisation"]))
        if related.get("missing_comparison"):
            lines.append("")
            lines.append("以下句子只列举文献而未说明与本文的关系：")
            for quote in related["missing_comparison"][:5]:
                lines.append("- %s" % quote)
    else:
        lines.append(related.get("reason"))
    return "\n".join(lines)


def _page_of(doc, offset):
    for item in doc.get("page_offsets") or []:
        if item[0] <= offset < item[1]:
            return item[2]
    return None


def _honest_gaps(bundle, doc, intro, related, contributions, gaps):
    if not intro:
        bundle.gap(item="引言", reason="未识别出引言章节，可能标题不同或为扫描件",
                   field="introduction_section", state="not_reported")
        return
    if not related.get("found"):
        bundle.note("相关工作：%s" % (related.get("reason") or ""))
        bundle.put("related_work_state", "not_applicable")
    if not contributions["count"]:
        bundle.gap(item="贡献", reason="未找到贡献陈述句，可能本文风格不使用"
                   "「we propose」类句式，需人工确认",
                   field="contributions", state="partial")
    elif contributions["unsupported"]:
        bundle.gap(item="贡献无对应结果",
                   reason="%d 处贡献陈述在正文中未找到数值结果支撑，"
                          "已逐条列出而非默认成立"
                          % len(contributions["unsupported"]),
                   field="contributions", state="partial")
    if gaps["count"] and not gaps["explains_cause"]:
        bundle.note("%d 处空白陈述均为现象描述，未说明为何存在该空白；"
                    "这是原文的写法，不是抽取缺失。" % gaps["count"])
