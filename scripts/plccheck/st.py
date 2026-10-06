"""Structural lint for IEC 61131-3 Structured Text and its close dialects.

Covers IEC ST, Siemens SCL sources, CODESYS / TwinCAT ST and Logix ST well enough to
catch the mistakes that survive a read-through: unbalanced blocks, IF without THEN,
`=` used as assignment, EXIT outside a loop, duplicate declarations, and timer /
edge-trigger instances that are only called conditionally.

It is NOT a compiler. It does no type checking and resolves no symbols across files.
A clean run means "structurally plausible", never "compiles".

Modes:
  file         a complete source file (POUs closed with END_*)
  declaration  a declaration part whose POU header has no END_* (TwinCAT .TcPOU,
               PLCopen interface text); the header may stay open at EOF
  body         statements only (PLCopen <ST> body, TwinCAT <Implementation>)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .findings import Finding, error, warning

TIME_TYPES = {
    "T", "TIME", "LT", "LTIME", "D", "DATE", "LD", "LDATE", "TOD", "TIME_OF_DAY",
    "LTOD", "LTIME_OF_DAY", "DT", "DATE_AND_TIME", "LDT", "LDATE_AND_TIME",
}

VAR_KINDS = {
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_GLOBAL", "VAR_EXTERNAL",
    "VAR_TEMP", "VAR_STAT", "VAR_INST", "VAR_CONFIG", "VAR_ACCESS",
}
# Openers whose frame starts a new declaration scope.
SCOPE_OPENERS = {
    "PROGRAM", "FUNCTION_BLOCK", "FUNCTION", "METHOD", "PROPERTY", "CLASS", "INTERFACE",
    "ORGANIZATION_BLOCK", "DATA_BLOCK", "CONFIGURATION", "RESOURCE", "ACTION", "TRANSITION",
}
HEADER_KINDS = {"PROGRAM", "FUNCTION_BLOCK", "FUNCTION", "METHOD", "PROPERTY", "CLASS", "INTERFACE"}
CONTROL_OPENERS = {"IF", "CASE", "FOR", "WHILE", "REPEAT"}
DECL_OPENERS = VAR_KINDS | {"TYPE", "STRUCT", "UNION"}
CONTEXTUAL = {"STEP", "INITIAL_STEP", "ACTION", "TRANSITION", "REGION"}
OTHER_OPENERS = {"NAMESPACE"}
OPENERS = SCOPE_OPENERS | CONTROL_OPENERS | DECL_OPENERS | CONTEXTUAL | OTHER_OPENERS

CLOSERS: dict[str, set[str]] = {
    "END_IF": {"IF"}, "END_CASE": {"CASE"}, "END_FOR": {"FOR"}, "END_WHILE": {"WHILE"},
    "END_REPEAT": {"REPEAT"}, "END_VAR": VAR_KINDS, "END_TYPE": {"TYPE"},
    "END_STRUCT": {"STRUCT"}, "END_UNION": {"UNION"}, "END_PROGRAM": {"PROGRAM"},
    "END_FUNCTION_BLOCK": {"FUNCTION_BLOCK"}, "END_FUNCTION": {"FUNCTION"},
    "END_METHOD": {"METHOD"}, "END_PROPERTY": {"PROPERTY"}, "END_INTERFACE": {"INTERFACE"},
    "END_CLASS": {"CLASS"}, "END_NAMESPACE": {"NAMESPACE"}, "END_ACTION": {"ACTION"},
    "END_TRANSITION": {"TRANSITION"}, "END_STEP": {"STEP", "INITIAL_STEP"},
    "END_REGION": {"REGION"}, "END_CONFIGURATION": {"CONFIGURATION"},
    "END_RESOURCE": {"RESOURCE"}, "END_ORGANIZATION_BLOCK": {"ORGANIZATION_BLOCK"},
    "END_DATA_BLOCK": {"DATA_BLOCK"},
}
EXPECT = {"IF": "THEN", "ELSIF": "THEN", "CASE": "OF", "FOR": "DO", "WHILE": "DO"}
LOOPS = {"FOR", "WHILE", "REPEAT"}
CONDITIONALS = {"IF", "CASE"}
MODIFIERS = {"PUBLIC", "PRIVATE", "PROTECTED", "INTERNAL", "ABSTRACT", "FINAL", "OVERRIDE"}

KEYWORDS = (
    set(CLOSERS) | OPENERS
    | {"THEN", "ELSE", "ELSIF", "OF", "DO", "TO", "BY", "UNTIL", "EXIT", "CONTINUE", "RETURN",
       "BEGIN", "NOT", "AND", "OR", "XOR", "MOD", "AND_THEN", "OR_ELSE", "TRUE", "FALSE",
       "SUPER", "THIS"}
)

# Instances of these types only do their job when called every scan.
_SCAN_FB_RE = re.compile(
    r"^(?:(?:TON|TOF|TP|TONR)(?:_L?TIME)?|L(?:TON|TOF|TP)|IEC_L?TIMER|[RF]_TRIG|CT(?:U|D|UD)(?:_[A-Z]+)?)$"
)
_TIMER_MEMBER_CALLS = {"TON", "TOF", "TP", "TONR"}  # Siemens IEC_TIMER multi-instance: #t.TON(...)
_ADDR_RE = re.compile(r"^%(?:[IQM](?:\*|[XBWDL]?\d+(?:\.\d+)*)|DB\d+\.DB[XBWD]\d+(?:\.\d+)?)$", re.I)


@dataclass(frozen=True)
class Tok:
    kind: str  # word | num | str | dstr | op | addr
    text: str
    line: int
    member: bool = False  # word directly after "."
    real: bool = False  # numeric literal with fraction or exponent

    @property
    def up(self) -> str:
        return self.text.upper()


@dataclass
class StAnalysis:
    """What one lint pass saw, for cross-part checks (TwinCAT methods, PLCopen interfaces)."""

    instances: dict[str, tuple[str, str, int]] = field(default_factory=dict)  # UPPER -> (name, type, line)
    calls: list[tuple[str, int, bool, bool]] = field(default_factory=list)  # (UPPER, line, conditional, in_loop)
    member_refs: dict[str, int] = field(default_factory=dict)  # UPPER -> first line
    has_body: bool = False
    header: tuple[str, str] | None = None  # (kind, name) of the first POU header

    def shifted(self, offset: int) -> "StAnalysis":
        """The same analysis with every line moved by offset (text embedded in a file)."""
        return StAnalysis(
            {k: (n, t, line + offset) for k, (n, t, line) in self.instances.items()},
            [(n, line + offset, c, lp) for n, line, c, lp in self.calls],
            {k: line + offset for k, line in self.member_refs.items()},
            self.has_body,
            self.header,
        )


def tokenize(src: str) -> tuple[list[Tok], list[Finding]]:
    toks: list[Tok] = []
    findings: list[Finding] = []
    i, n, line = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r\f\v":
            i += 1
            continue
        two = src[i:i + 2]
        if two in ("(*", "/*"):
            close = "*)" if two == "(*" else "*/"
            start, depth = line, 1
            i += 2
            while i < n and depth:
                t2 = src[i:i + 2]
                if t2 == two:
                    depth += 1
                    i += 2
                elif t2 == close:
                    depth -= 1
                    i += 2
                else:
                    if src[i] == "\n":
                        line += 1
                    i += 1
            if depth:
                findings.append(error("ST001", f"unterminated comment opened with '{two}'", start))
            continue
        if two == "//":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "{":
            j = src.find("}", i)
            if j < 0:
                findings.append(error("ST001", "unterminated pragma '{'", line))
                break
            line += src.count("\n", i, j)
            i = j + 1
            continue
        if c in "'\"":
            start, start_i = line, i
            i += 1
            while i < n and src[i] != c:
                if src[i] == "$" and i + 1 < n:
                    if src[i + 1] == "\n":
                        line += 1
                    i += 2
                    continue
                if src[i] == "\n":
                    line += 1
                i += 1
            if i >= n:
                findings.append(error("ST001", f"unterminated string literal opened with {c}", start))
                break
            toks.append(Tok("str" if c == "'" else "dstr", src[start_i:i + 1], start))
            i += 1
            continue
        if c.isalpha() or c == "_" or (c == "#" and i + 1 < n and (src[i + 1].isalpha() or src[i + 1] == "_")):
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            if j < n and src[j] == "#" and not word.startswith("#"):
                # typed / time literal: T#5s, INT#5, E_Color#Red, DT#2026-01-01-12:00:00
                extra = "-:+" if word.upper() in TIME_TYPES else ""
                k = j + 1
                while k < n and (src[k].isalnum() or src[k] in "_." + extra):
                    k += 1
                toks.append(Tok("num", src[i:k], line))
                i = k
                continue
            member = bool(toks) and toks[-1].kind == "op" and toks[-1].text == "."
            toks.append(Tok("word", word, line, member=member))
            i = j
            continue
        if c.isdigit():
            j = i
            while j < n and (src[j].isdigit() or src[j] == "_"):
                j += 1
            if j < n and src[j] == "#":  # based literal 16#FF, 2#1010
                j += 1
                while j < n and (src[j].isalnum() or src[j] == "_"):
                    j += 1
                toks.append(Tok("num", src[i:j], line))
                i = j
                continue
            real = False
            if j + 1 < n and src[j] == "." and src[j + 1].isdigit():
                real = True
                j += 1
                while j < n and (src[j].isdigit() or src[j] == "_"):
                    j += 1
            if j < n and src[j] in "eE":
                k = j + 1
                if k < n and src[k] in "+-":
                    k += 1
                if k < n and src[k].isdigit():
                    real = True
                    j = k
                    while j < n and src[j].isdigit():
                        j += 1
            toks.append(Tok("num", src[i:j], line, real=real))
            i = j
            continue
        if c == "%":
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] in ".*"):
                j += 1
            toks.append(Tok("addr", src[i:j], line))
            i = j
            continue
        if two in (":=", "=>", "<=", ">=", "<>", "**", "..", "?="):
            toks.append(Tok("op", two, line))
            i += 2
            continue
        if c in "+-*/=<>&(),;:[].^@":
            toks.append(Tok("op", c, line))
        i += 1
    return toks, findings


@dataclass
class _Frame:
    kw: str
    line: int
    scope: dict[str, int] | None = None  # declared names, for scope openers
    body: bool = False  # statements allowed at this level


def _is_zero(t: Tok) -> bool:
    try:
        return float(t.text.replace("_", "")) == 0.0
    except ValueError:
        return False


def _is_op(t: Tok | None, *texts: str) -> bool:
    return t is not None and t.kind == "op" and t.text in texts


def _is_word(t: Tok | None) -> bool:
    return t is not None and t.kind == "word"


def _keyword(toks: list[Tok], idx: int) -> str | None:
    """Return the keyword at idx, or None when the word is used as an identifier."""
    t = toks[idx]
    if t.kind != "word" or t.member or t.text.startswith("#"):
        return None
    u = t.up
    if u not in KEYWORDS:
        return None
    if u in CONTEXTUAL:
        prev = toks[idx - 1] if idx else None
        nxt = toks[idx + 1] if idx + 1 < len(toks) else None
        if prev is not None and prev.kind == "op" and prev.text not in (";",):
            return None  # operand: x := region;
        if u in ("STEP", "INITIAL_STEP", "ACTION"):
            nxt2 = toks[idx + 2] if idx + 2 < len(toks) else None
            return u if (_is_word(nxt) and _is_op(nxt2, ":")) else None
        if u == "TRANSITION":
            window = toks[idx + 1: idx + 8]
            return u if any(w.kind == "word" and w.up == "FROM" for w in window) else None
        if u == "REGION":
            if nxt is None or _is_op(nxt, ":=", ".", "(", "[", ":", ",", ";", "=", ")", "^"):
                return None
    return u


def _designator_then_eq(stmt: list[Tok]) -> bool:
    """True for `a.b[i]^ = expr` — a comparison written where an assignment belongs."""
    if not stmt or stmt[0].kind not in ("word", "dstr"):
        return False
    if stmt[0].kind == "word" and stmt[0].up in KEYWORDS:
        return False
    i = 1
    while i < len(stmt):
        t = stmt[i]
        if _is_op(t, ".") and i + 1 < len(stmt) and stmt[i + 1].kind == "word":
            i += 2
        elif _is_op(t, "^"):
            i += 1
        elif _is_op(t, "["):
            depth = 0
            while i < len(stmt):
                if _is_op(stmt[i], "["):
                    depth += 1
                elif _is_op(stmt[i], "]"):
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            i += 1
        else:
            break
    return i < len(stmt) and _is_op(stmt[i], "=")


def lint_st(src: str, mode: str = "file") -> tuple[list[Finding], StAnalysis]:
    toks, findings = tokenize(src)
    an = StAnalysis()
    root = _Frame("<root>", 0, scope={}, body=(mode != "declaration"))
    stack: list[_Frame] = [root]
    pending: tuple[str, str, int] | None = None  # (awaited keyword, opener, line)
    stmt: list[Tok] = []
    paren = 0

    def scope_frame() -> _Frame:
        for fr in reversed(stack):
            if fr.scope is not None:
                return fr
        return root

    def in_decl() -> bool:
        return stack[-1].kw in DECL_OPENERS

    def in_body() -> bool:
        return scope_frame().body and not in_decl()

    def fail_pending(at_line: int) -> None:
        nonlocal pending
        if pending:
            awaited, opener, line = pending
            findings.append(error("ST003", f"{opener} at line {line} has no {awaited} before line {at_line}", line))
            pending = None

    def end_statement(t: Tok) -> None:
        nonlocal stmt, paren
        if paren:
            findings.append(error("ST006", "unbalanced parentheses/brackets in statement", t.line))
            paren = 0
        if stack[-1].kw in VAR_KINDS:
            _declaration(stmt)
        elif in_body() and stmt:
            s = stmt
            if stack[-1].kw == "CASE":  # strip a case label: `1, 2:` / `E.Idle:` / `1..5:`
                for k, tk in enumerate(s):
                    if _is_op(tk, ":="):
                        break
                    if _is_op(tk, ":"):
                        s = s[k + 1:]
                        break
            if _designator_then_eq(s):
                findings.append(error("ST010", "statement uses '=' (comparison) where ':=' (assignment) is needed", s[0].line))
        stmt = []

    def _declaration(decl: list[Tok]) -> None:
        colon = next((k for k, tk in enumerate(decl) if _is_op(tk, ":")), None)
        if colon is None:
            return
        names = [tk for tk in decl[:colon] if tk.kind in ("word", "dstr") and tk.up != "AT"]
        tname = ""
        k = colon + 1
        while k < len(decl) and decl[k].kind != "word":
            k += 1
        if k < len(decl) and decl[k].up not in ("ARRAY", "POINTER", "REFERENCE", "REF_TO", "STRING", "WSTRING"):
            # qualified library type: Tc2_Standard.TON -> TON
            while k + 2 < len(decl) and _is_op(decl[k + 1], ".") and _is_word(decl[k + 2]):
                k += 2
            tname = decl[k].up
        scope = scope_frame().scope
        assert scope is not None
        for nm in names:
            key = nm.text.strip('"').upper()
            if key in scope:
                findings.append(error("ST040", f"'{nm.text}' declared twice in the same POU (first at line {scope[key]})", nm.line))
            else:
                scope[key] = nm.line
            if tname and _SCAN_FB_RE.match(tname):
                an.instances.setdefault(key, (nm.text.strip('"'), tname, nm.line))

    for idx, t in enumerate(toks):
        if t.kind == "addr" and not _ADDR_RE.match(t.text):
            findings.append(warning("ST050", f"unusual direct address '{t.text}' (expected e.g. %IX0.0, %QW4, %MD10)", t.line))
        if t.kind == "op":
            if t.text in "([":
                paren += 1
            elif t.text in ")]":
                paren -= 1
            if t.text == ";":
                fail_pending(t.line)
                end_statement(t)
                continue
            if t.text in ("=", "<>") and in_body():
                nxt = toks[idx + 1] if idx + 1 < len(toks) else None
                if nxt is not None and _is_op(nxt, "-") and idx + 2 < len(toks):
                    nxt = toks[idx + 2]
                prev = toks[idx - 1] if idx else None
                # PLCopen CP8 allows exact comparison with 0.0 (e.g. a division guard)
                if any(o is not None and o.real and not _is_zero(o) for o in (prev, nxt)):
                    findings.append(warning("ST020", f"exact '{t.text}' comparison against a REAL literal; compare with a tolerance (ABS(a - b) < eps)", t.line))
            stmt.append(t)
            continue

        kw = _keyword(toks, idx)
        if kw is None:
            if t.kind == "word" and in_body():
                an.has_body = True
                name = t.text.lstrip("#").upper()
                nxt = toks[idx + 1] if idx + 1 < len(toks) else None
                conditional = any(fr.kw in CONDITIONALS for fr in stack)
                in_loop = any(fr.kw in LOOPS for fr in stack)
                if not t.member:
                    if _is_op(nxt, "("):
                        an.calls.append((name, t.line, conditional, in_loop))
                    elif _is_op(nxt, ".") and idx + 3 < len(toks) and toks[idx + 2].up in _TIMER_MEMBER_CALLS and _is_op(toks[idx + 3], "("):
                        an.calls.append((name, t.line, conditional, in_loop))
                    elif _is_op(nxt, "."):
                        an.member_refs.setdefault(name, t.line)
            stmt.append(t)
            continue

        # PROGRAM inside RESOURCE/CONFIGURATION is an instance declaration (P1 WITH Task : Type), not a POU
        if kw == "PROGRAM" and stack[-1].kw in ("RESOURCE", "CONFIGURATION"):
            stmt.append(t)
            continue

        # --- keyword handling ---
        if pending and kw != pending[0] and (kw in OPENERS or kw in CLOSERS or kw in ("ELSIF", "ELSE", "UNTIL", "THEN", "DO", "OF")):
            fail_pending(t.line)

        if kw in ("THEN", "DO", "OF"):
            if pending and pending[0] == kw:
                pending = None
            if in_body() or kw != "OF":
                stmt = []
                paren = 0
            else:
                stmt.append(t)
            continue

        if kw in OPENERS:
            if kw in EXPECT:
                pending = (EXPECT[kw], kw, t.line)
            fr = _Frame(kw, t.line)
            if kw in SCOPE_OPENERS:
                fr.scope = {}
                fr.body = kw in ("ACTION", "TRANSITION")
                if kw in HEADER_KINDS and an.header is None:
                    k = idx + 1
                    while k < len(toks) and toks[k].kind == "word" and toks[k].up in MODIFIERS:
                        k += 1
                    if k < len(toks) and toks[k].kind in ("word", "dstr"):
                        an.header = (kw, toks[k].text.strip('"'))
            stack.append(fr)
            stmt = []
            continue

        if kw == "ELSIF":
            if stack[-1].kw != "IF":
                findings.append(error("ST002", "ELSIF outside an IF block", t.line))
            pending = ("THEN", "ELSIF", t.line)
            stmt = []
            continue
        if kw == "ELSE":
            if stack[-1].kw not in ("IF", "CASE"):
                findings.append(error("ST002", "ELSE outside an IF or CASE block", t.line))
            stmt = []
            continue
        if kw == "UNTIL":
            if stack[-1].kw != "REPEAT":
                findings.append(error("ST002", "UNTIL outside a REPEAT block", t.line))
            stmt = [t]
            continue
        if kw in ("EXIT", "CONTINUE"):
            if not any(fr.kw in LOOPS for fr in stack):
                findings.append(error("ST005", f"{kw} outside FOR/WHILE/REPEAT", t.line))
            stmt.append(t)
            continue
        if kw == "BEGIN":
            scope_frame().body = True
            stmt = []
            continue

        if kw in CLOSERS:
            expected = CLOSERS[kw]
            pos = next((k for k in range(len(stack) - 1, 0, -1) if stack[k].kw in expected), None)
            if pos is None:
                findings.append(error("ST002", f"{kw} without a matching {'/'.join(sorted(expected))}", t.line))
            else:
                for fr in stack[pos + 1:]:
                    findings.append(error("ST002", f"{fr.kw} opened at line {fr.line} is not closed before {kw}", fr.line))
                closed = stack[pos]
                del stack[pos:]
                if closed.kw in VAR_KINDS:
                    scope_frame().body = True
            stmt = []
            paren = 0
            continue

        stmt.append(t)

    if pending:
        awaited, opener, line = pending
        findings.append(error("ST003", f"{opener} at line {line} has no {awaited}", line))
    leftover = stack[1:]
    if mode == "declaration" and leftover and leftover[0].kw in SCOPE_OPENERS:
        leftover = leftover[1:]
    for fr in leftover:
        findings.append(error("ST002", f"{fr.kw} opened at line {fr.line} is never closed", fr.line))
    if paren:
        findings.append(error("ST006", "unbalanced parentheses/brackets at end of text", toks[-1].line if toks else None))
    return findings, an


def scan_call_findings(analyses: list[StAnalysis], extra_instances: dict[str, tuple[str, str, int]] | None = None) -> list[Finding]:
    """Timer / edge / counter instances that are not called exactly once, unconditionally."""
    instances: dict[str, tuple[str, str, int]] = {}
    for an in analyses:
        instances.update(an.instances)
    if extra_instances:
        instances.update(extra_instances)
    if not any(an.has_body for an in analyses):
        return []
    calls: dict[str, list[tuple[int, bool, bool]]] = {}
    refs: dict[str, int] = {}
    for an in analyses:
        for name, line, cond, loop in an.calls:
            calls.setdefault(name, []).append((line, cond, loop))
        for name, line in an.member_refs.items():
            refs.setdefault(name, line)
    out: list[Finding] = []
    for key, (name, tname, dline) in sorted(instances.items(), key=lambda kv: kv[1][2]):
        sites = calls.get(key, [])
        if not sites:
            if key in refs:
                out.append(warning("ST033", f"{tname} instance '{name}' is read but never called, so its outputs never update", refs[key]))
            continue
        if all(cond for _, cond, _ in sites):
            out.append(warning(
                "ST030",
                f"{tname} instance '{name}' is only called inside IF/CASE; when the branch is not taken the "
                "instance is not evaluated (timers freeze, edges are missed). Call it every scan and gate its input instead",
                sites[0][0],
            ))
        if len(sites) > 1:
            out.append(warning("ST031", f"{tname} instance '{name}' is called at {len(sites)} places (lines {', '.join(str(s[0]) for s in sites)}); call each instance once per scan", sites[1][0]))
        loop_site = next((s for s in sites if s[2]), None)
        if loop_site:
            out.append(warning("ST032", f"{tname} instance '{name}' is called inside a loop, i.e. several times per scan", loop_site[0]))
    return out


def check_st_file(text: str) -> list[Finding]:
    findings, an = lint_st(text, "file")
    return findings + scan_call_findings([an])
