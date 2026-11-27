"""Meaning-preservation checks shared by the polishing rules.

An edit is only worth offering if it cannot change what the sentence claims.
Four things carry a claim: the numbers, whether it is negated, which direction
a comparison points, and which named things it is about. This module compares
those four between the original and the edited sentence and returns a verdict
per axis, so a rejected edit can say exactly which axis it would have broken.
"""

import re

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# Contracted forms carry a negation of their own; without them, expanding
# "doesn't" to "does not" reads as a new negation and the edit is rejected.
NEGATION = re.compile(r"\b(?:not|no|never|none|neither|nor|without|cannot|"
                      r"can't|don't|doesn't|didn't|isn't|aren't|wasn't|weren't|"
                      r"won't|wouldn't|shouldn't|couldn't|hasn't|haven't|hadn't|"
                      r"fail(?:s|ed)?|unable)\b", re.I)
COMPARATIVE = re.compile(r"\b(?:higher|lower|more|less|better|worse|greater|"
                         r"smaller|larger|faster|slower|increase[sd]?|"
                         r"decrease[sd]?|improve[sd]?|reduce[sd]?|"
                         r"outperform[sd]?|exceed[sd]?)\b", re.I)
NAMED = re.compile(r"\b(?:[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)\b")


def numbers(sentence):
    return NUMBER.findall(sentence)


def negation_count(sentence):
    return len(NEGATION.findall(sentence))


def comparatives(sentence):
    return [m.group(0).lower() for m in COMPARATIVE.finditer(sentence)]


def named_terms(sentence, ignore=None):
    """Capitalised tokens, minus the stop list of ordinary sentence openers."""
    out = []
    for match in NAMED.finditer(sentence):
        token = match.group(0)
        if ignore and token in ignore:
            continue
        out.append(token)
    return out


STOPWORD_HEADS = {
    "The", "This", "These", "Those", "We", "Our", "It", "Its", "A", "An",
    "In", "On", "For", "With", "As", "However", "Therefore", "Thus", "While",
    "Although", "Because", "Since", "If", "When", "Table", "Figure", "Fig",
    "Section", "Equation", "Notably", "Moreover", "Furthermore", "Finally",
    "First", "Second", "Third", "Such", "Both", "Each", "All", "Some", "Many",
}


def preserves(before, after):
    """Compare the four claim-bearing axes between two versions of a sentence."""
    n_before = sorted(numbers(before))
    n_after = sorted(numbers(after))
    numbers_ok = n_before == n_after

    neg_before = negation_count(before)
    neg_after = negation_count(after)
    negation_ok = neg_before == neg_after

    c_before = sorted(comparatives(before))
    c_after = sorted(comparatives(after))
    comparison_ok = c_before == c_after

    e_before = {t.lower() for t in named_terms(before, STOPWORD_HEADS)}
    e_after = {t.lower() for t in named_terms(after, STOPWORD_HEADS)}
    entities_ok = e_before == e_after

    preserved = numbers_ok and negation_ok and comparison_ok and entities_ok

    reasons = []
    if not numbers_ok:
        reasons.append("数值由 %s 变为 %s" % (n_before, n_after))
    if not negation_ok:
        reasons.append("否定数量由 %d 变为 %d" % (neg_before, neg_after))
    if not comparison_ok:
        reasons.append("比较词由 %s 变为 %s" % (c_before, c_after))
    if not entities_ok:
        lost = sorted(e_before - e_after)
        gained = sorted(e_after - e_before)
        reasons.append("专名变化：丢失 %s，新增 %s" % (lost, gained))

    return {
        "preserved": preserved,
        "numbers_preserved": numbers_ok,
        "negation_preserved": negation_ok,
        "comparison_preserved": comparison_ok,
        "entities_preserved": entities_ok,
        "reason": "；".join(reasons) if reasons else
                  "数值、否定、比较方向与专名均未变化",
    }
