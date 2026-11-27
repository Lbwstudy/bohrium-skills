"""Topic 02 — summaries and structured notes.

The rubric asks whether a note matches the source, whether it keeps what
matters, whether a claim can be found again, and whether the note is usable
downstream. Only the first and third are about writing; the rest are about
whether every note carries a locator that survives being copied elsewhere.

So this module does not write the prose. It mines the paper for the sentences
that carry claims, limits, methods and results, keeps their page and verbatim
text, and hands the agent a fixed note schema to fill. A note that cannot be
traced to a mined sentence is visible as a hole rather than as fluent text.
"""

import re

from . import base

# Cue patterns, ordered by how strongly the sentence signals its own role.
CUES = {
    "claim": [
        r"\bwe (?:propos|present|introduc|show|demonstrat|argu|find|"
        r"conclud|observ|establish|prov|deriv)\w*\b",
        r"\bthis (?:paper|work|study) (?:proposes|presents|shows|argues)\b",
        r"\bwe (?:establish|provide|derive)\b",
        r"\b(?:our|the) (?:key )?(?:contribution|finding|result)s? (?:is|are)\b",
    ],
    "method": [
        # Stems, not whole words: "we trained" is the ordinary way to write a
        # method, and requiring "train" hid every experimental setup section.
        r"\bwe (?:train|evaluat|appl|us|build|construct|design|formulat|"
        r"adopt|follow|fine-?tun|pre-?train|optimiz|initializ|sampl|"
        r"measur|compar|select|choose|split|encod)\w*\b",
        r"\bthe (?:proposed )?(?:method|approach|framework|architecture|model)\b",
        r"\b(?:consists?|comprises?|is composed of|is based on)\b",
    ],
    "result": [
        r"\b(?:outperform|achiev|improv|reduc|surpass|exceed)\w*\b",
        r"\b(?:accuracy|error rate|BLEU|F1|top-1)\b.{0,40}\d",
        r"\b\d+(?:\.\d+)?\s?%\b",
        r"\bstate-of-the-art\b",
    ],
    "limit": [
        r"\b(?:limitation|future work|remains? (?:unclear|open|difficult))\b",
        r"\b(?:fail|fails|fails to|cannot|suffer)\w*\b",
        r"\b(?:however|nevertheless|nonetheless)\b",
        r"\b(?:we|this work) (?:do|does) not\b",
    ],
    "background": [
        r"\b(?:recent|prior|previous|existing) (?:work|studies|approaches|methods)\b",
        r"\b(?:has|have) been (?:widely|extensively|shown)\b",
        r"\bin (?:recent|the last) years\b",
    ],
}
COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in CUES.items()}

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u4e00-\u9fff])")

# The note schema. Fixed on purpose: a downstream reader must be able to parse
# notes from any paper without guessing field names.
NOTE_FIELDS = ["note_id", "kind", "claim", "evidence", "page", "section",
               "terms", "numbers", "confidence", "needs_check"]

CONFIDENCE = {"direct": "原文直接陈述", "inferred": "由原文多句合并得出",
              "unverified": "原文未明确支持"}


def run(case, task, bundle, records, doc):
    if doc is None:
        base.refuse_empty(bundle, "document", records,
                         "输入目录中没有可读的文档")
        return
    base.degraded(bundle, doc)

    mined = _mine(doc)
    notes = _notes(doc, mined)
    notes.extend(_overviews(doc, notes))
    for index, note in enumerate(notes, 1):
        note["note_id"] = "N%03d" % index
    bundle.put("note_count", len(notes))
    bundle.put("notes", notes)
    bundle.put("note_schema", _schema())
    bundle.put("paper_card", _paper_card(doc, mined))
    bundle.put("section_summaries", _section_summaries(doc, mined))
    bundle.put("concept_index", _concepts(doc, notes))
    bundle.put("coverage", _coverage(doc, mined, notes))
    bundle.put("markdown", _markdown(doc, notes))

    _honest_gaps(bundle, doc, mined, notes)


def _mine(doc):
    """Every sentence in the paper, labelled by the role its cues suggest.

    Each row records its character offset in the joined page text, because a
    section boundary is a position in the stream, not a page: several headings
    share a page, and attributing by page alone would file every one of their
    notes under whichever heading happened to be last.
    """
    rows = []
    cursor = 0
    cutoff = _body_cutoff(doc)
    for page_no, page in enumerate(doc.get("pages") or [], 1):
        body, origin = _collapse(page)
        if re.match(r"(?i)^(references|bibliography)\b", body):
            cursor += len(page) + 1
            continue
        local = 0
        for sentence in SENT_SPLIT.split(body):
            sentence = sentence.strip()
            if not sentence:
                continue
            found = body.find(sentence[:60], local)
            if found < 0:
                found = local
            local = found + 1
            if not (40 <= len(sentence) <= 600):
                continue
            offset = cursor + origin[found]
            # The bibliography is not body text. Its entries match the result
            # cues ("… achieves 76.7% top-1") and previously produced 38 notes
            # per paper that said nothing about the paper itself.
            if cutoff is not None and offset >= cutoff:
                continue
            kinds = [kind for kind, patterns in COMPILED.items()
                     if any(p.search(sentence) for p in patterns)]
            if not kinds:
                continue
            rows.append({
                "sentence": sentence,
                "page": page_no,
                "offset": offset,
                "kinds": kinds,
                "numbers": sorted(set(re.findall(r"\d+(?:\.\d+)?%?", sentence)))[:8],
            })
        cursor += len(page) + 1
    return rows


def _body_cutoff(doc):
    """Character offset where the bibliography starts, or ``None``."""
    for item in doc.get("sections") or []:
        title = (item.get("title") or "").strip().lower()
        if title in ("references", "bibliography", "literature cited"):
            return item.get("offset", 0)
    return None


def _collapse(page):
    """Whitespace-collapse a page while remembering where each char came from.

    Sentences are split on the collapsed copy, but section boundaries are
    offsets into the raw stream. Returning the collapsed text alone and then
    searching for the sentence in the raw page silently fails whenever the page
    contains a line break or a double space, and the fallback put every such
    note at the wrong offset — which filed notes under the previous section and
    then reported that section as uncovered.
    """
    chars, origin = [], []
    pending_space = False
    for index, char in enumerate(page):
        if char.isspace():
            pending_space = True
            continue
        if pending_space and chars:
            chars.append(" ")
            origin.append(index)
        chars.append(char)
        origin.append(index)
        pending_space = False
    return "".join(chars), origin


def _section_at(doc, offset):
    """The innermost heading whose body contains this offset."""
    best = None
    for item in doc.get("sections") or []:
        if item.get("offset", 0) <= offset:
            best = item
        else:
            break
    if best is None:
        return None
    return (best.get("num", "") + " " + best["title"]).strip()


def _notes(doc, mined):
    """One note per distinct claim, deduplicated by what it says."""
    notes = []
    seen = set()
    for row in mined:
        if "claim" not in row["kinds"] and "result" not in row["kinds"]:
            continue
        key = re.sub(r"\W+", "", row["sentence"].lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        kind = "result" if "result" in row["kinds"] else "claim"
        notes.append({
            "note_id": "N%03d" % (len(notes) + 1),
            "kind": kind,
            "claim": row["sentence"],
            "evidence": row["sentence"],
            "page": row["page"],
            "section": _section_at(doc, row["offset"]),
            "terms": _terms(row["sentence"]),
            "numbers": row["numbers"],
            "confidence": "direct",
            "needs_check": [],
        })
        if len(notes) >= 200:
            break
    # limits and methods become notes too, with a distinct kind so a reader can
    # separate what the paper claims from what it concedes
    for want, label in (("limit", "limitation"), ("method", "method")):
        for row in mined:
            if want not in row["kinds"]:
                continue
            key = re.sub(r"\W+", "", row["sentence"].lower())[:80]
            if key in seen:
                continue
            seen.add(key)
            notes.append({
                "note_id": "N%03d" % (len(notes) + 1),
                "kind": label,
                "claim": row["sentence"],
                "evidence": row["sentence"],
                "page": row["page"],
                "section": _section_at(doc, row["offset"]),
                "terms": _terms(row["sentence"]),
                "numbers": row["numbers"],
                "confidence": "direct",
                "needs_check": [],
            })
            if len(notes) >= 240:
                break
    return notes


_STOP = set("""the a an of in on for to and or with by as at from is are was were
be been being this that these those we our it its their they them which who whom
whose what when where why how not no than then thus therefore however also such
can could may might must should would will shall do does did has have had more
most less least very much many few some any all both each other into over under
between among during within without through about after before while because
if so but yet still only just even well same different new two three one""".split())


def _terms(sentence):
    """Content words, so a reader can grep the note later by topic."""
    words = re.findall(r"[A-Za-z][A-Za-z-]{3,}", sentence)
    out = []
    for word in words:
        low = word.lower()
        if low in _STOP or low in out:
            continue
        out.append(low)
    return out[:8]


def _schema():
    return {
        "fields": NOTE_FIELDS,
        "field_meaning": {
            "note_id": "稳定标识，便于跨文件引用",
            "kind": "claim / result / method / limitation",
            "claim": "一句话结论，取自原文",
            "evidence": "支撑该结论的原文逐字片段",
            "page": "该片段所在页码（1 基）",
            "section": "所属章节标题，取不到为 null",
            "terms": "可检索的内容词",
            "numbers": "该句出现的数字，供核对",
            "confidence": CONFIDENCE,
            "needs_check": "需人工确认的点",
        },
        "rule": "claim 与 evidence 都必须能在原文逐字找到；找不到时 confidence 标 unverified 并写入 needs_check。",
    }


def _paper_card(doc, mined):
    """The one-screen summary a reader wants before reading anything else."""
    meta = doc.get("meta") or {}
    abstract = (doc.get("abstract") or {}).get("text") or ""
    contributions = [m["sentence"] for m in mined
                     if "claim" in m["kinds"]][:5]
    results = [m for m in mined if "result" in m["kinds"]][:5]
    limits = [m["sentence"] for m in mined if "limit" in m["kinds"]][:3]
    return {
        "title": meta.get("title"),
        "authors": meta.get("authors") or [],
        "year": _year(doc),
        "venue": meta.get("venue"),
        "one_line": _one_line(abstract),
        "abstract": base.excerpt(abstract, 1200) or None,
        "contributions": contributions,
        "key_results": [{"text": r["sentence"], "page": r["page"],
                         "numbers": r["numbers"]} for r in results],
        "stated_limits": limits,
        "section_count": len(doc.get("sections") or []),
        "page_count": len(doc.get("pages") or []),
    }


def _year(doc):
    text = " ".join(doc.get("pages") or [])[:4000]
    found = re.findall(r"\b(19|20)\d{2}\b", text)
    years = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", text)))
    return years[0] if years else None


def _one_line(abstract):
    if not abstract:
        return None
    first = SENT_SPLIT.split(" ".join(abstract.split()))[0]
    return first[:300] if first else None


def _overviews(doc, notes):
    """One verbatim opener for each section that no cue-based note reached.

    Descriptive sections ("3.3 Network Architectures") are written without any
    of the claim/result/method cue phrases, so cue mining leaves them empty
    even though they carry real content. Quoting the section's own opening
    sentence — verbatim, with its page — is the honest minimum: it is not a
    summary this Skill invented, and a reader can jump straight to it.
    """
    covered = {n["section"] for n in notes if n["section"]}
    extra = []
    for item in doc.get("sections") or []:
        title = (item.get("title") or "").strip().lower()
        if title in ("references", "bibliography", "literature cited"):
            continue
        if item.get("chars", 0) < 200:
            continue
        heading = (item.get("num", "") + " " + item["title"]).strip()
        if heading in covered:
            continue
        body = (item.get("body") or "").split("\n", 1)
        if len(body) != 2:
            continue
        sentences = [s.strip() for s in SENT_SPLIT.split(" ".join(body[1].split()))]
        lead = next((s for s in sentences if 40 <= len(s) <= 600), None)
        if not lead:
            continue
        extra.append({
            "note_id": None,
            "kind": "overview",
            "claim": lead,
            "evidence": lead,
            "page": base.page_of_offset(doc, item.get("offset", 0)),
            "section": heading,
            "terms": _terms(lead),
            "numbers": sorted(set(re.findall(r"\d+(?:\.\d+)?%?", lead)))[:8],
            "confidence": "direct",
            "needs_check": [],
        })
        covered.add(heading)
    return extra


def _section_summaries(doc, mined):
    """Per-section: the headings, the opening sentence, and the cues found."""
    rows = []
    for item in doc.get("sections") or []:
        heading = (item.get("num", "") + " " + item["title"]).strip()
        page = base.page_of_offset(doc, item.get("offset", 0))
        body = (item.get("body") or "").split("\n", 1)
        lead = None
        if len(body) == 2:
            sentences = SENT_SPLIT.split(" ".join(body[1].split()))
            lead = sentences[0][:300] if sentences and sentences[0] else None
        here = [m for m in mined if m["page"] == page]
        rows.append({
            "heading": heading,
            "level": item.get("level", 1),
            "page": page,
            "chars": item.get("chars", 0),
            "lead": lead,
            "claims_here": len([m for m in here if "claim" in m["kinds"]]),
            "results_here": len([m for m in here if "result" in m["kinds"]]),
        })
    return rows


def _concepts(doc, notes):
    """Where each recurring term lives, so a reader can jump to the discussion."""
    index = {}
    for note in notes:
        for term in note["terms"]:
            index.setdefault(term, []).append(note["note_id"])
    rows = [{"term": term, "notes": ids[:12], "count": len(ids)}
            for term, ids in index.items() if len(ids) >= 2]
    rows.sort(key=lambda r: (-r["count"], r["term"]))
    return rows[:60]


# Headings whose sections state no claim, so an empty note list is correct.
_BACK_MATTER = re.compile(
    r"(?i)^(?:\d*\.?\s*)?(?:acknowledg\w*|appendix\b|supplementar\w*|"
    r"author contributions?|funding|references?|bibliography|"
    r"conflicts? of interest|ethics statement|reproducibility statement)")


# Headings whose sections state no claim, so an empty note list is correct.
_BACK_MATTER = re.compile(
    r"(?i)^(?:acknowledg\w*|appendix\b|supplementar\w*|"
    r"author contributions?|funding|references?|bibliography|"
    r"conflicts? of interest|ethics statement|reproducibility statement)")


def _coverage(doc, mined, notes):
    """How much of the paper the notes actually account for.

    A section counts as covered when it, or any of its subsections, produced a
    note. Judging a parent heading by its own text alone reported
    "3 Deep Residual Learning" as uncovered even though 3.1, 3.2 and 3.3 were
    all noted: that body lives in the children, so the flag described the
    heading rather than a gap in the notes.
    """
    sections = doc.get("sections") or []
    covered = {n["section"] for n in notes if n["section"]}
    # The bibliography is excluded on both sides. It produced notes before the
    # body cutoff existed, and counting it as a section to be noted made the
    # denominator include a block no note should ever describe.
    total = [s for s in sections
             if s.get("chars", 0) > 0
             and (s.get("title") or "").strip().lower()
             not in ("references", "bibliography", "literature cited")
             and not _BACK_MATTER.search((s.get("title") or "").strip())]

    def label(section):
        return (section.get("num", "") + " " + section["title"]).strip()

    covered_nums = {s.get("num", "") for s in total if label(s) in covered}
    uncovered = []
    for section in total:
        num = section.get("num", "")
        if label(section) in covered:
            continue
        if any(other != num and other.startswith(num + ".")
               for other in covered_nums):
            continue
        uncovered.append(label(section))

    return {
        "sections_with_notes": len(total) - len(uncovered),
        "sections_with_body": len(total),
        "sentence_pool": len(mined),
        "notes_from_pool": len(notes),
        "uncovered_sections": uncovered[:20],
    }


def _markdown(doc, notes):
    """A notes file the reader can open without any tooling."""
    card = _paper_card(doc, [])
    lines = ["# %s" % (card.get("title") or "Untitled"), ""]
    if card.get("authors"):
        lines.append("- 作者：%s" % "、".join(card["authors"]))
    if card.get("year"):
        lines.append("- 年份：%s" % card["year"])
    lines.append("- 页数：%s" % card.get("page_count"))
    lines.append("")
    if card.get("one_line"):
        lines.extend(["## 一句话结论", "", card["one_line"], ""])
    lines.extend(["## 结构化笔记", ""])
    for note in notes[:120]:
        lines.append("### %s %s（第 %s 页）" % (note["note_id"], note["kind"],
                                              note["page"]))
        lines.append("")
        lines.append(note["claim"])
        lines.append("")
        if note.get("numbers"):
            lines.append("- 数字：%s" % ", ".join(note["numbers"]))
        lines.append("- 置信度：%s" % CONFIDENCE.get(note["confidence"],
                                                  note["confidence"]))
        lines.append("")
    return "\n".join(lines)


def _honest_gaps(bundle, doc, mined, notes):
    if not notes:
        bundle.gap(item="笔记", reason="未从原文中挖到可归类的结论句；"
                   "可能是扫描件、非英文或版式异常", field="notes",
                   state="not_reported")
        return
    kinds = {}
    for note in notes:
        kinds[note["kind"]] = kinds.get(note["kind"], 0) + 1
    bundle.put("note_kinds", kinds)
    if "limitation" not in kinds:
        bundle.gap(item="局限陈述", reason="原文未出现明确的局限/失败/未来工作表述，"
                   "笔记中遂无 limitation 条目；这不是遗漏，但需读者注意",
                   field="notes", state="uncertain")
    cov = _coverage(doc, mined, notes)
    if cov["sections_with_body"] and cov["sections_with_notes"] < cov["sections_with_body"]:
        bundle.gap(item="章节覆盖",
                   reason="%d/%d 个有正文的章节未产生任何笔记：%s"
                          % (cov["sections_with_body"] - cov["sections_with_notes"],
                             cov["sections_with_body"],
                             "、".join(cov["uncovered_sections"][:6])),
                   field="coverage", state="partial")
