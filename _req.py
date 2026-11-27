"""The request layer has only been exercised by "Parse the paper and summarise it.".
Build realistic task.md cases, including ones the Skill cannot answer, so the
coverage layer is checked where it matters: telling answered work from absent
work instead of always reporting success."""
import io
import json
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(ROOT, ".t", "req")
PAPER = os.path.join(ROOT, ".t", "input", "paper.pdf")

CASES = [
    ("title-authors", "Extract the title, authors, and affiliations. Output JSON."),
    ("refs", "List every reference with its year and count them."),
    ("section3", "Translate section 3 into Chinese."),
    ("table2", "Which table reports the ablation on Table 2?"),
    ("hyperparams", "What batch size and learning rate were used for training?"),
    ("figures", "How many figures does the paper contain?"),
    ("cjk", "\u8bf7\u628a\u7b2c 4 \u8282\u8bd1\u6210\u4e2d\u6587\uff0c\u5e76\u8bf4\u660e\u8868 2 \u7684\u7ed3\u679c\u3002"),
    ("abstract", "Summarise the abstract in three sentences, then give the DOI."),
]


def write_case(name, task):
    folder = os.path.join(BASE, name)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    shutil.copy2(PAPER, os.path.join(folder, "paper.pdf"))
    with io.open(os.path.join(folder, "task.md"), "w", encoding="utf-8", newline="") as handle:
        handle.write(task + "\n")
    case = {"case_id": name, "output_contract": {
        "paper_title": "string", "reference_count": "number"}}
    with io.open(os.path.join(folder, "case.json"), "w", encoding="utf-8", newline="") as handle:
        json.dump(case, handle, ensure_ascii=False, indent=2)


def main():
    for name, task in CASES:
        write_case(name, task)
    print("cases: %d in %s" % (len(CASES), BASE))
    for name, task in CASES:
        print("  %-14s %s" % (name, task[:56]))


if __name__ == "__main__":
    main()
