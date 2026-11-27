"""Shared plumbing for every topic module.

A topic module exposes ``run(case, task, bundle, records, doc)`` where ``doc``
is the recovered structure of the primary document. Everything here exists so
that topics differ only in what they extract, never in how they handle a
missing read, an unanchorable claim or a degraded backend.
"""

import re

from core import evidence as _evidence
from core import structure as _structure
from core import textio as _textio

PDFISH = {".pdf"}


# The runner's own contract files are not source material. They are short,
# they always sit next to the paper, and on a short input they will otherwise
# win the "first record" fallback and become the analysed document.
_NOT_MATERIAL = frozenset(["task.md", "case.json", "readme.md"])


def _is_material(record):
    """True when the record is source material rather than a contract file."""
    rel = (record.get("rel") or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return rel not in _NOT_MATERIAL and record.get("ext") not in (".json", ".md")


def primary(records):
    """The document the run is about: first PDF, else the longest real material.

    Contract files are excluded before choosing, and the choice falls back to
    the longest material rather than to whatever happened to be first: on a
    short paper the first record is `case.json`, and analysing that instead of
    the paper would be a silent, total miss.
    """
    pdf = _textio.first_pdf(records)
    if pdf:
        return pdf
    material = [r for r in records if _is_material(r) and (r.get("text") or "").strip()]
    if material:
        return max(material, key=lambda r: len(r["text"]))
    for record in records:
        if record.get("text") and len(record["text"]) > 400:
            return record
    # No source material at all: report that instead of analysing the runner's
    # own task statement, which would look like a successful parse of a paper
    # that never existed.
    return None


# Each topic refuses in its own vocabulary ("sections", "sentences"), but the
# reason a run had nothing to work on is the same fact in all of them, so the
# diagnosis lives here once instead of being reworded nine times.
_NO_MATERIAL_REASONS = {
    "no_text_layer": ("no_text_layer",
                      "PDF 可打开但没有任何文字层，内容可能是扫描页或纯图形；"
                      "需先做 OCR 才能读取正文"),
    "encrypted": ("encrypted", "PDF 已加密，未提供打开密码，正文不可读取"),
    "not_a_pdf": ("not_a_pdf", "扩展名是 .pdf 但内容不是 PDF，无法按 PDF 解析"),
    "damaged": ("damaged", "PDF 结构损坏，抽取工具无法重建交叉引用表"),
    "backend_missing": ("backend_missing", "运行环境里没有可用的 PDF 文本抽取工具"),
    "backend_failed": ("backend_failed", "PDF 文本抽取工具无法运行"),
    "extract_failed": ("extract_failed", "PDF 文本抽取失败"),
}


def unreadable(records):
    """The first material file whose bytes could not become text, or None.

    Only files that should have produced text count. An image, an archive or an
    empty directory is a different answer from a PDF that refused to open, and
    mixing them would let "I could not read it" stand in for "there was nothing
    to read".
    """
    for record in records or []:
        if record.get("text", None) and record["text"].strip():
            continue
        reason = _textio.unreadable_reason(record.get("path") or "")
        if reason:
            return (record, reason)
    return None


def refuse_empty(bundle, field, records, empty_message, extra=""):
    """Refuse with the most specific reason the input actually supports."""
    found = unreadable(records)
    if found:
        record, (code, message) = found
        name = record.get("rel") or record.get("path") or "材料"
        bundle.put("unreadable_input", {"file": name, "code": code,
                                        "reason": message})
        bundle.refuse(field, "材料 %s 无法读取：%s" % (name, message))
        return code
    bundle.refuse(field, empty_message + extra)
    return "empty"


def others(records, keep):
    """Every other material file, so cross-document work can see them."""
    return [r for r in records if r is not keep and (r.get("text") or "").strip()]


def recover(record):
    """Structure of one record, with the page split the rubric asks to cite."""
    if not record:
        return None
    text = record.get("text") or ""
    pages = _evidence.split_pages(text)
    struct = _structure.recover(text, pages)
    struct["path"] = record.get("rel")
    struct["backend"] = record.get("backend")
    struct["pages"] = pages
    struct["text"] = text
    struct["page_offsets"] = _page_offsets(pages)
    return struct


def _page_offsets(pages):
    """(start, end, 1-based page number) for the joined text, built once.

    Topics need to turn a character offset into a page; rebuilding the running
    total in each one invites the off-by-one that makes every citation wrong.
    """
    rows = []
    cursor = 0
    for index, page in enumerate(pages or [], 1):
        rows.append((cursor, cursor + len(page), index))
        cursor += len(page) + 1
    return rows


def page_index(struct):
    """Map a character offset in the joined text to a 1-based page number."""
    text = "\f".join(struct["pages"])
    starts = [0]
    running = 0
    for page in struct["pages"]:
        running += len(page) + 1
        starts.append(running)
    return text, starts


def page_of_offset(struct, offset):
    _, starts = page_index(struct)
    page = 1
    for idx, start in enumerate(starts):
        if offset >= start:
            page = idx + 1
        else:
            break
    return min(page, max(1, len(struct["pages"])))


def anchored(bundle, field, value, quote, records):
    """Store ``value`` with an anchor located from ``quote``."""
    anchor = _evidence.locate(quote, records) if quote else {"found": False,
                                                             "reason": "no_quote"}
    if anchor.get("found"):
        bundle.put(field, value, anchor=anchor)
    else:
        bundle.gap(item=field, reason="引文未能在输入材料中逐字定位",
                   field=field, state="unverified")
        bundle.put(field, value)
    return anchor


def declared(bundle, field, value, doc, label=None):
    """Record a field recovered from the material's own layout.

    Such a value is not a quote to be searched for: it was read out of the page
    structure, so its anchor is the page range it came from. That is the
    provenance the rubric asks for, and it does not downgrade the run.
    """
    anchor = {"found": True, "kind": "structural", "path": doc.get("path"),
              "page": 1, "reason": "read_from_layout"}
    bundle.put(field, value, anchor=anchor)
    return anchor


def excerpt(text, limit=1200):
    """A quote short enough to be verifiable, cut on a word boundary."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.6 else cut).strip()


def require(bundle, condition, what, reason="材料中未提供"):
    """Record a hard gap and report whether the caller may continue."""
    if condition:
        return True
    bundle.gap(item=what, reason=reason, state="not_reported")
    return False


# A lost character is a lost character in every topic, not only in the one
# whose job is parsing. 00-parse reports the full breakdown; the other nine
# still need to say that some span of the text they quote is incomplete,
# because a quote that silently drops a byte is not verbatim.
_UNMAPPED_CJK = re.compile(r"[　-鿿＀-￯]")


def degraded(bundle, struct, own_report=False):
    """Tell the reader when text came from a fallback extractor or is damaged.

    own_report is set by the topic that re-measures this itself (00-parse splits
    the count into accent-in-a-name versus operator-in-a-formula). Both filing a
    gap here and filing the richer one there would report one defect twice and
    read as two.
    """
    backend = (struct or {}).get("backend") or "unknown"
    if backend not in ("pdf-text-tool", "pdftotext"):
        bundle.note("文本抽取后端为 %s，非平台首选工具；版式细节可能丢失。" % backend)
    text = (struct or {}).get("text") or ""
    bad = text.count("�")
    if bad:
        share = bad / float(max(len(text), 1))
        if bad > max(20, len(text) // 2000) or share > 0.002:
            bundle.put("unmapped_char_count", bad)
            bundle.put("unmapped_char_share", round(share, 6))
            if own_report:
                return backend
            bundle.gap(item="字符映射",
                       reason="抽取文本含 %d 个未能映射的字符（占全文 %.2f%%），"
                              "本结果中引用到这些位置的片段不保证逐字完整；"
                              "未用猜测字符填充" % (bad, share * 100),
                       field="unmapped_char_count", state="uncertain")
    return backend


def page_offsets(struct):
    """Section -> page span, so every heading can be cited."""
    rows = []
    for item in struct.get("sections") or []:
        rows.append({
            "heading": (item["num"] + " " + item["title"]).strip(),
            "num": item.get("num"),
            "title": item.get("title"),
            "level": item["level"],
            "page": page_of_offset(struct, item.get("offset", 0)),
        })
    return rows
