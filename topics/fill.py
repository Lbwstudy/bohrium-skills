"""Contract-field autofill.

The platform hands each case its own ``output_contract`` and does not publish
its shape, so a Skill that hard-codes field names silently ships half-empty
results when the schema differs. This module maps *any* requested field name
onto real material-derived content, so an unfamiliar schema still gets answers
instead of placeholders.

It is a lookup, not a guess: a name that matches nothing stays a placeholder
and is reported as not_reported.
"""

import re

_NORM = re.compile(r"[^a-z0-9]+")


def _norm(name):
    return _NORM.sub("", str(name or "").lower())


def _walk(obj, *keys):
    for key in keys:
        if isinstance(obj, dict) and key in obj:
            return obj[key]
    return None


def _pages_text(doc):
    return "\f".join(doc.get("pages") or [])


def _quote_rows(doc, limit=12):
    """Verbatim sentence-sized quotes, each with its page."""
    text = _pages_text(doc)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    rows = []
    page_starts = [0]
    running = 0
    for page in doc.get("pages") or []:
        running += len(page) + 1
        page_starts.append(running)
    for sentence in sentences:
        body = " ".join(sentence.split())
        if len(body) < 60 or len(body) > 400:
            continue
        pos = text.find(body[:60])
        page = 1
        for idx, start in enumerate(page_starts):
            if pos >= start:
                page = idx + 1
            else:
                break
        rows.append({"quote": body, "page": page})
        if len(rows) >= limit:
            break
    return rows


def _citation_numbers(doc):
    """Distinct bracketed citation numbers appearing in the body text.

    Brackets also carry measurements ("shorter side randomly sampled in
    [256, 480]"), so numbers beyond the size of the reference list are excluded:
    a paper cannot cite source 480 when it lists 50.
    """
    text = _pages_text(doc)
    known = len(doc.get("references") or [])
    ceiling = known + 20 if known else 0
    seen = []
    for group in re.findall(r"\[(\d+(?:\s*[,\u2013-]\s*\d+)*)\]", text):
        for part in re.split(r"\s*,\s*", group):
            span = re.match(r"(\d+)\s*[\u2013-]\s*(\d+)", part)
            if span:
                low, high = int(span.group(1)), int(span.group(2))
                if 0 < high - low < 60:
                    seen.extend(range(low, high + 1))
                continue
            if part.strip().isdigit():
                seen.append(int(part))
    if ceiling:
        seen = [n for n in seen if 0 < n <= ceiling]
    return sorted(set(seen))


def _page_map(doc):
    rows = []
    for idx, page in enumerate(doc.get("pages") or [], 1):
        body = " ".join(page.split())
        rows.append({"page": idx,
                     "chars": len(page),
                     "words": len(page.split()),
                     "opening": body[:160]})
    return rows


def _summary(doc):
    """A summary built only from material: abstract, then section openings."""
    parts = []
    abstract = _walk(doc, "abstract") or {}
    if abstract.get("text"):
        parts.append(" ".join(abstract["text"].split())[:900])
    for item in (doc.get("sections") or [])[:6]:
        body = (item.get("body") or "").split("\n", 1)
        if len(body) == 2:
            lead = " ".join(body[1].split())[:220]
            if lead:
                parts.append("%s: %s" % (item["title"], lead))
    return " ".join(parts).strip() or None


def _keywords(doc):
    """High-frequency content words, a deterministic stand-in for a keyword list."""
    text = _pages_text(doc).lower()
    words = re.findall(r"[a-z][a-z-]{3,}", text)
    stop = {"that", "this", "with", "from", "have", "were", "which", "their",
            "there", "these", "those", "been", "they", "when", "also", "than",
            "such", "more", "most", "some", "into", "each", "both", "over",
            "however", "therefore", "using", "used", "based", "show", "shows"}
    counts = {}
    for word in words:
        if word in stop:
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, n in ranked[:20] if n >= 3]


def _section_rows(doc):
    rows = []
    for item in doc.get("sections") or []:
        rows.append({"heading": (item.get("num", "") + " " + item["title"]).strip(),
                     "level": item.get("level", 1),
                     "chars": item.get("chars", 0),
                     "words": item.get("words", 0)})
    return rows


def _figure_rows(doc):
    return [{"label": f["label"], "caption": " ".join(f["caption"].split())[:400]}
            for f in (doc.get("figures") or [])]


def _table_rows(doc):
    return [{"label": t["label"], "caption": " ".join(t["caption"].split())[:400]}
            for t in (doc.get("tables") or [])]


def _reference_rows(doc):
    """Bibliography entries as structure.recover names them.

    recover() returns them under "references"; reading "reference_entries"
    silently yielded an empty list, so every field built from the bibliography
    came back empty and the contract field reference_count was never answered.
    """
    return doc.get("references") or doc.get("reference_entries") or []


def candidates(doc, records):
    """Every field name this Skill can answer, and the material behind it."""
    if not doc:
        return {}
    meta = doc.get("meta") or {}
    text = _pages_text(doc)
    table = {
        "title": meta.get("title"),
        "documenttitle": meta.get("title"),
        "papertitle": meta.get("title"),
        "authors": meta.get("authors") or [],
        "author": meta.get("authors") or [],
        "affiliations": meta.get("affiliations_text"),
        "affiliation": meta.get("affiliations_text"),
        "doi": meta.get("doi"),
        "arxivid": meta.get("arxiv_id"),
        "arxiv": meta.get("arxiv_id"),
        "abstract": _walk(doc, "abstract", "text"),
        "abstracttext": _walk(doc, "abstract", "text"),
        "summary": _summary(doc),
        "sections": _section_rows(doc),
        "section": _section_rows(doc),
        "outline": _section_rows(doc),
        "sectioncount": len(doc.get("sections") or []),
        "figures": _figure_rows(doc),
        "figure": _figure_rows(doc),
        "figurecount": len(doc.get("figures") or []),
        "tables": _table_rows(doc),
        "table": _table_rows(doc),
        "tablecount": len(doc.get("tables") or []),
        "equations": doc.get("equations") or [],
        "equationcount": len(doc.get("equations") or []),
        "references": _reference_rows(doc),
        "referencecount": len(_reference_rows(doc)),
        "bibliography": _reference_rows(doc),
        "citation": _citation_numbers(doc),
        "quotes": _quote_rows(doc),
        "quote": _quote_rows(doc),
        "evidence": _quote_rows(doc),
        "citations": _quote_rows(doc),
        "pagemap": _page_map(doc),
        "pages": _page_map(doc),
        "pagecount": len(doc.get("pages") or []),
        "text": text,
        "fulltext": text,
        "content": text,
        "markdown": text,
        "plaintext": text,
        "keywords": _keywords(doc),
        "keyword": _keywords(doc),
        "status": "success",
        "backend": doc.get("backend"),
        "extractionbackend": doc.get("backend"),
        "source": doc.get("path"),
        "sourcefile": doc.get("path"),
        "filename": doc.get("path"),
    }
    return {key: value for key, value in table.items() if value not in (None, "", [], 0)}


_QUANTIFIER = re.compile(r"(?:count|counts|number|num|total|size|length)$")


def _lookup(key, table):
    """Exact match, else the longest candidate contained in or containing key."""
    if key in table:
        return key, table[key]
    best = None
    for name, value in table.items():
        if name and (name in key or key in name):
            if best is None or len(name) > len(best[0]):
                best = (name, value)
    return best if best else (None, None)


def resolve(field, table):
    """Find the best candidate for a requested field name.

    Count-shaped names are answered by measuring the named thing: `citation_count`
    resolves `citation` (through the substring rule) and reports its length,
    instead of falling through to a placeholder. Measurement is not a guess:
    only values already present in the table are counted.
    """
    key = _norm(field)
    if not key:
        return None

    # A count-shaped name must be measured before the substring rule gets a
    # chance: "citationcount" contains "citation", so a plain lookup would hand
    # back the whole list where the contract asked for a number.
    stripped = _QUANTIFIER.sub("", key)
    if stripped and stripped != key:
        name, value = _lookup(stripped, table)
        if value is not None and hasattr(value, "__len__") and not isinstance(value, (int, float)):
            return len(value)

    name, value = _lookup(key, table)
    return value if name is not None else None
