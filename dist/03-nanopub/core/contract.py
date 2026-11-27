"""Runtime contract adapter.

The platform ships a per-case ``output_contract`` whose exact shape is not
published. Rather than guessing a schema that would silently miss required
fields, this module discovers the contract at run time and guarantees the
emitted ``result.json`` carries every field it names.

Discovery is structural, not positional: any object key matching a known
contract alias is treated as the contract, and the required field names are
pulled out of whatever container form that key holds (list of strings, list
of objects, or JSON-Schema ``properties``).
"""

import json
import os
import re

CONTRACT_KEYS = (
    "output_contract",
    "outputContract",
    "output-contract",
    "result_contract",
    "resultContract",
    "expected_output",
    "expectedOutput",
    "output_fields",
    "outputFields",
    "deliverable_contract",
    "required_fields",
)

INPUT_DIR = os.environ.get("BSK_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("BSK_OUTPUT_DIR", "/app/output")
WORK_DIR = os.environ.get("BSK_WORK_DIR", "/app/work")

STATUS_OK = "success"
STATUS_PARTIAL = "partial"
STATUS_UNKNOWN = "cannot_determine"
STATUS_REFUSED = "refusal"


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def load_case(input_dir=None):
    """Return ``(case_dict, task_text)``; both empty when the input is absent."""
    base = input_dir or INPUT_DIR
    case = {}
    raw = _read_text(os.path.join(base, "case.json"))
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            case = parsed
        elif parsed is not None:
            case = {"case": parsed}
        else:
            case = {"_unparsed_case_json": raw[:2000]}
    else:
        case = {}
    task = _read_text(os.path.join(base, "task.md"))
    if not task.strip():
        for alt in ("task.txt", "README.md", "instructions.md"):
            task = _read_text(os.path.join(base, alt))
            if task.strip():
                break
    return case, task


def case_id(case):
    for key in ("case_id", "caseId", "id", "case", "name"):
        val = case.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, (int, float)):
            return str(val)
    return "unknown-case"


def _flatten_names(node, out, depth=0):
    """Collect field names from any reasonable contract container shape."""
    if depth > 6 or node is None:
        return
    if isinstance(node, str):
        name = node.strip()
        if name and len(name) < 80 and re.fullmatch(r"[\w.\[\]\- /]{1,80}", name):
            out.append(name)
        return
    if isinstance(node, list):
        for item in node:
            _flatten_names(item, out, depth + 1)
        return
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for key in props:
                out.append(key)
            return
        for key in ("fields", "required", "items", "keys", "columns",
                    "output_fields", "schema", "properties"):
            if key in node:
                _flatten_names(node[key], out, depth + 1)
        if not any(k in node for k in ("fields", "required", "items", "keys",
                                       "columns", "output_fields", "schema",
                                       "properties", "type", "description")):
            # an inline field map: {"summary": "...", "quotes": "..."}
            for key in node:
                out.append(key)


def find_contract(case):
    """Locate the output contract and return its raw value, or ``None``."""
    if not isinstance(case, dict):
        return None
    for key in CONTRACT_KEYS:
        if key in case and case[key]:
            return case[key]
    # one level down, for case files that nest the payload
    for key, val in case.items():
        if isinstance(val, dict):
            for alias in CONTRACT_KEYS:
                if alias in val and val[alias]:
                    return val[alias]
    if isinstance(case.get("schema"), dict):
        return case["schema"]
    return None


def required_fields(case):
    """Ordered, de-duplicated list of field names the contract demands."""
    contract = find_contract(case)
    names = []
    _flatten_names(contract, names)
    seen = set()
    ordered = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def _placeholder(field):
    return {
        "value": None,
        "state": "not_reported",
        "note": ("该字段在本次运行的可用材料中没有可核验取值，"
                 "按可核验性要求留空而非推测填写。"),
        "field": field,
    }


def ensure_contract_fields(payload, case):
    """Return ``(payload, filled_missing)`` with every contract field present."""
    fields = required_fields(case)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    filled = []
    for field in fields:
        if field in payload:
            continue
        payload[field] = _placeholder(field)
        filled.append(field)
    return payload, filled


def make_result(case, status, payload, evidence=None, uncertainty=None,
                sources=None, changes=None, notes=None):
    """Assemble the platform-facing result envelope."""
    payload, filled = ensure_contract_fields(payload, case)
    if filled:
        notes = list(notes or [])
        notes.append("contract_fields_without_evidence: " + ", ".join(filled))
    result = {
        "case_id": case_id(case),
        "status": status,
        "result": payload,
        "evidence": evidence or [],
        "sources": sources or [],
        "uncertainty": uncertainty or [],
        "changes": changes or [],
        "notes": notes or [],
    }
    return result


def status_reason(status, extra=None, missing=()):
    """One sentence describing why the run stopped where it did.

    `missing` names contract fields that carry no verifiable value; the `success`
    sentence must not claim full support while one of those exists.
    """
    ok = "全部要求的字段均有材料支撑并已给出定位。"
    if missing:
        ok = ("题目要求的字段均已给出并带定位；合同另有 %d 个字段在材料中无"
              "可核验取值，已按占位符登记：%s。"
              % (len(missing), "、".join(missing)))
    table = {
        STATUS_OK: ok,
        STATUS_PARTIAL: "部分字段已给出且有定位，剩余部分材料不足，已逐项标注。",
        STATUS_UNKNOWN: "输入材料不足以支撑判定，未做推测。",
        STATUS_REFUSED: "输入不满足任务前提，已说明具体缺口。",
    }
    reason = table.get(status, "未分类状态。")
    if extra:
        reason = reason + " " + extra
    return reason


def write_result(result, output_dir=None, name="result.json"):
    base = output_dir or OUTPUT_DIR
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        pass
    path = os.path.join(base, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    return path


def write_artifact(text, name, output_dir=None):
    base = output_dir or OUTPUT_DIR
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        pass
    path = os.path.join(base, name)
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def ensure_dirs():
    for path in (OUTPUT_DIR, WORK_DIR):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
