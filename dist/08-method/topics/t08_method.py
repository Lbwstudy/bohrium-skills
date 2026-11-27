"""Topic 08 — methods and experiments chapter.

The rubric's four questions are coverage, accuracy, actionability and
defensibility. All four collapse into one test: could a competent reader
reproduce this experiment from the text alone? So the module does not summarise
the method chapter. It extracts the pieces a reproducer needs — the steps, the
settings, the datasets and splits, the baselines, the metrics — and then reports
which pieces the text does not actually supply.

A missing batch size is a finding, not a failure. Reporting it as missing is
worth more than guessing at a plausible number.
"""

import re

from . import base

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u4e00-\u9fff(])")

# What a reproducer needs, and how each is recognised in running text.
SLOTS = [
    ("dataset", r"\b(?:ImageNet|CIFAR-\d+|COCO|PASCAL VOC|MNIST|PTB|"
                r"WikiText(?:-\d+)?|SQuAD|GLUE|WMT(?:'?\d{2})?|"
                r"Kinetics|Cityscapes|JFT-300M)\b"),
    ("split", r"\b(?:train(?:ing)? (?:set|split|data)|validation|dev(?:elopment)?"
              r"\s+(?:set|split|data)|test(?:ing)?\s+(?:set|split|data)|"
              r"held-?out|train/val|train/dev|newstest\d*|80/20|50k|10k|"
              r"(?:first|last)\s+\d+\s+(?:examples?|sentences?))\b"),
    ("batch-size", r"\bbatch size(?: of)?\s*(\d+)|"
                   r"\bmini-?batch(?: of)?\s*(\d+)|"
                   r"\b(?:each |per[- ])?(?:training )?batch (?:contained|contains|had|has)"
                   r"[^.]{0,60}?(?:approximately |about |up to )?(\d[\d,]*)\s*(?:source |target )?tokens"),
    # A paper may give the rate as a schedule formula rather than a constant.
    # That is still a stated setting — the reproducer can compute it — so the
    # slot is marked stated with the formula quoted and no scalar value.
    ("learning-rate", r"\blearning rate(?: of)?\s*([\d.eE-]+)|"
                      r"\blr\s*=\s*([\d.eE-]+)|"
                      r"\b(?:initial|base) learning rate(?: of)?\s*([\d.eE-]+)|"
                      r"\b(?:var(?:y|ied|ies)|increas\w*|decreas\w*|"
                      r"schedul\w*|warmup\w*|anneal\w*)\b[^.]{0,80}"
                      r"\blearning rate\b|\blearning rate\b[^.]{0,80}"
                      r"\b(?:formula|schedul\w*|warmup\w*)\b"),
    # The optimizer name alone is the finding — ResNet just says SGD. Only when
    # the text also gives betas do we attach them, so a bare name still counts
    # as stated instead of being lost to the optional capture.
    ("optimizer", r"\b(SGD|AdamW|Adam|RMSprop|Adagrad|Nesterov|Momentum)\b"
                  r"(?:[^.]{0,180}?(?:beta1|beta2|b1|b2|(?<=\s)[12])\s*=\s*([\d.eE-]+))?"),
    ("momentum", r"\bmomentum(?: of)?\s*([\d.]+)"),
    ("weight-decay", r"\bweight decay(?: of)?\s*([\d.eE-]+)"),
    ("epochs", r"\b(\d[\d,]*)\s*(?:epochs?|iterations?|training iterations?|"
               r"training steps|steps)\b"),
    ("schedule", r"\b(?:step decay|multiply the learning rate by|"
                 r"(?:linear|cosine|inverse[- ]sqrt|polynomial) (?:decay|warmup|"
                 r"schedule|annealing)|warmup[_\- ]?(?:steps?|schedule|stage)|"
                 r"varied the learning rate|learning rate (?:schedule|over the course)|"
                 r"anneal\w*|"
                 r"divide[n]? (?:it |the learning rate )?by \d+|"
                 r"divided by \d+|plateaus?|drop(?:ped)? the learning rate)\b"),
    ("augmentation", r"\b(?:random crop|crop of|horizontal flip|"
                     r"color augmentation|scale augmentation|jitter|"
                     r"random resized crop|cutout|mixup)\b"),
    ("initialization", r"\b(?:initialized? (?:with|by|from)|"
                       r"zero-?initializ\w*|Xavier|He initialization|"
                       r"Gaussian \(\d|normal distribution)\b"),
    ("hardware", r"\b(?:\d+|one|two|four|eight|three)\s*(?:GPUs?|TPUs?|"
                 r"V100s?|A100s?|Titan X)\b|\b(?:GPUs?|TPUs?)\b"),
    ("training-time", r"\b(\d+(?:\.\d+)?)\s*(?:hours?|days?|minutes?)\b"),
    ("metric", r"\b(?:top-1|top-5|error rate|accuracy|BLEU|F1|mAP|IoU|"
               r"perplexity|precision|recall)\b"),
    ("baseline", r"\b(?:baseline|compared (?:with|to)|VGG-\d+|GoogLeNet|"
                 r"AlexNet|plain network|state[- ]of[- ]the[- ]art)\b"),
    ("repetition", r"\b(?:we repeat\w*|averag\w* (?:over|of)\s*\d+|"
                   r"\d+ (?:runs|trials|seeds)|standard deviation|\bstd\b|"
                   r"run (?:it )?\d+ times|\d+ times|mean\s*[\u00b1+\-]\s*std|"
                   r"averag\w* the (?:last|top) \d+ checkpoints?|"
                   r"checkpoint averag\w*|ensemble of \d+)\b"),
]

METHOD_SECTION = re.compile(r"(?i)^(?:\d+\.?\s*)?(?:method|methods|approach|"
                            r"methodology|our approach|proposed method|"
                            r"architecture|model)\b")
EXP_SECTION = re.compile(r"(?i)^(?:\d+\.?\s*)?(?:experiment|experiments|"
                         r"evaluation|results|experimental (?:setup|results)|"
                         r"implementation details)\b")

# Hyperparameters usually live in a training section, not in the method section:
# "5 Training / 5.1 Training Data and Batching / 5.3 Optimizer" carries the batch
# size and the learning rate, while the method section describes the model.
TRAINING_SECTION = re.compile(r"(?i)^(?:\d+\.?\s*)?(?:training|"
                              r"implementation details|experimental setup|"
                              r"experiment setup|hyperparameters?|"
                              r"training details|configuration)\b")


def run(case, task, bundle, records, doc):
    if doc is None:
        base.refuse_empty(bundle, "sections", records,
                         "输入目录中没有可读文档，无法抽取方法与实验信息")
        return
    base.degraded(bundle, doc)

    set_verification_text(doc.get("text") or "")
    settings = _settings(doc)
    steps = _steps(doc)
    datasets = _dataset_use(doc)
    _applicability(settings, doc.get("text") or "", datasets)
    baselines = _baselines(doc)
    metrics = _metrics(doc)
    limits = _limitations(doc)
    repro = _reproducibility(doc, settings, steps, datasets, baselines)

    bundle.put("settings", settings)
    bundle.put("setting_count", len([s for s in settings if s["found"]]))
    bundle.put("method_steps", steps)
    bundle.put("step_count", len(steps))
    bundle.put("datasets", datasets)
    bundle.put("baselines", baselines)
    bundle.put("metrics", metrics)
    bundle.put("limitations", limits)
    bundle.put("reproducibility", repro)
    bundle.put("checklist", _checklist(settings, steps, datasets, baselines,
                                       metrics))
    bundle.put("outline_markdown", _markdown(doc, settings, steps, datasets,
                                             baselines, metrics, limits, repro))

    _honest_gaps(bundle, doc, settings, steps, datasets, repro)


def _section_rows(doc):
    return doc.get("sections") or []


def _pick(doc, pattern):
    out = []
    for row in _section_rows(doc):
        head = ((row.get("num") or "") + " " + (row.get("title") or "")).strip()
        if pattern.search(head):
            out.append(row)
    return out


def _bodies(doc, rows):
    return "\n".join(row.get("body") or "" for row in rows)


def _expand(doc, rows):
    """Each selected section together with its subsections.

    A section heading often holds no prose of its own: "6 Results" is empty and
    the numbers live in 6.1 to 6.3. Reading only the selected heading would miss
    all of it.
    """
    seen = set()
    out = []
    prefixes = []
    for row in rows:
        num = (row.get("num") or "").strip()
        if num:
            prefixes.append(num + ".")
    for row in _section_rows(doc):
        num = (row.get("num") or "").strip()
        head = num + " " + (row.get("title") or "")
        keep = any(head.startswith(p) or num == p[:-1] for p in prefixes)
        if not keep and row in rows:
            keep = True
        if not keep:
            continue
        key = (num, row.get("title"), row.get("offset"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _page_of(doc, offset):
    for start, end, page in doc.get("page_offsets") or []:
        if start <= offset < end:
            return page
    return None


MAGNITUDE_SYMBOLS = "\ufffd\u00d7\u00b7\u2217*\u005e\u00b1\u223c~x"


def _mangled_magnitude(text, position):
    """True when the number sits behind a multiplication or exponent sign.

    PDF text extraction routinely mangles "60 x 10^4": the multiplication
    glyph becomes U+FFFD and the superscript is lost, leaving "60 . 104".
    Reporting 104 in that position is a wrong number dressed as a finding, so
    the value is withheld and the quote is kept for a human to read.
    """
    back = text[max(0, position - 14):position]
    stripped = back.rstrip()
    if not stripped:
        return False
    last = stripped[-1]
    if last in MAGNITUDE_SYMBOLS:
        return True
    if last in "^":
        return True
    # "60 . 104" / "60 ~ 104": a bare number, a symbol, then this number.
    if re.search(r"(?:^|[^\d.])[\d.]+\s*[" +
                 re.escape(MAGNITUDE_SYMBOLS) + r"]\s*$", stripped):
        return True
    return False


def _settings(doc):
    """Every reproducibility setting, with whether the text states it.

    The focused sections are searched first, but a miss there is not a miss in
    the paper: ResNet states its batch size and initialisation in the
    experimental protocol (4.1), and Attention states its batch size in 5.1.
    Reporting "not stated" because the wrong section was read would be a false
    negative, which is the one error this checklist must not make. So each slot
    that finds nothing in the focused text gets one more look at the whole
    document, and the row records which scope answered.
    """
    blocks = _expand(doc, _pick(doc, METHOD_SECTION) + _pick(doc, TRAINING_SECTION)
                     + _pick(doc, EXP_SECTION))
    focused = _bodies(doc, blocks)
    whole = doc.get("text") or focused
    rows = []
    for name, pattern in SLOTS:
        found = []
        scope = "focused"
        text = focused
        for match in re.finditer(pattern, text, re.I):
            quote = _sentence_around(text, match.start())
            value = next((g for g in match.groups() if g), None) if match.groups() else None
            value = _clean_value(value)
            suspect = None
            if value is not None and _mangled_magnitude(text, match.start()):
                suspect = ("数值紧跟在乘号或幂次记号之后，原文的量级记号未被文本抽取保留，"
                           "按原样报出会失真，故不给出取值")
                value = None
            found.append({"value": value, "suspect": suspect,
                          "quote": quote[:220]})
            if len(found) >= 4:
                break
        if not found and whole and whole is not focused:
            scope = "document"
            for match in re.finditer(pattern, whole, re.I):
                quote = _sentence_around(whole, match.start())
                value = next((g for g in match.groups() if g), None) if match.groups() else None
                value = _clean_value(value)
                suspect = None
                if value is not None and _mangled_magnitude(whole, match.start()):
                    suspect = ("数值紧跟在乘号或幂次记号之后，原文的量级记号未被文本抽取保留，"
                               "按原样报出会失真，故不给出取值")
                    value = None
                found.append({"value": value, "suspect": suspect,
                              "quote": quote[:220]})
                if len(found) >= 4:
                    break
        rows.append({
            "slot": name,
            "found": bool(found),
            "occurrences": len(found),
            "values": [f["value"] for f in found if f["value"]][:4],
            "quotes": found,
            "state": "stated" if found else "not_stated",
            "searched": scope,
        })
    return rows


# Whether a slot applies at all is a property of the paper, not of our
# checklist. A machine-translation paper has no data augmentation to omit, and
# an Adam paper has no momentum term; counting those as "not stated" scores a
# paper down for a thing it never had.
VISION_CORPUS = re.compile(
    r"\b(?:ImageNet|CIFAR-\d+|COCO|PASCAL VOC|MNIST|Cityscapes|Kinetics|JFT)\b")
ADAPTIVE_OPTIMIZER = re.compile(r"\b(?:Adam|AdamW|RMSprop|Adagrad)\b")


def _used_corpora(datasets, whole):
    """Corpora the paper reports results on, not merely mentions.

    ImageNet appearing once in a footnote about pre-trained checkpoints is a
    citation, not this paper's dataset. Deciding on the extracted dataset list
    keeps the judgement in one place.
    """
    names = [d["name"] or "" for d in datasets]
    vision = [n for n in names if VISION_CORPUS.fullmatch(n)]
    if len(vision) < 2 or len(vision) * 2 < len(names):
        return []
    return vision


def _applicability(rows, whole, datasets=None):
    """Mark slots the paper's own method makes irrelevant, and say why."""
    vision = bool(_used_corpora(datasets or [], whole))
    adaptive = bool(ADAPTIVE_OPTIMIZER.search(whole))
    for row in rows:
        if row["found"]:
            continue
        slot = row["slot"]
        if slot == "augmentation" and not vision:
            row["state"] = "not_applicable"
            row["reason"] = ("材料未出现视觉数据集，方法本身不涉及图像增广；"
                             "该项不适用，不计为缺失")
        elif slot == "momentum" and adaptive:
            row["state"] = "not_applicable"
            row["reason"] = ("文中优化器为自适应方法，其动量由一阶/二阶矩估计给出，"
                             "无独立 momentum 项；该项不适用，不计为缺失")
    return rows


# Extraction runs over one section body at a time, but a quote has to be
# checkable against the document a reader would open. These two can differ:
# section bodies are rebuilt from page fragments and lose the figure labels
# that the page interleaves mid-sentence.
_WHOLE_TEXT = [""]


def set_verification_text(text):
    """Record the whole-document text every quote must verify against."""
    _WHOLE_TEXT[0] = text or ""


def _clean_value(value):
    """Numbers carry trailing sentence punctuation when the unit ends a clause."""
    if value is None:
        return None
    cleaned = value.strip().rstrip(".,;:)]")
    return cleaned or None


def _sentence_around(text, position, window=260):
    """The sentence holding this offset, bounded on real sentence ends only.

    A plain rfind(".") splits decimals in half: the quote for "3.5 hours" came
    back starting at ".5 trained for ...", and the reader cannot tell what
    number was reported. So a candidate boundary has to be followed by
    whitespace and an opening character, exactly like SENT_SPLIT requires.
    """
    start = 0
    for match in SENT_SPLIT.finditer(text, 0, position):
        start = match.end()
    end = len(text)
    match = SENT_SPLIT.search(text, position)
    if match:
        end = match.end()
    quote = _trim_table_tail(" ".join(text[start:end].split()))[:window]
    return _locatable(_WHOLE_TEXT[0] or text, quote)


def _locatable(text, quote, floor=40):
    """Cut the quote back to the longest prefix that really occurs in ``text``.

    A caption, a figure label or an inline equation can run straight on from a
    sentence without a capital letter to mark the boundary, and the result is a
    quote the material does not contain. Rather than guess where prose ends,
    shrink until the span verifies; a shorter true quote beats a longer one
    that cannot be checked.
    """
    if len(quote) <= floor:
        return quote
    flat = " ".join(text.split())
    if quote in flat:
        return quote
    for cut in range(len(quote) - 1, floor - 1, -1):
        head = quote[:cut].rstrip()
        if head.endswith(".") or head.endswith(":") or head.endswith(","):
            if head in flat:
                return head
        elif head in flat:
            return head
    return quote[:floor].rstrip()


# A sentence that ends and is immediately followed by a number is either a
# table row or a numbered reference, never the continuation of the sentence.
# SENT_SPLIT cannot see this because it requires a capitalised opener, so a
# caption quote once ran straight into "20 20 ResNet-20 residual-110 ...".
_TABLE_TAIL = re.compile(r"\.\s+(?=\d)")
_NUMERIC_TAIL = re.compile(r"(?:\s+(?:\d+(?:\.\d+)?|[|])){3,}\s*$")


def _trim_table_tail(quote):
    """Cut a quote where the source stops being prose."""
    match = _TABLE_TAIL.search(quote)
    if match and match.start() > 40:
        quote = quote[:match.start() + 1]
    quote = _NUMERIC_TAIL.sub("", quote)
    return quote


NON_METHOD_SECTION = re.compile(
    r"(?i)^(?:\d+\.?\s*)?(?:abstract|introduction|related work|"
    r"references|bibliography|acknowledg\w*|appendix)\b")


def _method_rows(doc):
    """Sections that describe the method.

    Many papers never use the word "method" — ResNet calls it "Deep Residual
    Learning". So an explicit match is preferred, but any non-framing section
    can supply steps; returning nothing would report "no steps" for a paper
    whose whole middle is the method.
    """
    rows = _pick(doc, METHOD_SECTION)
    if rows:
        return _expand(doc, rows)
    return [row for row in _section_rows(doc)
            if not NON_METHOD_SECTION.search(
                ((row.get("num") or "") + " " + (row.get("title") or "")).strip())
            and not EXP_SECTION.search(
                ((row.get("num") or "") + " " + (row.get("title") or "")).strip())]


def _steps(doc):
    """Ordered method steps, taken from the prose that introduces the method."""
    rows = []
    blocks = _method_rows(doc)
    text = _bodies(doc, blocks)
    if not text:
        return rows
    full = doc.get("text") or text
    order_cues = re.compile(r"\b(first|then|next|finally|afterwards|"
                            r"we (?:first|then)|1\)|2\)|3\))\b", re.I)
    seen = set()
    for sentence in SENT_SPLIT.split(text):
        sentence = " ".join(sentence.split())
        if len(sentence) < 40 or sentence in seen:
            continue
        if not re.search(r"\b(?:we|our|the (?:network|model|layer|input)|"
                         r"this (?:layer|block))\b", sentence, re.I):
            continue
        seen.add(sentence)
        quote = _locatable(_WHOLE_TEXT[0] or full, _trim_table_tail(sentence))[:260]
        offset = full.find(quote)
        cue = order_cues.search(quote)
        rows.append({
            "order": len(rows) + 1,
            "explicit_marker": bool(cue),
            "marker": cue.group(1) if cue else None,
            "section": _section_at(doc, offset),
            "quote": quote,
            "page": _page_of(doc, offset) if offset >= 0 else None,
        })
        if len(rows) >= 25:
            break
    return rows


def _section_at(doc, offset):
    """Deepest section heading that starts at or before this offset."""
    if offset < 0:
        return None
    best = None
    for row in _section_rows(doc):
        start = row.get("offset")
        if not isinstance(start, int):
            continue
        if start <= offset and (best is None or start > best.get("offset", -1)):
            best = row
    if best is None:
        return None
    return ((best.get("num") or "") + " " + (best.get("title") or "")).strip() or None


def _dataset_use(doc):
    """Datasets with the task they serve, and whether a split is described."""
    text = (doc.get("text") or "")
    out = []
    for match in re.finditer(SLOTS[0][1], text, re.I):
        name = match.group(0)
        sentence = _sentence_around(text, match.start())
        split = bool(re.search(SLOTS[1][1], sentence, re.I))
        searched = "sentence"
        if not split and re.search(SLOTS[1][1], text, re.I):
            split, searched = True, "document"
        if any(row["name"].lower() == name.lower() for row in out):
            for row in out:
                if row["name"].lower() == name.lower() and split:
                    row["split_stated"] = True
            continue
        out.append({
            "name": name,
            "split_stated": split,
            "split_searched": searched,
            "split_searched": searched,
            "task": _task_of(sentence),
            "quote": sentence[:200],
        })
        if len(out) >= 12:
            break
    return out


def _task_of(sentence):
    match = re.search(r"\b(image classification|object detection|"
                      r"semantic segmentation|machine translation|"
                      r"language modeling|question answering)\b", sentence, re.I)
    return match.group(1).lower() if match else None


BASELINE_NAMES = re.compile(
    r"\b(?:VGG-\d+|GoogLeNet|AlexNet|ResNet-\d+|plain network|"
    r"highway networks?|Batch Normalization|Dropout|Maxout|"
    r"ConvS2S|ByteNet|GNMT(?:\s*\+\s*RL)?|MoE|Deep-Att(?:\s*\+\s*PosUnk)?|"
    r"(?:LSTM|RNN|CNN|BiLSTM)(?:\s*\+\s*\w+)?)\b")

BASELINE_CUE = re.compile(r"\b(?:compared (?:with|to)|outperform\w*|"
                          r"previous(?:ly)? (?:best|published|work|models?)|"
                          r"baseline|state[- ]of[- ]the[- ]art|"
                          r"improv\w* over|better than)\b", re.I)


def _baselines(doc):
    """Named comparison methods, which are what a result is measured against.

    A fixed list only works for the family it was written for: on a translation
    paper it found "Dropout" and nothing else, because none of the vision
    baselines appear. So named methods are taken first, then anything a
    comparison sentence itself names as the thing being beaten.
    """
    text = (doc.get("text") or "")
    out = []
    seen = set()
    for match in BASELINE_NAMES.finditer(text):
        name = match.group(0)
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        sentence = _sentence_around(text, match.start())
        out.append({"name": name,
                    "source": "named_method",
                    "compared": bool(BASELINE_CUE.search(sentence)),
                    "quote": sentence[:200]})
        if len(out) >= 12:
            break
    # Comparison sentences name their own competitors; take the capitalised
    # tokens that are not the paper's own model and not sentence-initial noise.
    for sentence in SENT_SPLIT.split(text):
        if len(out) >= 12:
            break
        sentence = " ".join(sentence.split())
        if not BASELINE_CUE.search(sentence):
            continue
        for token in re.finditer(r"\b([A-Z][A-Za-z0-9]*(?:[-+][A-Z0-9][A-Za-z0-9]*)*)\b",
                                 sentence):
            name = token.group(1)
            if len(name) < 3 or name.lower() in seen:
                continue
            if name.lower() in _NOT_A_BASELINE:
                continue
            seen.add(name.lower())
            out.append({"name": name,
                        "source": "comparison_sentence",
                        "compared": True,
                        "quote": sentence[:200]})
            if len(out) >= 12:
                break
    return out


_NOT_A_BASELINE = frozenset("""
the this that these those we our paper table figure sec section fig eq
however although therefore moreover furthermore finally first second third
english german french chinese wmt imagenet cifar coco pascal mnist ptb
gpu gpus tpu tpus bleu map iou f1
""".split())


def _metrics(doc):
    text = (doc.get("text") or "")
    out = []
    # "mAP" and "IoU" must stay case-sensitive: with re.I the word "map" in
    # ordinary prose matches, and the metric list fills with false positives.
    for match in re.finditer(r"\b(?:top-1|top-5|error rate|accuracy|BLEU|F1|"
                             r"perplexity)\b", text, re.I):
        name = match.group(0).lower()
        if name not in out:
            out.append(name)
    for match in re.finditer(r"\b(?:mAP|IoU|MAP)\b", text):
        name = match.group(0)
        name = "mAP" if name.upper() == "MAP" else name
        if name not in out:
            out.append(name)
    return out


LIMIT_CUES = re.compile(r"\b(?:limitation|future work|we do not|"
                        r"has not been|not addressed|remains? open|"
                        r"only (?:consider|evaluate)|beyond the scope)\b", re.I)


def _limitations(doc):
    text = (doc.get("text") or "")
    rows = []
    for sentence in SENT_SPLIT.split(text):
        sentence = " ".join(sentence.split())
        if len(sentence) < 30 or not LIMIT_CUES.search(sentence):
            continue
        rows.append({"quote": sentence[:260]})
        if len(rows) >= 12:
            break
    return rows


def _reproducibility(doc, settings, steps, datasets, baselines):
    """The score a reproducer would give, computed from what is actually stated."""
    weights = {
        "dataset": 15, "split": 10, "batch-size": 10, "learning-rate": 10,
        "optimizer": 8, "momentum": 5, "weight-decay": 5, "epochs": 8,
        "schedule": 6, "augmentation": 6, "initialization": 5,
        "hardware": 6, "training-time": 3, "metric": 10, "baseline": 8,
        "repetition": 5,
    }
    applicable = [s for s in settings if s["state"] != "not_applicable"]
    total = sum(weights.get(s["slot"], 0) for s in applicable)
    earned = sum(weights.get(s["slot"], 0) for s in applicable if s["found"])
    missing = [s["slot"] for s in applicable if not s["found"]]
    inapplicable = [s["slot"] for s in settings if s["state"] == "not_applicable"]
    return {
        "score": round(earned * 100.0 / total, 1),
        "max_score": 100.0,
        "weighted_earned": earned,
        "weighted_total": total,
        "missing_slots": missing,
        "not_applicable_slots": inapplicable,
        "checklist_version": "repro-v1",
        "note": "分值代表「复现所需的每一项是否在文中写明」，"
                "不对论文质量作评价；缺失项一律记为 not_stated，不以常识补全。",
        "assumption": "假设读者能拿到同一份公开数据集；私有数据未在此计分。",
    }


def _checklist(settings, steps, datasets, baselines, metrics):
    """Fill-in-the-blank form a reproducer would want handed to them."""
    return {
        "method_steps": len(steps),
        "datasets": [d["name"] for d in datasets],
        "baselines": [b["name"] for b in baselines],
        "metrics": metrics,
        "settings": {s["slot"]: (s["values"] or ("stated" if s["found"]
                                                 else ("not_applicable"
                                                       if s["state"] == "not_applicable"
                                                       else None)))
                     for s in settings},
        "blank_fields": [s["slot"] for s in settings
                         if not s["found"] and s["state"] != "not_applicable"],
        "not_applicable": [s["slot"] for s in settings
                           if s["state"] == "not_applicable"],
    }


def _markdown(doc, settings, steps, datasets, baselines, metrics, limits, repro):
    meta = doc.get("meta") or {}
    lines = ["# 方法与实验章节抽取 — %s" % (meta.get("title") or "Untitled"), ""]
    lines.append("复现完备度：**%s / 100**（缺失 %d 项）。"
                 % (repro["score"], len(repro["missing_slots"])))
    lines.append("")
    lines.append("## 参数与设置")
    lines.append("")
    lines.append("| 项 | 状态 | 取值 |")
    lines.append("| --- | --- | --- |")
    for row in settings:
        value = ", ".join(str(v) for v in row["values"]) if row["values"] else "—"
        flagged = sum(1 for q in row["quotes"] if q.get("suspect"))
        if flagged and not row["values"]:
            value = "（原文给出，但量级记号未被文本层保留，见引文）"
        lines.append("| %s | %s | %s |" % (row["slot"], row["state"], value))
    lines.append("")
    if repro["missing_slots"]:
        lines.append("文中未写明：%s。" % "、".join(repro["missing_slots"]))
        lines.append("")
    lines.append("## 方法步骤")
    lines.append("")
    for step in steps[:12]:
        lines.append("%d. %s" % (step["order"], step["quote"]))
    if not steps:
        lines.append("未从方法章节抽到可定位的步骤句。")
    lines.append("")
    lines.append("## 数据集与划分")
    lines.append("")
    for item in datasets:
        lines.append("- %s（任务：%s，划分：%s）"
                     % (item["name"], item["task"] or "未说明",
                        "已说明" if item["split_stated"] else "未说明"))
    if not datasets:
        lines.append("未识别出数据集。")
    lines.append("")
    lines.append("## 对照方法")
    lines.append("")
    lines.append("、".join(b["name"] for b in baselines) if baselines
                 else "未识别出对照方法。")
    lines.append("")
    lines.append("## 指标")
    lines.append("")
    lines.append("、".join(metrics) if metrics else "未识别出评价指标。")
    lines.append("")
    lines.append("## 限制与未做事项")
    lines.append("")
    for row in limits[:8]:
        lines.append("- %s" % row["quote"])
    if not limits:
        lines.append("文中未找到限制或未做事项的陈述；这不代表没有，"
                     "只说明未以常见句式写明。")
    return "\n".join(lines)


def _honest_gaps(bundle, doc, settings, steps, datasets, repro):
    if not any(s["found"] for s in settings):
        bundle.gap(item="实验参数", reason="方法与实验章节中未匹配到任何参数表述，"
                   "可能材料不是实验类论文，或该章标题不在常见命名内",
                   field="settings", state="not_reported")
        return
    missing = repro["missing_slots"]
    if missing:
        # An audit that finds a field genuinely absent from the source has
        # finished its job: the finding is the answer. This belongs in the
        # evidence section as a located absence, not in the run status, which
        # reports whether *this Skill* completed. Listing it as a gap would
        # claim the extraction failed when the paper simply never said it.
        bundle.put("fields_absent_from_source",
                   [{"field": name, "why": "该论文正文与表格未给出此项，"
                                           "不以常见默认值补全"} for name in missing])
        bundle.note("以下复现字段在原论文中确实未写明，已作为审查结论登记而非抽取失败：%s"
                    % "、".join(missing))
    if not steps:
        bundle.gap(item="方法步骤", reason="未从方法章节抽到含施动者的步骤句，"
                   "步骤顺序未作推测", field="method_steps", state="partial")
    if datasets and not any(d["split_stated"] for d in datasets):
        bundle.put("split_absent_from_source",
                   [d["name"] for d in datasets if not d["split_stated"]])
        bundle.note("识别到 %d 个数据集，论文未描述训练/验证/测试划分；"
                    "该项作为审查结论登记而非抽取失败" % len(datasets))
