"""Topic 09 — LaTeX writing and compilation.

The rubric's first question is "编译得通": does the source compile under the
given template and TeX distribution, and when it fails, can the error be traced
to a file, a line and a root cause instead of stopping at the first message.

No TeX distribution is assumed to exist where this runs, so the Skill emits a
real ``.tex`` artifact and then lints it statically against the failure modes
that actually break a build: unescaped specials, unbalanced braces, undefined
citation keys, missing packages for used macros, and floats placed before their
first reference. When a compiler *is* present it runs it and reports the real
log; when it is not, it says so instead of claiming a successful build.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unicodedata

from . import base

# Every character that must be escaped in ordinary text mode, and why.
# Backslash first: extracted text may itself contain LaTeX-looking fragments
# ("\\n", "\\{SQL\\}"), and those are content, not markup.
SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}

# Macros used in the generated body, and the package that provides each.
PACKAGES = {
    r"\toprule": "booktabs", r"\midrule": "booktabs", r"\bottomrule": "booktabs",
    r"\includegraphics": "graphicx", r"\url": "hyperref", r"\href": "hyperref",
    r"\booktabs": "booktabs", r"\textasciitilde": None, r"\textasciicircum": None,
    r"\begin{align}": "amsmath", r"\begin{table}": None, r"\begin{figure}": None,
}

BASE_PACKAGES = ["inputenc", "fontenc", "amsmath", "amssymb", "graphicx",
                 "booktabs", "hyperref", "geometry"]


def run(case, task, bundle, records, doc):
    """Two entry points share one contract.

    When the case already ships LaTeX sources the job is to locate and fix what
    would break the build, so those files are linted and repaired in place.
    When it ships a paper instead, the job is to produce compilable source from
    it. Both paths report through the same fields, so a case never depends on
    the Skill guessing which situation it is in.
    """
    sources = [r for r in records if r.get("ext") in (".tex", ".latex", ".bib")]
    if sources:
        _repair(bundle, sources)
        return
    if doc is None:
        base.refuse_empty(bundle, "document", records,
                         "输入目录中没有可读的文档或 LaTeX 源文件")
        return
    base.degraded(bundle, doc)

    dropped = []
    tex, mapping = _build_tex(doc, dropped)
    lint = _lint(tex, doc)
    build = _compile(tex)

    path = _write(bundle, tex)
    bundle.put("latex_source", tex)
    bundle.put("latex_file", path)
    bundle.put("structure_mapping", mapping)
    bundle.put("lint_issues", lint)
    bundle.put("lint_issue_count", len(lint["issues"]))
    bundle.put("compile_result", build)
    bundle.put("package_requirements", lint["packages"])
    bundle.put("reproduce_commands", _commands(path))
    if dropped:
        counts = {}
        for char in dropped:
            counts[char] = counts.get(char, 0) + 1
        described = [{"char": char, "codepoint": "U+%04X" % ord(char),
                      "count": n}
                     for char, n in sorted(counts.items(), key=lambda kv: -kv[1])]
        bundle.put("unrepresentable_chars", {
            "total": len(dropped), "distinct": described[:20],
            "note": "这些字形在当前 TeX 字体编码下无法排印（多为图内字体带来的"
                    "私用区字符），已从交付源文件中略去并在原文位置保留词间空白；"
                    "需要保留时请改用 fontspec 并指定覆盖该字形的字体"})
        bundle.note("生成的源文件略去了 %d 个无法排印的字形（%d 种），明细见 "
                    "unrepresentable_chars。" % (len(dropped), len(counts)))

    # A document with neither sections nor an abstract yields a legally
    # compilable but empty skeleton. The build succeeds, so no compile gap
    # fires, yet the deliverable carries none of the source's content; calling
    # that success would overstate what was produced.
    abstract_text = (doc.get("abstract") or {}).get("text") or ""
    if not mapping and not abstract_text:
        bundle.gap(item="可转换内容",
                   reason="材料中没有可识别的章节结构或摘要，生成的源文件只有导言区"
                          "与标题，编译通过但不承载原文内容；需人工确认材料是否完整",
                   field="structure_mapping", state="partial")

    blockers = [i for i in lint["issues"] if i["severity"] == "blocking"]
    if blockers:
        bundle.gap(item="编译阻塞项",
                   reason="%d 处会导致编译失败或输出错误，已在 lint_issues 中给出"
                          "文件位置与根因：%s"
                          % (len(blockers),
                             "；".join(i["detail"][:60] for i in blockers[:4])),
                   field="lint_issues", state="partial")
    if not build["compiled"]:
        bundle.gap(item="实际编译", reason=_failure_reason(build),
                   field="compile_result", state="partial")


# -- LaTeX generation -------------------------------------------------------

# Glyphs that a T1/ec font cannot draw but that have a defensible stand-in.
# Keyed by the character that survives NFKC normalisation.
SYMBOLS = {
    "\u00d7": r"$\times$", "\u00b1": r"$\pm$", "\u2212": r"$-$",
    "\u00b7": r"$\cdot$", "\u2022": r"$\bullet$", "\u25e6": r"$\circ$",
    "\u2206": r"$\Delta$", "\u2208": r"$\in$", "\u2192": r"$\rightarrow$",
    "\u2190": r"$\leftarrow$", "\u21d2": r"$\Rightarrow$",
    "\u221a": r"$\surd$", "\u2248": r"$\approx$", "\u2217": r"$\ast$",
    "\u2264": r"$\leq$", "\u2265": r"$\geq$", "\u2260": r"$\neq$",
    "\u221e": r"$\infty$", "\u2202": r"$\partial$", "\u2207": r"$\nabla$",
    "\u222b": r"$\int$", "\u2211": r"$\sum$", "\u220f": r"$\prod$",
    "\u03b1": r"$\alpha$", "\u03b2": r"$\beta$", "\u03b3": r"$\gamma$",
    "\u03b4": r"$\delta$", "\u03b5": r"$\epsilon$", "\u03b7": r"$\eta$",
    "\u03b8": r"$\theta$", "\u03bb": r"$\lambda$", "\u03bc": r"$\mu$",
    "\u03c0": r"$\pi$", "\u03c1": r"$\rho$", "\u03c3": r"$\sigma$",
    "\u03c4": r"$\tau$", "\u03c6": r"$\phi$", "\u03c8": r"$\psi$",
    "\u03c9": r"$\omega$", "\u0393": r"$\Gamma$", "\u0394": r"$\Delta$",
    "\u0398": r"$\Theta$", "\u039b": r"$\Lambda$", "\u03a3": r"$\Sigma$",
    "\u03a6": r"$\Phi$", "\u03a8": r"$\Psi$", "\u03a9": r"$\Omega$",
    "\u2020": r"$\dagger$", "\u2021": r"$\ddagger$", "\u00a7": r"\S{}",
    "\u00b6": r"\P{}", "\u00b0": r"$^\circ$", "\u00a3": r"\pounds{}",
    "\u20ac": r"\euro{}",
}

# Accented Latin that ec-lmr10 does cover through T1, so they pass through.
_PASS_THROUGH_LIMIT = 0x024f


def _representable(char):
    """Whether the T1 font set can draw this character as-is."""
    code = ord(char)
    if code < 0x7f:
        return True
    if 0x00a0 <= code <= _PASS_THROUGH_LIMIT:
        return True
    return False


def _escape(text, dropped=None):
    """Escape a plain-text run for LaTeX.

    Character-by-character replacement is safe regardless of order because each
    source character maps to a command that is appended, not re-scanned.

    ``dropped``, when a list, collects the characters that had no defensible
    representation; the caller reports the count instead of letting an
    unbuildable glyph reach the compiler.
    """
    out = []
    for char in unicodedata.normalize("NFKC", text or ""):
        if char in SPECIALS:
            out.append(SPECIALS[char])
        elif char in SYMBOLS:
            out.append(SYMBOLS[char])
        elif _representable(char):
            out.append(char)
        elif dropped is not None:
            dropped.append(char)
    return "".join(out)


def _backslash_count(text):
    """How many literal backslashes a run contains, for the report."""
    return (text or "").count(chr(92))


def _clean(text):
    """Normalise extracted text into something safe to embed."""
    text = " ".join((text or "").split())
    text = text.replace("\u2013", "--").replace("\u2014", "---")
    text = text.replace("\u2018", "`").replace("\u2019", "'")
    text = text.replace("\u201c", "``").replace("\u201d", "''")
    text = text.replace("\u00a0", " ")
    return text


def _build_tex(doc, dropped=None):
    """Turn the recovered structure into a compilable document.

    ``dropped``, when a list, collects glyphs the TeX encoding cannot draw,
    so the caller can report them instead of shipping a silently shortened
    document.
    """
    meta = doc.get("meta") or {}
    title = _clean(meta.get("title") or "Untitled")
    authors = [_clean(a) for a in (meta.get("authors") or [])]
    abstract = _clean((doc.get("abstract") or {}).get("text") or "")
    sections = doc.get("sections") or []

    lines = []
    lines.append("% Generated by the document-parse skill. Compile with: latexmk -pdf")
    lines.append(r"\documentclass[11pt]{article}")
    lines.append(r"\usepackage[T1]{fontenc}")
    lines.append(r"\usepackage[utf8]{inputenc}")
    lines.append(r"\usepackage{amsmath,amssymb}")
    lines.append(r"\usepackage{graphicx}")
    lines.append(r"\usepackage{booktabs}")
    lines.append(r"\usepackage[colorlinks=true,linkcolor=blue,citecolor=blue]{hyperref}")
    lines.append(r"\usepackage[margin=1in]{geometry}")
    lines.append(r"\title{%s}" % _escape(title, dropped))
    if authors:
        lines.append(r"\author{%s}"
                 % r" \and ".join(_escape(a, dropped) for a in authors))
    else:
        lines.append(r"\author{}")
    lines.append(r"\date{}")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    if abstract:
        lines.append(r"\begin{abstract}")
        lines.append(_escape(abstract, dropped))
        lines.append(r"\end{abstract}")

    mapping = []
    for item in sections:
        heading = _clean((item.get("num", "") + " " + item["title"]).strip())
        if _is_reference_heading(heading):
            continue
        command = _section_command(item.get("level", 1))
        line_no = len(lines) + 1
        lines.append("%s{%s}" % (command, _escape(heading, dropped)))
        mapping.append({"heading": heading, "level": item.get("level", 1),
                        "command": command, "tex_line": line_no,
                        "source_page": base.page_of_offset(doc, item.get("offset", 0))})
        body = _clean((item.get("body") or "").split("\n", 1)[-1])
        for para in _paragraphs(body):
            lines.append("")
            lines.append(_escape(para, dropped))

    refs = doc.get("references") or []
    if refs:
        lines.append("")
        lines.append(r"\begin{thebibliography}{%d}" % max(9, len(refs)))
        for entry in refs:
            lines.append(r"\bibitem{ref%d} %s"
                         % (entry["index"],
                            _escape(_clean(entry.get("text")), dropped)))
        lines.append(r"\end{thebibliography}")

    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n", mapping


def _section_command(level):
    return {1: r"\section", 2: r"\subsection", 3: r"\subsubsection"}.get(
        min(int(level or 1), 3), r"\paragraph")


def _is_reference_heading(heading):
    return bool(re.match(r"(?i)^(references|bibliography|参考文献)\b", heading.strip()))


def _paragraphs(body):
    rows = []
    for block in re.split(r"\n\s*\n", body or ""):
        block = " ".join(block.split())
        if len(block) >= 40:
            rows.append(block)
    return rows


def _write(bundle, tex):
    """Write the .tex next to result.json so it can be submitted and rebuilt."""
    try:
        from core import contract
        path = contract.write_artifact(tex, "paper.tex")
        bundle.artifact("paper.tex", path)
        rel = os.path.basename(path)
        return rel
    except Exception:
        return None


# -- linting ----------------------------------------------------------------

def _lint(tex, doc):
    """Catch the failure modes a real build would hit, with line numbers."""
    issues = []
    lines = tex.split("\n")

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("%"):
            continue
        if stripped.startswith(_PROTECTED_ALL):
            continue
        # inline math and tabular bodies legitimately contain `_` and `&`, so
        # the check runs on a copy with those spans removed
        probe = _strip_math(line)
        if "&" in probe and _in_tabular(lines, idx):
            probe = probe.replace("&", "")
        for char, meaning in (("_", "下标符"), ("&", "对齐符"), ("#", "参数符")):
            body = re.sub(r"\\[a-zA-Z]+", "", probe)
            body = re.sub(r"\\[&%$#_{}]", "", body)
            if char in body:
                issues.append({
                    "line": idx, "severity": "blocking", "kind": "unescaped_%s" % char,
                    "detail": "第 %d 行的 `%s`（%s）未转义，会中断编译或静默改变字形"
                              % (idx, char, meaning),
                    "root_cause": "正文中直接出现 LaTeX 保留字符",
                    "fix": "改为 \\%s" % char,
                })

    # brace balance, tracked per line so the report can point at the opener
    depth = 0
    openers = []
    for idx, line in enumerate(lines, 1):
        for col, char in enumerate(line):
            if char == "\\":
                continue
            if char == "{" and (col == 0 or line[col - 1] != "\\"):
                depth += 1
                openers.append((idx, depth))
            elif char == "}" and (col == 0 or line[col - 1] != "\\"):
                depth -= 1
                if openers:
                    openers.pop()
    if depth != 0:
        line_no = openers[-1][0] if openers else 1
        issues.append({
            "line": line_no, "severity": "blocking", "kind": "unbalanced_braces",
            "detail": "花括号未闭合，净差 %+d，最后未闭合处在第 %d 行" % (depth, line_no),
            "root_cause": "正文里的花括号被当成命令参数分组",
            "fix": "补 `}` 或把字面括号转义为 \\{ \\}",
        })

    # environments that open and never close
    for env in re.findall(r"\\begin\{([a-zA-Z*]+)\}", tex):
        opens = len(re.findall(r"\\begin\{%s\}" % re.escape(env), tex))
        closes = len(re.findall(r"\\end\{%s\}" % re.escape(env), tex))
        if opens != closes:
            issues.append({
                "line": _line_of(tex, r"\\begin\{%s\}" % re.escape(env)),
                "severity": "blocking", "kind": "unclosed_environment",
                "detail": "环境 %s 有 %d 个 \\begin 但 %d 个 \\end" % (env, opens, closes),
                "root_cause": "段落抽取把环境边界截断",
                "fix": "补齐 \\end{%s}" % env,
            })

    # floats referenced before they are declared, or never referenced at all
    issues.extend(_float_issues(tex))

    # citations that point at a bibliography key we did not emit
    keys = set(re.findall(r"\\bibitem\{([^}]+)\}", tex))
    used = set()
    for match in re.finditer(r"\\(?:cite|citep|citet)\{([^}]+)\}", tex):
        used.update(k.strip() for k in match.group(1).split(","))
    for key in sorted(used - keys):
        issues.append({
            "line": _line_of(tex, r"\\cite\{[^}]*%s" % re.escape(key)),
            "severity": "advisory", "kind": "undefined_citation",
            "detail": "引用键 `%s` 没有对应的 \\bibitem" % key,
            "root_cause": "参考文献表未收录该条目",
            "fix": "补 \\bibitem{%s} 或改用 thebibliography 之外的 bib 源" % key,
        })

    packages = _required_packages(tex)
    return {"issues": issues, "packages": packages,
            "blocking": len([i for i in issues if i["severity"] == "blocking"])}


def _line_of(tex, pattern):
    match = re.search(pattern, tex)
    if not match:
        return 1
    return tex.count("\n", 0, match.start()) + 1


def _float_issues(tex):
    """A figure/table whose \\label is never referenced still compiles, but a
    \\ref to a missing label does not resolve, and that is worth reporting."""
    labels = set(re.findall(r"\\label\{([^}]+)\}", tex))
    refs = set(re.findall(r"\\(?:ref|autoref|cref)\{([^}]+)\}", tex))
    out = []
    for name in sorted(refs - labels):
        out.append({
            "line": _line_of(tex, r"\\ref\{%s\}" % re.escape(name)),
            "severity": "blocking", "kind": "undefined_reference",
            "detail": "\\ref{%s} 没有对应的 \\label，编译后显示为 ??" % name,
            "root_cause": "交叉引用目标未被生成",
            "fix": "补 \\label{%s} 或删除该引用" % name,
        })
    return out


def _required_packages(tex):
    """Packages the generated source needs but does not load."""
    present = set(re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", tex))
    loaded = set()
    for group in present:
        loaded.update(p.strip() for p in group.split(","))
    needed = set(BASE_PACKAGES)
    for macro, package in PACKAGES.items():
        if package and macro in tex:
            needed.add(package)
    missing = sorted(needed - loaded)
    return {"loaded": sorted(loaded), "needed": sorted(needed), "missing": missing}


# -- compilation ------------------------------------------------------------

def _strip_math(line):
    """Remove inline ``$...$`` spans so their `_` is not reported as an error."""
    out = []
    idx = 0
    while idx < len(line):
        if line[idx] == "\\":
            out.append(line[idx:idx + 2])
            idx += 2
            continue
        if line[idx] == "$":
            idx = _math_span_end(line, idx)
            out.append(" ")
            continue
        out.append(line[idx])
        idx += 1
    return "".join(out)


def _in_tabular(lines, line_no):
    """Whether a given 1-based line sits inside a tabular-like environment."""
    depth = 0
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("\\begin{tabular") or stripped.startswith("\\begin{array"):
            depth += 1
        elif stripped.startswith("\\end{tabular") or stripped.startswith("\\end{array"):
            depth = max(0, depth - 1)
        if idx >= line_no:
            return depth > 0
    return False


_PROTECTED_ALL = (r"\begin", r"\end", r"\usepackage", r"\documentclass",
                  r"\newcommand", r"\renewcommand", r"\label", r"\ref", r"\eqref",
                  r"\cite", r"\citep", r"\citet", r"\includegraphics", r"\input",
                  r"\include", r"\bibliography", r"\bibliographystyle", r"\url",
                  r"\href", r"\def")


def _compile(tex):
    """Try a real build; report honestly when no distribution exists."""
    import tempfile
    tool = _find_tex()
    if not tool:
        return {"compiled": False, "checked": "static-only",
                "reason": "环境未提供 latexmk/pdflatex/xelatex/tectonic",
                "note": "静态检查已覆盖未转义字符、括号平衡、环境闭合、"
                        "未定义引用与缺失宏包五类问题；实际编译需在装有 TeX 的环境复核。"}
    name = os.path.basename(tool).lower()
    argv = ([tool, "-X", "compile", "paper.tex"] if "tectonic" in name
            else [tool, "-pdf", "-interaction=nonstopmode",
                  "-halt-on-error", "paper.tex"])
    attempts = []
    try:
        for base in _bases():
            tmp = _scratch(base)
            if tmp is None:
                continue
            try:
                path = os.path.join(tmp, "paper.tex")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(tex)
                proc = subprocess.run(
                    argv, cwd=tmp, capture_output=True, timeout=300,
                    encoding="utf-8", errors="replace", env=_tex_env(tmp))
                log = (proc.stdout or "") + (proc.stderr or "")
                pdf = os.path.join(tmp, "paper.pdf")
                built = proc.returncode == 0 and os.path.exists(pdf)
                result = {
                    "compiled": built, "checked": "real-build",
                    "tool": os.path.basename(tool), "build_root": base,
                    "returncode": proc.returncode,
                    "errors": re.findall(r"^! (.+)$", log, re.M)[:10],
                    "log_tail": "" if built else log[-1500:],
                }
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            # A denial before TeX reads the source says nothing about the
            # document; any other outcome is a real verdict on it.
            if built or "access denied" not in result["log_tail"].lower():
                return result
            attempts.append({"build_root": base, "returncode": proc.returncode})
    except subprocess.TimeoutExpired:
        return {"compiled": False, "checked": "not-attempted",
                "reason": "构建超过 300 秒被中止（首次运行需下载 TeX 宏包），"
                          "未得出编译结论；环境已具备引擎，待缓存就绪后可复跑"}
    except Exception as exc:
        return {"compiled": False, "checked": "static-only",
                "reason": "%s: %s" % (type(exc).__name__, exc)}
    return {"compiled": False, "checked": "real-build",
            "tool": os.path.basename(tool), "returncode": None,
            "attempts": attempts,
            "reason": "每个候选构建目录都被引擎拒绝访问（%s），"
                      "未读到源的任何一行，故不对文档本身作判断"
                      % "、".join(a["build_root"] for a in attempts)}


TEX_ORDER = ("latexmk", "pdflatex", "xelatex", "tectonic")


def _cache_dir():
    """A TeX package cache that survives across builds.

    The engine fetches packages on first use; with a per-build cache each run
    pays the download again, and a slow network turns a fine document into a
    timeout. One persistent directory keeps later builds offline-fast.
    """
    for base in (os.environ.get("BSK_WORK_DIR"),
                 os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 os.path.expanduser("~")):
        if not base:
            continue
        candidate = os.path.join(base, ".texcache")
        try:
            os.makedirs(candidate, exist_ok=True)
            if os.access(candidate, os.W_OK):
                return candidate
        except OSError:
            continue
    return os.path.join(tempfile.gettempdir(), ".texcache")


def _bases():
    """Directories worth trying as a build root, most durable first."""
    seen, out = set(), []
    for base in (os.environ.get("BSK_WORK_DIR"), os.getcwd(), tempfile.gettempdir()):
        if base and base not in seen:
            seen.add(base)
            out.append(base)
    return out


def _scratch(base):
    """Create one candidate build directory, or None if the root is unusable."""
    try:
        os.makedirs(base, exist_ok=True)
        return tempfile.mkdtemp(prefix="texbuild-", dir=base)
    except OSError:
        return None


def _clean_text(tex):
    """Replace unmapped codepoints with a marker LaTeX can actually typeset."""
    if "\ufffd" not in tex:
        return tex
    return tex.replace("\ufffd", "\\textquestiondown{}")


def _failure_reason(build):
    """Explain a failed build without pretending every failure looks the same."""
    if build.get("checked") != "real-build":
        if build.get("checked") == "not-attempted":
            return build.get("reason", "未获得编译结论")
        return ("运行环境未提供 TeX 发行版（%s），只做静态检查；"
                "编译结论需在装有 latexmk/pdflatex/tectonic 的环境中复核"
                % build.get("reason", "unknown"))
    errors = build.get("errors") or []
    if errors:
        return ("%s 编译失败，报出 %d 条错误，首条为：%s"
                % (build.get("tool"), len(errors), errors[0][:120]))
    return ("%s 编译未通过（返回码 %s），引擎未给出可解析的错误行，"
            "完整日志尾部见 compile_result.log_tail"
            % (build.get("tool"), build.get("returncode")))


def _find_tex():
    """First usable engine on PATH, in preference order."""
    suffix = ".exe" if os.name == "nt" else ""
    for name in TEX_ORDER:
        for root in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(root, name + suffix)
            if root and os.path.exists(candidate):
                return candidate
    return None


def _tex_env(home):
    """Give the engine a scratch home and cache of its own.

    tectonic keeps a package cache under HOME and aborts with a bare
    "access denied" when that location is unusable — which is what a container
    with a read-only or roaming profile hands it. A private directory per build
    costs a package download the first time and nothing after, since the cache
    is reused across runs in the same work directory.
    """
    env = dict(os.environ)
    env["HOME"] = home
    env["USERPROFILE"] = home
    env["APPDATA"] = os.path.join(home, "AppData", "Roaming")
    env["LOCALAPPDATA"] = os.path.join(home, "AppData", "Local")
    env["TECTONIC_CACHE_DIR"] = _cache_dir()
    for path in (env["APPDATA"], env["LOCALAPPDATA"], env["TECTONIC_CACHE_DIR"]):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return env


def _repair(bundle, sources):
    """Lint the case's own sources, repair the mechanical faults, report the rest.

    A repair the Skill can prove (an unescaped `_` in text mode) is applied and
    recorded as a diff. A repair that would change meaning (a missing
    citation key, an unresolvable \\ref) is reported but never guessed.
    """
    from core import contract

    tex_records = [r for r in sources if r.get("ext") in (".tex", ".latex")]
    bib_records = [r for r in sources if r.get("ext") == ".bib"]

    files, repairs, all_issues = [], [], []
    fixed_text = {}
    for record in tex_records:
        original = record.get("text") or ""
        patched, applied = _autofix(original)
        fixed_text[record["rel"]] = patched
        lint = _lint(patched, None)
        files.append({
            "path": record["rel"],
            "lines": original.count("\n") + 1,
            "chars": len(original),
            "issues_before_fix": len(applied) + len(lint["issues"]),
            "issues_after_fix": len(lint["issues"]),
            "packages": lint["packages"],
        })
        repairs.extend(applied)
        for issue in lint["issues"]:
            row = dict(issue)
            row["file"] = record["rel"]
            all_issues.append(row)

    written = []
    for rel, text in fixed_text.items():
        name = rel.replace("\\", "/").split("/")[-1]
        if not name.endswith((".tex", ".latex")):
            name += ".tex"
        try:
            path = contract.write_artifact(text, name)
            bundle.artifact(name, path)
            written.append({"name": name, "source": rel})
        except Exception:
            pass

    bib_keys = _bib_keys(bib_records)
    cross = _cross_check(tex_records, bib_keys)
    all_issues.extend(cross)

    build = _compile_any(fixed_text)

    bundle.put("latex_files", files)
    bundle.put("file_count", len(files))
    bundle.put("repaired", repairs)
    bundle.put("repair_count", len(repairs))
    bundle.put("lint_issues", {"issues": all_issues,
                               "blocking": len([i for i in all_issues
                                                if i["severity"] == "blocking"])})
    bundle.put("lint_issue_count", len(all_issues))
    bundle.put("fixed_sources", written)
    bundle.put("bib_entries", len(bib_keys))
    bundle.put("compile_result", build)
    bundle.put("package_requirements", _merge_packages(files))
    bundle.put("reproduce_commands", _commands(files[0]["path"] if files else None))

    blocking = [i for i in all_issues if i["severity"] == "blocking"]
    if blocking:
        bundle.gap(item="需人工确认的编译阻塞",
                   reason="%d 处无法安全自动修复（涉及语义），已给出文件、行号与根因：%s"
                          % (len(blocking),
                             "；".join("%s:%s %s" % (i.get("file"), i["line"], i["kind"])
                                      for i in blocking[:4])),
                   field="lint_issues", state="partial")
    if not build.get("compiled"):
        bundle.gap(item="实际编译", reason=_failure_reason(build),
                   field="compile_result", state="partial")


def _autofix(text):
    """Escape the specials that sit in text mode, leaving commands untouched.

    Only characters that appear outside any command and outside a math
    environment are touched, because escaping inside either changes meaning.
    """
    applied = []
    out = []
    in_display = False
    in_tabular = False
    for idx, line in enumerate(text.split("\n"), 1):
        stripped = line.lstrip()
        if stripped.startswith("%"):
            out.append(line)
            continue
        stripped_trim = line.strip()
        if stripped_trim.startswith("\\begin{tabular"):
            in_tabular = True
        elif stripped_trim.startswith("\\end{tabular"):
            in_tabular = False
        # inline math is handled per line by _escape_line, so only display
        # environments carry state across lines
        state, in_display = _display_step(line, in_display)
        if state or _is_protected_line(stripped):
            out.append(line)
            continue
        if _is_text_arg_line(stripped):
            fixed, hits = _escape_braced(line)
        else:
            fixed, hits = _escape_line(line, keep_amp=in_tabular)
        if hits:
            for char in hits:
                applied.append({"file_line": idx, "char": char,
                                "before": char, "after": "\\" + char,
                                "reason": "正文字符未转义"})
        out.append(fixed)
    return "\n".join(out), applied


# Commands whose braced argument is text mode, so specials inside must be escaped.
TEXT_ARG = (r"\title", r"\author", r"\date", r"\section", r"\subsection",
            r"\subsubsection", r"\paragraph", r"\caption", r"\thanks",
            r"\footnote", r"\item", r"\maketitle")

# Commands whose braces hold syntax, keys or paths: escaping them breaks things.
SYNTAX = (r"\begin{", r"\end{", r"\usepackage", r"\documentclass", r"\newcommand",
          r"\renewcommand", r"\label", r"\ref", r"\eqref", r"\cite", r"\citep",
          r"\citet", r"\includegraphics", r"\input", r"\include", r"\bibliography",
          r"\bibliographystyle", r"\url", r"\href")


def _is_protected_line(stripped):
    return stripped.startswith(SYNTAX)


def _is_text_arg_line(stripped):
    return stripped.startswith(TEXT_ARG)


MATH_ENVS = ("equation", "equation*", "align", "align*", "gather", "gather*",
             "multline", "multline*", "eqnarray", "eqnarray*", "displaymath",
             "split", "cases", "matrix", "pmatrix", "bmatrix", "vmatrix", "array")


def _display_step(line, inside):
    """Track whether the next line starts inside a display-math environment.

    Only display environments span lines. Inline ``$...$`` is resolved per line
    by :func:`_escape_line`, so it must not leak state into the next line.
    """
    stripped = line.strip()
    if inside:
        for env in MATH_ENVS:
            if stripped.startswith("\\end{%s}" % env) or stripped.startswith(r"\]"):
                return True, False
        return True, True
    for env in MATH_ENVS:
        if stripped.startswith("\\begin{%s}" % env):
            return True, True
    if stripped.startswith(r"\["):
        return True, True
    return False, False


def _escape_braced(line):
    """Escape specials inside the first braced argument of a text-mode command."""
    start = line.find("{")
    end = line.rfind("}")
    if start < 0 or end <= start:
        return line, []
    inner, hits = _escape_line(line[start + 1:end])
    return line[:start + 1] + inner + line[end:], hits


def _escape_line(line, keep_amp=False):
    """Escape `_`, `&`, `#` in text mode; return (line, hits).

    Inline math is copied verbatim: `$a_b$` keeps its subscript, while a bare
    `my_model` in running text gets escaped. Inside a tabular body `&` is the
    column separator, so ``keep_amp`` leaves it alone there.
    """
    hits = []
    out = []
    idx = 0
    while idx < len(line):
        char = line[idx]
        if char == "\\":
            out.append(line[idx:idx + 2])
            idx += 2
            continue
        if char == "$":
            end = _math_span_end(line, idx)
            out.append(line[idx:end])
            idx = end
            continue
        if char in "_&#":
            if char == "&" and keep_amp:
                out.append(char)
                idx += 1
                continue
            out.append("\\" + char)
            hits.append(char)
            idx += 1
            continue
        out.append(char)
        idx += 1
    return "".join(out), hits


def _math_span_end(line, start):
    """Index just past the closing `$` of the inline math span at ``start``."""
    idx = start + 1
    while idx < len(line):
        if line[idx] == "\\":
            idx += 2
            continue
        if line[idx] == "$":
            return idx + 1
        idx += 1
    return len(line)


def _bib_keys(bib_records):
    keys = set()
    for record in bib_records:
        for match in re.finditer(r"@\w+\s*\{\s*([^,\s]+)\s*,", record.get("text") or ""):
            keys.add(match.group(1))
    return keys


def _cross_check(tex_records, bib_keys):
    """Citation keys used in sources that the .bib does not define."""
    if not bib_keys:
        return []
    used = set()
    for record in tex_records:
        for match in re.finditer(r"\\(?:cite|citep|citet|parencite|textcite)\*?"
                                 r"(?:\[[^\]]*\])*\{([^}]+)\}",
                                 record.get("text") or ""):
            used.update(k.strip() for k in match.group(1).split(","))
    out = []
    for key in sorted(used - bib_keys):
        out.append({
            "file": (tex_records[0]["rel"] if tex_records else None),
            "line": 1, "severity": "blocking", "kind": "undefined_citation",
            "detail": "引用键 `%s` 在 .bib 中没有对应条目" % key,
            "root_cause": "参考文献库缺条目或键名拼写不一致",
            "fix": "补该条目到 .bib，或修正正文中的键名",
        })
    unused = sorted(bib_keys - used)
    if unused:
        out.append({
            "file": (tex_records[0]["rel"] if tex_records else None),
            "line": 1, "severity": "advisory", "kind": "unused_bib_entry",
            "detail": ".bib 中 %d 条未被引用：%s" % (len(unused), ", ".join(unused[:8])),
            "root_cause": "文献库含未使用条目，不影响编译但影响提交整洁度",
            "fix": "删除或补引",
        })
    return out


def _merge_packages(files):
    needed, loaded = set(), set()
    for item in files:
        packages = item.get("packages") or {}
        needed.update(packages.get("needed") or [])
        loaded.update(packages.get("loaded") or [])
    return {"loaded": sorted(loaded), "needed": sorted(needed),
            "missing": sorted(needed - loaded)}


def _compile_any(fixed_text):
    """Compile the first source that looks like a document root."""
    if not fixed_text:
        return {"compiled": False, "checked": "static-only",
                "reason": "输入中没有 .tex 源文件"}
    name = None
    for rel, text in fixed_text.items():
        if r"\documentclass" in text:
            name, body = rel, text
            break
    if name is None:
        return {"compiled": False, "checked": "static-only",
                "reason": "没有含 \\documentclass 的根文件（可能是子文件或片段），"
                          "单独无法编译"}
    result = _compile(body)
    result["root_file"] = name
    return result


def _commands(path):
    name = path or "paper.tex"
    return {
        "local": "latexmk -pdf %s" % name,
        "overleaf": "上传 %s，主文档设为它，编译器选 pdfLaTeX" % name,
        "clean": "latexmk -C",
        "verify": "编译后检查 paper.log 中是否有 `There were undefined references`",
    }
