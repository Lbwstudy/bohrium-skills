"""Build one submission directory per topic.

The platform copies a submission directory to `/app/submission` and runs the
Skill there, so each directory must be self-contained: the shared kernel is
vendored in, the entry point names its own topic, and nothing points back at
this repository layout.

File count matters. The rubric caps a submission at 50 UTF-8 text files, so the
build measures what it produced and fails loudly rather than shipping something
the evaluator will reject.
"""

import argparse
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")

CORE_MODULES = ["__init__.py", "contract.py", "textio.py", "evidence.py",
                "emit.py", "structure.py", "selfcheck.py", "handoff.py", "request.py",
                "pdfcore.py"]  # stdlib-only fallback when no PDF tool exists
TOPIC_MODULES = ["__init__.py", "base.py", "fill.py"]
TOPIC_FILES = {
    "00-parse": "t00_parse.py",
    "01-translate": "t01_translate.py",
    "02-notes": "t02_notes.py",
    "03-nanopub": "t03_nanopub.py",
    "04-kg": "t04_kg.py",
    "05-polish": "t05_polish.py",
    "06-cite": "t06_cite.py",
    "07-intro": "t07_intro.py",
    "08-method": "t08_method.py",
    "09-latex": "t09_latex.py",
}

# Modules a topic imports but is not itself named after. Forgetting one ships a
# submission that raises ImportError at run time, so the build copies these too.
TOPIC_SUPPORT = {
    "05-polish": ["t05_support.py"],
}

MAX_FILES = 50
MAX_FILE_BYTES = 500 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024

GITHUB_FILE = "GITHUB_URL.txt"

# The submission root must carry a GITHUB_URL.txt whose first line is the public
# link and whose second line points at this topic inside that repository. One
# repository holds all ten submissions, so the link has to land on the topic
# directory itself: the rubric awards the point only when the reviewer reaches
# the work without signing in.
GITHUB_BASE = os.environ.get("BSK_GITHUB_BASE",
                             "https://github.com/Lbwstudy/bohrium-skills")

GITHUB_HINT = ("第 2 行起为该题作品在本仓库中的位置（相对仓库根）。"
               "评审可直接打开上面的链接，无需登录。")


def github_url(topic, base=None):
    """Deep link to one topic inside the repository."""
    return "%s/tree/main/dist/%s" % ((base or GITHUB_BASE).rstrip("/"), topic)


# The evaluator reads the resource entry point from environment/resources.yaml.
# Every path in it is relative to that directory, so the entries stay valid no
# matter where the submission is unpacked.
RESOURCES = """\
# Resource entry point for this submission.
# Paths are resolved relative to the directory holding this file
# (environment/), so "../run.py" is the submission's entry point.

entry_point:
  path: ../run.py
  language: python
  runtime: ">=3.8"
  command: "python ../run.py --topic {topic}"
  note: >-
    Pure standard-library Python. No third-party package is required, and no
    network access is performed.

skill:
  path: ../SKILL.md
  format: "YAML frontmatter + Markdown body"

inputs:
  - path: /input/case.json
    required: true
    description: case identifier and optional output_contract
  - path: /input/task.md
    required: false
    description: the task statement for this case
  - path: /input/
    required: true
    description: >-
      source material (PDF / DOCX / HTML / Markdown / TXT, or .tex and .bib for
      the LaTeX topic); any readable file in this directory is considered

outputs:
  - path: /app/output/result.json
    required: true
    description: >-
      fixed keys case_id / status / result / evidence / sources / uncertainty /
      changes / notes

working_directory: /app/work

determinism:
  seeds: none
  network: false
  clock: false
  note: >-
    Output depends only on the input files and on no external state. Repeating
    the same input reproduces the same findings, evidence and status. The only
    fields that vary between runs are the timing ones (run.elapsed_seconds and
    the elapsed_seconds / seconds_headroom / words_per_second entries of
    self_check.axes.cost), which record how long this machine took.
"""


def _copy_tree(src_dir, dst_dir, names=None):
    os.makedirs(dst_dir, exist_ok=True)
    copied = []
    for name in (names or sorted(os.listdir(src_dir))):
        if not name.endswith(".py"):
            continue
        src = os.path.join(src_dir, name)
        dst = os.path.join(dst_dir, name)
        shutil.copyfile(src, dst)
        copied.append(dst)
    return copied


def build(topic, skill_text, clean=True):
    """Assemble one submission directory and return its path."""
    target = os.path.join(DIST, topic)
    if clean and os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target, exist_ok=True)

    copies = []
    copies += _copy_tree(os.path.join(ROOT, "core"),
                         os.path.join(target, "core"), CORE_MODULES)
    copies += _copy_tree(os.path.join(ROOT, "topics"),
                         os.path.join(target, "topics"), TOPIC_MODULES)
    topic_src = os.path.join(ROOT, "topics", TOPIC_FILES[topic])
    topic_dst = os.path.join(target, "topics", TOPIC_FILES[topic])
    shutil.copyfile(topic_src, topic_dst)
    copies.append(topic_dst)

    for name in TOPIC_SUPPORT.get(topic, []):
        src = os.path.join(ROOT, "topics", name)
        dst = os.path.join(target, "topics", name)
        shutil.copyfile(src, dst)
        copies.append(dst)

    shutil.copyfile(os.path.join(ROOT, "run.py"), os.path.join(target, "run.py"))
    copies.append(os.path.join(target, "run.py"))

    with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8",
              newline="\n") as handle:
        handle.write(skill_text)
    copies.append(os.path.join(target, "SKILL.md"))

    with open(os.path.join(target, "TOPIC"), "w", encoding="utf-8",
              newline="\n") as handle:
        handle.write(topic + "\n")
    copies.append(os.path.join(target, "TOPIC"))

    env_dir = os.path.join(target, "environment")
    os.makedirs(env_dir, exist_ok=True)
    resources_path = os.path.join(env_dir, "resources.yaml")
    with open(resources_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(RESOURCES.replace("{topic}", topic))
    copies.append(resources_path)

    with open(os.path.join(target, GITHUB_FILE), "w", encoding="utf-8",
              newline="\n") as handle:
        handle.write(github_url(topic) + "\n" + GITHUB_HINT + "\n")
    copies.append(os.path.join(target, GITHUB_FILE))

    return target, copies


def check_imports(target):
    """Fail if a copied module imports a sibling the build did not copy.

    A missing sibling only shows up as ImportError when the evaluator runs the
    Skill, which is the worst place to find out. Relative imports are resolved
    statically here instead.
    """
    pattern = re.compile(r"^\s*from\s+\.\s*import\s+(.+)$", re.M)
    pattern_mod = re.compile(r"^\s*from\s+\.([A-Za-z_]\w*)\s+import", re.M)
    problems = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        pkg = os.path.relpath(dirpath, target).replace("\\", "/")
        if pkg == ".":
            continue
        available = {n[:-3] for n in filenames if n.endswith(".py")}
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(dirpath, name), "r", encoding="utf-8",
                      errors="replace") as handle:
                source = handle.read()
            wanted = set()
            for group in pattern.findall(source):
                for part in group.split(","):
                    token = part.strip().split()
                    if token:
                        wanted.add(token[0])
            wanted.update(pattern_mod.findall(source))
            for want in sorted(wanted):
                if want and want not in available:
                    problems.append("%s/%s imports missing %s"
                                    % (pkg, name, want))
    return problems


def measure(target):
    """Report submission size against the platform's resource caps.

    A bytecode cache is a hard failure, not something to skip. The directory
    measured here is the directory that gets submitted, so a leftover
    __pycache__ from a local test run would be uploaded too. The run loop must
    therefore execute outside the submission tree, or clean up afterwards.
    """
    files = []
    total = 0
    problems = []
    for dirpath, dirnames, filenames in os.walk(target):
        for cache in [d for d in dirnames if d == "__pycache__"]:
            problems.append("bytecode cache present: %s"
                            % os.path.relpath(os.path.join(dirpath, cache), target))
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in sorted(filenames):
            if name.endswith(".pyc"):
                problems.append("bytecode file present: %s"
                                % os.path.relpath(os.path.join(dirpath, name), target))
                continue
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                raise SystemExit("symlink not allowed: %s" % full)
            size = os.path.getsize(full)
            rel = os.path.relpath(full, target).replace("\\", "/")
            files.append({"path": rel, "bytes": size})
            total += size
    if len(files) > MAX_FILES:
        problems.append("%d files > %d" % (len(files), MAX_FILES))
    for item in files:
        if item["bytes"] > MAX_FILE_BYTES:
            problems.append("%s is %d bytes > %d"
                            % (item["path"], item["bytes"], MAX_FILE_BYTES))
    if total > MAX_TOTAL_BYTES:
        problems.append("total %d bytes > %d" % (total, MAX_TOTAL_BYTES))
    return {"files": len(files), "total_bytes": total, "problems": problems,
            "detail": files}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build one topic submission.")
    parser.add_argument("topic", choices=sorted(TOPIC_FILES))
    parser.add_argument("--check", action="store_true",
                        help="only report size, do not rebuild")
    args = parser.parse_args(argv)

    target = os.path.join(DIST, args.topic)
    if not args.check:
        skill_path = os.path.join(ROOT, "skills", args.topic, "SKILL.md")
        if not os.path.exists(skill_path):
            raise SystemExit("missing SKILL.md: %s" % skill_path)
        with open(skill_path, "r", encoding="utf-8") as handle:
            skill_text = handle.read()
        target, _ = build(args.topic, skill_text)

    report = measure(target)
    sys.stdout.write("%s: %d files, %d bytes\n"
                     % (args.topic, report["files"], report["total_bytes"]))
    for problem in report["problems"]:
        sys.stdout.write("  FAIL %s\n" % problem)
    for problem in check_imports(target):
        sys.stdout.write("  FAIL %s\n" % problem)
        report["problems"].append(problem)
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
