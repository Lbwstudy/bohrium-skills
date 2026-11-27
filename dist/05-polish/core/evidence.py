"""Evidence anchors.

Grading rewards results that can be walked back to the source. Every claim a
Skill emits therefore carries an anchor built here. Anchors are created only
from material that actually exists in the parsed text, so a claim that cannot
be anchored is a claim the Skill should not be making.
"""

import re

PAGE_RE = re.compile(r"^\s*(?:page|Page|PAGE)\s*(\d+)", re.M)


def split_pages(text):
    """Split extracted text into page chunks using the extractor's markers.

    The bundled reader and pdftotext both separate pages with a form feed; when
    no marker is present the whole text is one page.
    """
    if not text:
        return []
    if "\f" in text:
        parts = text.split("\f")
    elif re.search(r"^\s*-{0,3}\s*(?:page|Page)\s+\d+\s*-{0,3}\s*$", text, re.M):
        parts = re.split(r"^\s*-{0,3}\s*(?:page|Page)\s+\d+\s*-{0,3}\s*$", text,
                         flags=re.M)
    else:
        parts = [text]
    return [p for p in parts]


def paragraphs(text):
    """Paragraph-ish units: blank-line separated, then single-line merged."""
    if not text:
        return []
    blocks = re.split(r"\n\s*\n", text)
    out = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        out.append(" ".join(lines))
    return out


def _line_index(text):
    return [ln.strip() for ln in text.splitlines()]


def locate(quote, records, window=90):
    """Find the strongest anchor for ``quote`` across input records.

    Returns a dict with ``found``, and when found: ``path``, ``page``,
    ``line``, ``char``, ``snippet``. Returns ``found: False`` when the quote
    does not occur verbatim in any recoverable text.
    """
    probe = (quote or "").strip()
    if not probe:
        return {"found": False, "reason": "empty_quote"}
    needle = re.sub(r"\s+", " ", probe)[:400]
    for rec in records:
        text = rec.get("text") or ""
        if not text:
            continue
        flat = re.sub(r"\s+", " ", text)
        pos = flat.find(needle)
        if pos < 0:
            head = needle[:60]
            if len(head) >= 20:
                pos = flat.find(head)
        if pos < 0:
            continue
        page = 1
        page_start = 0
        running = 0
        for idx, chunk in enumerate(split_pages(text)):
            flat_chunk = re.sub(r"\s+", " ", chunk)
            if running + len(flat_chunk) >= pos:
                page = idx + 1
                page_start = running
                break
            running += len(flat_chunk) + 1
        line = flat.count("\n", 0, 0)
        before = flat[:pos]
        line = before.count("\n") + 1
        start = max(0, pos - window // 2)
        snippet = flat[start:pos + window].strip()
        return {
            "found": True,
            "path": rec.get("rel"),
            "page": page,
            "line": line,
            "char": pos - page_start,
            "snippet": snippet,
        }
    return {"found": False, "reason": "quote_not_in_material"}


def anchor_from_text(rel, page, line, snippet=""):
    return {"found": True, "path": rel, "page": page, "line": line,
            "snippet": (snippet or "")[:200]}


def page_of(records, rel, needle, window=80):
    """Locate ``needle`` inside one already-parsed record and return a page anchor."""
    for rec in records:
        if rec.get("rel") != rel:
            continue
        text = rec.get("text") or ""
        flat = re.sub(r"\s+", " ", text)
        probe = re.sub(r"\s+", " ", needle or "")
        pos = flat.find(probe[:200])
        if pos < 0:
            return {"found": False, "reason": "not_in_record", "path": rel}
        page = 1
        running = 0
        for idx, chunk in enumerate(split_pages(text)):
            flat_chunk = re.sub(r"\s+", " ", chunk)
            if running + len(flat_chunk) >= pos:
                page = idx + 1
                break
            running += len(flat_chunk) + 1
        return {"found": True, "path": rel, "page": page,
                "snippet": flat[max(0, pos - window // 2):pos + window].strip()}
    return {"found": False, "reason": "record_missing", "path": rel}


def collect_unsupported(items):
    """Normalise the not-reported bucket so it never hides behind prose."""
    out = []
    for item in items or []:
        if isinstance(item, str):
            out.append({"item": item, "state": "not_reported"})
        elif isinstance(item, dict):
            row = dict(item)
            row.setdefault("state", "not_reported")
            out.append(row)
    return out


def numbers_in(text):
    """Numeric tokens worth checking for verbatim fidelity."""
    return re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?", text or "")


def text_fidelity(source, produced):
    """Cheap overlap check used as a self-audit, not as a grade claim."""
    src = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", source or ""))
    got = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", produced or ""))
    if not src:
        return {"coverage": 0.0, "missing": []}
    missing = sorted(src - got)[:40]
    return {"coverage": round(len(src & got) / len(src), 4), "missing": missing}
