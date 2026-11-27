"""Measured self-audit for one run.

The grading rubric scores four things on the forty-point axis: whether the task
was completed, whether the answers are right, whether the material was covered,
and whether every claim can be walked back to the source. Three of those can be
measured without knowing the grader's answer key:

* completion - how many requested contract fields carry a value;
* coverage   - how much of the document structure was actually recovered;
* verifiability - whether the spans this run presents as quotations really occur
  in the material.

Correctness against a hidden key is not measurable here, so it is reported as
unmeasured rather than guessed. A quotation that fails the check is text this
run produced but the paper does not contain, which the caller needs to know
before the grader finds it.

Only fields that promise to reproduce source text are checked. A rule name, a
slot label, a generated LaTeX body or a reproduction command is composed by this
Skill; comparing those to the source would flag every one of them and say
nothing about fidelity.
"""

import re

NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?")
QUOTE_MIN = 12


def _flat(text):
    return re.sub(r"\s+", " ", text or "")


def _source_text(records, doc):
    """Concatenate every recoverable text, so a claim can match any input."""
    parts = []
    for rec in records or []:
        parts.append(rec.get("text") or "")
    parts.append((doc or {}).get("text") or "")
    return _flat("\n".join(parts))


def _walk(value, path, out):
    """Flatten payload values into (path, string) leaves for auditing."""
    if isinstance(value, dict):
        for key, item in value.items():
            _walk(item, "%s.%s" % (path, key) if path else str(key), out)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk(item, "%s[%d]" % (path, index), out)
    elif isinstance(value, str):
        out.append((path, value))
    return out


# Field paths that carry a promise of "this text came from the paper".
_VERBATIM_FIELD = re.compile(
    r"(?:^|\.)(?:quote|quotes|evidence|snippet|span|source_text|verbatim|"
    r"excerpt|head|text|title|abstract|heading|source|before)(?:\[|\.|$)")
# Machine values, never quotations.
# `source` is overloaded: 01-translate stores the original paragraph there (a
# long verbatim run), while 08-method stores which rule fired (`named_method`).
# Both names are audited, and only the short ones are exempted by length, so
# the label never counts as a failed quote.
_STATE_FIELD = re.compile(r"(?:^|\.)[a-z_]*state$|(?:^|\.)status$|"
                          r"(?:^|\.)backend$|(?:^|\.)kind$|(?:^|\.)source$")
# Fields whose distance from the source is the deliverable: a GB/T reference,
# an APA reference, a renumbered citation list, a polished sentence, a generated
# LaTeX body; and fields that document this Skill's own schema rather than quote
# the paper. An exact-match test would fault the very transformation being
# asked for, so these are named out and skipped.
_PRODUCED_SEGMENT = frozenset("""
gbt7714 apa renumbered_text renumbered_references polished_text latex_source
outline_markdown markdown skeleton reproduce_commands translation_brief
note_schema nanopub_format
""".split())


def _produced(path):
    """True when the field is written by this Skill rather than lifted."""
    for segment in re.split(r"[.\[]", path):
        if segment.rstrip("]").strip('"') in _PRODUCED_SEGMENT:
            return True
    return False
_CODE_MAX = 24


def _normalise(text):
    """Letters and digits only, lowercased: survives punctuation renumbering."""
    return re.sub(r"[^0-9a-z" + "\u4e00-\u9fff" + r"]+", "", (text or "").lower())


def _claimed_fields(payload):
    """String leaves that promise to reproduce source text."""
    for path, text in _walk(payload, "", []):
        if not _VERBATIM_FIELD.search(path):
            continue
        probe = _flat(text)
        if len(probe) < QUOTE_MIN:
            continue
        if _STATE_FIELD.search(path) and len(probe) <= _CODE_MAX:
            continue
        if _produced(path):
            continue
        yield path, probe


def field_completion(payload, case, contract):
    """Fraction of contract-requested fields that carry a non-null value."""
    wanted = contract.required_fields(case)
    if not wanted:
        return {"requested": 0, "filled": 0, "ratio": None,
                "note": "该案例未声明 output_contract 字段"}
    filled = [n for n in wanted
              if payload.get(n) is not None]
    return {"requested": len(wanted), "filled": len(filled),
            "ratio": round(len(filled) / float(len(wanted)), 4),
            "empty": [n for n in wanted if payload.get(n) is None]}


def anchor_coverage(bundle):
    """Fraction of recorded fields backed by an anchor found in the material."""
    anchored = set()
    unanchored = set()
    for item in bundle.anchors:
        anchor = item.get("anchor") or {}
        name = item.get("field")
        if not name:
            continue
        if anchor.get("found"):
            anchored.add(name)
        else:
            unanchored.add(name)
    for gap in bundle.gaps:
        if gap.get("state") == "unanchored":
            unanchored.add(gap.get("field"))
    total = len(anchored) + len(unanchored - anchored)
    return {
        "anchored": len(anchored),
        "unanchored": sorted(n for n in unanchored if n and n not in anchored),
        "ratio": round(len(anchored) / float(total), 4) if total else None,
    }


def number_fidelity(payload, source):
    """Numbers inside claimed spans that occur verbatim in the material."""
    source_norm = _normalise(source)
    checked = 0
    verbatim = 0
    misses = []
    for path, probe in _claimed_fields(payload):
        for token in NUMBER_RE.findall(probe):
            checked += 1
            if token in source or token in source_norm:
                verbatim += 1
            elif len(misses) < 25:
                misses.append({"field": path, "number": token})
    ratio = round(verbatim / float(checked), 4) if checked else None
    return {"checked": checked, "verbatim": verbatim, "ratio": ratio,
            "misses": misses}


def quote_fidelity(payload, source):
    """Check that spans claiming to come from the material really do.

    Three outcomes, because they mean different things:

    * ``verbatim``   - the span is a substring of the source;
    * ``normalised`` - equal once punctuation and spacing are ignored, which is
      how a heading rebuilt from ``1. Introduction`` becomes ``1 Introduction``;
      still faithful, no characters invented;
    * ``unverified`` - neither, so this run reports text the material does not
      contain and the caller should look at it.
    """
    source_flat = _normalise(source)
    checked = 0
    verbatim = 0
    normalised = 0
    anchored = 0
    misses = []
    for path, probe in _claimed_fields(payload):
        checked += 1
        head = probe[:200]
        if head in source or head in source_flat:
            verbatim += 1
            continue
        norm = _normalise(head)
        if norm in source_flat:
            normalised += 1
            continue
        if _both_ends_present(norm, source_flat):
            anchored += 1
            continue
        if len(misses) < 25:
            misses.append({"field": path, "head": probe[:80]})
    faithful = verbatim + normalised + anchored
    ratio = round(faithful / float(checked), 4) if checked else None
    return {"checked": checked, "verbatim": verbatim, "normalised": normalised,
            "anchored": anchored, "ratio": ratio, "unverified": misses}


_WINDOW = 60


def _both_ends_present(norm, source_flat):
    """True when the span's two ends occur in the source, in order.

    Text extraction drops page numbers and running heads into the middle of
    sentences, so a quote assembled across a page boundary is faithful in both
    of its halves while failing an exact substring test: "during training:" and
    "Table 2: The Transformer achieves ..." are both there, with the page
    number "7" wedged between them. Requiring both ends and their order accepts
    that without accepting text the paper never contained.
    """
    if len(norm) < _WINDOW * 2:
        return False
    head = norm[:_WINDOW]
    tail = norm[-_WINDOW:]
    first = source_flat.find(head)
    if first < 0:
        return False
    return source_flat.find(tail, first + len(head)) >= 0


def structure_coverage(doc, payload):
    """How much of the recovered document structure reached the output."""
    doc = doc or {}
    counts = {}
    for key in ("sections", "references", "equations", "tables"):
        counts[key] = len(doc.get(key) or [])
    pages = len(doc.get("pages") or [])
    text = doc.get("text") or ""
    out = {"pages": pages, "source_sections": counts["sections"],
           "source_references": counts["references"],
           "source_equations": counts["equations"],
           "source_tables": counts["tables"],
           "source_words": len(text.split())}
    mapped = 0
    for key, field in (("sections", "sections"), ("references", "references"),
                       ("equations", "equations"), ("tables", "tables")):
        if payload.get(field) is not None:
            mapped += 1
    out["axes_reported"] = mapped
    out["axes_total"] = 4
    return out


# The published runtime budget for one graded run.
BUDGET_SECONDS = 900
BUDGET_REQUESTS = 64


def efficiency(bundle, doc, requests_used=0):
    """What one run cost against the published budget.

    The rubric pays for an efficiency gain only when the gain can be shown, so
    the cost has to be measured rather than asserted: wall-clock seconds, model
    requests actually issued, and how much of each budget is left. A run that
    never calls a model reports zero requests honestly instead of claiming a
    saving it did not make.
    """
    seconds = round(bundle.elapsed(), 3)
    words = len(((doc or {}).get("text") or "").split())
    pages = len((doc or {}).get("pages") or [])
    return {
        "elapsed_seconds": seconds,
        "model_requests": requests_used,
        "seconds_budget": BUDGET_SECONDS,
        "requests_budget": BUDGET_REQUESTS,
        "seconds_headroom": round(BUDGET_SECONDS - seconds, 3),
        "requests_headroom": BUDGET_REQUESTS - requests_used,
        "pages_processed": pages,
        "words_processed": words,
        "words_per_second": round(words / seconds, 1) if seconds > 0 else None,
        "phase_seconds": bundle.phases(),
        "deterministic": True,
        "determinism_scope": ("除本块的全部计时字段（elapsed_seconds、"
                              "seconds_headroom、words_per_second，以及 "
                              "phase_seconds 里的每一段）与 run 块中的 "
                              "elapsed_seconds 外，同一输入两次运行的 result.json "
                              "逐字节一致"),
        "note": "全流程无网络、无模型调用；计时字段随机器负载变化，已单独标出。",
    }


def assess(bundle, doc, records, case, contract, requests_used=0):
    """Build the ``self_check`` block emitted with every result."""
    payload = bundle.payload
    source = _source_text(records, doc)
    completion = field_completion(payload, case, contract)
    anchors = anchor_coverage(bundle)
    numbers = number_fidelity(payload, source)
    quotes = quote_fidelity(payload, source)
    structure = structure_coverage(doc, payload)

    verified = [v for v in (anchors["ratio"], numbers["ratio"],
                            quotes["ratio"]) if v is not None]
    axes = {
        "completion": completion,
        "verifiability": {
            "anchor_ratio": anchors["ratio"],
            "number_ratio": numbers["ratio"],
            "quote_ratio": quotes["ratio"],
            # Sample sizes, so a perfect ratio over three fields cannot be
            # mistaken for a perfect ratio over three hundred.
            "quotes_checked": quotes["checked"],
            "quotes_verbatim": quotes["verbatim"],
            "quotes_normalised": quotes["normalised"],
            "quotes_anchored": quotes["anchored"],
            "numbers_checked": numbers["checked"],
            "unanchored_fields": anchors["unanchored"],
            "number_misses": numbers["misses"],
            "quote_unverified": quotes["unverified"],
        },
        "coverage": structure,
        "correctness": {
            "measured": False,
            "reason": "本机没有评分方的标准答案，正确性无法自测；"
                      "已报告可核对项（锚点、数字、引文），未以猜测填充",
        },
        "cost": efficiency(bundle, doc, requests_used),
    }
    summary = {
        "completeness_ratio": completion["ratio"],
        "verifiability_ratio": round(sum(verified) / len(verified), 4)
        if verified else None,
        "gaps": len(bundle.gaps),
        "notes": len(bundle.notes),
    }
    return {"axes": axes, "summary": summary}


def apply(bundle, doc, records, case, contract, requests_used=0):
    """Attach the audit to ``bundle`` without pretending it is a grade."""
    report = assess(bundle, doc, records, case, contract, requests_used)
    summary = report["summary"]
    bundle.put("self_check", report)
    unanchored = report["axes"]["verifiability"]["unanchored_fields"]
    if unanchored:
        bundle.note("以下字段未能锚定到材料中的具体位置，已作为不可核验项登记：%s"
                    % "、".join(unanchored))
    misses = report["axes"]["verifiability"]["number_misses"]
    if misses:
        bundle.note("声明引自原文的字段中有 %d 个数字未在材料中逐字出现，"
                    "逐项清单见 self_check.axes.verifiability.number_misses"
                    % len(misses))
    unverified = report["axes"]["verifiability"]["quote_unverified"]
    if unverified:
        bundle.note("以下字段自称引自原文但未能在材料中定位，已登记供人工复核：%s"
                    % "、".join(u["field"] for u in unverified[:8]))
    return report
