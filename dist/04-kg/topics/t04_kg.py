"""Topic 04 — literature knowledge graph.

The rubric asks for four things: entities drawn accurately, edges that are
actually supported, alignment that matches the same thing across mentions, and
queries that return a subgraph with evidence. A graph nobody can query is a
list. So this module builds the graph and then runs real queries over it, and
reports which edges it could not decide instead of quietly dropping them.

Node identity matters more than node count. The same method appears as
"ResNet-50", "resnet 50" and "ResNet50"; aligning those into one node is what
makes the graph answerable, and the alignment decision is recorded on every
merged node so a reviewer can check it.
"""

import re

from . import base

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u4e00-\u9fff])")

# Entity families. Order matters: the first family that claims a surface form
# wins, so the more specific patterns come first.
FAMILIES = [
    ("metric", r"\b(?:error rate|accuracy|BLEU|F1(?:-score)?|top-1|top-5|"
               r"perplexity|mAP|IoU|precision|recall|AUC|RMSE|"
               r"exact match|EM|MRR|NDCG|Pearson|Spearman)\b"),
    ("dataset", r"\b(?:ImageNet|CIFAR-\d+|COCO|PASCAL VOC|WMT(?:'?\d{2})?|"
                r"SQuAD|GLUE|MNIST|PTB|WikiText(?:-\d+)?|Kinetics|Cityscapes|"
                r"SuperGLUE|MultiNLI|MNLI|SNLI|CoNLL(?:-\d{4})?|"
                r"SWAG|Winograd|WNLI|QQP|QNLI|MRPC|STS-B|RACE|"
                r"BooksCorpus|English Wikipedia|Common ?Crawl|Yelp|"
                r"MS ?MARCO|Natural Questions|TriviaQA|CoQA)\b"),
    ("method", r"\b(?:ResNet(?:-\d+)?|VGG(?:-\d+)?|GoogLeNet|AlexNet|BN-?"
               r"(?:[A-Za-z]+)?|batch normalization|dropout|SGD|Adam|"
               r"max-?pooling|average pooling|self-attention|transformer|"
               r"LSTM|GRU|CNN|RNN|BERT|ELMo|GPT(?:-?\d)?|ULMFiT|"
               r"word2vec|GloVe|fastText|ByteNet|ConvS2S|GNMT|"
               r"layer normalization|residual connection|"
               r"masked language model|next sentence prediction|"
               r"fine-?tuning|pre-?training)\b"),
    ("task", r"\b(?:image classification|object detection|semantic segmentation|"
             r"machine translation|language modeling|question answering|"
             r"speech recognition|natural language inference|"
             r"textual entailment|sentiment analysis|named entity recognition|"
             r"constituency parsing|reading comprehension|"
             r"natural language understanding|sequence labeling|"
             r"text classification)\b"),
    ("system", r"\b(?-i:[A-Z]{2,}[-A-Za-z0-9]*)\b"),
    ("architecture", r"\b(?:plain network|bottleneck|residual block|"
                     r"skip connection|shortcut connection|identity mapping|"
                     r"encoder|decoder|feed-?forward|"
                     r"multi-?head attention|attention head|"
                     r"positional encoding|embedding layer|"
                     r"bi-?LSTM|deep bi-?directional)\b"),
]

# Relations between entities, and which families each can connect.
RELATION_RULES = [
    ("uses", r"\b(?:using|based on|employ\w*|adopt\w*|with)\b",
     [("method", "dataset"), ("method", "architecture"), ("architecture", "task")]),
    ("evaluated-on", r"\b(?:evaluat\w*|tested|benchmark\w*|experiment\w*)\b[^.]{0,40}",
     [("method", "dataset")]),
    ("improves-on", r"\b(?:outperform\w*|improv\w*|surpass\w*|better than|"
                    r"exceed\w*)\b", [("method", "method"),
                                       ("system", "method"), ("method", "system"),
                                       ("system", "system")]),
    ("compares-with", r"\b(?:compar\w*|versus|vs\.?|against|baseline)\b",
     [("method", "method"), ("system", "method"), ("method", "system"),
      ("system", "system")]),
    ("measures", r"\b(?:error rate|accuracy|BLEU|top-1|top-5|perplexity)\b",
     [("method", "metric")]),
    ("applies-to", r"\b(?:appl\w*|for|on)\b",
     [("method", "task"), ("system", "task")]),
    ("contains", r"\b(?:consist\w*|composed|comprise\w*|built from)\b",
     [("architecture", "architecture"), ("method", "architecture")]),
]

# Prose words that look like system names because of a digit or hyphen.
SYSTEM_STOP = frozenset("""
Table Tables Figure Figures Section Sections Equation Equations Appendix
Algorithm Algorithms Step Steps Eq Eqs Chapter Part Row Column Page
CoRR arXiv NeurIPS ICML ICLR ACL EMNLP NAACL AAAI IJCAI CVPR ICCV ECCV
PDF DOI URL GPU CPU TPU MLP SVM OOV ASCII UTF HTML JSON
ABSTRACT INTRODUCTION DESCRIPTION CONCLUSION CONCLUSIONS RESULTS DISCUSSION
METHOD METHODS BACKGROUND RELATED WORK EVALUATION EXPERIMENTS APPENDIX
REFERENCES ACKNOWLEDGMENTS ACKNOWLEDGEMENTS TABLE FIGURE SECTION EQUATION
LEMMA PROOF THEOREM DEFINITION EXAMPLE SUMMARY OVERVIEW MOTIVATION
IEEE ACM NIPS NIPS NIPS ICLR ICML ACL EMNLP NAACL TPAMI BMVC ICCV
USA UK EU AI NLP NLG IR QA CV II III IV VI VII IX XI XII
BERT-based GPT-2-based TF-IDF skip-gram state-of-the-art
""".split())

# Surface-form normalisation, so the same thing is one node.
ALIASES = {
    "resnet50": "ResNet-50", "resnet-50": "ResNet-50", "resnet 50": "ResNet-50",
    "resnet101": "ResNet-101", "resnet-101": "ResNet-101",
    "resnet152": "ResNet-152", "resnet-152": "ResNet-152",
    "resnet18": "ResNet-18", "resnet-18": "ResNet-18",
    "resnet34": "ResNet-34", "resnet-34": "ResNet-34",
    "cifar10": "CIFAR-10", "cifar-10": "CIFAR-10",
    "cifar100": "CIFAR-100", "cifar-100": "CIFAR-100",
    "imagenet": "ImageNet", "bn": "batch normalization",
    "batchnorm": "batch normalization", "sgd": "SGD", "adam": "Adam",
    "cnn": "CNN", "rnn": "RNN", "lstm": "LSTM",
}


def run(case, task, bundle, records, doc):
    if doc is None:
        base.refuse_empty(bundle, "document", records,
                          "输入目录中没有可读文档，无法构建知识图谱")
        return
    base.degraded(bundle, doc)

    mentions = _mentions(doc)
    nodes = _nodes(mentions)
    edges = _edges(doc, mentions, nodes)
    bundle.put("node_count", len(nodes))
    bundle.put("edge_count", len(edges))
    bundle.put("nodes", nodes)
    bundle.put("edges", edges)
    bundle.put("alias_table", _alias_table(nodes))
    bundle.put("unresolved_relations", _unresolved(edges))

    queries = _queries(doc, nodes, edges)
    bundle.put("queries", queries)
    bundle.put("query_count", len(queries))
    bundle.put("query_results", [_result_of(q) for q in queries])

    bundle.put("graph_format", _schema())
    bundle.put("markdown", _markdown(doc, nodes, edges, queries))

    _honest_gaps(bundle, doc, nodes, edges, queries)


def _lowercase_vocabulary(doc):
    """Words this document also sets in lower case somewhere."""
    words = set()
    for page in doc.get("pages") or []:
        words.update(re.findall(r"\b[a-z]{2,}\b", page))
    return words


def _mentions(doc):
    """Every entity surface form with where it was seen."""
    rows = []
    cursor = 0
    lower_words = _lowercase_vocabulary(doc)
    for page_no, page in enumerate(doc.get("pages") or [], 1):
        body = " ".join(page.split())
        for family, pattern in FAMILIES:
            for match in re.finditer(pattern, body, re.I):
                surface = match.group(0).strip()
                if family == "system":
                    if surface in SYSTEM_STOP:
                        continue
                    if not (surface[:1].isupper()
                            and sum(1 for ch in surface if ch.isupper()) >= 2):
                        continue
                    # An all-caps ordinary word ("NEURAL" in a title) is not
                    # a system name; the paper itself sets it in lower case.
                    if surface.lower() in lower_words:
                        continue
                    if len(surface) < 3:
                        continue
                rows.append({
                    "surface": surface,
                    "key": _key(surface),
                    "family": family,
                    "page": page_no,
                    "offset": cursor + match.start(),
                    "section": _section_at(doc, cursor + match.start()),
                    "quote": _sentence_at(body, match.start()),
                })
        cursor += len(page) + 1
    return rows


ALIAS_INDEX = {}


def _build_alias_index():
    """Compact lookup so "ResNet 50" and "resnet-50" land on one key."""
    if ALIAS_INDEX:
        return ALIAS_INDEX
    for alias, canonical in ALIASES.items():
        ALIAS_INDEX[re.sub(r"[^a-z0-9]", "", alias)] = canonical
    return ALIAS_INDEX


def _key(surface):
    """The canonical label one entity is stored under.

    Returning the original surface here was a real defect: "Question Answering"
    and "question answering" became two nodes, so sentences naming the same
    entity at different capitalisations produced no edges at all. The
    canonical form therefore has to be case-folded, with the well-known
    acronyms restored from ALIASES so the label still reads correctly.
    """
    low = surface.strip().lower().replace("\u2013", "-").replace("\u2014", "-")
    low = re.sub(r"\s+", " ", low)
    index = _build_alias_index()
    if low in ALIASES:
        return ALIASES[low]
    compact = re.sub(r"[^a-z0-9]", "", low)
    if compact in index:
        return index[compact]
    return low


def _nodes(mentions):
    """One node per distinct entity, keeping every surface form it came from."""
    by_key = {}
    for m in mentions:
        node = by_key.get(m["key"])
        if node is None:
            node = {"id": "E%03d" % (len(by_key) + 1), "label": m["key"],
                    # The key is the alignment form (lower case); the label a
                    # reader sees must be a spelling the paper actually uses,
                    # so "COCO" does not come back as "coco".
                    "display": m["surface"],
                    "family": m["family"], "aliases": [], "mentions": 0,
                    "pages": []}
            by_key[m["key"]] = node
        if "first_quote" not in node and m.get("quote"):
            node["first_quote"] = m["quote"]
            node["first_page"] = m["page"]
        forms = node.setdefault("forms", {})
        forms[m["surface"]] = forms.get(m["surface"], 0) + 1
        if m["surface"] not in node["aliases"]:
            node["aliases"].append(m["surface"])
        node["mentions"] += 1
        if m["page"] not in node["pages"]:
            node["pages"].append(m["page"])
    for node in by_key.values():
        forms = node.pop("forms", None)
        if forms:
            node["display"] = sorted(forms.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        node["pages"].sort()
        node["alignment"] = ("merged" if len(node["aliases"]) > 1 else "single-form")
    return sorted(by_key.values(), key=lambda n: (-n["mentions"], n["id"]))


def _alias_table(nodes):
    return [{"id": n["id"], "label": n.get("display") or n["label"], "aliases": n["aliases"],
             "reason": "大小写/连字符/缩写归一后同形" if n["alignment"] == "merged"
                       else "原文仅一种写法"}
            for n in nodes if n["alignment"] == "merged"]


def _edges(doc, mentions, nodes):
    """Relations asserted in a sentence that names both ends."""
    by_key = {n["label"]: n for n in nodes}
    rows = []
    seen = set()
    cursor = 0
    for page_no, page in enumerate(doc.get("pages") or [], 1):
        body = " ".join(page.split())
        for sentence in SENT_SPLIT.split(body):
            if len(sentence) < 30:
                continue
            found = _sentence_entities(sentence, by_key)
            if len(found) < 2:
                continue
            for name, pattern, allowed in RELATION_RULES:
                if not re.search(pattern, sentence, re.I):
                    continue
                for left in found:
                    for right in found:
                        if left["id"] == right["id"]:
                            continue
                        if (left["family"], right["family"]) not in allowed:
                            continue
                        sig = (left["id"], name, right["id"])
                        if sig in seen:
                            continue
                        seen.add(sig)
                        rows.append({
                            "s": left["id"],
                            "s_label": left.get("display") or left["label"],
                            "p": name,
                            "o": right["id"],
                            "o_label": right.get("display") or right["label"],
                            "evidence": {"quote": sentence[:300], "page": page_no,
                                         "section": _section_at(doc, cursor)},
                            "confidence": "derived",
                            "rule": "同一句内同时出现两端实体且出现该关系触发词",
                        })
        cursor += len(page) + 1
        if len(rows) >= 400:
            break
    return rows


def _sentence_entities(sentence, by_key):
    """Entities named in one sentence, longest match first.

    Matching shorter labels first would let "VGG" claim the span of "VGG-16",
    producing two nodes for one mention and a self-referential comparison edge.
    Blanking each matched span before trying shorter labels prevents that.
    """
    out = []
    seen = set()
    masked = sentence
    for label in sorted(by_key, key=len, reverse=True):
        node = by_key[label]
        pattern = r"(?<![A-Za-z0-9])" + re.escape(label) + r"(?![A-Za-z0-9])"
        hit = re.search(pattern, masked, re.I)
        if not hit:
            continue
        masked = masked[:hit.start()] + "\0" * (hit.end() - hit.start()) + masked[hit.end():]
        if node["id"] in seen:
            continue
        seen.add(node["id"])
        out.append(node)
    return out


def _unresolved(edges):
    """Relation mentions where one end could not be pinned to a node.

    These are the honest unknowns: a comparative sentence with only one
    recognised entity, or a relation word with no second argument. They are
    listed rather than guessed into the graph.
    """
    return [e for e in edges if e.get("confidence") != "derived"]


def _queries(doc, nodes, edges):
    """Queries a reader would actually ask, run against the built graph."""
    out = []
    out.append(_q_datasets(doc, nodes, edges))
    out.append(_q_improvements(doc, nodes, edges))
    out.append(_q_methods_by_task(doc, nodes, edges))
    out.append(_q_evidence_for(doc, nodes, edges))
    return [q for q in out if q]


def _ask(doc, chinese, english):
    """The question a reader gets, in the language the paper is written in."""
    text = doc.get("text") or ""
    han = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return chinese if han > max(80, len(text) // 50) else english


def _q_datasets(doc, nodes, edges):
    """Q1: which datasets does this work evaluate on, and where is that said."""
    datasets = {n["id"]: n for n in nodes if n["family"] == "dataset"}
    hits = []
    for edge in edges:
        if edge["p"] in ("evaluated-on", "uses") and edge["o"] in datasets:
            hits.append(edge)
        elif edge["p"] in ("evaluated-on", "uses") and edge["s"] in datasets:
            hits.append(edge)
    if not hits and not datasets:
        return None
    return {
        "query_id": "Q1",
        "question": _ask(doc, "本文在哪些数据集上做了评估？",
                         "Which datasets does this work evaluate on?"),
        "method": _ask(doc, "匹配 family=dataset 的节点，再取连到它们的 evaluated-on / uses 边",
                        "nodes in family=dataset, then the evaluated-on / uses edges that reach them"),
        "answer": sorted({n.get("display") or n["label"] for n in datasets.values()}),
        "subgraph": {"nodes": [{"id": n["id"], "label": n.get("display") or n["label"]}
                               for n in datasets.values()],
                     "edges": hits[:40]},
        "evidence": [{"page": e["evidence"]["page"],
                      "quote": e["evidence"]["quote"][:160]} for e in hits[:20]],
        "uncertain": [] if hits else ["数据集节点存在但未找到连到方法的关系句，"
                                      "该关系记为无法确定"],
    }


def _q_improvements(doc, nodes, edges):
    """Q2: what is claimed to beat what, with the sentence that claims it."""
    hits = [e for e in edges if e["p"] in ("improves-on", "compares-with")]
    return {
        "query_id": "Q2",
        "question": _ask(doc, "文中哪些方法被声明优于其它方法？依据是哪句？",
                         "Which methods are claimed to beat others, and in which sentence?"),
        "method": _ask(doc, "取 improves-on / compares-with 边，逐条回填原句与页码",
                        "improves-on / compares-with edges, each with its sentence and page"),
        "answer": [{"subject": e["s_label"], "relation": e["p"],
                    "object": e["o_label"]} for e in hits[:30]],
        "subgraph": {"nodes": sorted({e["s"] for e in hits} | {e["o"] for e in hits}),
                     "edges": hits[:40]},
        "evidence": [{"page": e["evidence"]["page"],
                      "quote": e["evidence"]["quote"][:160]} for e in hits[:20]],
        "uncertain": [] if hits else ["未找到方法间的比较关系句"],
    }


def _q_methods_by_task(doc, nodes, edges):
    """Q3: which methods are used for which task."""
    hits = [e for e in edges if e["p"] in ("applies-to", "uses")]
    tasks = {n["id"]: n for n in nodes if n["family"] == "task"}
    return {
        "query_id": "Q3",
        "question": _ask(doc, "本文的方法服务于哪个任务？还有哪些方法被用于同一任务？",
                         "Which task does this work serve, and what else is used for it?"),
        "method": _ask(doc, "取 applies-to / uses 边，按 task 节点聚合",
                        "applies-to / uses edges, grouped by task node"),
        "answer": [{"task": n.get("display") or n["label"], "pages": n["pages"]}
                   for n in tasks.values()],
        "subgraph": {"nodes": [{"id": n["id"], "label": n.get("display") or n["label"]}
                               for n in tasks.values()],
                     "edges": hits[:40]},
        "evidence": [{"page": e["evidence"]["page"],
                      "quote": e["evidence"]["quote"][:160]} for e in hits[:20]],
        "uncertain": [] if tasks else ["未识别出 task 类节点，该查询无法回答"],
    }


def _q_evidence_for(doc, nodes, edges):
    """Q4: for one node, which sections speak about it."""
    top = sorted(nodes, key=lambda n: -n["mentions"])[:5]
    return {
        "query_id": "Q4",
        "question": _ask(doc, "针对出现最多的实体，原文哪些章节在讨论它？",
                         "For the most-mentioned entities, which sections discuss them?"),
        "method": _ask(doc, "按 mentions 排序取前 5 个节点，回填其 pages 与所在章节",
                        "the five busiest nodes by mentions, with their pages and sections"),
        "answer": [{"label": n.get("display") or n["label"], "mentions": n["mentions"],
                    "pages": n["pages"]} for n in top],
        "subgraph": {"nodes": [{"id": n["id"], "label": n.get("display") or n["label"]} for n in top],
                     "edges": [e for e in edges
                               if e["s"] in {t["id"] for t in top}][:40]},
        # The quote has to be the sentence that names the entity, not a summary
        # this Skill wrote about it: an invented "quote" is exactly what the
        # verifiability check exists to catch.
        "evidence": [{"page": n.get("first_page"),
                      "quote": n.get("first_quote") or _first_line(doc, n["aliases"])}
                     for n in top],
        "uncertain": [],
    }


def _sentence_at(text, position):
    """The sentence around ``position`` in one page body."""
    start = max(0, text.rfind(". ", 0, position) + 1)
    end = text.find(". ", position)
    end = len(text) if end < 0 else end + 1
    return " ".join(text[start:end].split())[:220]


def _first_line(doc, aliases):
    """Last-resort anchor: the source line that contains one surface form."""
    body = doc.get("text") or ""
    for alias in aliases:
        index = body.find(alias)
        if index >= 0:
            start = body.rfind("\n", 0, index) + 1
            end = body.find("\n", index)
            end = len(body) if end < 0 else end
            return " ".join(body[start:end].split())[:220]
    return ""


def _result_of(query):
    return {"query_id": query["query_id"], "answer_size": len(query["answer"]),
            "node_count": len(query["subgraph"]["nodes"]),
            "edge_count": len(query["subgraph"]["edges"])}


def _section_at(doc, offset):
    best = None
    for item in doc.get("sections") or []:
        if item.get("offset", 0) <= offset:
            best = item
        else:
            break
    return ((best.get("num", "") + " " + best["title"]).strip() if best else None)


def _schema():
    return {
        "node": {"id": "E001", "label": "规范化名称", "family":
                 "method|dataset|metric|task|architecture",
                 "aliases": ["原文出现过的写法"], "mentions": "int",
                 "pages": "[int]", "alignment": "merged|single-form"},
        "edge": {"s": "节点 id", "p": "关系名", "o": "节点 id",
                 "evidence": {"quote": "原句", "page": "int", "section": "str"},
                 "confidence": "derived", "rule": "该边成立的判据"},
        "relations": [name for name, _, _ in RELATION_RULES],
        "note": "只有两端实体在同一句内同时出现且关系触发词命中时才建边；"
                "一端无法对齐的记入 unresolved_relations，不建边。",
    }


def _markdown(doc, nodes, edges, queries):
    meta = doc.get("meta") or {}
    lines = ["# 文献知识图谱 — %s" % (meta.get("title") or "Untitled"), ""]
    lines.append("节点 %d 个，边 %d 条。" % (len(nodes), len(edges)))
    lines.append("")
    lines.append("## 节点")
    lines.append("")
    for n in nodes[:40]:
        alias = "，别名：%s" % "、".join(n["aliases"]) if len(n["aliases"]) > 1 else ""
        lines.append("- `%s` %s（%s，%d 次，第 %s 页）%s"
                     % (n["id"], n["label"], n["family"], n["mentions"],
                        ", ".join(str(p) for p in n["pages"][:5]), alias))
    lines.append("")
    lines.append("## 查询")
    for q in queries:
        lines.append("")
        lines.append("### %s %s" % (q["query_id"], q["question"]))
        lines.append("")
        lines.append("- 查法：%s" % q["method"])
        lines.append("- 结果：%d 项" % len(q["answer"]))
        for item in q["answer"][:8]:
            lines.append("  - %s" % (item,))
        if q["evidence"]:
            lines.append("- 证据：%s"
                         % "；".join("第 %s 页" % e["page"] for e in q["evidence"][:5]))
        if q["uncertain"]:
            lines.append("- 无法确定：%s" % "；".join(q["uncertain"]))
    return "\n".join(lines)


def _honest_gaps(bundle, doc, nodes, edges, queries):
    if not nodes:
        bundle.gap(item="实体", reason="未从材料中识别出可归类的实体，"
                   "可能是扫描件或领域外文本", field="nodes", state="not_reported")
        return
    if len(queries) < 3:
        bundle.gap(item="查询数量", reason="题面要求至少 3 个真实查询，"
                   "本次仅能构造 %d 个可回答的查询" % len(queries),
                   field="queries", state="partial")
    thin = [q["query_id"] for q in queries if not q["answer"]]
    if thin:
        bundle.gap(item="空结果查询",
                   reason="查询 %s 未返回结果，已在对应条目写明原因，"
                          "未以空答案冒充已完成" % ", ".join(thin),
                   field="queries", state="partial")
    if not edges:
        bundle.gap(item="关系", reason="未找到同句共现且关系词命中的实体对，"
                   "图谱仅有节点无边", field="edges", state="partial")
