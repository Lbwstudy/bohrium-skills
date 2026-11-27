"""Result assembly with status discipline.

The topic rubric scores "结果可核验性" and "异常处理" separately. Both fail the
same way in practice: a good-looking answer that quietly invents the parts it
could not read. This module makes the honest path the shortest path, so a
Skill cannot accidentally ship a confident guess.

Every emitted bundle separates three things the rubric wants kept apart:
what the material supports, what it does not, and why the run ended as it did.
"""

import json
import os
import time

from . import contract as _contract
from . import evidence as _evidence

STATUS_OK = _contract.STATUS_OK
STATUS_PARTIAL = _contract.STATUS_PARTIAL
STATUS_UNKNOWN = _contract.STATUS_UNKNOWN
STATUS_REFUSED = _contract.STATUS_REFUSED


class Bundle(object):
    """Accumulates one run's findings, anchors and gaps."""

    def __init__(self, case=None, task=""):
        self.case = case or {}
        self.task = task or ""
        self.payload = {}
        self.anchors = []
        self.gaps = []
        self.changes = []
        self.notes = []
        self.artifacts = []
        self.source_files = []
        self._status = STATUS_OK
        self._started = time.time()
        self.marks = []

    # -- findings -----------------------------------------------------------

    def put(self, field, value, anchor=None, note=None):
        """Record one contract field together with the material that backs it."""
        entry = value
        if anchor is not None:
            entry = value
            self.anchors.append({"field": field, "anchor": anchor})
        self.payload[field] = entry
        if note:
            self.notes.append({"field": field, "note": note})
        return entry

    def put_unanchored(self, field, value, reason):
        """Record a value the material does not let us anchor, and say so."""
        self.payload[field] = value
        self.gaps.append({"field": field, "state": "unanchored", "reason": reason})
        self.downgrade(STATUS_PARTIAL)
        return value

    def anchor_generated(self, field):
        """Mark a field as derived from the document structure, not from a quote.

        Autofilled contract fields are read out of the extracted layout, so no
        verbatim span exists to point at. Recording that explicitly keeps the
        provenance honest without pretending the value is unsupported.
        """
        self.anchors.append({
            "field": field,
            "anchor": {"found": True, "kind": "derived",
                       "reason": "derived_from_extracted_structure"},
        })

    def gap(self, item, reason, field=None, state="not_reported"):
        """Record something the material does not answer."""
        row = {"item": item, "reason": reason, "state": state}
        if field:
            row["field"] = field
        self.gaps.append(row)
        return row

    def refuse(self, field, reason):
        row = self.gap(field, reason, state="cannot_determine")
        self.payload[field] = {"value": None, "state": "cannot_determine",
                               "reason": reason}
        self.downgrade(STATUS_UNKNOWN)
        return row

    def change(self, kind, before, after, where=None, reason=None):
        row = {"kind": kind, "before": before, "after": after}
        if where:
            row["where"] = where
        if reason:
            row["reason"] = reason
        self.changes.append(row)
        return row

    def note(self, text):
        self.notes.append({"note": text})

    def artifact(self, name, path):
        # Keep the recorded location relative to the output directory. An
        # absolute or run-relative host path would differ between two runs of
        # the same input and would tell a reader nothing that `name` does not.
        shown = path
        base = os.path.abspath(_contract.OUTPUT_DIR)
        try:
            absolute = os.path.abspath(path)
            if absolute == base or absolute.startswith(base + os.sep):
                shown = os.path.relpath(absolute, base).replace(os.sep, "/")
        except (OSError, ValueError):
            shown = path
        self.artifacts.append({"name": name, "path": shown})

    # -- status -------------------------------------------------------------

    RANK = {STATUS_OK: 0, STATUS_PARTIAL: 1, STATUS_UNKNOWN: 2, STATUS_REFUSED: 3}

    def downgrade(self, status):
        if self.RANK.get(status, 0) > self.RANK.get(self._status, 0):
            self._status = status

    def status(self):
        if self.gaps and self._status == STATUS_OK:
            return STATUS_PARTIAL
        return self._status

    def elapsed(self):
        return round(time.time() - self._started, 3)

    def mark(self, name):
        """Cumulative seconds at the end of a named stage.

        Cumulative, not incremental, so a stage that raises still leaves a
        usable number behind for the stages that did finish.
        """
        self.marks.append({"name": name, "seconds": self.elapsed()})

    def phases(self):
        """Seconds spent in each stage, derived from the cumulative marks.

        Returns an empty dict when nothing was marked, so a caller that
        never opted in does not have to special-case the output.
        """
        out = {}
        previous = 0.0
        for item in self.marks:
            spent = round(item["seconds"] - previous, 3)
            out[item["name"]] = spent if spent > 0 else 0.0
            previous = item["seconds"]
        return out

    # -- assembly -----------------------------------------------------------

    def uncertainty(self):
        rows = list(self.gaps)
        for item in self.anchors:
            anchor = item.get("anchor") or {}
            if not anchor.get("found", False):
                rows.append({
                    "field": item.get("field"),
                    "state": "unverified",
                    "reason": anchor.get("reason", "anchor_missing"),
                })
        return rows

    def build(self, extra_note=None):
        payload = dict(self.payload)
        payload.setdefault("run", {
            "status": self.status(),
            "elapsed_seconds": self.elapsed(),
            "artifacts": self.artifacts,
        })
        notes = [n.get("note") if isinstance(n, dict) else str(n)
                 for n in self.notes]
        if extra_note:
            notes.append(extra_note)
        wanted = _contract.required_fields(self.case)
        missing = []
        for name in wanted:
            value = payload.get(name)
            if value is None:
                missing.append(name)                       # placeholder added later
            elif isinstance(value, dict) and value.get("state") == "not_reported":
                missing.append(name)
        notes.append(_contract.status_reason(self.status(), missing=missing))
        result = _contract.make_result(
            self.case,
            self.status(),
            payload,
            evidence=self.anchors,
            uncertainty=self.uncertainty(),
            sources=self._sources(),
            changes=self.changes,
            notes=notes,
        )
        return result

    def _sources(self):
        """Which files the run actually read, and what each one contributed.

        The rubric asks for the source of every claim, so the list names the
        input files themselves. An anchor only contributes a row when it points
        at a real location; a structural anchor has no file span and is not a
        source.
        """
        rows = []
        for item in self.source_files:
            rows.append({"name": item.get("rel") or item.get("path"),
                         "kind": "material",
                         "backend": item.get("backend"),
                         "bytes": item.get("size")})
        for item in self.artifacts:
            rows.append({"name": item["name"], "kind": "artifact"})
        for anchor in self.anchors:
            data = anchor.get("anchor") or {}
            if data.get("found") and data.get("path"):
                rows.append({"name": data.get("path"), "kind": "material",
                             "page": data.get("page")})
        seen = set()
        out = []
        for row in rows:
            key = (row.get("name"), row.get("page"))
            if key in seen or not row.get("name"):
                continue
            seen.add(key)
            out.append(row)
        return out

    def write(self, output_dir=None):
        return _contract.write_result(self.build(), output_dir)


def quote_anchor(bundle, field, quote, records, value=None):
    """Anchor ``quote`` to the material and store it under ``field``.

    When the quote cannot be located the value is still recorded, but marked
    unanchored, so the run downgrades to partial instead of overclaiming.
    """
    anchor = _evidence.locate(quote, records)
    payload_value = value if value is not None else quote
    if anchor.get("found"):
        bundle.put(field, payload_value, anchor=anchor)
    else:
        bundle.put_unanchored(field, payload_value,
                              "引文未能在输入材料中逐字定位")
    return anchor


def finish(bundle, output_dir=None, extra_files=None):
    """Write ``result.json`` plus any text artifacts, and return the payload."""
    for name, text in (extra_files or {}).items():
        path = _contract.write_artifact(text, name, output_dir)
        bundle.artifact(name, path)
    path = bundle.write(output_dir)
    return bundle.build(), path


def bootstrap():
    """Prepare runtime directories and return ``(case, task, records)``."""
    _contract.ensure_dirs()
    case, task = _contract.load_case()
    from . import textio as _textio
    records = _textio.load_all()
    return case, task, records
