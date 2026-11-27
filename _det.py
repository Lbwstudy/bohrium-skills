"""Determinism check: two runs of the same input must agree on everything except
the four timing fields. Those are named here rather than skipped by a wildcard,
so a new nondeterministic field cannot hide behind the excuse."""
import io
import json
import sys

TIMERS = ("elapsed_seconds", "seconds_headroom", "words_per_second")
# Whole subtrees that hold timing: phase_seconds maps a stage name to
# seconds. Stage names are ordinary words, so skip the subtree by its
# parent key instead of listing "extract"/"analyze"/"answer" as timers.
TIMED_SUBTREES = ("phase_seconds",)


def strip(node):
    if isinstance(node, dict):
        return dict((k, strip(v)) for k, v in node.items()
                    if k not in TIMERS and k not in TIMED_SUBTREES)
    if isinstance(node, list):
        return [strip(v) for v in node]
    return node


def load(path):
    return strip(json.load(io.open(path, encoding="utf-8")))


def walk(a, b, path=""):
    out = []
    if type(a) is not type(b):
        return ["TYPE %s %s %s" % (path, type(a).__name__, type(b).__name__)]
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append("MISSING %s.%s" % (path, key))
            else:
                out.extend(walk(a[key], b[key], path + "." + key))
    elif isinstance(a, list):
        if len(a) != len(b):
            return ["LEN %s %d %d" % (path, len(a), len(b))]
        for index, (left, right) in enumerate(zip(a, b)):
            out.extend(walk(left, right, "%s[%d]" % (path, index)))
    elif a != b:
        out.append("DIFF %s %r | %r" % (path, a, b))
    return out


def main():
    left, right = sys.argv[1], sys.argv[2]
    diffs = walk(load(left), load(right))
    if not diffs:
        print("identical outside %s"
          % ", ".join(TIMERS + TIMED_SUBTREES))
        return 0
    for line in diffs[:40]:
        print(line)
    print("differences: %d" % len(diffs))
    return 1


if __name__ == "__main__":
    sys.exit(main())
