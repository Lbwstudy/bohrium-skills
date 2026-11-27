"""Topic 06 — reference and citation management.

This topic is the most deterministic of the ten: bibliography entries are
structured records, so deduplication, field repair and format conversion are
checkable rather than judged. The Skill therefore goes further than the others
and produces real converted output, not just findings.

The four rubric questions map to four passes:
挂得对 anchor each in-text citation to a bibliography entry;
编得顺 renumber and report the order that would result;
收得净 merge duplicates with an explicit reason for each merge;
对得上 emit GB/T 7714-2015 and APA strings and name what could not be completed.
"""

import re
import unicodedata

from . import base

BRACKET = re.compile(r"\[(\d{1,3}(?:\s*[,\u2013-]\s*\d{1,3})*)\]")
CITE_CMD = re.compile(r"\\(?:cite|citep|citet|parencite|textcite|autocite)\*?"
                      r"(?:\[[^\]]*\])*\{([^}]+)\}")

# Author-year styles cite as "(Devlin et al., 2018)" or "(Vaswani et al., 2017;
# He et al., 2016)". A parser that only knows "[n]" reports zero in-text
# citations for such a paper, which reads as "this manuscript cites nothing".
# A long parenthetical is still one citation group: papers routinely list seven
# works in a row, and at 120 characters the whole group fell outside the window
# so every member of it looked uncited.
AUTHOR_YEAR = re.compile(
    r"\(([^()]{2,600}?)\)")
AUTHOR_YEAR_PART = re.compile(
    r"([A-Z][\w\u00c0-\u024f'\-]+(?:\s+[A-Z][\w\u00c0-\u024f'\-]+)?"
    # "&" is as common as "and" ("Kingma & Ba, 2017"). Without it the two-name
    # form never matched, the match restarted at the second surname, and the
    # citation resolved against the wrong entry.
    r"(?:\s+(?:et\s+al\.?|(?:and|&)\s+[A-Z][\w\u00c0-\u024f'\-]+))?)"
    # The disambiguating letter belongs inside the capture: without it "2019a"
    # and "2019b" both arrived as "2019" and the two works were indistinguishable.
    r"[,\s]\s*((?:19|20)\d{2}[a-z]?)")
# "Hochreiter and Schmidhuber (1997)" is a citation whose surnames sit
# outside any bracket, so the parenthetical scan cannot see them. The name part
# accepts the same three shapes the bracketed form does.
NARRATIVE_CITE = re.compile(
    r"\b([A-Z][\w\u00c0-\u024f'\-]+"
    r"(?:\s+(?:et\s+al\.?|(?:and|&)\s+[A-Z][\w\u00c0-\u024f'\-]+))?)"
    r"\s*\(((?:19|20)\d{2})[a-z]?\)")
DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
YEAR = re.compile(r"\b(1[89]\d{2}|20\d{2})[a-z]?\b")
PAGES = re.compile(r"\b(\d{1,5})\s*[-\u2013]\s*(\d{1,5})\b")

# A number this far beyond the last reference entry is a measurement, not a
# citation. Real citation lists do not skip hundreds of entries.
CITE_SLACK = 20


def run(case, task, bundle, records, doc):
    entries = list((doc or {}).get("references") or [])
    if not entries:
        base.refuse_empty(bundle, "references", records,
                         "未在材料中定位到编号参考文献表")
        return
    base.degraded(bundle, doc)

    enriched = [_parse_entry(e) for e in entries]
    bundle.put("reference_count", len(enriched))
    bundle.put("references", enriched)

    _in_text(bundle, doc, enriched)
    _renumber(bundle, doc, enriched)
    _dedupe(bundle, enriched)
    _formats(bundle, enriched)
    _field_gaps(bundle, enriched)


_BODY_LEAK = re.compile(r"(\b(?:19|20)\d{2})\.\s+(\S.*)$", re.S)
# A citation tail names a venue or a volume:pages range. Without this guard a
# perfectly ordinary entry is truncated at its own year — "Rie Kubota Ando and
# Tong Zhang. 2005. A framework for learning … Journal of Machine Learning
# Research, 6(Nov):1817-1853." loses the title and the venue because the words
# "a", "for" and "from" in the title read as running prose.
_CITE_FIELD = re.compile(
    r"\b(?:Journal|Proceedings|Conference|Workshop|Symposium|Transactions|"
    r"arXiv|preprint|Press|Publishing|Springer|ACM|IEEE|LNCS|LNIP|"
    r"vol\.|volume|pp\.|no\.|eds?\.)"
    r"|\bIn\s+(?:Proc|Proceedings|Advances|International|IEEE|ACM|ECCV|ICCV|"
    r"CVPR|NeurIPS|NIPS|ICLR|ICML|AAAI|IJCAI|ACL|EMNLP|NAACL|SIGIR|KDD|"
    r"[A-Z][a-z]+\s+(?:on|of)\b)"
    r"|\d+\s*\(\s*\d+\s*\)\s*:|\d+\s*:\s*\d+\s*[-\u2013]\s*\d+", re.I)


def _trim_body_leak(text):
    """Drop the section body that runs on after the last bibliography entry.

    The reference list is not always the end of the document: an appendix
    ("A. Object Detection Baselines") can follow entry 50 on the same page and
    the extractor hands it over as part of that entry. Which suffix is body
    depends on where the citation ends, and the citation always keeps its own
    name and venue first — "…[J]. In ECCV, 2014. A. Object Detection
    Baselines …" has one legitimate citation tail before the appendix starts.
    So each sentence boundary is a candidate cut, and the earliest boundary
    whose remainder is running prose wins.
    """
    for match in _BODY_LEAK.finditer(text):
        tail = match.group(2)
        if len(tail.split()) < 10:
            continue
        base = match.start(2)
        # A numbered or lettered heading ("A. Object Detection Baselines",
        # "8.2 Ablation") marks exactly where the bibliography ended. Cutting
        # at the next sentence boundary instead leaves the heading letter
        # behind, which then reads as a volume number in the rendered entry.
        if re.match(r"^(?:[A-Z]|\d+(?:\.\d+)*)\.\s+\S{2,}", tail):
            return text[:base].rstrip()
        cut = None
        for boundary in re.finditer(r"\.\s+", tail):
            rest = tail[boundary.end():]
            if len(rest.split()) < 10:
                continue
            if re.search(r"@|https?://|\bDOI\b", rest):
                continue
            if _CITE_FIELD.search(rest):
                continue
            words = rest.lower().split()
            prose = sum(1 for w in words if w.strip(".,;:") in _PROSE_STOP)
            if prose < 3:
                continue
            cut = base + boundary.end()
            break
        if cut is not None:
            return text[:cut].rstrip()
    return text


_PROSE_STOP = frozenset("""a an the we our this that these those is are was were be been
being has have had not no of in on at to for from with by as it its their they
here there which who whom whose and or but if then than so such can could may
might must should would will""".split())


def _cite_surname(text):
    """The surname a citation names, which is not always the first word.

    "(Tjong Kim Sang and De Meulder, 2003)" names one first author whose
    surname is several tokens long, and "(Peters et al., 2018a)" keeps the
    "et al." suffix. Both must reduce to the surname the bibliography sorts
    on, or every multi-token name is reported as an unresolved citation.
    """
    cleaned = re.sub(r"\bet\s+al\.?", " ", text or "")
    cleaned = re.split(r"\s+and\s+", cleaned)[0]
    tokens = [t.strip(".,;") for t in cleaned.split() if t.strip(".,;")]
    if not tokens:
        return None
    return tokens[-1]


def _surname_candidates(text):
    """Every token in a citation, so a multi-token surname can still resolve.

    "Tjong Kim Sang and De Meulder" is two authors whose surnames are "Sang"
    and "Meulder", but "(Tjong Kim Sang, 2003)" alone could equally be a
    single author "Tjong Kim Sang". Trying each token against the bibliography
    resolves both shapes without guessing which one the style intends.
    """
    cleaned = re.sub(r"\bet\s+al\.?", " ", text or "")
    out = []
    for chunk in re.split(r"\s+and\s+", cleaned):
        for token in chunk.split():
            token = token.strip(".,;")
            if token and token[0].isupper():
                out.append(token)
    return out


def _entry_surnames(entry):
    """Every author surname of an entry, first author first.

    A citation may name a later author ("De Meulder" for a paper whose first
    author is "Sang"), so indexing only the first surname reports real
    citations as unresolved.
    """
    out = []
    for part in entry.get("author_parts") or []:
        if isinstance(part, (list, tuple)) and part:
            out.append(str(part[0]))
        elif isinstance(part, dict) and part.get("surname"):
            out.append(part["surname"])
    if not out:
        first = _first_surname(entry)
        if first:
            out.append(first)
    return out


def _first_surname(entry):
    """The surname an author-year citation would use for this entry."""
    parts = entry.get("author_parts") or []
    if parts:
        first = parts[0]
        if isinstance(first, (list, tuple)) and first:
            return str(first[0])
        if isinstance(first, dict):
            return first.get("surname") or None
    blob = entry.get("author_blob") or ""
    for chunk in re.split(r",|\band\b", blob):
        name = chunk.strip().strip(".")
        if not name:
            continue
        tokens = name.split()
        return tokens[-1] if len(tokens) >= 2 else tokens[0]
    return None


# A year glued to one of these is an identifier, not a date: "arXiv:2001.04413",
# "abs/1905.10337", "doi=10.1145". A comma is deliberately absent, because
# "In NeurIPS, 2019" is the normal way a year appears.
_YEAR_GLUE = ":/=-" + "\u2013"

def _pick_year(text):
    """The publication year, ignoring years embedded in identifiers.

    arXiv IDs carry YYMM, so "arXiv:2001.04413, 2020a" contains both 2001 and
    2020. A trailing URL does the same. Bibliography years cluster at the end,
    so: drop matches whose context is an identifier, then take the last one.
    """
    candidates = []
    for match in YEAR.finditer(text):
        before = text[max(0, match.start() - 12):match.start()]
        # Wide enough to see a whole page range: "1914- 1925" and "1914–1925"
        # both put a dash and sometimes a space before the second number.
        after = text[match.end():match.end() + 10]
        left = before.rstrip()
        if left and left[-1] in _YEAR_GLUE:
            continue
        # "pages 1914-1925": two four-digit numbers joined by a dash are a page
        # range. Reading 1914 as the publication year made a 2018 paper look
        # like a 1914 one, so its own citation could never resolve to it.
        if re.match(r"\s*[-\u2013]\s*\d{4}\b", after):
            continue
        if re.search(r"\b\d{4}\s*[-\u2013]\s*$", before):
            continue
        # "2001.04413": four digits, a dot, then more digits is an identifier.
        if re.match(r"\.\d{4,}", after):
            continue
        candidates.append(match.group(1))
    if not candidates:
        return None
    return candidates[-1]


def _parse_entry(entry):
    """Split a bibliography entry into the fields the two formats need."""
    text = " ".join((entry.get("text") or "").split())
    text = _expand_ligatures(text)
    text = _trim_body_leak(text)
    row = {"index": entry.get("index"), "raw": text}
    doi = DOI.search(text)
    if doi:
        row["doi"] = doi.group(0).rstrip(".,;")
    picked = _pick_year(text)
    if picked:
        row["year"] = picked
        # NLP lists print "2018a" / "2018b" for two works by one author in one
        # year, and the citation repeats the letter. Recording it lets a citation
        # bind to the entry it names instead of to whichever came first.
        letter = re.search(r"\b" + picked + r"([a-z])\b", text)
        if letter:
            row["year_suffix"] = letter.group(1)
    pages = PAGES.search(text)
    if pages:
        row["pages"] = "%s-%s" % (pages.group(1), pages.group(2))
    row.update(_authors(text))
    span = _title_span(text, row.get("author_blob") or "")
    row["title"] = _dehyphenate(text[span[0]:span[1]].strip())
    row.update(_venue(text, title_span=span, year=row.get("year")))
    # The year is often attached to whichever field precedes it: "In ECCV. 2014"
    # as the venue, or "… vision algorithms, 2008" as the title. Leaving it in
    # place duplicates it in both renderings ("In ECCV. 2014, 2014").
    year = row.get("year")
    if year:
        row["title"] = re.sub(r",?\s*\.?\s*" + year + r"\s*$", "", row["title"]).strip(" .,;:")
        row["venue"] = re.sub(r",?\s*\.?\s*" + year + r"\s*$", "", row.get("venue") or "").strip(" .,;:")
    return row


def _author_blob(text):
    """The leading author run, consumed one name-list chunk at a time.

    Splitting on the first period truncates "Y. Bengio, P. Simard" to "Y." —
    initials contain periods too. So each period-delimited chunk is tested: if
    it still reads as a list of names the run continues; the first chunk that
    reads as a title ends it.
    """
    # "et al." is the last token of the author run, and the token before it
    # ("McCormick,") looks like a title once the period splits the string.
    marker = re.search(r"\bet\.?\s*al\.?(?=\s|$)", text)
    if marker and marker.start() < 400:
        head = text[:marker.start()]
        if _name_chunk(head + "."):
            return text[:marker.end()].rstrip()
    pos, end = 0, 0
    for match in re.finditer(r"\.\s+", text):
        chunk = text[pos:match.end()]
        if re.search(r"\bet\.?\s*al\b", chunk, re.I):
            # "et al." closes the author run; the next chunk is the title even
            # when it happens to look like a list of capitalised words.
            end = match.end()
            break
        if _name_chunk(chunk):
            end = match.end()
            pos = match.end()
            continue
        break
    if not end:
        return ""
    return text[:end].rstrip()


# A mark that belongs inside a name, with a space where it was lost.
_SPLIT_MARK = re.compile(r"(\w)\s+([-\u2019'\u00b4])\s+(?=\w)")
# The mark stayed with the word and the space came after it: "Marc' Aurelio".
_GLUED_MARK = re.compile(r"(\w[-\u2019'\u00b4])\s+(?=[A-Z\u00c0-\u024f])")
# A lone capital immediately before a lowercase word: "L ukasz" is "Lukasz"
# with the stroke of the L dropped, not two people.
_LONE_CAPITAL = re.compile(r"(?<![\w\u00c0-\u024f])([A-Z])\s+(?=[a-z\u00c0-\u024f]{3,})")


def _rejoin_names(body):
    """Put back the spaces that lost marks left inside author names."""
    fixed = _SPLIT_MARK.sub(r"\1\2", body)
    fixed = _GLUED_MARK.sub(r"\1", fixed)
    return _LONE_CAPITAL.sub(r"\1", fixed)


def _name_chunk(chunk):
    """True when a period-terminated chunk reads as personal names, not a title."""
    body = chunk.strip().rstrip(".")
    if not body:
        return True
    body = _rejoin_names(body)
    pieces = [p for p in re.split(r",\s*|\s+and\s+|\s*&\s*", body) if p.strip()]
    if not pieces:
        return False
    # An author list is bounded by its length, not by how many people wrote the
    # paper: a real reference can name twenty authors, while a title runs long
    # even before it has any commas at all.
    if len(body) > 400:
        return False
    for piece in pieces:
        tokens = [t for t in re.split(r"\s+", piece.strip()) if t]
        if not tokens or len(tokens) > 5:
            return False
        for token in tokens:
            if _name_ok(token):
                continue
            # A short lowercase fragment between two capitalised tokens is a
            # name whose hyphen was lost ("Wen tau Yih"). The same word next to
            # other lowercase words is prose, so the neighbours decide.
            if not _BROKEN_MIDDLE.fullmatch(token):
                return False
            at = tokens.index(token)
            if at == 0 or at == len(tokens) - 1:
                return False
            if not (_CAP_START.match(tokens[at - 1]) and _CAP_START.match(tokens[at + 1])):
                return False
    return True


# A personal-name token. Three shapes are names: initials ("Y.", "B.", and the
# hyphenated pair "K.-R."), CamelCase or hyphenated surnames ("McCormick",
# "Warde-Farley"), and plain capitalised surnames. A replaced character
# (U+FFFD) counts as a letter because pdftotext drops accented bytes
# ("Montúfar" arrives as "Montu\uFFFdfar") and losing the whole author run over
# one lost byte is worse than carrying the corruption into the reported gap.
# All-caps acronyms ("R-CNN", "VGG-16") still fail, which keeps a capitalised
# title out of the author run.
_NAME_LETTER = r"A-Za-z\u00c0-\u024f\ufffd"
_NAME_TOKEN = re.compile(
    r"^(?:"
    r"[A-Z\u00c0-\u024f\ufffd]\.(?:-?[A-Z\u00c0-\u024f\ufffd]\.?)*"
    r"|[A-Z\u00c0-\u024f\ufffd][%s]*"
    r"(?:[\u2019'\-][A-Z\u00c0-\u024f\ufffd][%s]+"
    r"|[A-Z\u00c0-\u024f\ufffd][%s]+)*\.?"
    r")$" % (_NAME_LETTER, _NAME_LETTER, _NAME_LETTER)
)

# A surname particle belongs to the name even when it starts lowercase, so
# 'van Merrie\u00a8nboer' and 'dos Santos' cannot be rejected on case alone.
# Anything else that starts lowercase still is.
_LOWER_PARTICLE = re.compile(
    r"^(?:(?:van|von|der|den|de|del|della|di|du|da|das|dos|le|la|ten|ter|bin|ibn|st)\s+)?[A-Z\u00c0-\u024f]")


_NAME_START = re.compile(r"^[A-Z\u00c0-\u024f\ufffd]")

# Hyphenated given names keep a lowercase tail: "Wen-tau Yih", "Jean-Pierre".
# The all-caps protection that rejects "R-CNN" and "VGG-16" still holds, since
# these require a lowercase letter after every hyphen.
_HYPHEN_NAME = re.compile(
    r"^[A-Z\u00c0-\u024f][a-z\u00c0-\u024f]+"
    r"(?:-[a-z\u00c0-\u024f][a-z\u00c0-\u024f]*)+$")


# pdftotext renders an accented vowel as the plain vowel plus a stray backtick
# ("Candès" -> "Cande`s", "Nicolò" -> "Nicolo`"). The mark belongs to the letter
# it decorates; leaving it in made one author sink the whole run.
# pdftotext writes a lost diacritic as a separate glyph: "ñ" arrives as
# "N~ eco", "ü" as "Mu×nchen", "è" as "Cande`s". The mark is not part of the
# name, and leaving it in made the whole author run unreadable.
# Spacing diacritics: the PDF puts the mark before the base letter, so the
# accent cannot be recomposed onto the right vowel. Dropping the mark keeps
# the name matchable; guessing the vowel would invent a spelling.
# Presentation-form ligatures the PDF draws as one glyph. Expanding them is
# lossless and keeps surnames searchable; NFKC is deliberately not used here
# because it also rewrites spacing diacritics as a space plus a combining
# mark, which would split "Ru¨ckle" into two tokens.
_LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
    "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
}


def _expand_ligatures(text):
    """Replace ligature glyphs with the letters they stand for."""
    if not text:
        return text
    for ligature, plain in _LIGATURES.items():
        text = text.replace(ligature, plain)
    return text


_ACCENT_MARK = re.compile("[`\u00b4~\u00a8\u02c7\u02d8\u02d9\u02da\u02db\u02dd\u02c6\u02dc]")
# The mark of a lost diacritic sitting on its own before a space: "N~ eco".
# A spacing diacritic that lost its base letter leaves "mark + space" behind:
# "N\u02dc eco", "Dus\u02c7 ek". Drop the mark together with the space it pulled
# in, otherwise the surname stays split in two and matches no entry.
_MARK_GAP = re.compile("[" + "`\u00b4~\u00a8\u02c7\u02d8\u02d9\u02da\u02db\u02dd\u02c6\u02dc" + r"]\s+(?=[a-z\u00c0-\u024f])")


_BROKEN_MIDDLE = re.compile(r"[a-z\u00c0-\u024f]{2,5}")
_CAP_START = re.compile(r"^[A-Z\u00c0-\u024f]")


def _name_ok(token):
    bare = _ACCENT_MARK.sub("", token)
    return bool(_NAME_TOKEN.match(bare) or _HYPHEN_NAME.match(bare)
                or bare.lower().strip(".") in _NAME_CONNECTORS)

_NAME_CONNECTORS = {"and", "et", "al", "etal", "eds", "ed", "jr", "sr",
                    "iii", "ii", "van", "von", "de", "den", "der", "del",
                    "della", "da", "di", "du", "dos", "das", "do", "la", "le",
                    "ten", "ter", "bin", "ibn", "st"}


def _split_name(name):
    """Return (surname, initials) for a reference-style personal name."""
    tokens = [t for t in re.split(r"\s+", name.strip()) if t]
    given, i = [], 0
    while i < len(tokens) and re.fullmatch(r"[A-Z](?:\.?-?[A-Z]?)*\.?", tokens[i]):
        # "C.-Y." and "K.-R." carry two initials; keep every capital in the token
        # so the rendered form is "LEE CY", not "LEE C".
        given.extend(ch for ch in tokens[i].upper() if ch.isalpha())
        i += 1
    surname = " ".join(tokens[i:])
    if not given and len(tokens) >= 2:
        # "Kaiming He" — given name spelled out, surname last.
        surname = tokens[-1]
        given = tokens[:-1]
    return surname, given


def _authors(text):
    blob = _author_blob(text)
    if not blob:
        return {"authors": [], "author_blob": "", "author_parts": []}
    cleaned = re.sub(r"\bet\s+al\.?", " ", blob, flags=re.I)
    cleaned = re.sub(r"\beds?\.?", " ", cleaned, flags=re.I)
    # Normalise the final conjunction before splitting: "A, B, and C" splits on
    # the comma into "and C", which no longer starts with a capital and would be
    # dropped. Folding "and"/"&" into a comma keeps C a name.
    cleaned = re.sub(r",?\s+(?:and|&)\s+", ", ", cleaned)
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    parts = []
    for piece in cleaned.split(","):
        piece = " ".join(piece.split()).strip(" ,;.")
        if not piece or piece.lower() in _NAME_CONNECTORS:
            continue
        if len(piece.split()) > 6 or not _LOWER_PARTICLE.match(piece):
            continue
        parts.append(piece)
    return {"authors": parts[:20], "author_blob": " ".join(blob.split()),
            "author_parts": [_split_name(a) for a in parts[:20]]}


HYPHEN_BREAK = re.compile(r"(\w)-\s+(?=[a-z])")


def _dehyphenate(value):
    """Rejoin words split across a line break: "hier- archies" -> "hierarchies".

    PDF extraction keeps the newline where the typesetter broke a long word. A
    reference list is dense with long technical terms, so leaving the break in
    corrupts the title in every downstream format.
    """
    if not value:
        return value
    return HYPHEN_BREAK.sub(r"\1", value)


def _title_span(text, author_blob):
    """Start and end offsets of the title inside the raw entry text.

    The span is reported instead of the cleaned string because dehyphenation
    rewrites it ("hier- archies" -> "hierarchies"), and a later lookup by the
    cleaned value would never find its place in the raw text.
    """
    start = 0
    if author_blob:
        cut = text.find(author_blob)
        if cut >= 0:
            start = cut + len(author_blob)
    rest = text[start:]
    lead = len(rest) - len(rest.lstrip(" .,;:"))
    start += lead
    rest = rest[lead:]
    match = re.match(r"(.{10,300}?)(?:\.\s|\.$)", rest)
    end = start + (match.end(1) if match else min(len(rest), 300))
    return start, end


def _title(text, author_blob):
    start, end = _title_span(text, author_blob)
    return _dehyphenate(text[start:end].strip())


VOLUME_ISSUE = re.compile(r"\b(\d{1,4})\s*\(\s*(\d{1,3})\s*\)")


def _venue(text, title_span=None, year=None, pages=None):
    """Journal name plus volume/issue, taken from the tail after the title.

    The tail is one comma-joined run ("IEEE Transactions on Neural Networks,
    5(2):157-166, 1994"), so the journal is whatever precedes the first
    comma-delimited numeric segment. Returning the whole tail as the journal
    would repeat the year and pages in every formatted entry.
    """
    rest = text
    if title_span:
        rest = text[title_span[1]:]
    rest = rest.lstrip(" .,;:")
    if not rest:
        return {"venue": "", "volume_issue": ""}
    segments = [s.strip() for s in rest.split(",") if s.strip()]
    journal_parts = []
    for segment in segments:
        if re.match(r"^[\d\s:p()\-]+$", segment):
            break
        if re.match(r"^(?:pages?|pp\.?)\s", segment, re.I):
            break
        if year and segment.strip(". ") == str(year):
            break
        journal_parts.append(segment.strip(". "))
    journal = ", ".join(journal_parts).strip(". ")
    vi = VOLUME_ISSUE.search(rest)
    volume_issue = "%s(%s)" % (vi.group(1), vi.group(2)) if vi else ""
    return {"venue": journal[:200], "volume_issue": volume_issue}


def _in_text(bundle, doc, entries):
    """Every in-text citation marker, and whether it resolves to an entry.

    Brackets also hold measurements: ResNet samples the shorter image side in
    "[256, 480]", which the naive pattern reads as citations 256 and 480 and
    then reports as dangling. A number far outside the reference list cannot be
    a citation to it, so those brackets are separated out and counted instead
    of being raised as defects.
    """
    text = "\f".join(doc["pages"])
    known = {e["index"] for e in entries if isinstance(e.get("index"), int)}
    ceiling = (max(known) if known else 0) + CITE_SLACK
    marked = []
    rejected = []
    for match in BRACKET.finditer(text):
        for part in re.split(r"\s*,\s*", match.group(1)):
            span = re.match(r"(\d+)\s*[\u2013-]\s*(\d+)", part)
            if span:
                low, high = int(span.group(1)), int(span.group(2))
                if 0 < high - low <= 30 and high <= ceiling:
                    marked.extend(range(low, high + 1))
                    continue
                if high > ceiling:
                    rejected.append(match.group(0))
                continue
            if part.strip().isdigit():
                value = int(part.strip())
                if value <= ceiling:
                    marked.append(value)
                else:
                    rejected.append(match.group(0))
    for match in CITE_CMD.finditer(text):
        for key in match.group(1).split(","):
            marked.append(key.strip())

    # 0 is never a bibliography index: it comes from "[0, p]" style tuples in
    # extracted layout instructions. Dropping it is not leniency about dangling
    # refs, it is refusing to call a non-citation a broken citation.
    numeric = [m for m in marked if isinstance(m, int) and m >= 1]
    dangling = sorted({m for m in numeric if known and m not in known})
    bundle.put("in_text_citation_count", len(marked))
    bundle.put("dangling_citations", dangling)
    bundle.put("non_citation_brackets", sorted(set(rejected))[:20])
    if rejected:
        bundle.note("有 %d 处方括号不是引用（数值超出参考文献条目范围），已作为测量值排除：%s"
                    % (len(set(rejected)), "、".join(sorted(set(rejected))[:5])))
    if dangling:
        bundle.gap(item="悬空引用", reason="正文引用了参考文献表中不存在的编号：%s"
                   % ", ".join(str(d) for d in dangling[:20]),
                   field="dangling_citations", state="partial")
    # Only a numbered bibliography can have unused numbers. In an author-year
    # paper nothing is numbered, so listing all 56 entries as "never cited"
    # states a defect that does not exist.
    # Which style is this? A numbered bibliography is cited by number and has
    # no author-year markers; the reverse holds for an author-year paper. Only
    # the dominant style can say anything about uncited entries: a stray "[12]"
    # in an author-year paper is a figure reference, not a citation style.
    ay_markers = len(AUTHOR_YEAR.findall("\f".join(doc["pages"])))
    style = "numeric" if len(numeric) > ay_markers else "author-year"
    bundle.put("citation_style", style)
    if style == "numeric":
        uncited = sorted(known - set(numeric))
        bundle.put("uncited_entries", uncited)
        if uncited:
            bundle.gap(item="未引用条目", reason="参考文献表中存在正文从未引用的条目：%s"
                       % ", ".join(str(u) for u in uncited[:20]),
                       field="uncited_entries", state="partial")
    else:
        bundle.put("uncited_entries", [])
        bundle.note("正文以作者-年份形式标注引用（%d 处），编号方括号 %d 处不计为引用计数；"
                    "未引用条目改由作者-年份比对给出。"
                    % (ay_markers, len(numeric)))

    _author_year(bundle, doc, entries, numeric, style=style)


def _author_year(bundle, doc, entries, numeric, style="numeric"):
    """Author-year citations, the other half of the 挂得对 question.

    A bracketed-number parser sees nothing in "(Devlin et al., 2018)" and then
    reports that the manuscript cites no references at all. Both styles are
    counted here, and each author-year hit is resolved to a bibliography entry
    by surname plus year so "cites X but X is not in the list" is detectable.

    The year suffix is load bearing. NLP bibliographies disambiguate two works
    by the same author in the same year as 2018a / 2018b, and the citation uses
    the suffix too. Keying the index on the bare year collapsed those pairs into
    one entry: whichever was indexed first absorbed every citation and its
    sibling was then reported as never cited, which is exactly backwards.
    """
    if numeric and len(numeric) > 20:
        return  # a numbered bibliography; author-year scanning adds noise only
    text = _MARK_GAP.sub("", "\f".join(doc["pages"]))
    # Same expansion the entries get: "Rebuf\ufb01 et al., 2017" in the body
    # must match the "Rebuffi" the reference list produces.
    text = _expand_ligatures(text)

    # (surname, year) -> [(entry, is_first_author), ...]; the suffix decides
    # among siblings. Whether the surname is the entry's first author matters:
    # "Mikolov et al., 2013" most often means Mikolov's own paper, but he is
    # also a middle author on the One Billion Word benchmark published the same
    # year, and without this flag the earlier entry absorbed the citation.
    index = {}
    for entry in entries:
        year = entry.get("year")
        if not year:
            continue
        key_year = str(year)
        surnames = _entry_surnames(entry)
        for position, surname in enumerate(surnames):
            index.setdefault((surname.lower(), key_year), []).append(
                (entry, position == 0))

    if not index:
        return

    hits = []
    for match in AUTHOR_YEAR.finditer(text):
        inner = match.group(1)
        if "[" in inner or "\f" in inner:
            continue
        for part in AUTHOR_YEAR_PART.finditer(inner):
            hits.append((part.group(1), part.group(2), match.group(0)))
    for match in NARRATIVE_CITE.finditer(text):
        hits.append((match.group(1), match.group(2), match.group(0)))

    resolved, unresolved = [], []
    # Deduplicate per worked citation, not per parenthetical: one parenthetical
    # routinely carries several works -- "(Brown et al., 1992; Ando and Zhang,
    # 2005; Blitzer et al., 2006)" -- and keying on the whole group dropped
    # every work after the first, which then showed up as an uncited entry.
    seen = set()
    for surname, year_field, raw in hits:
        year, suffix = _split_year(year_field)
        key_seen = (surname.lower(), year, suffix)
        if key_seen in seen:
            continue
        seen.add(key_seen)

        matched = None
        for candidate in _surname_candidates(surname):
            bucket = index.get((candidate.lower(), year))
            if not bucket:
                continue
            picked = _pick_by_suffix(bucket, suffix, resolved)
            if picked:
                matched = (candidate, picked)
                break

        row = {"author": surname, "year": year_field, "marker": raw[:80]}
        if matched:
            row["author"] = matched[0]
            row["entry_index"] = matched[1].get("index")
            row["year_suffix"] = suffix or None
            resolved.append(row)
        else:
            unresolved.append(row)

    if not resolved and not unresolved:
        return
    bundle.put("author_year_citations", resolved)
    bundle.put("author_year_unresolved", unresolved[:30])
    bundle.put("author_year_citation_count", len(resolved))

    cited = {r.get("entry_index") for r in resolved}
    never = [e.get("index") for e in entries
             if e.get("index") not in cited and e.get("index") not in set(numeric)]

    # Before calling an entry uncited, check whether the text names it with a
    # different year. Papers cite a work by its published year while their own
    # bibliography prints the preprint year, and saying "never cited" about such
    # an entry is a statement the material contradicts.
    drifted = []
    if never:
        cited_years = {}
        for row in resolved + unresolved:
            cited_years.setdefault((row.get("author") or "").lower(), set()).add(
                str(row.get("year")))
        remaining = []
        for entry in entries:
            index = entry.get("index")
            if index not in never:
                continue
            surnames = {s.lower() for s in _entry_surnames(entry)}
            seen_years = set()
            for surname in surnames:
                seen_years |= cited_years.get(surname, set())
            listed = str(entry.get("year") or "")
            other = sorted(y for y in seen_years if y and y != listed)
            if listed and other:
                drifted.append({"entry_index": index,
                                "listed_year": listed,
                                "cited_years": other})
            else:
                remaining.append(index)
        never = remaining
    # An entry with no readable year never entered the index, so no citation
    # could reach it. Calling it "never cited" blames the manuscript for what the
    # bibliography did not print.
    by_index = {}
    for entry in entries:
        by_index[entry.get("index")] = entry
    dateless = [i for i in never if not (by_index.get(i) or {}).get("year")]
    if dateless:
        never = [i for i in never if i not in dateless]
        bundle.put("entries_without_year", dateless)
        bundle.note("有 %d 条文献自身未印年份，无法参与作者-年份比对，不作为未引用处理：%s"
                    % (len(dateless), ", ".join(str(x) for x in dateless[:10])))
    bundle.put("author_year_uncited", never)
    if drifted:
        bundle.put("year_disagreements", drifted)
        bundle.note("有 %d 条文献在正文中被引用时写作另一个年份（文献表印的是预印本年，"
                    "正文按发表年引用），已作为年份不一致登记而非未引用：%s"
                    % (len(drifted),
                       "、".join("%s 表列 %s / 正文 %s" % (
                           d["entry_index"], d["listed_year"], "/".join(d["cited_years"]))
                           for d in drifted[:6])))
    # In an author-year paper this comparison is the only evidence there is, so
    # it is reported. In a numbered paper the same comparison would call every
    # entry uncited, because author-year markers are not how it cites.
    if never and style == "author-year":
        bundle.gap(item="未引用条目（作者-年份）",
                   reason="以下条目未在正文中以作者-年份形式引用：%s"
                          % ", ".join(str(x) for x in never[:20]),
                   field="uncited_entries", state="partial")


def _split_year(value):
    """Split "2018a" into ("2018", "a"); a bare year keeps an empty suffix."""
    value = str(value or "").strip()
    match = re.fullmatch(r"((?:19|20)\d{2})([a-z]?)", value)
    if not match:
        return value, ""
    return match.group(1), match.group(2)


def _pick_by_suffix(bucket, suffix, already):
    """Choose among same-surname same-year entries, honouring an a/b suffix.

    Preference order: a first-author match, then a sibling no other citation has
    claimed, then the earliest entry. Without the first-author preference a
    commonly cited researcher who is also a middle author elsewhere lets the
    earlier paper absorb the citation and leaves their own paper looking uncited.
    """
    taken = {row.get("entry_index") for row in already}
    ordered = sorted(bucket, key=lambda pair: pair[0].get("index") or 0)
    if suffix and len(ordered) > 1:
        # The bibliography's own letter decides. Position in the list does not:
        # the entry printed "2018b" can come first, and then "2018a" bound to it
        # and the real 2018a was reported as never cited.
        printed = [pair for pair in ordered
                   if (pair[0].get("year_suffix") or "") == suffix]
        if len(printed) == 1:
            return printed[0][0]
        if printed:
            for entry, _ in printed:
                if entry.get("index") not in taken:
                    return entry
            return printed[0][0]
        position = ord(suffix) - ord("a")
        if 0 <= position < len(ordered):
            return ordered[position][0]
    for entry, first_author in ordered:
        if first_author and entry.get("index") not in taken:
            return entry
    for entry, _ in ordered:
        if entry.get("index") not in taken:
            return entry
    return ordered[0][0]

def _renumber(bundle, doc, entries):
    """The order citations actually appear in, and the mapping that produces it."""
    text = "\f".join(doc["pages"])
    known = {e.get("index") for e in entries if isinstance(e.get("index"), int)}
    ceiling = (max(known) + CITE_SLACK) if known else None
    order = []
    skipped = []
    for match in BRACKET.finditer(text):
        for part in re.split(r"\s*,\s*", match.group(1)):
            span = re.match(r"(\d+)\s*[\u2013-]\s*(\d+)", part)
            values = (range(int(span.group(1)), int(span.group(2)) + 1)
                      if span else ([int(part)] if part.strip().isdigit() else []))
            for value in values:
                # The same measurement brackets CITE_SLACK excludes from the
                # citation count also appear here; leaving them in produces a
                # renumber map that renumbers "[256, 480]" into [51] and [52].
                if ceiling is not None and value > ceiling:
                    if value not in skipped:
                        skipped.append(value)
                    continue
                if value not in order:
                    order.append(value)
    if not order:
        ay_hits = len(bundle.payload.get("author_year_citations") or [])
        if ay_hits:
            bundle.put("renumber_applicability", "not_applicable")
            bundle.note("该文献表按作者-年份标注引用（共 %d 处），不使用编号，"
                        "因此无需推导重编号映射；作者-年份的解析结果见 "
                        "author_year_citations" % ay_hits)
        else:
            bundle.gap(item="引用顺序",
                       reason="正文中未找到编号引用标记，也未识别到作者-年份标注，"
                              "无法推导重编号映射",
                       field="renumber_map", state="not_reported")
        return
    if skipped:
        bundle.note("有 %d 处方括号数值超出文献表范围，未计入引用顺序：%s"
                    % (len(skipped), "、".join(str(s) for s in skipped[:10])))
    mapping = [{"old": old, "new": idx + 1} for idx, old in enumerate(order)]
    moved = [m for m in mapping if m["old"] != m["new"]]
    bundle.put("citation_order", order)
    bundle.put("renumber_map", mapping)
    bundle.put("renumber_changes", len(moved))
    for item in moved[:40]:
        bundle.change("renumber", "[%d]" % item["old"], "[%d]" % item["new"],
                      where="正文引用与参考文献表", reason="按首次出现顺序重排")
    if moved:
        renumber = {item["old"]: item["new"] for item in mapping}
        bundle.put("renumbered_text",
                   _apply_renumber(text, renumber, ceiling))
        bundle.put("renumbered_references",
                   [{"new_index": renumber.get(e.get("index"), e.get("index")),
                     "entry": e.get("raw")}
                    for e in entries])
        bundle.note("%d 条参考文献按首次引用顺序重排，正文与文献表均已生成重编号后的"
                    "文本；映射见 renumber_map，可据它回退原编号" % len(moved))


def _apply_renumber(text, mapping, ceiling):
    """Rewrite every citation marker in the body to its new number.

    Markers whose numbers fall outside the bibliography are measurements, not
    citations, and are left exactly as printed.
    """
    def swap(match):
        inner = match.group(1)
        parts = []
        for part in re.split(r"\s*,\s*", inner):
            span = re.match(r"(\d+)\s*[\u2013-]\s*(\d+)", part)
            if span:
                low, high = int(span.group(1)), int(span.group(2))
                if ceiling is not None and high > ceiling:
                    parts.append(part)
                    continue
                parts.append("%d\u2013%d" % (mapping.get(low, low),
                                              mapping.get(high, high)))
                continue
            if part.strip().isdigit():
                value = int(part)
                if ceiling is not None and value > ceiling:
                    parts.append(part)
                    continue
                parts.append(str(mapping.get(value, value)))
                continue
            parts.append(part)
        return "[" + "".join(parts) + "]"

    return BRACKET.sub(swap, text)


def _norm_title(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _dedupe(bundle, entries):
    """Merge entries that are the same work under different spellings."""
    groups = []
    seen = {}
    for entry in entries:
        key = None
        if entry.get("doi"):
            key = "doi:" + entry["doi"].lower()
        else:
            norm = _norm_title(entry.get("title"))
            if len(norm) >= 20:
                key = "title:" + norm
        if key is None:
            continue
        if key in seen:
            groups.append((seen[key], entry))
        else:
            seen[key] = entry
    merged = [{"keep": a["index"], "drop": b["index"],
               "reason": ("DOI 相同" if a.get("doi") and a.get("doi") == b.get("doi")
                          else "标题归一化后相同"),
               "title": (a.get("title") or "")[:120]} for a, b in groups]
    bundle.put("duplicate_groups", merged)
    bundle.put("duplicate_count", len(merged))
    for item in merged:
        bundle.change("merge", "[%s]" % item["drop"], "[%s]" % item["keep"],
                      where="参考文献表", reason=item["reason"])
    if not merged:
        bundle.put("dedupe_note", "未发现 DOI 或标题完全一致的重复条目")


def _formats(bundle, entries):
    """GB/T 7714-2015 and APA renderings, plus what blocked completion."""
    gbt, apa, blocked = [], [], []
    for entry in entries:
        gb, miss1 = _gbt7714(entry)
        ap, miss2 = _apa(entry)
        if gb:
            gbt.append({"index": entry["index"], "text": gb})
        if ap:
            apa.append({"index": entry["index"], "text": ap})
        missing = sorted(set(miss1) | set(miss2))
        if missing:
            blocked.append({"index": entry["index"], "missing": missing})
    bundle.put("gbt7714", gbt)
    bundle.put("apa", apa)
    bundle.put("format_blocked", blocked)
    if blocked:
        bundle.put("format_blocked_count", len(blocked))
        bundle.note("%d 条记录缺少 GB/T 7714—2015 或 APA 要求的字段，"
                    "已按可得字段给出条目并在 format_blocked 中逐条登记缺项；"
                    "这些字段在原文文献表中未印，补齐需回到原文或外部数据库"
                    % len(blocked))


def _gbt7714(entry):
    miss = []
    authors = entry.get("author_parts") or []
    if not authors:
        miss.append("作者")
    author_text = _gbt_authors(authors) if authors else "[佚名]"
    title = entry.get("title") or ""
    if not title:
        miss.append("题名")
    venue = entry.get("venue") or ""
    if not venue:
        miss.append("刊名")
    year = entry.get("year")
    if not year:
        miss.append("年")
    # GB/T 7714-2015: 主要责任者. 题名[文献类型标志]. 出版项. 出版年: 页码.
    head = "%s. %s[J]" % (author_text, title)
    tail = []
    if venue:
        tail.append(venue)
    if year:
        tail.append(year)
    body = ", ".join(x for x in tail if x)
    if entry.get("volume_issue") or entry.get("pages"):
        cite = ": ".join(x for x in (entry.get("volume_issue"), entry.get("pages")) if x)
        body = (body + ", " if body else "") + cite
    parts = [head]
    if body:
        parts.append(body)
    if entry.get("doi"):
        parts.append("DOI: %s" % entry["doi"])
    return ". ".join(p for p in parts if p.strip(" .")) + ".", miss


def _gbt_authors(author_parts):
    """GB/T 7714 lists at most three names, then 等."""
    flipped = []
    for surname, given in author_parts[:3]:
        initials = "".join(g[:1].upper() for g in given if g)
        flipped.append(("%s %s" % (surname.upper(), initials)).strip())
    text = ", ".join(flipped)
    if len(author_parts) > 3:
        text += ", 等"
    return text


def _apa(entry):
    miss = []
    author_parts = entry.get("author_parts") or []
    if not author_parts:
        miss.append("作者")
    year = entry.get("year")
    if not year:
        miss.append("年")
    title = entry.get("title") or ""
    if not title:
        miss.append("题名")
    author_text = _apa_authors(author_parts) if author_parts else "[Anonymous]"
    tail = []
    if entry.get("venue"):
        tail.append(entry["venue"])
    if entry.get("volume_issue"):
        tail.append(entry["volume_issue"])
    if entry.get("pages"):
        tail.append(entry["pages"])
    text = "%s (%s). %s." % (author_text, year or "n.d.", title)
    if tail:
        text += " " + ", ".join(tail) + "."
    if entry.get("doi"):
        text += " https://doi.org/%s" % entry["doi"]
    return text, miss


def _apa_authors(author_parts):
    """APA 7: up to 20 names, 'Surname, I.' with an ampersand before the last."""
    formatted = []
    for surname, given in author_parts[:20]:
        initials = " ".join("%s." % g[:1].upper() for g in given if g)
        formatted.append(("%s, %s" % (surname, initials)).strip().rstrip(","))
    if not formatted:
        return "[Anonymous]"
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + ", & " + formatted[-1]


_NEEDED = ("authors", "title", "venue", "year", "pages", "doi")


SOURCE_PROPERTY = {
    "doi": "预印本与多数会议论文本身不印 DOI",
    "pages": "会议论文与预印本常以篇号代替页码",
    "venue": "部分条目在该文献表中的印法不含刊名",
}


def _field_gaps(bundle, entries):
    """Which fields are missing, and which of them the source never carried."""
    # An entry whose own year line never printed cannot be counted as an
    # extraction miss: the note raised while indexing already says the
    # bibliography did not carry it. Reuse that decision instead of re-deriving it.
    dateless = set(bundle.payload.get("entries_without_year") or [])
    totals = {}
    for key in _NEEDED:
        if key == "year" and dateless:
            totals[key] = sum(1 for e in entries
                              if not e.get(key) and e.get("index") not in dateless)
        else:
            totals[key] = sum(1 for e in entries if not e.get(key))
    bundle.put("missing_field_totals", totals)
    if not entries:
        return
    live, inherent = [], []
    for key in _NEEDED:
        if not totals[key]:
            continue
        (inherent if key in SOURCE_PROPERTY else live).append(
            "%s(%d)" % (key, totals[key]))
    rows = [{"field": k, "missing": totals[k], "why": SOURCE_PROPERTY[k]}
            for k in _NEEDED if totals.get(k) and k in SOURCE_PROPERTY]
    if dateless:
        rows.append({"field": "year", "missing": len(dateless),
                     "why": "该条文献在原文文献表中未印年份，无法比对"})
        inherent.append("year(%d)" % len(dateless))
    if inherent:
        bundle.put("fields_absent_from_source", rows)
        bundle.note("以下字段在原文文献表中未印，属材料自身信息，"
                    "不是抽取失败：%s" % "、".join(inherent))
    if live:
        bundle.gap(item="字段补齐", reason="以下字段在部分条目中缺失且原文应当可查："
                   "%s；补齐需查证原文或外部数据库，本 Skill 不臆造"
                   % "、".join(live),
                   field="missing_field_totals", state="partial")
