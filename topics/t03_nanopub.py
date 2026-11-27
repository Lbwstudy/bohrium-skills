"""Topic 03 — nanopublications.

A nanopublication is a claim small enough to be checked on its own, tied to the
evidence that supports it and to where that evidence came from. The rubric
grades exactly that: is the claim atomic, does the evidence match, can a reader
trace it back, and is it readable without the paper in hand.

The hard part is not the format, it is refusing to split a compound sentence
into two claims that each lose the qualifier that made them true. So the split
keeps the qualifier attached to the claim it qualifies, and any claim whose
subject cannot be resolved stays marked unresolved instead of being given an
invented subject.
"""

import re

from . import base

# A running head such as "6 Results 6.1 Machine Translation" is glued to the
# sentence before it because the splitter only looked for a capital letter; the
# section number starts with a digit, so the boundary was missed and one claim
# absorbed an entire section opening.
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=(?:[A-Z\u4e00-\u9fff]|"
                        r"\d+(?:\.\d+)*\s+[A-Z]))"
                        r"|(?<=[.!?])\s+(?=\d+\)\s)")

# Claim-bearing predicates. A sentence without one is background, not a claim.
CLAIM_CUES = [
    r"\b(?:achiev|outperform|improv|reduc|surpass|exceed|yield)\w*\b",
    r"\b(?:we|this paper|this work) (?:propose|present|introduce|show|find|demonstrate)\b",
    r"\b(?:is|are) (?:more|less|better|worse|equivalent|comparable|consistent)\b",
    r"\b(?:indicates?|suggests?|implies?|confirms?|reveals?)\b",
    r"\b(?:because|due to|as a result|therefore|thus)\b",
]
CLAIM_RE = [re.compile(p, re.I) for p in CLAIM_CUES]

# A number plus the thing it measures is the strongest evidence a claim has.
MEASURE = re.compile(r"(\d+(?:\.\d+)?)\s?(%|percent|seconds|hours|days|"
                     r"points|GB|MB|M|K|B)?", re.I)

# Relations a claim asserts between entities, in the order that matters when a
# sentence contains more than one.
RELATIONS = [
    # Stems are written without the trailing "e" so that inflections which drop
    # it ("propos-ing", "improv-ing") still match; the earlier full-word forms
    # silently missed those and left ordinary claims unlabelled.
    ("achieves", r"\b(?:achiev|obtain|reach|yield|attain)\w*\b"),
    ("proposes", r"\b(?:propos|propose|present|introduc|develop|design|construct)\w*\b"),
    ("shows", r"\b(?:show|demonstrat|find|report|observ|reveal|indicat|suggest|"
                r"hypothes|assum|argu|claim|contend|establish|verif)\w*\b"),
    ("outperforms", r"\b(?:outperform|surpass|exceed|better than|improve over|"
                   r"superior to|beats?)\w*\b"),
    ("reduces", r"\b(?:reduc|lower|decreas|cut|drop|fall)\w*\b"),
    ("increases", r"\b(?:increas|rais|boost|gain|improv)\w*\b"),
    ("causes", r"\b(?:because|due to|leads? to|results? in|causes?|attributable|"
                r"generat|produc|introduc)\w*\b"),
    ("uses", r"\b(?:(?:based|rely\w*) on|us(?:e|es|ed|ing)|employ|adopt|leverage|"
             r"finetun|fine-tun|perform|conduct|carr(?:y|ies|ied) out|"
             r"appl(?:y|ies|ied))\w*\b"),
    # Choosing or treating something a particular way is a claim about the
    # method even when it states no result, and leaving it unlabelled drops
    # a triple the paper does assert.
    ("sets", r"\b(?:set|sets|setting|treat|treats|treated|regard|regards|"
             r"consider|considers|view|views|choose|chooses|"
             r"initializ|initialis)\w*\b"),
    ("compares", r"\b(?:compar|versus|vs\.?|against)\w*\b"),
    # Copular predication states an identity or a property. It is the last
    # row on purpose: it matches far too often to outrank a real verb.
    ("is", r"\b(?:is|are|was|were|remains?|becomes?)\b"),
    ("contradicts", r"\b(?:contradict|conflict|inconsistent|contrary)\b"),
    ("supports", r"\b(?:support|confirm|consistent with|corroborat)\w*\b"),
    # A stated size or count is a claim even without a result verb; without a
    # predicate these triples cannot be published at all.
    ("quantifies", r"\b(?:has|have|had|contains?|consists? of|comprises?|"
                   r"uses?|takes?|requires?)\s+(?:a |an |the )?[^.]{0,40}?"
                   r"\d"),
    ("excludes", r"\b(?:exclud|omit|discard|skip|withhold|remov)\w*\b"),
    ("differs", r"\b(?:differ\w*|different from|distinct from|unlike|"
                r"in contrast to)\b"),
    ("limits", r"\b(?:cannot|can not|not all|fail\w*|lack\w*|suffer\w*|"
               r"struggl\w*|limitation\w*|restricted to)\b"),
    ("cites", r"\b(?:described in|introduced (?:in|by)|proposed (?:in|by)|"
              r"reported (?:in|by)|following)\b"),
]

# Qualifiers that must travel with a claim, or it becomes false when isolated.
QUALIFIERS = [
    ("scope", r"\b(on|in|for|across|within|under)\s+([A-Z][\w-]*(?:\s+[\w-]+){0,3})"),
    ("condition", r"\b(?:when|if|unless|provided that|assuming)\b[^,.;]{0,60}"),
    ("dataset", r"\b(?:ImageNet|CIFAR-\d+|COCO|PASCAL|WMT|SQuAD|GLUE|MNIST|"
                r"PTB|WikiText)\b"),
    ("metric", r"\b(?:error rate|accuracy|BLEU|F1|top-1|top-5|perplexity|"
              r"mAP|IoU|RMSprop|SGD)\b"),
    ("hedge", r"\b(?:may|might|could|suggest|appears?|likely|potentially|"
             r"in some cases)\b"),
]


def run(case, task, bundle, records, doc):
    if doc is None:
        base.refuse_empty(bundle, "document", records,
                         "输入目录中没有可读的文档")
        return
    base.degraded(bundle, doc)

    candidates = _candidates(doc)
    assertions = _assertions(doc, candidates)
    bundle.put("assertion_count", len(assertions))
    bundle.put("assertions", assertions)
    bundle.put("nanopub_format", _format_doc())
    bundle.put("provenance", _provenance(doc))
    bundle.put("quality", _quality(assertions))
    bundle.put("sample_20", _sample(assertions))
    bundle.put("triples", _triples(assertions))
    bundle.put("markdown", _markdown(doc, assertions))

    _honest_gaps(bundle, doc, assertions)


_TITLE_HEADS = set()


# The reference list often starts mid-page: skipping whole pages that begin
# with the heading misses it entirely, and entry titles then read as claims
# about the paper ("Acute-eval: Improved dialogue evaluation ..."). The
# heading is a line of its own, which survives collapsing to spaces only as
# a position, so cut the raw page text and collapse the prefix.
_REF_HEADING = re.compile(
    r"(?im)^[ \t\f]*(?:\d+\.?[ \t]*)?(?:references|bibliography|"
    r"works cited|literature cited)[ \t]*\r?$")


def _body_before_references(page):
    """Body text up to a reference heading, and whether one was found.

    The flag is separate from the text because the heading usually sits
    mid-page: body before it is still body, but every later page is a
    list entry and must not be read as prose.
    """
    marker = _REF_HEADING.search(page)
    if marker is None:
        return " ".join(page.split()), False
    return " ".join(page[:marker.start()].split()), True


def _candidates(doc):
    """Sentences that assert something checkable, with their located context."""
    global _TITLE_HEADS
    title = ((doc.get("meta") or {}).get("title") or "").lower()
    _TITLE_HEADS = set()
    words = title.split()
    for i in range(1, min(7, len(words) + 1)):
        _TITLE_HEADS.add(" ".join(words[:i]))
    rows = []
    cursor = 0
    in_references = False
    for page_no, page in enumerate(doc.get("pages") or [], 1):
        if in_references:
            cursor += len(page) + 1
            continue
        body, heading = _body_before_references(page)
        if heading:
            # The heading is on this page; everything after it is a list
            # entry, including on the pages that follow.
            in_references = True
            cursor += len(page) + 1
            continue
        if not body:
            cursor += len(page) + 1
            continue
        local = 0
        for sentence in SENT_SPLIT.split(body):
            sentence = sentence.strip()
            if not sentence:
                continue
            found = body.find(sentence[:60], local)
            start = found if found >= 0 else local
            local = start + 1
            sentence = _HEADING.sub("", sentence).strip()
            if not (40 <= len(sentence) <= 500):
                continue
            if not any(p.search(sentence) for p in CLAIM_RE):
                continue
            if _noise(sentence):
                continue
            rows.append({"sentence": sentence, "page": page_no,
                         "offset": cursor + start})
        cursor += len(page) + 1
    return rows


# A numbered section label that the extractor glued to the sentence it runs
# into. Number and capitalised run of words, then the sentence proper.
_HEADING = re.compile(r"^(?:\d+(?:\.\d+)*\s+[A-Z][\w:-]*"
                      r"(?:\s+[A-Z][\w:-]*){0,5}\s+){1,3}(?=[A-Z][a-z])")

NOISE_RE = re.compile(r"(?:arxiv:\s*\d|doi:\s*10\.|©|copyright|"
                      r"preprint|under review|all rights reserved|"
                      r"^\W*(?:figure|table|fig\.|tab\.)\s*\d)", re.I)


def _noise(sentence):
    """Bibliographic lines and captions are not claims about the work."""
    if NOISE_RE.search(sentence):
        return True
    if len(sentence.split()) < 8:
        return True
    if " ".join(sentence.split()[:6]).lower() in _TITLE_HEADS:
        return True
    return False


def _section_at(doc, offset):
    best = None
    for item in doc.get("sections") or []:
        if item.get("offset", 0) <= offset:
            best = item
        else:
            break
    return ((best.get("num", "") + " " + best["title"]).strip() if best else None)


def _assertions(doc, candidates):
    """Split compound sentences into atomic assertions without losing qualifiers."""
    meta = doc.get("meta") or {}
    paper = meta.get("title")
    rows = []
    previous = None
    for cand in candidates:
        for piece in _atomize(cand["sentence"]):
            rows.append(_assertion(doc, cand, piece, paper, len(rows) + 1,
                                   previous))
            if len(rows) >= 200:
                return rows
        previous = cand["sentence"]
    return rows


# A citation group can carry a semicolon of its own: "(Houlsby et al.,
# 2019; Rebuffi et al., 2017)". Splitting there cuts the group in half and
# the right half begins inside the citation, where no subject rule applies.
_ATOM_SPLIT = re.compile(r";\s+|,\s+(?=(?:and|but|while|whereas|although)\b)")


def _split_outside_parens(sentence):
    """Split on coordination cues that sit outside any parenthetical."""
    parts = []
    depth = 0
    last = 0
    index = 0
    while index < len(sentence):
        char = sentence[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            match = _ATOM_SPLIT.match(sentence, index)
            if match:
                parts.append(sentence[last:index])
                last = match.end()
                index = match.end()
                continue
        index += 1
    parts.append(sentence[last:])
    return parts



def _atomize(sentence):
    """Break on coordination only when both halves keep their own verb.

    A comma-joined clause that merely continues the verb phrase is not a
    separate assertion, and splitting it produces two claims that are each
    incomplete. Requiring a verb in both halves is what keeps that from
    happening.
    """
    parts = _split_outside_parens(sentence)
    parts = [p.strip() for p in parts if p and len(p.strip()) >= 30]
    if len(parts) <= 1:
        return [sentence]
    kept = []
    for part in parts:
        if re.search(r"\b(?:is|are|was|were|has|have|had|achiev|show|use|"
                     r"propose|improve|reduce|increase|outperform)\w*\b", part, re.I):
            kept.append(part if part.endswith((".", "!", "?")) else part + ".")
    return kept or [sentence]


def _assertion(doc, cand, piece, paper, index, previous=None):
    """One assertion with its qualifiers, evidence and provenance.

    ``previous`` is the sentence immediately before this one in the body, so a
    fragment that opens with a conjunction can fall back to the subject of the
    clause it continues rather than being withheld.
    """
    qualifiers = {}
    for name, pattern in QUALIFIERS:
        match = re.search(pattern, piece, re.I)
        if match:
            qualifiers[name] = match.group(0).strip()[:120]
    subject = _subject(piece)
    if not subject and _SHARED_SUBJECT.match(piece.strip()):
        # The atomizer cut a compound predicate off its head clause; the two
        # halves share one subject, which is still present in the source.
        subject = _subject(cand["sentence"])
        if not subject and previous:
            subject = _subject(previous)
    relation = _relation(piece)
    obj = _object(piece, relation)
    measures = [{"value": m.group(1), "unit": (m.group(2) or "").strip() or None}
                for m in MEASURE.finditer(piece)][:6]
    qualifiers["measures"] = measures
    gaps = []
    if not subject:
        gaps.append("未能从该句确定主语，需人工补充后再作为独立断言发布")
    if not relation:
        gaps.append("句中未出现明确关系动词，关系字段留空而非推断")
    if not measures and re.search(r"\b(?:more|less|better|faster|higher|lower)\b",
                                  piece, re.I):
        gaps.append("仅给出相对比较而无绝对数值，读者无法据此复核幅度")
    return {
        "assertion_id": "A%03d" % index,
        "text": piece,
        "subject": subject,
        "relation": relation,
        "object": obj,
        "qualifiers": qualifiers,
        "evidence": {"quote": piece, "page": cand["page"],
                     "section": _section_at(doc, cand["offset"])},
        "provenance": {"paper": paper, "doi": (doc.get("meta") or {}).get("doi"),
                       "arxiv_id": (doc.get("meta") or {}).get("arxiv_id"),
                       "source_file": doc.get("path")},
        "atomicity": _atomicity(piece, qualifiers),
        "needs_review": gaps,
    }


# Only a genuinely subordinate opener is trimmed. Treating every first
# comma as a clause boundary cut the main clause off sentences like
# "The deeper network has higher training error, and thus test error."
# and left them without a subject.
LEAD_CLAUSE = re.compile(
    r"^(?:although|though|while|whereas|because|since|if|when|whenever|"
    r"as|despite|in order to|to this end|for this purpose|by contrast|"
    r"in contrast|on the contrary|in particular|in fact|in practice|"
    r"specifically|similarly|additionally|consequently|accordingly|"
    r"at least partly|compared (?:to|with)|first|second|third|finally|"
    r"as a result|as a side benefit|as side benefit|in terms of|"
    r"according to|while for|for (?:the |small |large |all )?[a-z0-9-]+|"
    r"to (?:improve|reduce|avoid|address|evaluate|measure|compare|enable|"
    r"achieve|test|verify|study|investigate|assess|mitigate|support)|"
    r"question|answer|however|moreover|furthermore|therefore|thus|hence)"
    r"\b[^,;]{0,200},\s+"
    r"(?=[A-Za-z])", re.I)

_SUBJECT_VERBS = (
    r"is|are|was|were|has|have|had|can|could|may|might|must|should|will|would"
    r"|does|do|did|remains|remain|becomes|become|became"
    r"|achiev\w*|improv\w*|reduc\w*|increas\w*|outperform\w*"
    r"|surpass\w*|exceed\w*|show\w*|demonstrat\w*|reveal\w*"
    r"|indicat\w*|suggest\w*|find\w*|found|report\w*|observ\w*"
    r"|propos\w*|present\w*|introduc\w*|develop\w*|design\w*"
    r"|construct\w*|us(?:e|es|ed|ing)|appl(?:y|ies|ied)|allow\w*"
    r"|enabl\w*|requir\w*|yield\w*|obtain\w*|reach\w*|attain\w*"
    r"|provid\w*|giv(?:e|es|en|ing)|exhibit\w*|perform\w*|offer\w*"
    r"|consist\w*|compris\w*|contain\w*|includ\w*|leads?|led"
    r"|tend\w*|adopt\w*|follow\w*|differ\w*|outweigh\w*|matter\w*"
    r"|help\w*|achieves?|gains?|drops?|falls?|rises?|scales?"
    r"|generat\w*|bring\w*|won|win\w*|make\w*"
    r"|represent\w*|begin\w*|show(?:s|ed|n)?|gain\w*"
    r"|occur\w*|seem\w*|harm\w*|affect\w*|impact\w*|dominat\w*"
    r"|contribut\w*|account\w*"
)
COMPARATIVE = re.compile(r"\b(?:higher|lower|more|less|better|worse|"
                         r"greater|larger|smaller|faster|slower)\b", re.I)


def _subject(sentence, mid=False):
    """The noun phrase the sentence makes a claim about.

    Cross-sentence fragments that start with a coordinating conjunction ("but
    the counterpart nets exhibit ...", "and multi-scale testing are also
    adopted") are re-joined to their head clause first: the conjunction is a
    seam artefact of sentence splitting, not part of the claim. Anything still
    without a recoverable subject returns ``None``, because an assertion whose
    subject cannot be determined has to be withheld rather than attributed to
    whichever noun happened to come first.
    """
    trimmed = sentence.strip()
    stripped = False
    for _ in range(3):
        seam = _SEAM.match(trimmed)
        if not seam:
            break
        trimmed = trimmed[seam.end():].strip()
        stripped = True
    for _ in range(2):
        hit = LEAD_CLAUSE.match(trimmed)
        if not hit:
            break
        trimmed = trimmed[hit.end():].strip()
        stripped = True

    # A short appositive ("MNLI, BERT obtains ..."), a Q/A label, an
    # enumeration and a "Note that" opener are all left over from the running
    # text, not part of the claim subject.
    for pattern in (_ENUM, _THAT_OPENER, _APPOSITIVE, _QA_LABEL):
        hit = pattern.match(trimmed)
        if hit:
            trimmed = trimmed[hit.end():].strip()
            stripped = True

    verbs = _SUBJECT_VERBS
    # A citation marker often sits between the noun phrase and its verb
    # ("Recent evidence [41, 44] reveals ..."); without allowing it the verb
    # stays hidden and an otherwise clean subject is lost.
    gap = (r"(?:\s*[\[\d,\s\u2013-]+\])?"
           r"(?:\s*\((?:[^()]{0,50})\))?"
           r"(?:\s+\w+ly)?")

    match = re.match(r"^((?:The|A|An|This|These|Those|Our|We|It|Its|They)\b"
                     r"[^,;:]{0,90}?)%s\s+(?:%s)\b" % (gap, verbs),
                     trimmed, re.I)
    if match:
        return _trim_adverb(match.group(1))
    # The predicate has to be there: without one this is a fragment, and a
    # fragment's leading noun is not yet a claim subject.
    if re.match(r"^[^,;:]{1,120}?\s+(?:%s)\b" % verbs,
                _strip_brackets(trimmed), re.I):
        candidate = _trim_adverb(
            _noun_phrase(trimmed, allow_lower=stripped or mid) or "")
        if candidate and candidate.lower() not in _SUBJECT_STOP:
            return candidate
    aux = re.match(r"^(?:Do|Does|Did|Is|Are|Was|Were|Can|Could|Will|Would|"
                   r"Should|May|Might|Has|Have|Had)\s+"
                   r"((?:[A-Z][\w.\-]*|[A-Z]{2,})"
                   r"(?:\s+[\w.\-]+){0,5})\s+(?:[a-z]+\w*)\b", trimmed)
    if aux:
        candidate = aux.group(1).strip()
        if candidate.lower() not in _SUBJECT_STOP:
            return candidate
    gerund = re.match(r"^([a-z]+ing\b[^,;:]{0,60}?)\s+(?:%s|results?|leads?|"
                      r"yields?|allows?|enables?)\b" % verbs, trimmed, re.I)
    if gerund:
        phrase = re.split(r"\s+(?:in|on|at|for|with|to|from|by|of|into|over|"
                          r"under|across|within|without)\s", gerund.group(1))[0]
        return phrase.strip()
    fronted = _FRONTED.match(trimmed)
    if fronted:
        rest = trimmed[fronted.end():].strip()
        inner = _subject(rest, mid=True) if rest and rest != trimmed else None
        if inner:
            return inner
    pronoun = re.search(r"\b(we|our [a-z]+(?: [a-z]+)?)\b", trimmed, re.I)
    if pronoun:
        return pronoun.group(1)
    return None


# A fronted adverbial phrase pushes the subject past the comma.
_FRONTED = re.compile(r"^(?:On|In|For|From|With|Under|Across|At|"
                      r"During|Among|Within|After|Before|Unlike|Given|As|"
                      r"Since|Because|While|When|If|Although|Though)"
                      r"\s[^,]{2,90},\s+", re.I)


# A coordinating conjunction at the start of a fragment means the splitter cut
# a compound sentence in two; the fragment has no subject of its own until the
# conjunction is removed.
_SEAM = re.compile(r"^(?:but|and|so|yet|or|nor|plus)\s+", re.I)



# A numbered clause and a "Note that" opener are formatting, not content.
_ENUM = re.compile(r"^(?:\d+\)|\(\d+\)|\([a-z]\)|[a-z]\))\s+")
_THAT_OPENER = re.compile(r"^(?:Note|Notice|Recall|Observe|Assume|Suppose|"
                          r"Consider|Importantly)\s+that\s+", re.I)


# A short leading appositive sits between the opener and the real subject.
_APPOSITIVE = re.compile(r"^[A-Z][^,;:]{1,24},\s+(?=[A-Za-z])")
# "Question: ..." / "Answer: ..." labels come from the running text.
_QA_LABEL = re.compile(r"^(?:Question|Answer|Q|A)\s*:\s*", re.I)

# A determiner-led noun phrase that is one of these is a discourse pointer or a
# structural reference, not a claim subject.
_SUBJECT_STOP = frozenset("""
there here this that these those it they them their its
however moreover furthermore therefore thus hence similarly
first second third finally next then also still yet
when where while because since although though if
table figure section appendix algorithm equation
""".split())


_TRAILING_ADVERB = re.compile(r"\s+\w+ly$")

# Tokens that end a claim subject: a predicate, a complementizer, or the
# preposition that starts the complement. The phrase walker below stops there.
_SUBJECT_BREAK = re.compile(
    r"^(?:(?:%s)|that|which|who|whom|whose|where|when|while|because|since|if|"
    r"and|but|or|than|as|in|of|for|on|with|from|by|to|at|into|over|under|"
    r"across|within|without|between|among|via|per|"
    r"later|earlier|also|further|furthermore|then|now|first|second|third|"
    r"finally|still|already|only|even|well|often|usually|typically|"
    r"recently|previously|respectively|however|moreover|therefore|thus)$"
    # Only inflected predicates end a phrase: a bare stem collides with nouns
    # ("differ" would stop "Differentiable retrieval").
    # Whole predicates only: an inferred "ends in s/ed" rule also matched
    # "Fedus" and "learned", emptying the phrases it was meant to bound.
    % (r"is|are|was|were|has|have|had|does|do|did|can|could|may|might|must|"
       r"should|will|would|remain|remains|become|becomes|became|"
       r"show|shows|showed|shown|outperform|outperforms|outperformed|"
       r"improve|improves|improved|achiev\w*|obtain\w*|report\w*|"
       r"propose\w*|proposed|present\w*|introduc\w*|find|finds|found|"
       r"demonstrat\w*|reveal\w*|indicat\w*|suggest\w*|use|uses|used|"
       r"requir\w*|yield\w*|perform\w*|contain\w*|includ\w*|leads|led|"
       r"makes|made|allows|allowed|enabl\w*|consists|comprises|provid\w*|"
       r"gives|gave|takes|took"),
    re.I)
_SUBJECT_TOKEN = re.compile(
    r"^(?:[A-Za-z][\w.\-\u2019']*|[\d][\w.\-]*|"
    r"\[[\d,\s\u2013-]+\]|\([^()]{0,50}\)|,)$")


_BRACKETED = re.compile(r"\[[^\]]*\]|\([^)]*\)")


def _strip_brackets(text):
    """Drop bracketed groups so their commas stop imitating clause breaks."""
    return _BRACKETED.sub(" ", text)


def _noun_phrase(trimmed, limit=8, allow_lower=False):
    """Leading noun phrase of a sentence, stopping at the first break token.

    Returns ``None`` unless the phrase begins with a capital, because a
    lowercase opener is a continuation of the previous clause rather than a
    subject of its own.
    """
    tokens = re.findall(r"\[[\d,\s\u2013-]+\]|\([^()]{0,50}\)|\S+", trimmed)
    if not tokens:
        return None
    head = tokens[0].strip(",;:")
    if not head[:1].isupper() and not allow_lower:
        return None
    kept = []
    for token in tokens[:limit]:
        bare = token.strip(",;:")
        if not bare or _SUBJECT_BREAK.match(bare):
            break
        if not _SUBJECT_TOKEN.match(bare):
            break
        kept.append(token)
    phrase = " ".join(kept).strip(" ,;:")
    return phrase or None


def _trim_adverb(candidate):
    """Drop a trailing adverb the verb slot let into the subject.

    "The model significantly outperforms" names the model, not "the model
    significantly"; without this the modifier would be reported as part of the
    claim subject.
    """
    trimmed = _TRAILING_ADVERB.sub("", candidate.strip())
    return trimmed or candidate.strip()


def _relation(sentence):
    """Relation in priority order, with a comparison fallback.

    A bare "higher training error" asserts a difference without asserting a
    cause; naming it differs keeps that weaker claim from being promoted to
    causes.
    """
    for name, pattern in RELATIONS:
        if re.search(pattern, sentence, re.I):
            return name
    if COMPARATIVE.search(sentence):
        return "differs"
    return None


def _object(sentence, relation):
    """The other end of the triple, when the sentence names one.

    A triple whose object is missing is not publishable, so each relation gets
    its own pattern rather than one generic "after the verb" rule: the object of
    "achieves" is a measurement, the object of "outperforms" is a baseline, and
    the object of "uses" is a component. ``None`` is still returned when the
    sentence genuinely does not name one — the caller marks that assertion for
    review instead of inventing a filler.
    """
    text = sentence.strip()

    if relation in ("outperforms", "compares"):
        match = re.search(r"\b(?:than|over|versus|vs\.?|against|superior to|"
                          r"compared (?:to|with))\s+([^,.;]{2,70})", text, re.I)
        if match:
            return _trim_object(match.group(1))
        # "X outperforms Y" / "X surpasses Y" — object follows the verb.
        match = re.search(r"\b(?:outperform|surpass|exceed|beat)\w*\s+"
                          r"([^,.;]{2,70})", text, re.I)
        return _trim_object(match.group(1)) if match else None

    if relation == "uses":
        match = re.search(r"\b(?:based on|using|used|employ\w*|adopt\w*|"
                          r"leverage\w*|finetun\w*|fine-tun\w*|with)\s+"
                          r"([^,.;]{2,70})", text, re.I)
        return _trim_object(match.group(1)) if match else None

    if relation in ("achieves", "reduces", "increases"):
        # The object of a measurement claim is the quantity, not the sentence tail.
        match = re.search(r"\b(?:achiev|obtain|reach|yield|attain|reduc|lower|"
                          r"decreas|cut|drop|increas|rais|boost|gain|improv)\w*"
                          r"\s+(?:a |an |the )?([^,.;]{2,70})", text, re.I)
        return _trim_object(match.group(1)) if match else None

    if relation == "proposes":
        match = re.search(r"\b(?:propos|propose|present|introduc|develop|design|"
                          r"construct)\w*\s+(?:a |an |the )?([^,.;]{2,70})",
                          text, re.I)
        return _trim_object(match.group(1)) if match else None

    if relation == "shows":
        match = re.search(r"\b(?:show|demonstrat|find|report|observ|reveal|"
                          r"indicat|suggest)\w*\s+(?:that\s+)?([^,.;]{4,90})",
                          text, re.I)
        return _trim_object(match.group(1)) if match else None

    if relation == "causes":
        match = re.search(r"\b(?:because|due to|leads? to|results? in|causes?)\w*"
                          r"\s+(?:of |the )?([^,.;]{2,70})", text, re.I)
        return _trim_object(match.group(1)) if match else None

    if relation == "supports":
        match = re.search(r"\b(?:support|confirm|consistent with|corroborat)\w*"
                          r"\s+(?:of |the )?([^,.;]{2,70})", text, re.I)
        return _trim_object(match.group(1)) if match else None

    if relation == "contradicts":
        match = re.search(r"\b(?:contradict|conflict|inconsistent|contrary)\w*"
                          r"\s+(?:with |to |the )?([^,.;]{2,70})", text, re.I)
        return _trim_object(match.group(1)) if match else None

    return None


# A fragment that opens with a coordinating conjunction continues the previous
# predicate; it has no subject of its own but is not subject-less either.
_SHARED_SUBJECT = re.compile(r"^(?:but|and|so|yet|or|nor|plus)\b", re.I)

# A trailing comparison or citation is not part of the object it follows.
_OBJECT_TAIL = re.compile(r"\s+(?:in|on|for|with|when|while|where|which|that|"
                          r"rather|compared|than|over|and|but|as|at)\b.*$", re.I)


def _trim_object(value):
    """Cut a captured object at the first clause boundary it should not cross."""
    value = (value or "").strip(" ,;:.'’”")
    value = _OBJECT_TAIL.sub("", value).strip(" ,;:.'’”")
    value = re.sub(r"^(?:a|an|the)\s+", "", value, flags=re.I)
    return value if len(value) >= 2 else None


def _atomicity(sentence, qualifiers):
    """Whether the claim can stand alone, and what it would lose if cut."""
    issues = []
    if len(sentence.split()) > 60:
        issues.append("句子过长，可能含多个可独立检验的事实")
    if re.search(r"\b(?:and|as well as|along with)\b", sentence, re.I) and \
            len(re.findall(r"\b(?:is|are|achiev|improv|reduc|show)\w*\b",
                           sentence, re.I)) > 2:
        issues.append("含并列谓词，拆分后需补全各自主语")
    if re.search(r"\b(?:this|it|these|they|such)\b", sentence[:40], re.I):
        issues.append("句首使用回指代词，脱离上下文后指代不明")
    return {"standalone": not issues, "issues": issues,
            "qualifier_count": len([k for k, v in qualifiers.items()
                                    if v and k != "measures"])}


def _format_doc():
    """The nanopublication shape, so a consumer knows what each field means."""
    return {
        "nanopub": {
            "assertion": {"subject": "被断言的对象", "relation": "关系类型",
                          "object": "关系另一端或结果"},
            "provenance": {"paper": "来源论文标题", "doi": "DOI",
                           "arxiv_id": "arXiv 编号", "source_file": "输入文件"},
            "publication": {"assertion_id": "稳定标识",
                            "evidence": "逐字引文 + 页码 + 章节"},
        },
        "relations": [name for name, _ in RELATIONS],
        "rule": "qualifiers 必须随 assertion 一起传递；主语缺失的断言不得发布，"
                "标 needs_review 交人工补充。",
    }


def _provenance(doc):
    meta = doc.get("meta") or {}
    return {
        "title": meta.get("title"),
        "authors": meta.get("authors") or [],
        "doi": meta.get("doi"),
        "arxiv_id": meta.get("arxiv_id"),
        "source_file": doc.get("path"),
        "extractor": doc.get("backend"),
        "pages": len(doc.get("pages") or []),
        "note": "每条 assertion 的 evidence.page 指向上表页码；DOI/arXiv 缺失时"
                "该字段为 null，不以推测填充。",
    }


def _quality(assertions):
    """The checks a nanopublication consumer would run, run here instead."""
    total = len(assertions)
    if not total:
        return {"total": 0}
    standalone = [a for a in assertions if a["atomicity"]["standalone"]]
    with_subject = [a for a in assertions if a["subject"]]
    with_relation = [a for a in assertions if a["relation"]]
    with_numbers = [a for a in assertions
                    if a["qualifiers"].get("measures")]
    review = [a["assertion_id"] for a in assertions if a["needs_review"]]
    return {
        "total": total,
        "standalone": len(standalone),
        "standalone_ratio": round(len(standalone) / total, 3),
        "with_subject": len(with_subject),
        "with_relation": len(with_relation),
        "with_numbers": len(with_numbers),
        "needs_review": len(review),
        "review_ids": review[:30],
        "relation_histogram": _histogram(a["relation"] for a in assertions),
    }


def _histogram(values):
    out = {}
    for value in values:
        key = value or "unresolved"
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _sample(assertions):
    """The 20-assertion sample the topic asks for, chosen by spread not by luck.

    Taking the first twenty would sample one section; taking every k-th keeps
    the sample representative of the whole paper.
    """
    total = len(assertions)
    if total <= 20:
        return assertions
    step = total / 20.0
    return [assertions[int(i * step)] for i in range(20)]


def _triples(assertions):
    """The assertion set as subject-relation-object rows for a graph loader."""
    rows = []
    for a in assertions:
        if not (a["subject"] and a["relation"]):
            continue
        rows.append({
            "id": a["assertion_id"],
            "s": a["subject"],
            "p": a["relation"],
            "o": a["object"] or (a["qualifiers"].get("measures") or [{}])[0].get("value"),
            "page": a["evidence"]["page"],
        })
    return rows


def _markdown(doc, assertions):
    meta = doc.get("meta") or {}
    lines = ["# Nanopublications — %s" % (meta.get("title") or "Untitled"), ""]
    lines.append("每条断言均可在原文逐字定位；主语缺失者标 needs_review，不作独立断言发布。")
    lines.append("")
    for a in assertions[:60]:
        lines.append("## %s" % a["assertion_id"])
        lines.append("")
        lines.append("- 断言：%s" % a["text"])
        if a["subject"]:
            lines.append("- 主语：%s" % a["subject"])
        if a["relation"]:
            lines.append("- 关系：%s" % a["relation"])
        q = {k: v for k, v in a["qualifiers"].items() if v}
        if q:
            lines.append("- 限定：%s" % ", ".join("%s=%s" % (k, v)
                                                for k, v in q.items() if k != "measures"))
        lines.append("- 证据：第 %s 页%s" % (a["evidence"]["page"],
                                          "（%s）" % a["evidence"]["section"]
                                          if a["evidence"]["section"] else ""))
        if a["needs_review"]:
            lines.append("- 待确认：%s" % "；".join(a["needs_review"]))
        lines.append("")
    return "\n".join(lines)


def _honest_gaps(bundle, doc, assertions):
    if not assertions:
        bundle.gap(item="断言", reason="未从原文提取到可检验的断言，"
                   "可能是扫描件、非英文或缺少结论性表述",
                   field="assertions", state="not_reported")
        return
    quality = _quality(assertions)
    if quality["with_subject"] < quality["total"]:
        bundle.gap(item="主语缺失",
                   reason="%d/%d 条断言未能确定主语，已标 needs_review，"
                          "未以推测主语发布"
                          % (quality["total"] - quality["with_subject"], quality["total"]),
                   field="assertions", state="partial")
    if quality["with_relation"] < quality["total"]:
        bundle.gap(item="关系类型",
                   reason="%d 条断言未匹配到预设关系动词，relation 留空而非指派"
                          % (quality["total"] - quality["with_relation"]),
                   field="assertions", state="partial")
    if len(assertions) < 20:
        bundle.gap(item="样例数量",
                   reason="题面要求 20 条断言样例，本次仅得 %d 条可定位断言；"
                          "该材料断言密度不足，需换更长的材料或合并相邻材料"
                          % len(assertions),
                   field="sample_20", state="partial")
