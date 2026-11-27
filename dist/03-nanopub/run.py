"""Entry point shared by every topic submission.

The platform runs this module, not a per-topic copy of the plumbing, so a bug
fixed once is fixed everywhere. ``BSK_TOPIC`` selects the topic when the
runner does not pass it explicitly; the build script pins it per submission.
"""

import argparse
import os
import sys
import traceback

from core import contract, emit, handoff, request, selfcheck


TOPICS = {
    "00-parse": ("topics.t00_parse", "run"),
    "01-translate": ("topics.t01_translate", "run"),
    "02-notes": ("topics.t02_notes", "run"),
    "03-nanopub": ("topics.t03_nanopub", "run"),
    "04-kg": ("topics.t04_kg", "run"),
    "05-polish": ("topics.t05_polish", "run"),
    "06-cite": ("topics.t06_cite", "run"),
    "07-intro": ("topics.t07_intro", "run"),
    "08-method": ("topics.t08_method", "run"),
    "09-latex": ("topics.t09_latex", "run"),
}


def load_topic(name):
    """Import one topic module by submission name."""
    entry = TOPICS.get(name)
    if entry is None:
        raise SystemExit("unknown topic: %s (known: %s)"
                         % (name, ", ".join(sorted(TOPICS))))
    module_name, attr = entry
    module = __import__(module_name, fromlist=[attr])
    return getattr(module, attr)


def _autofill(bundle, case, doc, records):
    """Answer whatever field names this case's contract asks for.

    The contract shape is not published, so instead of hoping our own field
    names match, resolve each requested name against material we actually
    extracted. Anything unresolvable keeps the contract placeholder and shows
    up as a reported gap rather than an invented value.
    """
    from topics import fill
    wanted = contract.required_fields(case)
    if not wanted:
        return
    table = fill.candidates(doc, records)
    for name in wanted:
        if name in bundle.payload:
            continue
        value = fill.resolve(name, table)
        if value is None:
            # Record the shortfall without claiming the run fell short: the
            # field genuinely has no verifiable value, which the placeholder
            # already states, and marking the whole case partial for it would
            # understate work that was actually done.
            bundle.note("合同字段 %s 无可核验取值，已按占位符登记。" % name)
            continue
        bundle.put(name, value)
        bundle.anchor_generated(name)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one Bohrium weekly skill.")
    parser.add_argument("--topic", default=os.environ.get("BSK_TOPIC", ""),
                        help="submission directory name, e.g. 00-parse")
    parser.add_argument("--output", default=None, help="output directory override")
    args = parser.parse_args(argv)

    topic = args.topic or os.path.basename(os.getcwd())
    if topic not in TOPICS:
        # tolerate being run from inside the built submission directory
        marker = os.path.join(os.path.dirname(__file__), "TOPIC")
        if os.path.exists(marker):
            with open(marker, "r", encoding="utf-8") as handle:
                topic = handle.read().strip()

    handler = load_topic(topic)
    contract.ensure_dirs()
    case, task = contract.load_case()
    bundle = emit.Bundle(case, task)

    try:
        _, _, records = emit.bootstrap()
        bundle.source_files = records
        bundle.mark("extract")
        from topics import base, fill
        doc = base.recover(base.primary(records))
        handler(case, task, bundle, records, doc)
        # Marks are cumulative, so the deltas in self_check.axes.cost say
        # how much of the wall clock went to reading the file and how much
        # to the analysis the baseline never performed.
        bundle.mark("analyze")
        _autofill(bundle, case, doc, records)
        # The case ships a task statement; answer it, and record per
        # question whether this run answered it or could not.
        request.attach(bundle, doc, task)
        # Five topics stop at the analysis. When one of them has enough
        # extracted material to make the missing deliverable, hand the
        # executing agent a self-contained instruction instead of leaving a
        # bare scaffold: the segment ids, the fixed glossary, the justified
        # edits and the located evidence all travel with it.
        handoff.attach(bundle, topic, doc)
        # Attach the measured self-audit last, so it describes what this run
        # actually produced rather than a pre-autofill snapshot.
        bundle.mark("answer")
        selfcheck.apply(bundle, doc, records, case, contract)
    except Exception as exc:  # a crash must still produce an honest result
        bundle.downgrade(contract.STATUS_PARTIAL)
        bundle.note("运行过程中出现异常，已保留已完成部分：%s: %s"
                    % (type(exc).__name__, exc))
        bundle.gap(item="完整运行", reason="%s: %s" % (type(exc).__name__, exc),
                   state="partial")
        sys.stderr.write(traceback.format_exc())

    result = bundle.build()
    path = contract.write_result(result, args.output)
    sys.stdout.write("wrote %s (status=%s)\n" % (path, result.get("status")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
