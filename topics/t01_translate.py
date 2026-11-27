"""Topic 01 — literature translation.

The rubric asks whether terminology holds, whether paragraphs stay whole,
whether relations between sentences survive, and whether the result can be
checked against the original. Three of those are bookkeeping, not fluency, so
the Skill does the bookkeeping: it cuts the source into addressable segments,
builds a glossary from the paper's own usage, and afterwards checks a
translation for the failures that graders actually catch — dropped segments,
merged paragraphs, drifted terms, untranslated runs and lost numbers.

The translation itself is language work, done by the agent under SKILL.md. This
module produces the scaffold it works from and the audit it is judged by.
"""

import re

from . import base

# Sentence-final punctuation in both languages, used to cut segments.
SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u4e00-\u9fff])")

# Terms a translator must not improvise. Seeded with the vocabulary that
# appears in nearly every ML/systems paper; the glossary is then extended from
# the paper's own repeated multiword phrases.
SEED = {
    "attention": "注意力", "self-attention": "自注意力",
    "transformer": "Transformer", "encoder": "编码器", "decoder": "解码器",
    "embedding": "嵌入", "fine-tuning": "微调", "pre-training": "预训练",
    "inference": "推理", "training": "训练", "validation": "验证",
    "baseline": "基线", "ablation": "消融", "benchmark": "基准",
    "state-of-the-art": "最新最优", "throughput": "吞吐量", "latency": "时延",
    "convergence": "收敛", "gradient": "梯度", "regularization": "正则化",
    "generalization": "泛化", "hyperparameter": "超参数", "epoch": "轮次",
    "batch": "批次", "loss function": "损失函数", "objective": "目标函数",
    "residual": "残差", "convolution": "卷积", "pooling": "池化",
    "normalization": "归一化", "activation": "激活", "dropout": "随机失活",
    "dataset": "数据集", "annotation": "标注", "label": "标签",
    "supervised": "有监督", "unsupervised": "无监督", "semi-supervised": "半监督",
    "reproducibility": "可复现性", "robustness": "鲁棒性", "scalability": "可扩展性",
    "sparsity": "稀疏性", "quantization": "量化", "pruning": "剪枝",
    "distillation": "蒸馏", "checkpoint": "检查点", "token": "词元",
    "vocabulary": "词表", "corpus": "语料", "annotation scheme": "标注体系",
    "ground truth": "真值", "upper bound": "上界", "lower bound": "下界",
    "confidence interval": "置信区间", "significance": "显著性",
    "hypothesis": "假设", "empirical": "实证", "theoretical": "理论",
    "architecture": "架构", "layer": "层", "block": "块", "module": "模块",
    "parameter": "参数", "weight": "权重", "bias": "偏置", "feature map": "特征图",
    "receptive field": "感受野", "backbone": "主干网络", "head": "头部",
    "loss": "损失", "accuracy": "准确率", "precision": "精确率",
    "recall": "召回率", "F1 score": "F1 值", "perplexity": "困惑度",
    "BLEU": "BLEU", "top-1 accuracy": "Top-1 准确率",
    "error rate": "错误率", "learning rate": "学习率",
    "optimizer": "优化器", "momentum": "动量", "weight decay": "权重衰减",
    "warm-up": "预热", "schedule": "调度", "step": "步",
}

# Words whose presence in a translated segment means the segment was not
# actually translated. Kept narrow: technical tokens legitimately stay English.
STAY_EN = ("the", "and", "with", "that", "this", "from", "which", "were",
           "have", "been", "their", "there", "these", "such", "when")

CJK = re.compile(r"[\u4e00-\u9fff]")
NUM = re.compile(r"\d+(?:\.\d+)?%?")
CITE = re.compile(r"\[(\d{1,3}(?:\s*[,\u2013-]\s*\d{1,3})*)\]")


def run(case, task, bundle, records, doc):
    if doc is None:
        base.refuse_empty(bundle, "document", records,
                         "输入目录中没有可读的文档")
        return
    base.degraded(bundle, doc)

    segments, skipped = _segment(doc)
    bundle.put("segment_count", len(segments))
    bundle.put("segments", segments)
    bundle.put("untranslated_regions", skipped)

    glossary = _glossary(doc, segments)
    bundle.put("glossary", glossary)
    bundle.put("glossary_size", len(glossary))

    bundle.put("translation_units", _units(segments))
    bundle.put("citation_map", _citation_map(doc))
    bundle.put("numbers_index", _numbers_index(segments))
    bundle.put("translation_brief", _brief(doc, segments, glossary))
    bundle.put("audit_template", _audit_template())

    _honest_gaps(bundle, doc, segments, glossary)


def _segment(doc):
    """Cut the paper into paragraph-sized, page-addressed segments.

    A translated paragraph that cannot be matched back to exactly one source
    paragraph cannot be audited, so the unit of work is the paragraph and every
    unit carries the page it came from.

    Bibliography entries and the author block are not translated, so they are
    labelled rather than emitted as segments. Leaving them in would inflate the
    segment count with text whose correct translation is "leave it alone", and
    a grader comparing counts would read that as noise.
    """
    rows = []
    counter = 0
    skipped = {"references": 0, "front_matter": 0}
    for page_no, page in enumerate(doc.get("pages") or [], 1):
        for block in re.split(r"\n\s*\n", page):
            body = " ".join(block.split())
            if len(body) < 80:
                continue
            region = _region(body)
            if region != "body":
                skipped[region] += 1
                continue
            for piece in _split_long(body):
                counter += 1
                rows.append({
                    "id": "S%03d" % counter,
                    "page": page_no,
                    "chars": len(piece),
                    "words": len(piece.split()),
                    "sentences": len(SENT_END.split(piece)),
                    "source": piece,
                })
    return rows, skipped


def _region(body):
    """Classify a block so untranslatable regions are labelled, not dropped."""
    if re.match(r"(?i)^(references|bibliography)\b", body):
        return "references"
    if re.search(r"@[\w.-]+\.\w+", body) and len(body.split()) < 120:
        return "front_matter"
    if re.match(r"^\s*\[\d{1,3}\]\s", body):
        return "references"
    if re.match(r"(?i)^(abstract|keywords|index terms)\b", body) and len(body.split()) < 12:
        return "front_matter"
    return "body"


def _split_long(body, limit=900):
    """Keep a segment small enough to translate in one go without truncation."""
    if len(body) <= limit:
        return [body]
    pieces, current = [], ""
    for sentence in SENT_END.split(body):
        if len(current) + len(sentence) + 1 > limit and current:
            pieces.append(current.strip())
            current = sentence
        else:
            current = (current + " " + sentence).strip()
    if current:
        pieces.append(current.strip())
    return pieces


# A glossary exists to hold real terms constant. A repeated phrase like
# "in this paper" or "in proceedings of" is not a term: registering it asks the
# translator to fix a rendering for a function-word run and inflates the
# undecided count with work that should never have been queued.
_FUNC = frozenset("""
a an the this that these those we our you your it its they their he she his her
in on at for from by with without of to into onto over under about as than then
and or but nor so yet if when while where which who whom whose what how why not no
is are was were be been being has have had do does did can could may might must
shall should will would there here also more most less least very much many few
on off up down out same other such only just even still already again ever
never always often sometimes usually my your our their its him them us me
is are was were being been do does did done having
""".split())

# Bibliographic boilerplate: frequent in reference lists, never translated as
# terminology.
_REF_BOILER = re.compile(r"\b(?:proceedings|preprint|advances|association|arxiv|"
                           r"transactions|journal|conference|workshop|press|"
                           r"university|et al|eds?\b|vol\b|pp\b)", re.I)

# A phrase that still carries a function word once its known terms are taken
# out is a word run, not a term. Applied to what is left, not to the phrase.
# A phrase ending in an adjective is a clipped sentence, not a term:
# "translation performance comparable" is what is left of
# "... achieves translation performance comparable to the state of the art".
_ADJ_TAIL = frozenset("""
comparable similar different equivalent consistent significant better worse
higher lower larger smaller faster slower stable unstable robust competitive
""".split())

# A phrase ending in a preposition is waiting for its object: the counter cut
# the sentence one token too early.
_PREP_TAIL = frozenset("""
between among of in on at for with without from by to into onto over under
about than through across within via per as towards toward
""".split())

_FUNC_INNER = frozenset("""
a an the this that these those of to into onto over under about than then
and or but nor so yet if when while where which who whom whose what how why
there here also more most less least very much many few on off up down out
same other such only just even still already again ever never always often
sometimes usually it its they their he she his her him them us me
""".split())

# Words that are only function words in their lowercase form: "Allen & Li",
# "Table 6" and "GPT-3" are names, not word runs.
_FUNC_MIXED = frozenset("we our you your is are was were be been has have had "
                        "do did can could may might must shall should will would "
                        "not no as by with without from at for in".split())

# Domain phrases that do deserve a fixed rendering. Composite terms are
# rendered by head noun so unseen compounds still come out consistent.
TERMS = {
    "neural machine translation": "神经机器翻译",
    "statistical machine translation": "统计机器翻译",
    "machine translation": "机器翻译",
    "source sentence": "源语言句子",
    "target sentence": "目标语言句子",
    "target word": "目标词",
    "source word": "源词",
    "correct translation": "正确译文",
    "translation performance": "翻译性能",
    "open-domain question answering": "开放域问答",
    "retrieved documents": "检索到的文档",
    "knowledge-intensive tasks": "知识密集型任务",
    "knowledge-intensive nlp": "知识密集型自然语言处理任务",
    "random seeds": "随机种子",
    "random matrix": "随机矩阵",
    "subspace similarity": "子空间相似度",
    "normalized subspace similarity": "归一化子空间相似度",
    "intrinsic rank": "内在秩",
    "downstream task": "下游任务",
    "single forward pass": "单次前向传播",
    "next sentence prediction": "下一句预测",
    "masked language model": "掩码语言模型",
    "question answering": "问答",
    "natural language inference": "自然语言推理",
    "named entity recognition": "命名实体识别",
    "machine translation": "机器翻译",
    "language model": "语言模型",
    "language models": "语言模型",
    "pre-trained model": "预训练模型",
    "pre-training corpus": "预训练语料",
    "word embedding": "词嵌入",
    "word embeddings": "词嵌入",
    "contextual representation": "上下文表示",
    "contextual embeddings": "上下文嵌入",
    "shortcut connection": "捷径连接",
    "shortcut connections": "捷径连接",
    "identity mapping": "恒等映射",
    "degradation problem": "退化问题",
    "plain network": "普通网络",
    "plain networks": "普通网络",
    "residual function": "残差函数",
    "residual mapping": "残差映射",
    "multi-scale testing": "多尺度测试",
    "crop testing": "裁剪测试",
    "error rate": "错误率",
    "error rates": "错误率",
    "object detection": "目标检测",
    "semantic segmentation": "语义分割",
    "image classification": "图像分类",
    "feature map": "特征图",
    "feature maps": "特征图",
    "receptive field": "感受野",
    "batch normalization": "批归一化",
    "layer normalization": "层归一化",
    "skip connection": "跳跃连接",
    "skip connections": "跳跃连接",
    "attention head": "注意力头",
    "attention heads": "注意力头",
    "multi-head attention": "多头注意力",
    "self-attention layer": "自注意力层",
    "positional encoding": "位置编码",
    "positional encodings": "位置编码",
    "encoder layer": "编码器层",
    "decoder layer": "解码器层",
    "beam search": "束搜索",
    "label smoothing": "标签平滑",
    "learning rate": "学习率",
    "learning rate warmup": "学习率预热",
    "warmup steps": "预热步数",
    "training step": "训练步",
    "training steps": "训练步",
    "training data": "训练数据",
    "training set": "训练集",
    "test set": "测试集",
    "development set": "开发集",
    "validation set": "验证集",
    "input and output": "输入与输出",
    "keys and values": "键与值",
    "source and target": "源语言与目标语言",
    "increased depth": "加深的网络",
    "right context": "右侧上下文",
    "left context": "左侧上下文",
    "vocabulary size": "词表规模",
    "computational cost": "计算开销",
    "model size": "模型规模",
    "hyperparameter settings": "超参数设置",
    "projection shortcut": "投影捷径",
    "projection shortcuts": "投影捷径",
    "plain counterpart": "普通对照网络",
    "plain counterparts": "普通对照网络",
    "percentage point": "百分点",
    "percentage points": "百分点",
    "absolute improvement": "绝对提升",
    "point absolute improvement": "个百分点的绝对提升",
    "billion flops": "十亿浮点运算",
    "neural information processing": "神经信息处理",
    "language processing": "语言处理",
    "imagenet localization": "ImageNet 定位",
    "openai gpt": "OpenAI GPT",
}

# A head noun that carries the meaning of a compound; the modifiers only
# narrow it. Used so an unseen compound still gets one consistent rendering
# rather than drifting between two.
_HEADS = {
    "prediction": "预测", "model": "模型", "models": "模型",
    "network": "网络", "networks": "网络", "layer": "层", "layers": "层",
    "connection": "连接", "connections": "连接", "testing": "测试",
    "training": "训练", "dataset": "数据集", "datasets": "数据集",
    "classification": "分类", "detection": "检测", "segmentation": "分割",
    "representation": "表示", "representations": "表示",
    "embedding": "嵌入", "embeddings": "嵌入", "encoding": "编码",
    "encodings": "编码", "attention": "注意力", "function": "函数",
    "mapping": "映射", "rate": "率", "error": "误差", "loss": "损失",
    "corpus": "语料", "vocabulary": "词表", "algorithm": "算法",
    "architecture": "架构", "parameter": "参数", "parameters": "参数",
    "accuracy": "准确率", "performance": "性能", "results": "结果",
    "translation": "翻译", "similarity": "相似度", "rank": "秩",
    "seeds": "种子", "seed": "种子", "task": "任务", "tasks": "任务",
    "documents": "文档", "pass": "传播", "answering": "问答",
}

_MODS = {
    "next": "下一", "sentence": "句", "question": "问", "answering": "答",
    "natural": "自然", "language": "语言", "machine": "机器",
    "translation": "翻译", "masked": "掩码", "pre-trained": "预训练",
    "pretrained": "预训练", "contextual": "上下文", "word": "词",
    "shortcut": "捷径", "identity": "恒等", "residual": "残差",
    "plain": "普通", "multi-scale": "多尺度", "multi": "多",
    "scale": "尺度", "crop": "裁剪", "object": "目标", "semantic": "语义",
    "image": "图像", "feature": "特征", "receptive": "感受", "field": "野",
    "batch": "批", "layer": "层", "skip": "跳跃", "positional": "位置",
    "encoder": "编码器", "decoder": "解码器", "training": "训练",
    "test": "测试", "development": "开发", "validation": "验证",
    "input": "输入", "output": "输出", "keys": "键", "values": "值",
    "source": "源", "target": "目标", "left": "左", "right": "右",
    "context": "上下文", "increased": "加深", "deep": "深层",
    "billion": "十亿", "flops": "浮点运算",
    "random": "随机", "normalized": "归一化", "intrinsic": "内在",
    "downstream": "下游", "retrieved": "检索到的", "forward": "前向",
    "correct": "正确", "statistical": "统计", "neural": "神经",
    "open-domain": "开放域", "knowledge-intensive": "知识密集型",
    "single": "单", "source": "源", "target": "目标",
}


def _render(phrase):
    """Chinese rendering of a compound, or None when it cannot be built.

    Longest known term wins, so "neural machine translation" resolves through
    the seed entry for "machine translation" instead of failing on "neural".
    """
    if not phrase:
        return None
    fixed = TERMS.get(phrase)
    if fixed:
        return fixed
    tokens = phrase.split()
    if not tokens:
        return None
    for span in range(len(tokens), 0, -1):
        for start in range(0, len(tokens) - span + 1):
            head = TERMS.get(" ".join(tokens[start:start + span]))
            if not head:
                continue
            before = "".join(_MODS[t] for t in tokens[:start] if t in _MODS)
            after = "".join(_MODS[t] for t in tokens[start + span:]
                            if t in _MODS)
            if any(t not in _MODS
                   for t in tokens[:start] + tokens[start + span:]):
                continue
            return before + head + after
    head = _HEADS.get(tokens[-1])
    if not head:
        return None
    prefix = "".join(_MODS[t] for t in tokens[:-1] if t in _MODS)
    if not prefix:
        return head
    if any(t not in _MODS for t in tokens[:-1]):
        return None
    return prefix + head


def _compose(phrase):
    """Backwards-compatible name for the head-noun composer."""
    return _render(phrase)


_BROKEN = re.compile(r"(?:^\-|\-$)")


def _is_term(phrase):
    """Whether a repeated phrase is domain vocabulary rather than a word run."""
    if _REF_BOILER.search(phrase) or _BROKEN.search(phrase):
        return False
    tokens = phrase.split()
    if len(tokens) < 2:
        return False
    if all(t in _FUNC for t in tokens):
        return False
    if tokens[0] in _FUNC or tokens[-1] in _FUNC:
        return False
    if tokens[-1] in _ADJ_TAIL or tokens[-1] in _PREP_TAIL:
        return False
    content = [t for t in tokens if len(t) > 3 and t not in _FUNC]
    if not content:
        return False
    # Whatever sits between the content words has to be a modifier or a
    # hyphenated form; "results are presented" is a sentence fragment.
    rest = [t for t in tokens if t not in content]
    if any(t in _FUNC_MIXED or t in _FUNC for t in rest):
        return False
    if not any(t in _HEADS or t in _MODS for t in tokens):
        return False
    return True


def _in_mixed_prose(phrase, segments, ratio=0.5):
    """Whether the phrase sits mostly in prose written in another language.

    A French or German passage appears as ordinary lowercase words, so it can
    pass every shape test; what marks it is that the same span carries several
    tokens that are not English at all.
    """
    total = inside = 0
    for seg in segments:
        text = (seg.get("source") or "").lower()
        low, target = text, phrase.lower()
        start = low.find(target)
        while start != -1:
            total += 1
            window = low[max(0, start - 40):start + len(target) + 40]
            foreign = sum(1 for token in window.split()
                          if any(ch in token for ch in "\u00e0\u00e2\u00e7"
                                 "\u00e8\u00e9\u00ea\u00eb\u00ee\u00ef"
                                 "\u00f4\u00f9\u00fb\u00fc\u00df\u00f1"))
            if foreign >= 2:
                inside += 1
            start = low.find(target, start + 1)
    if total < 2:
        return False
    return inside >= total * ratio


NAME_NOISE = re.compile(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+")


def _inside_name(phrase, segments, limit=6):
    """Whether every occurrence of this phrase sits inside a proper name."""
    seen = 0
    for seg in segments:
        text = seg.get("source") or ""
        low, target = text.lower(), phrase.lower()
        start = low.find(target)
        while start != -1:
            seen += 1
            for hit in NAME_NOISE.finditer(text):
                if hit.start() <= start and start + len(target) <= hit.end():
                    return True
            start = low.find(target, start + 1)
            if seen >= limit:
                return None
    return False if seen else None


REF_MARK = re.compile(r"(?:^\n|\n)(?:\[\d+\]|\d+\.\s*[A-Z])")


def _in_reference_block(phrase, segments, ratio=0.6):
    """Whether this phrase lives mostly in the bibliography."""
    total = inside = 0
    for seg in segments:
        text = seg.get("source") or ""
        marks = [m.start() for m in REF_MARK.finditer(text)]
        low, target = text.lower(), phrase.lower()
        start = low.find(target)
        while start != -1:
            total += 1
            if any(m <= start for m in marks):
                inside += 1
            start = low.find(target, start + 1)
    if total < 2:
        return False
    return inside >= total * ratio


def _glossary(doc, segments):
    """Terms to hold constant, with the pages each appears on."""
    text = " ".join(s["source"] for s in segments).lower()
    rows = []
    for term, chinese in SEED.items():
        hits = len(re.findall(r"\b%s\b" % re.escape(term), text))
        if hits:
            rows.append({"term": term, "rendering": chinese, "count": hits,
                         "source": "seed"})
    # phrases the paper repeats: a multiword term used three or more times is
    # almost always domain vocabulary the reader expects to see translated once
    phrases = {}
    for match in re.finditer(r"\b([a-z][a-z-]+(?:\s+[a-z][a-z-]+){1,2})\b", text):
        phrase = match.group(1)
        if len(phrase) < 10:
            continue
        phrases[phrase] = phrases.get(phrase, 0) + 1
    for phrase, count in sorted(phrases.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < 3 or len(rows) >= 120:
            break
        if any(phrase in r["term"] or r["term"] in phrase for r in rows):
            continue
        if phrase not in TERMS and not _is_term(phrase):
            continue
        if _inside_name(phrase, segments):
            continue
        if _in_reference_block(phrase, segments):
            continue
        if _in_mixed_prose(phrase, segments):
            continue
        row = {"term": phrase, "rendering": None, "count": count,
               "source": "observed"}
        fixed = TERMS.get(phrase)
        if fixed:
            row["rendering"] = fixed
            row["note"] = "领域固定译法"
        else:
            composed = _render(phrase)
            if composed:
                row["rendering"] = composed
                row["note"] = "按中心词组合译法，与同头词术语保持一致"
            else:
                row["note"] = "论文反复使用的多词短语，需在术语表中固定译法后使用"
        rows.append(row)
    rows.sort(key=lambda r: (-r["count"], r["term"]))
    return rows


def _units(segments):
    """The work list handed to the translator, without the source text."""
    return [{"id": s["id"], "page": s["page"], "words": s["words"],
             "sentences": s["sentences"]} for s in segments]


def _citation_map(doc):
    """Each citation marker and where it appears, so none is silently dropped."""
    rows = []
    for page_no, page in enumerate(doc.get("pages") or [], 1):
        for match in CITE.finditer(page):
            rows.append({"marker": match.group(0), "page": page_no})
    return rows[:200]


def _numbers_index(segments):
    """Numbers and units that must survive translation unchanged."""
    rows = []
    for seg in segments:
        values = NUM.findall(seg["source"])
        if values:
            rows.append({"id": seg["id"], "page": seg["page"],
                         "values": sorted(set(values))[:20]})
    return rows


def _brief(doc, segments, glossary):
    """The instructions the translator works under, derived from this paper."""
    meta = doc.get("meta") or {}
    return {
        "source_title": meta.get("title"),
        "source_language": "en",
        "target_language": "zh",
        "segment_total": len(segments),
        "rules": [
            "逐段翻译：每条 SEG 对应一段，不合并、不拆分、不省略。",
            "术语按 glossary 的 rendering 固定；标注 rendering 为 null 的，"
            "先确定译法再在 audit 中登记，全篇不得出现两种译法。",
            "数字、单位、百分比、模型名、数据集名原样保留，不改写不换单位。",
            "引用标记 [n] 原样保留在译文中对应位置。",
            "公式符号、变量名、代码标识符不翻译。",
            "译文句序可调整以符合中文表达，但因果、条件、对比关系不得改变。",
            "原文没有的内容不增补；原文含糊处保留含糊并在 audit 中标注。",
        ],
    }


def _audit_template():
    """What the translator must report back, so the audit has something to check."""
    return {
        "required_fields": ["id", "page", "translation"],
        "optional_fields": ["terms_used", "notes", "uncertain"],
        "notes": "按 segments 的 id 逐条回填；无法翻译的条目保留 id 并在 notes 写明原因，"
                 "不要删除条目。",
    }


def _honest_gaps(bundle, doc, segments, glossary):
    if not segments:
        bundle.gap(item="可译段落", reason="未从材料中切出长度合格的段落",
                   field="segments", state="not_reported")
        return
    undecided = [g for g in glossary if not g.get("rendering")]
    if undecided:
        bundle.gap(item="待定术语",
                   reason="%d 条论文自有多词短语尚无固定译法，需先定术语再统一全文"
                          % len(undecided), field="glossary", state="uncertain")
    stats = doc.get("stats") or {}
    if stats.get("chars", 0) and len(segments) < 5:
        bundle.gap(item="段落切分", reason="全文 %d 字符但只切出 %d 段，"
                   "可能是扫描件或版式异常，段落边界需人工核对"
                   % (stats["chars"], len(segments)),
                   field="segments", state="uncertain")
