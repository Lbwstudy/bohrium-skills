"""Simulate the platform contract end to end.

The evaluator does four things we can copy exactly: it drops the Skill into a
directory, points the input at /input, points the output at /app/output, and
runs the entry point named in environment/resources.yaml. Everything else here
is a check that what we ship survives that shape rather than only our own
convenience layout.
"""
import io
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
TOPICS = ["00-parse", "01-translate", "02-notes", "03-nanopub", "04-kg",
          "05-polish", "06-cite", "07-intro", "08-method", "09-latex"]
REQUIRED = ["case_id", "status", "result", "evidence", "sources",
            "uncertainty", "changes", "notes"]


def read_yaml_paths(path):
    """Pull the entry_point path and the declared input/output paths."""
    lines = io.open(path, encoding="utf-8").read().split("\n")
    entry, outputs, inputs = None, [], []
    section = None
    for line in lines:
        stripped = line.strip()
        if stripped in ("entry_point:", "inputs:", "outputs:"):
            section = stripped.rstrip(":")
            continue
        if section == "entry_point" and stripped.startswith("path:"):
            entry = stripped.split(":", 1)[1].strip()
        elif section == "outputs" and stripped.startswith("- path:"):
            outputs.append(stripped.split(":", 1)[1].strip())
        elif section == "inputs" and stripped.startswith("- path:"):
            inputs.append(stripped.split(":", 1)[1].strip())
        if stripped and not stripped.startswith("-") and stripped.endswith(":") \
                and stripped not in ("entry_point:", "inputs:", "outputs:"):
            section = None
    return entry, inputs, outputs


def main():
    stage = os.path.join(ROOT, ".t", "sim3")
    shutil.rmtree(stage, ignore_errors=True)
    source_input = os.path.join(ROOT, ".t", "input")
    problems = []

    for topic in TOPICS:
        home = os.path.join(stage, topic)
        submission = os.path.join(home, "app", "submission")
        shutil.copytree(os.path.join(ROOT, "dist", topic), submission)
        out = os.path.join(home, "app", "output")
        os.makedirs(out, exist_ok=True)

        yaml_path = os.path.join(submission, "environment", "resources.yaml")
        entry, inputs, outputs = read_yaml_paths(yaml_path)
        if not entry:
            problems.append("%s: resources.yaml has no entry_point.path" % topic)
            continue
        target = os.path.normpath(os.path.join(submission, "environment", entry))
        if not os.path.isfile(target):
            problems.append("%s: entry_point resolves nowhere: %s" % (topic, entry))
            continue
        for declared in outputs:
            if not declared.endswith("result.json"):
                problems.append("%s: unexpected output %s" % (topic, declared))

        env = dict(os.environ)
        env["BSK_INPUT_DIR"] = source_input
        env["BSK_OUTPUT_DIR"] = out
        env["BSK_WORK_DIR"] = os.path.join(home, "app", "work")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PATH"] = os.path.join(ROOT, ".t", "texbin") + os.pathsep + env.get("PATH", "")
        run = subprocess.run([PY, target, "--topic", topic], cwd=os.path.dirname(target),
                             env=env, capture_output=True, timeout=900)
        result_path = os.path.join(out, "result.json")
        if run.returncode != 0:
            problems.append("%s: exit %d %s" % (topic, run.returncode,
                                                run.stderr.decode("utf-8", "replace")[-200:]))
            continue
        if not os.path.isfile(result_path):
            problems.append("%s: no result.json at the declared output path" % topic)
            continue
        payload = json.load(io.open(result_path, encoding="utf-8"))
        missing = [key for key in REQUIRED if key not in payload]
        if missing:
            problems.append("%s: result.json missing %s" % (topic, ", ".join(missing)))
        for extra in ("self_check", "request_coverage_summary"):
            if extra not in payload["result"]:
                problems.append("%s: result lacks %s" % (topic, extra))
        trace = run.stderr.decode("utf-8", "replace")
        if "Traceback" in trace:
            problems.append("%s: traceback on stderr" % topic)
        print("%-13s rc=%d status=%-16s keys=%d" % (topic, run.returncode,
                                                    payload.get("status"),
                                                    len(payload.get("result") or {})))

    if problems:
        print("\nproblems: %d" % len(problems))
        for line in problems:
            print(" -", line)
        return 1
    print("\nclean: all ten run from the declared entry point and write the declared output")
    return 0


if __name__ == "__main__":
    sys.exit(main())
