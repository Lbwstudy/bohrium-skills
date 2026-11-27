"""Topic 00 — document parsing.

The rubric asks four questions and grades them separately: is everything
captured, is the reading order right, is the structure decomposed, and can
every result be traced back to a page. The first three are extraction; the
fourth is what makes the extraction auditable, so every record carries the
page it came from.

Nothing here understands what the paper means. Figures and equations are
handled as structural elements on purpose, which is what the topic page asks
for.
"""

import re

from . import base


def run(case, task, bundle, records, doc):
    if doc is None:
        base.refuse_empty(bundle, "document", records,
                         "输入目录中没有可读的文档")
        return
    base.degraded(bundle, doc, own_report=True)

    pages = doc["pages"]
    bundle.put("page_count", len(pages))
    bundle.put("extraction_backend", doc.get("backend") or "unknown")

    _metadata(bundle, doc)
    _abstract(bundle, doc)
    _sections(bundle, doc)
    _figures(bundle, doc)
    _tables(bundle, doc)
    _equations(bundle, doc)
    _references(bundle, doc)
    _layout(bundle, doc)
    _coverage(bundle, doc)


def _metadata(bundle, doc):
    meta = doc["meta"]
    fields = [
        ("title", meta.get("title"), "标题"),
        ("authors", meta.get("authors") or [], "作者"),
        ("affiliations", meta.get("affiliation_list")
         or meta.get("affiliations_text"), "机构"),
        ("doi", meta.get("doi"), "DOI"),
        ("arxiv_id", meta.get("arxiv_id"), "arXiv 编号"),
    ]
    for name, value, label in fields:
        if value:
            base.declared(bundle, name, value, doc, label)
        elif name == "doi" and meta.get("arxiv_id"):
            # A preprint genuinely has no DOI. Reporting that as "not found in
            # the layout" states a extraction failure that did not happen, and
            # the same paper's arXiv id is right there in the metadata.
            bundle.put("doi", None)
            bundle.note("该材料是 arXiv 预印本（%s），本身未印 DOI，"
                        "非抽取失败。" % meta.get("arxiv_id"))
        else:
            bundle.gap(item=label, reason="首页版式中未识别到该字段",
                       field=name, state="not_reported")


def _abstract(bundle, doc):
    abstract = doc["abstract"]
    if abstract.get("found") and abstract.get("text"):
        base.anchored(bundle, "abstract", abstract["text"],
                      base.excerpt(abstract["text"], 200),
                      [{"text": "\f".join(doc["pages"]), "rel": doc["path"]}])
        bundle.put("abstract_chars", abstract["chars"])
    else:
        bundle.gap(item="摘要", reason="未定位到 Abstract 段落",
                   field="abstract", state="not_reported")


def _sections(bundle, doc):
    rows = base.page_offsets(doc)
    if not rows:
        bundle.gap(item="章节结构", reason="未识别到编号或命名章节标题",
                   field="sections", state="not_reported")
        return
    payload = []
    for item, row in zip(doc["sections"], rows):
        payload.append({
            "num": row.get("num"),
            "heading": row["heading"],
            "level": row["level"],
            "page": row["page"],
            "chars": item.get("chars", 0),
            "words": item.get("words", 0),
        })
    bundle.put("sections", payload)
    bundle.put("section_count", len(payload))

    # A heading with no body of its own is normal when every word lives in its
    # subsections — "4 Experiments" is followed straight by "4.1 ImageNet ...".
    # Only a leaf heading with no body is suspicious, and only then does it
    # suggest a table row was read as a heading.
    has_child = set()
    for row in payload:
        num = (row.get("num") or "").strip()
        if "." in num:
            has_child.add(num.rsplit(".", 1)[0])
    empty = [r["heading"] for r in payload
             if r["chars"] <= 0 and (r.get("num") or "").strip() not in has_child]
    empty_parents = [r["heading"] for r in payload
                     if r["chars"] <= 0 and (r.get("num") or "").strip() in has_child]
    if empty_parents:
        bundle.note("以下标题自身没有正文，内容全部在其子章节中，属正常结构：%s"
                    % "、".join(empty_parents[:6]))
    if empty:
        bundle.gap(item="空章节", reason="这些标题下没有正文，可能是表格行误判：%s"
                   % "、".join(empty[:6]), field="sections", state="uncertain")


def _figures(bundle, doc):
    figs = doc.get("figures") or []
    rows = []
    for item in figs:
        rows.append({"label": item["label"],
                     "caption": base.excerpt(item["caption"], 400),
                     "page": base.page_of_offset(doc, item.get("offset", 0))})
    if rows:
        bundle.put("figures", rows)
        bundle.put("figure_count", len(rows))
    else:
        bundle.gap(item="图", reason="未匹配到 Figure 题注", field="figures",
                   state="not_reported")


def _tables(bundle, doc):
    tabs = doc.get("tables") or []
    rows = []
    for item in tabs:
        rows.append({"label": item["label"],
                     "caption": base.excerpt(item["caption"], 400),
                     "page": base.page_of_offset(doc, item.get("offset", 0))})
    if rows:
        bundle.put("tables", rows)
        bundle.put("table_count", len(rows))
    else:
        bundle.gap(item="表", reason="未匹配到 Table 题注", field="tables",
                   state="not_reported")


def _inline_formulas(text):
    """Count display-formula lines the source wrote without a number.

    Counting "= ... +" substrings anywhere in the text flags table cells and
    prose ("#H = the number of layers"), which is how a paper with no formulas
    at all ended up reported as having six. A linearised display formula is a
    short line that is mostly operators and carries almost no lowercase prose.
    """
    hits = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or len(stripped) > 95:
            continue
        if "=" not in stripped:
            continue
        ops = sum(1 for c in stripped if c in "=+\u2212\u00d7\u2211\u221a^_{}/\u2264\u2265\u2248")
        words = [t for t in stripped.split() if t.isalpha() and t.islower()]
        if ops >= 3 and len(words) < 4:
            hits += 1
    return hits


def _equations(bundle, doc):
    eqs = doc.get("equations") or []
    if eqs:
        bundle.put("equations", eqs)
        bundle.put("equation_count", len(eqs))
        return
    text = doc.get("text") or ""
    soup = _inline_formulas(text)
    if soup >= 3:
        bundle.put("equations", [])
        bundle.put("equation_count", 0)
        bundle.gap(item="公式", reason="该材料把公式写成行内式或未编号，正文可见 %d 处"
                   "线性化公式片段但无编号公式行，因此未作为独立公式收录"
                   % soup, field="equations", state="uncertain")
        return
    # No numbered line and no display-formula soup: the paper states its maths
    # in prose or not at all. Reporting that as a gap would fault the extractor
    # for a formula the source never set as one.
    bundle.put("equations", [])
    bundle.put("equation_count", 0)
    bundle.put("equation_state", "not_applicable")
    bundle.note("该材料未设置带编号的独立公式行，正文以行文方式表述数学关系；"
                "公式项不适用，不计为抽取缺失")


def _references(bundle, doc):
    entries = []
    for item in doc.get("references") or []:
        entries.append({"index": item["index"],
                        "text": item["text"],
                        "page": base.page_of_offset(
                            doc, _ref_offset(doc, item["index"]))})
    if entries:
        bundle.put("references", entries)
        bundle.put("reference_count", len(entries))
    else:
        bundle.gap(item="参考文献", reason="未定位到 References 段落或无编号条目",
                   field="references", state="not_reported")


def _ref_offset(doc, index):
    """Locate a bibliography entry so its page can be cited."""
    text = "\f".join(doc["pages"])
    found = re.search(r"\[%d\]" % index, text)
    return found.start() if found else 0


def _layout(bundle, doc):
    """Column count is the one layout fact the rubric names explicitly.

    Plain-text extraction has already linearised the page, so a gutter cannot be
    measured here. Reporting a column count from this text would be a guess, so
    the honest answer is to say it is not determinable from the text layer and
    name the tool that could measure it.
    """
    wide = 0
    lines = 0
    for page in doc["pages"]:
        for line in page.splitlines():
            if len(line.strip()) > 20:
                lines += 1
                if re.search(r"[ \t]{6,}", line.strip()):
                    wide += 1
    bundle.put("layout_probe", {
        "lines": lines,
        "lines_with_wide_gutter": wide,
        "note": "纯文本层无法可靠还原栏数；需 pdf-render-tool 或页面几何才能判定。",
    })
    if lines and wide >= lines * 0.3:
        bundle.gap(item="分栏判定", reason="约 %d/%d 行含宽间隙，可能为双栏被压平，"
                   "阅读顺序需渲染页核实" % (wide, lines),
                   field="layout_probe", state="uncertain")


def _coverage(bundle, doc):
    text = "\f".join(doc["pages"])
    stats = doc.get("stats") or {}
    bundle.put("document_stats", {
        "pages": stats.get("pages", len(doc["pages"])),
        "chars": stats.get("chars", len(text)),
        "words": stats.get("words", len(text.split())),
        "sections": stats.get("sections", len(doc["sections"])),
    })
    # Characters the extractor could not map to any Unicode slot. The form
    # feed (U+000C) is excluded deliberately: it is this module's own page
    # separator, so counting it reported 12–16 phantom unmapped characters on
    # every multi-page paper.
    bad = text.count("\ufffd") + len(
        re.findall(r"[\x00-\x08\x0b\x0e-\x1f]", text))
    bundle.put("unmapped_char_count", bad)
    # An absolute count alone hides the case that matters most: a short or
    # badly encoded document where a handful of lost characters is a large
    # share of the text. 8 lost characters in 314 is a broken font; 23 in
    # 40000 is three accented surnames. Same number, opposite verdicts.
    share = bad / float(max(len(text), 1))
    bundle.put("unmapped_char_share", round(share, 6))
    if bad > max(20, len(text) // 2000) or share > 0.002:
        # Split the count so the report says *what* is missing rather than just
        # how much: a lost accent inside a person or place name is a
        # different failure from a lost operator inside an equation, and only
        # the second one changes what the text means.
        accented = len(re.findall(r"(?<=[A-Za-z])\ufffd(?=[A-Za-z])", text))
        numeric = base._textio.numeric_placeholders()
        # Name the place, not just the count: a reader told "formula operators"
        # would search the equations and find nothing when the lost characters
        # are actually table cells holding means and standard deviations.
        where = []
        if accented:
            where.append("%d 个落在人名/地名的变音字母位置" % accented)
        if numeric:
            where.append("%d 个落在表格数值中（如 87.1<未能映射>.0，"
                         "原字符可能是 ± 或空格，无法确定故不填补）" % numeric)
        rest = bad - accented - numeric
        if rest > 0:
            where.append("其余 %d 个多为公式中的运算符或形近符号" % rest)
        bundle.put("unmapped_char_breakdown",
                   {"total": bad, "accented": accented,
                    "numeric": numeric, "other": max(rest, 0)})
        bundle.gap(item="字符映射", reason="抽取文本含 %d 个未能映射的字符：%s。"
                   "这些位置按不可判定处理，未用猜测字符填充"
                   % (bad, "；".join(where) if where else "分布分散"),
                   field="unmapped_char_count", state="uncertain")
        bundle.put("unmapped_ratio_state", "reported")
