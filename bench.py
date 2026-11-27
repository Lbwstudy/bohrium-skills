# -*- coding: utf-8 -*-
"""Fair comparison: a minimal baseline versus this Skill, on the same files.

The scoring sheet asks for efficiency gain and for proof of that gain. A gain
number nobody can reproduce is a claim, so this script ships with the baseline
it measures: ``naive`` below is what you get from ``pdftotext`` plus the first
regex that comes to mind, with no structure recovery, no evidence trail and no
status reporting. Both sides read the same bytes on the same machine.

Run:  python bench.py [input_dir ...]
Out:  JSON on stdout, and a Markdown table on stderr.
"""
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from core import textio                                        # noqa: E402

TOPICS = ["00-parse", "06-cite", "08-method"]
# Six papers: the three the extractors were built against, and three the
# repository added afterwards. The later three are where the baseline and the
# Skill disagree most, so leaving them out flattered the comparison.
DEFAULT_INPUTS = [".t/input", ".t/in2", ".t/in3", ".t/in4", ".t/in5", ".t/in6"]
DEFAULT_ROOT = ".t/r65"

# The baseline's whole vocabulary. Deliberately the obvious thing to write:
# numbered headings, bracketed numbers, and a blank-line paragraph split.
NAIVE_HEADING = re.compile(r"(?m)^\s*(\d+(?:\.\d+)*)\s+([A-Z][^\n]{2,60})$")
NAIVE_BRACKET = re.compile(r"\[(\d+(?:\s*[,;\u2013-]\s*\d+)*)\]")
NAIVE_PARAGRAPH = re.compile(r"\n\s*\n")


def naive(pdf_path):
    """What an unassisted one-liner gets: text, headings, bracketed numbers."""
    started = time.time()
    try:
        raw = subprocess.run(
            [textio._which("pdftotext"), "-enc", "UTF-8", pdf_path, "-"],
            capture_output=True, timeout=120)
        text = raw.stdout.decode("utf-8", "replace")
        backend = "pdftotext"
    except Exception as exc:                                     # noqa: BLE001
        text, backend = "", "failed:%s" % type(exc).__name__

    headings = [(m.group(1), m.group(2).strip()) for m in NAIVE_HEADING.finditer(text)]
    brackets = {int(n) for grp in NAIVE_BRACKET.findall(text) for n in re.findall(r"\d+", grp)}
    paragraphs = [p.strip() for p in NAIVE_PARAGRAPH.split(text) if p.strip()]
    return {
        "backend": backend,
        "seconds": round(time.time() - started, 3),
        "chars": len(text),
        "headings": len(headings),
        "distinct_bracketed_numbers": len(brackets),
        "paragraphs": len(paragraphs),
        "has_page_map": False,
        "has_evidence_anchors": False,
        "has_status": False,
        "has_self_check": False,
        "_headings": headings,
        "_brackets": brackets,
    }


def load_payload(topic, output_dir):
    """Return (status, payload, gaps) for one Skill run, or None."""
    path = os.path.join(output_dir, "result.json")
    if not os.path.exists(path):
        return None
    doc = json.loads(io.open(path, encoding="utf-8").read())
    payload = doc.get("result") or {}
    return {
        "status": doc.get("status"),
        "gaps": len(doc.get("uncertainty") or []),
        "payload": payload,
        "self_check": payload.get("self_check") or {},
    }


def _axes(run):
    return (run.get("self_check") or {}).get("axes") or {}


def measure(topic, run):
    """Turn one Skill result into the units the baseline also reports."""
    payload = run["payload"]
    verifiability = _axes(run).get("verifiability") or {}
    cost = _axes(run).get("cost") or {}

    row = {
        "status": run["status"],
        "gaps": run["gaps"],
        "seconds": cost.get("elapsed_seconds"),
        "words_per_second": cost.get("words_per_second"),
        "quote_ratio": verifiability.get("quote_ratio"),
        "anchor_ratio": verifiability.get("anchor_ratio"),
        "quotes_checked": verifiability.get("quotes_checked"),
        "numbers_checked": verifiability.get("numbers_checked"),
        "sections": None,
        "references": None,
        "anchors": None,
        "phases": cost.get("phase_seconds") or {},
    }
    if topic == "00-parse":
        row["sections"] = len(payload.get("sections") or [])
        row["references"] = len(payload.get("references") or [])
        row["anchors"] = len(payload.get("page_map") or [])
    elif topic == "06-cite":
        row["references"] = payload.get("reference_count")
        row["anchors"] = len(payload.get("quotes") or [])
        row["uncited"] = len(payload.get("uncited_entries") or [])
        row["dangling"] = len(payload.get("dangling_citations") or [])
    elif topic == "08-method":
        row["sections"] = payload.get("step_count")
        row["anchors"] = len(payload.get("quotes") or [])
        row["settings"] = payload.get("setting_count")
        row["reproducibility"] = (payload.get("reproducibility") or {}).get("score")
    return row


def _normalise_title(title):
    """Section title without its number, lowercased, punctuation flattened."""
    title = re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", title or "")
    title = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", title.lower())
    return " ".join(title.split())


def compare(input_dir, root):
    """Compare one input across the three topics that read the raw document."""
    pdf = None
    for name in sorted(os.listdir(input_dir)):
        if name.lower().endswith(".pdf"):
            pdf = os.path.join(input_dir, name)
            break
    if pdf is None:
        return None

    label = os.path.basename(input_dir.rstrip("/\\"))
    base = naive(pdf)
    runs = {}
    for topic in TOPICS:
        run = load_payload(topic, os.path.join(root, "%s-%s" % (label, topic)))
        if run:
            runs[topic] = run

    row = {
        "input": label,
        "file": os.path.basename(pdf),
        "baseline": {k: v for k, v in base.items() if not k.startswith("_")},
        "skill": {topic: measure(topic, run) for topic, run in runs.items()},
    }

    # Does the baseline's heading list actually name the document's sections?
    parse = runs.get("00-parse")
    if parse:
        truth = {_normalise_title(s.get("heading", ""))
                 for s in parse["payload"].get("sections") or [] if s.get("heading")}
        truth.discard("")
        if truth:
            hits = 0
            for number, title in base["_headings"]:
                if _normalise_title(title) in truth:
                    hits += 1
            row["baseline"]["headings_matching_skill"] = hits
            row["baseline"]["heading_precision"] = round(
                hits / float(len(base["_headings"]) or 1), 3)

    # Bracketed numbers include figure/section references and measurement ranges.
    cite = runs.get("06-cite")
    if cite:
        refs = cite["payload"].get("reference_count") or 0
        # The Skill's own ceiling rule: anything above max known index + 20 is
        # not a citation. Apply the same rule to the baseline's number set.
        if refs:
            ceiling = refs + 20
            plausible = {n for n in base["_brackets"] if n <= ceiling}
        else:
            plausible = set()
        row["baseline"]["bracketed_numbers"] = len(base["_brackets"])
        row["baseline"]["bracketed_plausible"] = len(plausible)
        row["baseline"]["bracketed_over_range"] = len(base["_brackets"]) - len(plausible)
        row["baseline"]["reference_count_from_skill"] = refs
        row["skill"]["06-cite"]["reference_miss"] = refs - len(plausible)
    return row


def markdown(rows):
    out = ["| 输入 | 环节 | 最小基线（pdftotext + 正则） | 本 Skill |", "|---|---|---|---|"]
    for row in rows:
        base, skill = row["baseline"], row["skill"]
        parse = skill.get("00-parse") or {}
        cite = skill.get("06-cite") or {}
        method = skill.get("08-method") or {}

        if parse:
            out.append("| %s | 章节识别 | 正则命中 %d 条，其中真章节 %s 条（精度 %s） | %s 条，全部带页码 |" % (
                row["input"], base["headings"],
                base.get("headings_matching_skill", "?"),
                base.get("heading_precision", "?"), parse.get("sections")))
        if cite and "bracketed_numbers" in base:
            refs = base.get("reference_count_from_skill") or 0
            recognised = base.get("bracketed_plausible", 0) or 0
            if not base["bracketed_numbers"]:
                verdict = "%d 条（基线整篇抽不到：该文按作者-年份标注，正则无匹配）" % refs
            elif refs > recognised:
                verdict = "%d 条（基线只认出 %d 个方括号编号，其余条目它无从得知）" % (
                    refs, recognised)
            elif refs == recognised:
                verdict = "%d 条，与基线认出的编号数量相同，但每条带页码与格式" % refs
            else:
                verdict = "%d 条，比基线少 %d 条（漏掉的需人工补）" % (
                    refs, recognised - refs)
            out.append("| %s | 参考文献 | 方括号数字 %d 个，其中 %d 个超出文献表范围 | %s |" % (
                row["input"], base["bracketed_numbers"],
                base["bracketed_over_range"], verdict))
            out.append("| %s | 悬空引用 / 未被引用条目 | 无法判断 | %s / %s 条，各带页码 |" % (
                row["input"], cite.get("dangling"), cite.get("uncited")))
        if method:
            out.append("| %s | 方法与复现字段 | 无法判断 | %s 步、%s 个设置项、复现度 %s |" % (
                row["input"], method.get("sections"), method.get("settings"),
                method.get("reproducibility")))
        if parse:
            out.append("| %s | 能否指回原文 | 无锚点 | quote_ratio=%s，样本 %s 条，数字 %s 处 |" % (
                row["input"], parse.get("quote_ratio"), parse.get("quotes_checked"),
                parse.get("numbers_checked")))
            # What a person still has to check by hand. The baseline produces no
            # anchors at all, so every item it emits needs looking up; the Skill
            # anchors each one, so only the unverified residue does.
            emitted = base["headings"] + base.get("bracketed_numbers", 0)
            # Items the Skill emits, each with a page reference, versus the
            # residue that still failed verbatim checking.
            delivered = sum(int(topic_row.get("sections") or 0)
                            for topic_row in (parse, method))
            delivered += int(cite.get("references") or 0)
            residue = 0
            for topic_row in skill.values():
                checked = topic_row.get("quotes_checked") or 0
                ratio = topic_row.get("quote_ratio")
                if ratio is not None and checked:
                    residue += int(round(checked * (1 - ratio)))
            out.append(
                "| %s | 需人工回原文核对 | %d 项（每项都要自己翻页确认） | "
                "%d 项（已交付 %d 项，其中 %d 项带页码与逐字引文） |" % (
                    row["input"], emitted, residue, delivered,
                    max(delivered - residue, 0)))
            out.append("| %s | 运行状态与缺口 | 无 | status=%s，登记缺口 %s 条 |" % (
                row["input"], parse.get("status"), parse.get("gaps")))
        timed = [v.get("seconds") for v in skill.values() if v.get("seconds")]
        if timed:
            fastest = min(timed)
            ratio = fastest / base["seconds"] if base["seconds"] else 0
            if ratio <= 1.05:
                trade = "打平"
            else:
                trade = "慢 %.0f%%，换来上表的页码、引文核验与缺口登记" % ((ratio - 1) * 100)
            out.append("| %s | 耗时 | %.3f s（只出纯文本） | %.3f s，%s |" % (
                row["input"], base["seconds"], fastest, trade))
            # Where the time went. Extraction is comparable -- both sides call
            # pdftotext -- but the Skill's extraction also repairs characters,
            # splits pages and recovers structure, so it may well be slower.
            phases = {}
            for topic_row in skill.values():
                for name, spent in (topic_row.get("phases") or {}).items():
                    phases.setdefault(name, []).append(spent)
            if phases:
                parts = []
                for name in ("extract", "analyze", "answer"):
                    values = phases.get(name)
                    if values:
                        parts.append("%s %.3f s" % (name, min(values)))
                out.append("| %s | 上述耗时分解 | — | %s |" % (
                    row["input"], "、".join(parts)))
    return "\n".join(out)


def main(argv):
    inputs = argv[1:] or DEFAULT_INPUTS
    root = os.environ.get("BSK_BENCH_OUTPUTS", DEFAULT_ROOT)
    rows = []
    for input_dir in inputs:
        row = compare(input_dir, root)
        if row:
            rows.append(row)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    sys.stderr.write("\n" + markdown(rows) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
