"""Layout-independent scientific structure recovery.

Works on text that some extractor already produced, so it holds for PDF,
LaTeX sources and plain text alike. The goal is not to re-parse the document
but to recover the skeleton a reader needs: what the paper is, who wrote it,
how the argument is divided, and where every element sits.

Every function returns plain dicts, which keeps the Skills free to reshape
them per topic while still sharing one recovery pass.
"""

import re

_NUM = r"(?:\d+(?:\.\d+)*)"
# The number and the title must share a line: \s would also match a newline,
# and a number stranded at the foot of a page would then adopt the first line of
# the next page's table as its title.
SECTION_RE = re.compile(
    r"^[ \t\f]*(?P<num>" + _NUM + r")\.?[ \t]+(?P<title>[A-Z][^\n]{1,90}?)[ \t\r]*$",
    re.M)


def _plausible_heading(num, title):
    """Reject table rows and figure captions that merely start with a number."""
    if len(title) < 3:
        return False
    if re.search(r"\d\s+\d", title):
        return False
    if re.search(r"[\u00b1\u00d7\u2248\u2264\u2265]", title):
        return False
    words = title.split()
    if len(words) > 14:
        return False
    digit_tokens = [w for w in words if re.fullmatch(r"[\d.,%\-]+", w)]
    if digit_tokens:
        return False
    if not re.match(
            r"^[A-Z][A-Za-z0-9\-,'()/?!\u2019:\u2013\u2014 ]+$", title):
        return False
    # A heading normally contains ordinary lowercase letters, which is what
    # rejects "ResNet-18" style table labels. All-caps headings are equally
    # legitimate ("3 BERT", "2 BACKGROUND: NEURAL MACHINE TRANSLATION"); the
    # colon above and the word-shape test here are what let them through
    # without also letting through rows such as "13.93 21.50" (no digit token
    # survives the check above, and every token here must start with a letter).
    if not re.search(r"[a-z]{2,}", title):
        words = title.split()
        if not all(re.fullmatch(r"[A-Z][A-Z0-9\-,()':/?!]{0,24}", word)
                   for word in words):
            return False
        if not any(len(word) >= 3 for word in words):
            return False
    if num.count(".") >= 2 and len(words) > 10:
        return False
    return True


# A number alone on its line, one blank line, then the title. Kept separate
# from SECTION_RE so that the ordinary same-line form stays strict; the form
# feed is excluded on purpose, because "3" above a page break is a page foot.
SPLIT_HEADING_RE = re.compile(
    r"^[ \t]*(?P<num>" + _NUM + r")[ \t]*\r?\n[ \t]*\r?\n"
    r"(?P<title>[A-Z][^\n]{1,90}?)[ \t\r]*$", re.M)


_CANONICAL_BARE = frozenset("""
abstract introduction background related methods methodology experiments
results evaluation discussion conclusion conclusions references
acknowledgments acknowledgements limitations appendix
""".split())


def _plausible_bare_heading(line):
    """Unnumbered headings must be title case or all caps, never a stray word."""
    stripped = line.strip()
    if len(stripped) < 4 or len(stripped) > 60:
        return False
    if " " not in stripped and stripped.lower() not in _CANONICAL_BARE:
        # A lone capitalised word above a table is far more often a column
        # label ("Method", "Dataset") than a section title.
        return False
    if stripped.isupper():
        return True
    words = stripped.split()
    if not words:
        return False
    return all(w[:1].isupper() or w.lower() in ("and", "of", "the", "for", "in", "on")
               for w in words)
BARE_SECTION_RE = re.compile(
    r"^\s*(?P<title>Abstract|Introduction|Related Work|Background|Methods?ology|Methods|"
    r"Approach|Experiments?|Results?|Evaluation|Discussion|Conclusions?|"
    r"Limitations?|Future Work|References|Acknowledg(?:e)?ments?|Appendix)\s*$",
    re.M | re.I)
FIG_RE = re.compile(
    r"(?:^|\n)\s*(?:Figure|Fig\.?)\s*(\d+[a-z]?)\s*[:.|]?\s*(.{0,600})", re.I | re.S)
TAB_RE = re.compile(
    r"(?:^|\n)\s*(?:Table|Tab\.?)\s*(\d+[a-z]?)\s*[:.|]?\s*(.{0,600})", re.I | re.S)
EQ_RE = re.compile(r"\((\d+[a-z]?)\)\s*$", re.M)
EQ_LINE_RE = re.compile(r"[=\u2248\u2264\u2265\u00b1\u00d7\u2211\u222b\u2202\u221a]")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
ARXIV_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})(v\d+)?", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
MATH_TOKENS = set("=\u2248\u2264\u2265\u00b1\u00d7\u00f7\u2211\u222b\u2202\u221a\u221e"
                  "\u03b1\u03b2\u03b3\u03b4\u03b5\u03b6\u03b7\u03b8\u03b9\u03ba\u03bb"
                  "\u03bc\u03bd\u03be\u03c0\u03c1\u03c3\u03c4\u03c5\u03c6\u03c7\u03c8"
                  "\u03c9\u0391\u0392\u0393\u0394\u0395\u0396\u0397\u0398\u0399\u039a"
                  "\u039b\u039c\u039d\u039e\u039f\u03a0\u03a1\u03a3\u03a4\u03a5\u03a6"
                  "\u03a7\u03a8\u03a9")


def _lines(text):
    return [ln.rstrip() for ln in (text or "").splitlines()]


def running_lines(pages, min_ratio=0.5):
    """Short lines repeated near page edges are running heads or folios."""
    if len(pages) < 3:
        return set()
    counts = {}
    for page in pages:
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        edge = lines[:2] + lines[-2:]
        for line in edge:
            if not line or len(line) > 90:
                continue
            key = re.sub(r"\d+", "#", line.lower())
            counts[key] = counts.get(key, 0) + 1
    threshold = max(3, int(len(pages) * min_ratio))
    return {k for k, v in counts.items() if v >= threshold}


def strip_running_heads(text, pages=None, pages_split=None):
    """Remove repeated edge lines so they never enter the body text."""
    if pages_split is None:
        return text or "", []
    drop = running_lines(pages_split)
    removed = []
    kept_pages = []
    for page in pages_split:
        lines = page.splitlines()
        kept = []
        for idx, line in enumerate(lines):
            stripped = line.strip()
            key = re.sub(r"\d+", "#", stripped.lower())
            if stripped and len(stripped) <= 90 and key in drop and (
                    idx < 2 or idx >= len(lines) - 2):
                removed.append(stripped)
                continue
            kept.append(line)
        kept_pages.append("\n".join(kept))
    return "\f".join(kept_pages), removed


# "Ming-Wei Chang" and "Jean-Pierre Serre" are single given names with a
# hyphen. The plain "[A-Z][a-z]+ [A-Z][a-z]+" pattern matched only the tail
# ("Wei Chang"), which both invents an author and silently drops the real one.
# A capitalised word here may begin with any Latin capital (U+0141, "L with
# stroke", starts "Lukasz") and may carry a capital in the middle, because
# "KyungHyun" is one given name, not two words.
_CAP_WORD = (r"[A-Z\u00c0-\u024f][a-z\u00e0-\u024f]+"
             r"(?:[A-Z][a-z\u00e0-\u024f]+)*")
# After a hyphen a given name may continue in lower case ("Wen-tau").
_HYPHEN_TAIL = r"-[A-Z\u00c0-\u024f]?[a-z\u00e0-\u024f]+"
NAME_RE = re.compile(_CAP_WORD + r"(?:" + _HYPHEN_TAIL + r")?"
                     r"\s+" + _CAP_WORD + r"(?:" + _HYPHEN_TAIL + r")?")

# "Aidan N. Gomez", "C. Daniel Freeman": NAME_RE sees only two adjacent
# capitalised words, so a name carrying initials between them matched nothing
# and the author disappeared from the list.
NAME_INITIAL_RE = re.compile(
    r"\b" + _CAP_WORD
    + r"(?:\s+[A-Z\u00c0-\u024f]\.){1,3}"
    + r"\s+" + _CAP_WORD)
AFFIL_RE = re.compile(r"\b(University|Universit\u00e4t|Institute|Institut|Department|"
                      r"Laborator|College|School|Academy|Research|Inc\.|Ltd|Corp|"
                      r"Center|Centre|Faculty|"
                      # Industry labs name themselves without any of the words
                      # above: "Google AI Language", "Microsoft Research",
                      # "Facebook AI Research".
                      r"Google|Microsoft|Facebook|Meta AI|Amazon|NVIDIA|DeepMind|"
                      r"OpenAI|Baidu|Tencent|Alibaba|Huawei|Apple|IBM|Samsung|"
                      r"ByteDance|Salesforce|Adobe)\b")
HEAD_STOP_RE = re.compile(r"^(abstract|keywords|arxiv|doi|copyright|ccs concepts)",
                          re.I)
BOILERPLATE_RE = re.compile(
    r"(provided proper attribution|hereby grants permission|reproduce the tables|"
    r"copyright|all rights reserved|licensed under|creative commons|"
    r"preprint|under review|published as a conference paper|"
    r"\barxiv:\s*\d|^\s*doi\b)", re.I)


def _squeeze(line):
    return re.sub(r"\s+", " ", line).strip()


def _grow_name(line, start, end, limit=3):
    """Finish a name whose tail NAME_RE could not match.

    NAME_RE needs two capitalised words separated by a space.  A surname that
    the extractor damaged ("Rockt?schel", with the umlaut replaced) breaks the
    second word, so the match stops at "Tim Rockt" and the person is recorded
    under half a name.  Only that case is repaired: if the character that
    stopped the match is a separator, the name ended there on its own.
    """
    tail = line[end:end + 1]
    if not tail or tail.isspace() or tail in FOOTMARK_CHARS or tail in ",;.:)":
        return line[start:end].strip()
    name = line[start:end]
    rest = line[end:]
    for _ in range(limit):
        step = re.match(r"(\S+)(?:\s+|$)", rest)
        if not step:
            break
        token = step.group(1).strip(",;.")
        if not token or _marks_only(token):
            break
        if token[0] in FOOTMARK_CHARS:
            break
        if AFFIL_RE.search(token) or token in AFFIL_JOIN_WORDS:
            break
        # A non-ASCII lowercase token is the rest of the surname that the
        # extractor split off ("Rockt" + "aschel"), so it reattaches
        # without a space; an ASCII lowercase token is a new word.
        continued = (token[:1] in "\u00d7\ufffd"
                     or (token[0].islower() and not token[0].isascii()))
        name = name + token if continued else name + " " + token
        rest = rest[step.end():]
    return name.strip()


# Footmark glyphs a publisher sets beside a name. They separate a name from the
# next name or from the affiliation, and never belong to a person's name.
FOOTMARK_CHARS = "\u2217*\u2020\u2021\u00a7\u00b6\u2223#"

# Words that continue an affiliation rather than a name ("University of
# Toronto" must survive as one span, but "Kaiming He" must not swallow it).
AFFIL_JOIN_WORDS = frozenset("of at for de di del van der den la le".split())

_FOOTMARK_RUN = re.compile("[%s]+" % re.escape(FOOTMARK_CHARS))


def _bare_token(token):
    """A token with footmarks, commas and periods removed."""
    return "".join(ch for ch in (token or "") if ch not in FOOTMARK_CHARS
                   ).strip(".,;:")

def _marks_only(token):
    """True when the token carries nothing but footmark glyphs."""
    return bool(token) and all(ch in FOOTMARK_CHARS for ch in token)


def _split_on_footmarks(line):
    """Pieces of a line with the footmarks removed.

    A footmark sits where a comma would sit in a well-set author list, so it is
    a separator. Splitting there is what recovers the second author on
    "Edward Hu Yelong Shen" without inventing a separator inside a name.
    """
    return [piece.strip(" ,;") for piece in _FOOTMARK_RUN.split(line or "")
            if piece.strip(" ,;")]


def _own_bibliography_offset(text):
    """Offset where the reference list starts, or len(text) when absent."""
    marks = []
    for match in re.finditer(
            r"(?im)^[ \t]*(?:\d+\.?[ \t]*)?(?:references|bibliography|"
            r"works cited|literature cited)[ \t]*\r?$", text or ""):
        marks.append(match.start())
    return min(marks) if marks else len(text or "")


def _own_doi(text):
    """The paper's own DOI, never one belonging to a cited paper."""
    if not text:
        return None
    head = text[:_own_bibliography_offset(text)]
    match = DOI_RE.search(head)
    return match.group(0) if match else None

def _looks_like_author_line(line):
    """A line that is a list of personal names is the author block, not a title."""
    names = NAME_RE.findall(line)
    if len(names) >= 3:
        return True
    if len(names) >= 2 and "," in line:
        return True
    if not names:
        return False
    # one name per line is common: accept it when the rest of the line is short
    # and carries no sentence punctuation, i.e. it reads as "Name Affiliation"
    residue = NAME_RE.sub(" ", line)
    residue = re.sub(r"[\s,;*&#\d]+", " ", residue).strip()
    if not residue:
        return True
    if re.search(r"[.!?]\s*$", line):
        return False
    tokens = residue.split()
    if len(tokens) > 8:
        return False
    # an affiliation word next to a capitalised name is enough evidence
    if any(t.lower().strip(",") in _INSTITUTION_HEADS for t in tokens):
        return True
    return len(tokens) <= 6


def _title_score(line):
    """How much a line looks like a paper title rather than a footer or name."""
    words = line.split()
    if not (2 <= len(words) <= 20) or len(line) > 170:
        return 0
    if line.endswith(".") and len(words) > 6:
        return 0
    # an author block is a list of names; it scores like a title on capitalisation
    # alone, so knock it out before capitalisation is counted
    persons = [n for n in NAME_RE.findall(line) if _is_person_name(n)]
    if len(persons) >= 3:
        return 0
    # An affiliation block also reads as a run of capitalised words: "Facebook
    # AI Research; University College London; New York University;".  Two or
    # more semicolon-separated segments that each contain an institution word
    # is a list of institutions, whatever its capitalisation score.
    if line.count(";") >= 1:
        segments = [seg for seg in line.split(";") if seg.strip()]
        houses = [seg for seg in segments if AFFIL_RE.search(seg)]
        if len(houses) >= 2:
            return 0
    caps = sum(1 for w in words if w[:1].isupper())
    ratio = caps / float(len(words))
    score = ratio
    if ratio >= 0.55:
        score += 0.5
    if 4 <= len(words) <= 14:
        score += 0.3
    if re.search(r"[:?]", line):
        score += 0.1
    return score


_CONT_TAIL = {"and", "of", "the", "for", "on", "in", "with", "a", "an", "to", "by",
              "via", "from", "at", "as", "or", "nor", "but", "than", "into"}


def _title_continues(line):
    """A wrapped title line ends mid-phrase: lowercase word, function word, comma."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped[-1] in ",;-\u2013\u2014":
        return True
    last_word = re.split(r"\s+", stripped)[-1].strip(".,;:!?")
    if not last_word:
        return False
    if last_word.lower() in _CONT_TAIL:
        return True
    # a title that continues onto the next line ends on a lowercase word
    return last_word[:1].islower()


_INSTITUTION_HEADS = {
    "google", "microsoft", "university", "institute", "research", "brain",
    "lab", "laboratory", "department", "dept", "center", "centre", "school",
    "college", "faculty", "academy", "inc", "ltd", "corp", "corporation",
    "meta", "facebook", "amazon", "apple", "nvidia", "intel", "ibm", "deepmind",
    "openai", "alibaba", "tencent", "baidu", "huawei", "bytedance", "tsinghua",
    "peking", "stanford", "berkeley", "mit", "cmu", "toronto", "montreal",
}


def _affiliation_spans(line, window=5, people=None):
    """Institution names inside a line that also holds author names.

    Extraction frequently puts "Kaiming He Xiangyu Zhang Microsoft Research"
    on one line, so a whole-line predicate can never identify the affiliation:
    the line is mostly person names. Instead the keyword marks an anchor and
    the span grows over capitalised tokens around it.

    Two traps this has to clear, both found by auditing its own output:

    * the name matcher happily reads "Google Brain" as a two-word person name,
      which then blocks the span from growing past "Google". Person tokens are
      therefore taken only from name matches that contain no affiliation
      keyword - an institution never is one.
    * "University of Toronto" contains a lowercase joiner, so a plain stop-list
      cut the span at "University". Joiners are allowed *inside* a span when a
      capitalised token follows them.
    """
    tokens = line.split()

    known = set()
    if people is not None:
        for name in people:
            known.update(name.split())
    person = set()
    for match in NAME_RE.finditer(line):
        toks = match.group(0).split()
        if known:
            # Only the tokens that occur in an extracted author name are
            # people. The rest of such a match is the institution's own name:
            # "New York" in "New York University", "University" in the
            # "Gomez  University" run that a double space welds together.
            # The line still carries the footmark beside the surname
            # ("Vaswani*"), while the author list holds the bare name.
            keep = [tok for tok in toks if _bare_token(tok) in known]
            person.update(keep)
            continue
        # A match that *begins* with an affiliation word is the institution
        # itself ("Google Brain"), not a person; one that begins with a person
        # and then runs into an institution ("Aidan N. Gomez University of
        # Toronto") is a person followed by an institution, and every token in
        # it must stay marked so the span cannot grow left across the name.
        if toks and AFFIL_RE.search(toks[0]):
            continue
        person.update(toks)

    spans = []
    for idx, token in enumerate(tokens):
        if not AFFIL_RE.search(token):
            continue
        if token.endswith("'s") or token.endswith("\u2019s"):
            continue  # possessive in running prose, not an institution
        start = idx
        while start > 0:
            prev = tokens[start - 1]
            if not _CAP_START.match(prev) or _bare_token(prev) in person:
                break
            if prev.lower().strip(".,") in _AFFIL_STOP:
                break
            start -= 1
        end = idx + 1
        while end < len(tokens) and end - start < window + 1:
            nxt = tokens[end]
            bare = nxt.lower().strip(".,;:")
            if bare in _AFFIL_JOIN and end + 1 < len(tokens):
                follower = tokens[end + 1]
                if (_CAP_START.match(follower) and _bare_token(follower) not in person
                        and follower.lower().strip(".,") not in _AFFIL_STOP):
                    end += 2
                    continue
                break
            if not _CAP_START.match(nxt) or _bare_token(nxt) in person:
                break
            if bare in _AFFIL_STOP:
                break
            end += 1
        span = EMAIL_RE.sub(" ", " ".join(tokens[start:end])).strip(" ,;")
        # The line still carries the footmark beside the surname of the
        # author standing next to the institution ("Vaswani* Google Brain").
        span = _bare_token(span)
        # A line can hold two sentences ("Google Brain. Work performed while
        # at Google Research."), and growth crosses the full stop freely. cut at
        # the first sentence boundary so the span stays one institution.
        span = re.split(r"(?<![A-Z])\.\s+(?=[A-Z])", span)[0].strip(" ,;.")
        # One line often lists several institutions.  Splitting them keeps each
        # one citable on its own, and stops a bare "University" from surviving
        # as a separate span after the head word took the rest.
        for part in re.split(r"\s*[;,]\s*", span):
            part = _bare_token(part).strip(" ,.")
            if not part or len(part) < 4 or part in spans:
                continue
            if not AFFIL_RE.search(part):
                continue
            # A bare head word identifies nothing: it is what remains when
            # growth was blocked by a name on the left.
            if len(part.split()) < 2:
                continue
            spans.append(part)
    # A wrapped line splits "Facebook AI Research" into "Facebook" and
    # "AI Research". Keep the longer span and drop the fragment.
    kept = []
    for span in spans:
        tail = any(other != span and other.endswith(span) for other in spans)
        if not tail:
            kept.append(span)
    return kept


_AFFIL_STOP = frozenset("""
a an the and or of for at in on to with by from abstract keywords arxiv
doi email e-mail fig figure table section eq equation
""".split())

# Lowercase words that belong inside a name rather than terminating it.
_AFFIL_JOIN = frozenset("of at for de di del van der".split())

_CAP_START = re.compile(r"^[A-Z\u00c0-\u024f]")


def _is_person_name(name):
    """Reject institution names that happen to look like two capitalised words."""
    first = name.split()[0].lower()
    return first not in _INSTITUTION_HEADS


def title_and_authors(text, pages_split=None):
    """Recover title, author line and affiliations from the first page head."""
    first = (pages_split[0] if pages_split else (text or "").split("\f")[0])
    lines = [_squeeze(ln) for ln in first.splitlines()]
    lines = [ln for ln in lines if ln]

    head = []
    for line in lines[:40]:
        if re.match(r"^abstract\b", line, re.I):
            break
        if BOILERPLATE_RE.search(line):
            continue
        # an author line often carries its e-mail inline; keep the name part
        if EMAIL_RE.search(line):
            line = _squeeze(EMAIL_RE.sub(" ", line))
            if not line:
                continue
        if re.match(r"^arxiv:", line, re.I) or HEAD_STOP_RE.match(line):
            continue
        head.append(line)

    # title first: the strongest capitalisation score wins, and the author test
    # must not veto it, because a title made of capitalised words also reads
    # like a list of names
    best_idx, best_score = -1, 0.0
    for idx, line in enumerate(head[:10]):
        score = _title_score(line)
        if score > best_score:
            best_idx, best_score = idx, score
    title_lines = []
    if best_idx >= 0 and best_score >= 0.6:
        title_lines.append(head[best_idx])
        for line in head[best_idx + 1:best_idx + 3]:
            if not _title_continues(title_lines[-1]):
                break
            if _title_score(line) < 0.6:
                break
            title_lines.append(line)
    title = " ".join(title_lines).strip()
    title_key = _squeeze(title).lower()

    authors = []
    affiliations = []
    for line in head:
        low = line.lower()
        if low and low in title_key:
            continue  # never mine names out of the title itself
        if _looks_like_author_line(line) or AFFIL_RE.search(line):
            # An affiliation roster ("Facebook AI Research; University
            # College London; New York University;") lists institutions and
            # no authors, but "New York" reads as a two-word person name.
            # Several semicolon-separated institutions on one line is what
            # tells the two apart, without guessing from word order.
            seats = [seg for seg in re.split(r"[;,]", line)
                     if AFFIL_RE.search(seg)]
            if len(seats) >= 2:
                continue
            # A footmark sits where a comma would sit in a well-set author
            # list, so "Edward Hu* Yelong Shen*" is two people, not one.
            # Splitting there first is what recovers the second author
            # without inventing a separator inside a name.
            for piece in _split_on_footmarks(line):
                for extra in NAME_INITIAL_RE.finditer(piece):
                    value = extra.group(0).strip()
                    if value not in authors and value.lower() not in title_key:
                        authors.append(value)
                for match in NAME_RE.finditer(piece):
                    name = match.group(0)
                    if not _is_person_name(name):
                        continue
                    if AFFIL_RE.search(name):
                        continue
                    # NAME_RE stops at the first token it cannot match, so a
                    # name whose later characters were lost by the extractor
                    # ("Tim Rockt" for "Tim Rocktuschel") comes out truncated.
                    # Grow the match over the adjoining capitalised token.
                    grown = _grow_name(piece, match.start(), match.end())
                    if grown and grown not in authors and grown.lower() not in title_key:
                        authors.append(grown)
    # "Kaiming He ... Microsoft Research" arrives as one extracted line, so a
    # whole-line test can never fire: the line always contains person names.
    # The institution is located *inside* the line instead, by growing
    # outwards from the affiliation keyword. This runs after every author line
    # has been read, because knowing who the authors are is what tells a place
    # name ("New York University") from a person ("Ashish Vaswani").
    for line in head:
        low = line.lower()
        if low and low in title_key:
            continue
        for span in _affiliation_spans(line, people=authors):
            if span and span not in affiliations:
                affiliations.append(span)
    return {
        "title": title,
        "affiliation_list": affiliations[:12],
        "authors_text": " ".join(authors)[:600],
        "authors": authors[:20],
        "affiliations_text": " ".join(affiliations)[:600],
        # Only the part of the text before the bibliography can carry the
        # paper's own DOI. Searching the whole text reported a cited paper's
        # DOI, which is a false metadata claim rather than a missed one.
        "doi": _own_doi(text),
        "arxiv_id": (ARXIV_RE.search(text or "").group(1)
                     if ARXIV_RE.search(text or "") else None),
    }


ABS_RE = re.compile(r"(?im)^[ \t]*abstract[ \t]*[.:\u2014-]*[ \t]*")


def abstract(text):
    """Abstract body, bounded by the next heading."""
    empty = {"text": "", "found": False, "chars": 0}
    if not text:
        return empty
    match = ABS_RE.search(text)
    if not match:
        return empty
    start = match.end()
    tail = text[start:start + 8000]
    tail = re.sub(r"(?i)^\s*arXiv:[^\n]*", "", tail)
    stop = re.search(r"(?im)^\s*(?:1\.?\s+)?(?:introduction|keywords|"
                     r"ccs concepts|categories and subject)", tail)
    body = tail[:stop.start()] if stop else tail[:2500]
    body = re.sub(r"\s+", " ", body).strip()
    return {"text": body, "found": bool(body), "chars": len(body)}


_BACK_MATTER = re.compile(
    r"(?i)^(?:references|bibliography|works cited|literature cited|"
    r"acknowledg(?:e)?ments?|appendix|appendices)\b")


def _heading_strength(title):
    """How much a line looks like a section title rather than a table cell."""
    words = title.split()
    score = 0
    if title.isupper():
        score += 2
    if words and all(w[:1].isupper() for w in words):
        score += 1
    if re.search(r"\d", title):
        # "RNNenc-50", "Warmup Steps 10" — cells, not outline entries.
        score -= 3
    if len(title) > 60:
        score -= 2
    return score


def _monotonic(secs):
    """Keep only headings whose numbering advances like a real document outline.

    Table rows and stray digits also match SECTION_RE, so a bare increasing-number
    test is not enough: a data row numbered "2" inside section 4 looks legal. A
    real outline is a state machine that only moves forward one step at a time,
    so track the current top-level number and accept only its continuation,
    its successor, or the first heading seen.
    """
    out = []
    current_top = None
    accepted_tops = set()
    last_title = None
    in_back_matter = False
    for item in secs:
        num = item["num"]
        if not num:
            if _BACK_MATTER.match(item["title"].strip()):
                in_back_matter = True
            out.append(item)
            continue
        if in_back_matter:
            # The outline ends at the reference list; a numbered line after it
            # is table content from an appendix.
            continue
        if "." not in num:
            value = int(num)
            if current_top is None:
                if value > 3:
                    continue
            elif value == current_top:
                # Only a page-break repeat if the title repeats as well.
                # "5 Warmup Steps" is a table row that happens to sit under
                # section 5; keeping it invents a heading with a duplicate
                # number, which breaks anything keyed by section number.
                if last_title is None or item["title"].strip().lower() != last_title:
                    # Same number, different title: one of them is a table
                    # cell. Keep whichever reads more like a heading, so a
                    # cell that landed first does not shadow the real one.
                    if (out and _heading_strength(item["title"])
                            > _heading_strength(out[-1]["title"])):
                        out.pop()
                        accepted_tops.discard(value)
                    else:
                        continue
            elif value == current_top + 1:
                pass
            elif current_top < value <= current_top + 3:
                # A forward gap means a heading was not detected (a number
                # stranded at a page foot is the usual cause), not that this
                # line is a table row: table rows number backwards or repeat.
                item["skipped_before"] = list(
                    range(current_top + 1, value))
            else:
                continue
            current_top = value
            accepted_tops.add(value)
            last_title = item["title"].strip().lower()
            out.append(item)
            continue
        head = int(num.split(".")[0])
        if current_top is None or head != current_top or head not in accepted_tops:
            continue
        out.append(item)
    return out or secs


def sections(text):
    """Ordered section records with level inferred from numbering depth."""
    if not text:
        return []
    found = []
    for match in SECTION_RE.finditer(text):
        num = match.group("num")
        title = match.group("title").strip()
        if not _plausible_heading(num, title):
            continue
        found.append({"num": num, "title": title,
                      "level": num.count(".") + 1,
                      "offset": match.start()})
    for match in BARE_SECTION_RE.finditer(text):
        title = match.group("title").strip()
        if any(abs(match.start() - f["offset"]) < 12 for f in found):
            continue
        if not _plausible_bare_heading(title):
            continue
        found.append({"num": "", "title": title, "level": 1,
                      "offset": match.start()})
    for match in SPLIT_HEADING_RE.finditer(text):
        num = match.group("num")
        title = match.group("title").strip()
        if not _plausible_heading(num, title):
            continue
        if any(abs(match.start("title") - f["offset"]) < 12 for f in found):
            continue
        found.append({"num": num, "title": title,
                      "level": num.count(".") + 1,
                      "offset": match.start()})
    found.sort(key=lambda f: f["offset"])
    seen = set()
    bare_seen = {}
    ordered = []
    for item in found:
        key = (item["title"].lower(), item["offset"] // 40)
        if key in seen:
            continue
        seen.add(key)
        if not item["num"]:
            count = bare_seen.get(item["title"].lower(), 0) + 1
            bare_seen[item["title"].lower()] = count
            if count > 1:
                # Table column labels repeat down a page; a section does not.
                continue
        ordered.append(item)
    return _monotonic(ordered)


def section_bodies(text, secs=None):
    """Attach each section's body text, up to the next heading."""
    secs = secs if secs is not None else sections(text)
    out = []
    for idx, item in enumerate(secs):
        start = item["offset"]
        line_end = text.find("\n", start)
        start = line_end + 1 if line_end >= 0 else start
        end = secs[idx + 1]["offset"] if idx + 1 < len(secs) else len(text)
        body = text[start:end].strip()
        row = dict(item)
        row["body"] = body
        row["chars"] = len(body)
        row["words"] = len(body.split())
        out.append(row)
    return out


def figures(text, limit=60):
    rows = []
    for match in FIG_RE.finditer(text or ""):
        caption = re.sub(r"\s+", " ", match.group(2) or "").strip()
        if len(caption) < 8:
            continue
        rows.append({"label": "Figure " + match.group(1),
                     "caption": caption[:400], "offset": match.start()})
        if len(rows) >= limit:
            break
    return rows


def tables(text, limit=60):
    rows = []
    for match in TAB_RE.finditer(text or ""):
        caption = re.sub(r"\s+", " ", match.group(2) or "").strip()
        if len(caption) < 5:
            continue
        rows.append({"label": "Table " + match.group(1),
                     "caption": caption[:400], "offset": match.start()})
        if len(rows) >= limit:
            break
    return rows


def equations(text, limit=80):
    """Numbered display equations.

    The equation number often trails the formula on the same extracted line,
    but pdftotext also breaks the formula across lines and leaves "(1)" alone.
    So a line that is nothing but a number is joined to the line before it
    before the math test runs; otherwise every split formula is lost.
    """
    rows = []
    lines = _lines(text)
    pending = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Blank lines do not clear the pending formula: pdftotext puts one
            # between "y = F (x, {Wi}) + x." and the following "(1)", and
            # clearing here lost every split equation in the paper.
            continue
        if len(stripped) > 220:
            pending = None
            continue
        bare = re.fullmatch(r"\((\d+[a-z]?)\)", stripped)
        if bare:
            body = pending or ""
            pending = None
            has_math = bool(EQ_LINE_RE.search(body)) or any(
                ch in MATH_TOKENS for ch in body)
            if body and has_math:
                rows.append({"label": "(" + bare.group(1) + ")",
                             "latexish": body[:300]})
                if len(rows) >= limit:
                    break
            continue
        num = EQ_RE.search(stripped)
        if not num:
            pending = stripped
            continue
        body = stripped[:num.start()].strip()
        if not body:
            continue
        has_math = bool(EQ_LINE_RE.search(body)) or any(
            ch in MATH_TOKENS for ch in body)
        if not has_math:
            continue
        rows.append({"label": "(" + num.group(1) + ")", "latexish": body[:300]})
        if len(rows) >= limit:
            break
    return rows


def footnotes(text, limit=40):
    rows = []
    for line in _lines(text):
        stripped = line.strip()
        if re.match(r"^[\u2020\u2021*]\s*\S", stripped) or re.match(
                r"^\d{1,2}\s+(?:Equal|Corresponding|Work done|Now at|Project lead)",
                stripped, re.I):
            rows.append({"text": stripped[:300]})
        if len(rows) >= limit:
            break
    return rows


def keywords(text):
    match = re.search(r"(?im)^\s*(?:keywords?|index terms)\b[\s:\u2014-]*(.{0,400})",
                      text or "")
    if not match:
        return []
    raw = match.group(1).split("\n")[0]
    parts = re.split(r"[;,]\s*", raw)
    return [p.strip() for p in parts if 2 < len(p.strip()) < 60][:20]


REF_MARK = re.compile(r"^\s*\[(\d{1,3})\]\s+", re.M)
REF_ANY = re.compile(r"\[(\d{1,3})\]")


def references(text, secs=None, limit=200):
    """Numbered bibliography entries, cut on the bracket markers.

    Multi-column PDFs put several entries on one text line, so a marker is not
    reliably at the start of a line. The reliable signal is the numbering: a
    bibliography counts up by one, while in-text citations point backwards. So
    the entries are the ascending run, and everything else in the block is
    treated as body text of the entry before it.
    """
    secs = secs if secs is not None else sections(text)
    start = None
    for item in secs:
        if re.match(r"(?i)^references$|^bibliography$|^literature cited$",
                    item["title"].strip()):
            start = item["offset"]
            break
    if start is None:
        match = re.search(r"(?im)^\s*(?:references|bibliography)\s*$", text or "")
        if not match:
            return []
        start = match.start()
    block = text[start:]

    picked = []
    expected = None
    for match in REF_ANY.finditer(block):
        number = int(match.group(1))
        if expected is None or number == expected:
            picked.append((match, number))
            expected = number + 1

    if not picked:
        return _unnumbered_references(block, limit)

    rows = []
    for pos, (match, number) in enumerate(picked[:limit]):
        end = picked[pos + 1][0].start() if pos + 1 < len(picked) else len(block)
        body = " ".join(block[match.end():end].split())
        if pos + 1 == len(picked):
            # No following marker bounds the last entry, so every trailing
            # appendix paragraph lands inside it. A bibliography entry is one
            # sentence chain; running prose after it announces itself.
            body = _trim_trailing_body(body)
        if body:
            rows.append({"index": number, "text": body[:600], "chars": len(body)})
    return rows


# An appendix heading, or the prose opener that follows one.
_TAIL_BREAK = re.compile(
    r"(?:\s[A-Z]\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,5}\s)"
    r"|(?:\s(?:In this (?:section|paper|appendix)|We (?:introduce|present|describe|"
    r"use|adopt|follow|report))\s)")
_PROSE_WORDS = frozenset("""
the of and to in that is are was were for with this these we our it its on by as
from be been which such than then when where while can may not also both all any
""".split())


def _trim_trailing_body(body):
    """Cut appendix prose that got appended to the final bibliography entry."""
    # "M. D. Zeiler" matches the initials pattern too, so the first hit is
    # almost always inside the author list. Scan forward for a candidate that
    # both sits past the entry head and reads as prose.
    for match in _TAIL_BREAK.finditer(body):
        if match.start() <= 40:
            continue
        rest = body[match.start():]
        words = rest.lower().split()
        if len(words) < 8 or sum(1 for w in words if w.strip(".,;:") in _PROSE_WORDS) < 3:
            continue
        return body[:match.start()].strip()
    return body


def _unnumbered_references(block, limit):
    """Author-year bibliographies carry no [n] marker at all.

    Rather than report "no references found" for a whole family of styles, cut
    on the shape every entry starts with: a capitalised surname, then a year
    somewhere in the leading 200 characters. Entries run until the next such
    line, which is what makes this work without the numbering.
    """
    lines = block.split("\n")
    cut = len(lines)
    for idx, line in enumerate(lines):
        if _APPENDIX_HEAD.match(line.strip()):
            cut = idx
            break
    lines = lines[:cut]
    starts = []
    for idx, line in enumerate(lines):
        head = line.strip()
        if not head or len(head) < 12:
            continue
        if not _ENTRY_START.match(head):
            continue
        # The year marks the entry, but it does not always arrive early: an
        # entry whose title and venue run long reaches it past character 200
        # ("... New York, NY, USA, July 2008."). At 200 those entries were not
        # recognised as starts and were appended to the entry above, so both
        # looked uncited afterwards.
        window = " ".join(lines[idx:idx + 6])[:400]
        if not re.search(r"\b(?:19|20)\d{2}[a-z]?\b", window):
            continue
        starts.append(idx)
    rows = []
    for pos, idx in enumerate(starts[:limit]):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(lines)
        body = " ".join(" ".join(lines[idx:end]).split())
        if body:
            rows.append({"index": pos + 1, "text": body[:600], "chars": len(body)})
    return rows


# A bibliography entry opens with a surname or initials, never with a numeral
# and never with a lowercase word.
_ENTRY_START = re.compile(r"^[A-Z\u00c0-\u024f][\w\u00c0-\u024f'\-]*(?:,|\.|\s+[A-Z])")

# Appendices follow the bibliography in most CS papers; without this cut the
# last entry swallows the whole appendix.
_APPENDIX_HEAD = re.compile(
    r"(?i)^(?:appendix\b|appendices\b|supplementary\b|"
    r"appendix for\b|[A-Z]\.?\d*\s+[A-Z][a-z]+\b.*(?:details|illustration|procedure)\b"
    # "A.1.1 RECURRENT NEURAL NETWORK": a numbered all-caps appendix heading.
    # Without this the appendix paragraphs after the bibliography are reported
    # as entries, and every one of them has no author to show.
    r"|[A-Z](?:\.\d+)*\s+[A-Z][A-Z\s\-]{3,}$)")


def recover(text, pages_split=None):
    """One pass producing the whole skeleton for downstream Skills."""
    pages_split = pages_split if pages_split is not None else (text or "").split("\f")
    body, removed = strip_running_heads(text, pages_split=pages_split)
    secs = section_bodies(body)
    head = title_and_authors(body, pages_split)
    return {
        "meta": head,
        "abstract": abstract(body),
        "keywords": keywords(body),
        "sections": secs,
        "figures": figures(body),
        "tables": tables(body),
        "equations": equations(body),
        "footnotes": footnotes(body),
        "references": references(body, secs),
        "removed_running_lines": removed[:20],
        "stats": {
            "chars": len(body),
            "words": len(body.split()),
            "pages": len(pages_split),
            "sections": len(secs),
        },
    }


def outline_text(structure, max_body=0):
    """Render the skeleton as indented text for an agent prompt or a report."""
    lines = []
    meta = structure.get("meta") or {}
    if meta.get("title"):
        lines.append("TITLE: " + meta["title"])
    if meta.get("authors_text"):
        lines.append("AUTHORS: " + meta["authors_text"][:200])
    if meta.get("doi"):
        lines.append("DOI: " + meta["doi"])
    abstract_block = structure.get("abstract") or {}
    if abstract_block.get("text"):
        lines.append("ABSTRACT: " + abstract_block["text"][:400])
    lines.append("")
    for sec in structure.get("sections") or []:
        pad = "  " * max(0, sec.get("level", 1) - 1)
        label = (sec.get("num") + " " + sec.get("title", "")).strip()
        lines.append(pad + "- " + label + "  [%dw]" % sec.get("words", 0))
        if max_body and sec.get("body"):
            lines.append(pad + "    " + sec["body"][:max_body].replace("\n", " "))
    if structure.get("figures"):
        lines.append("")
        for fig in structure["figures"][:20]:
            lines.append("FIG " + fig["label"] + ": " + fig["caption"][:120])
    if structure.get("tables"):
        lines.append("")
        for tab in structure["tables"][:20]:
            lines.append("TAB " + tab["label"] + ": " + tab["caption"][:120])
    return "\n".join(lines)
