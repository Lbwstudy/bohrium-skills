"""Pre-flight: does the pushed tree actually run?

The last push shipped ten Skills whose `core/selfcheck.py` was never tracked by
git, so no file was uploaded and every submission would have died on import.
Local green runs could not catch it: the file existed on disk. This check works
on a clean export of what git would send, and runs one Skill from it.
"""
import ast
import collections
import io
import os
import shutil
import subprocess
import sys
import tempfile

PY = sys.executable
STAGE = os.path.join(".t", "shipped")


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def shadowed(paths):
    """Top-level names defined more than once in one module.

    The last binding wins, so an earlier fix silently stops running. That cost
    a full debugging round on core/request.py's _cjk_terms.
    """
    out = []
    for rel in paths:
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse(io.open(rel, encoding="utf-8").read())
        except SyntaxError as exc:
            out.append("%s: cannot parse (%s)" % (rel, exc))
            continue
        names = collections.Counter(
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)))
        for name, count in sorted(names.items()):
            if count > 1:
                out.append("%s: %s defined %d times" % (rel, name, count))
    return out


def main():
    paths = tracked()
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(STAGE)

    # Copy exactly what git tracks, mirroring the push.
    for rel in paths:
        dst = os.path.join(STAGE, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(rel, dst)

    # Every module a shipped Skill imports must exist in that copy.
    problems = []
    for topic in sorted(os.listdir(os.path.join(STAGE, "dist"))):
        core = os.path.join(STAGE, "dist", topic, "core")
        topics = os.path.join(STAGE, "dist", topic, "topics")
        for folder in (core, topics):
            if not os.path.isdir(folder):
                problems.append("%s: missing %s" % (topic, os.path.basename(folder)))
        for name in ("selfcheck.py", "contract.py", "emit.py", "structure.py",
                     "textio.py", "evidence.py"):
            if not os.path.exists(os.path.join(core, name)):
                problems.append("%s: core/%s not in tree" % (topic, name))
        entry = os.path.join(topics, "t%s_%s.py" % (topic.split("-")[0], {
            "parse": "parse", "translate": "translate", "notes": "notes",
            "nanopub": "nanopub", "kg": "kg", "polish": "polish",
            "cite": "cite", "intro": "intro", "method": "method",
            "latex": "latex"}[topic.split("-")[1]]))
        if not os.path.exists(entry):
            problems.append("%s: %s not in tree" % (topic, os.path.basename(entry)))

    # Run one Skill from the staged copy, the way the platform would.
    out = os.path.join(STAGE, "_out")
    os.makedirs(out, exist_ok=True)
    run = subprocess.run(
        [PY, "run.py"],
        cwd=os.path.join(STAGE, "dist", "00-parse"),
        env=dict(os.environ,
                 BSK_INPUT_DIR=os.path.abspath(os.path.join(".t", "input")),
                 BSK_OUTPUT_DIR=os.path.abspath(out),
                 PYTHONIOENCODING="utf-8"),
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if run.returncode != 0:
        problems.append("staged run exited %d: %s"
                        % (run.returncode, (run.stderr or "")[-300:]))
    result = os.path.join(out, "result.json")
    if not os.path.exists(result):
        problems.append("staged run produced no result.json")
    else:
        text = io.open(result, encoding="utf-8").read()
        if "self_check" not in text:
            problems.append("staged result has no self_check block")
        if "Traceback" in (run.stderr or ""):
            problems.append("staged run wrote a traceback: %s" % run.stderr[-300:])

    for item in shadowed(paths):
        problems.append(item)

    print("tracked files: %d" % len(paths))
    if problems:
        print("PROBLEMS")
        for item in problems:
            print(" -", item)
        return 1
    print("clean: every shipped module is tracked, and the staged copy runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
