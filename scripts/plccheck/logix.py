"""Rockwell Studio 5000 Logix Designer exports: L5X (XML) and L5K (text)."""

from __future__ import annotations

import re
from bisect import bisect_left
from collections import Counter
from itertools import tee, zip_longest

from .findings import Finding, error, warning, with_context
from .st import lint_st
from .xmlutil import Node

ROUTINE_TYPES = {"RLL", "ST", "FBD", "SFC"}
# Operand counts from the neutral-text table of the Logix 5000 Import/Export Reference
# Manual (1756-RM014D). Studio 5000 v36 renamed compare/move/math mnemonics to IEC names
# (EQU->EQ, MOV->MOVE, LIM->LIMIT, ...); both spellings are listed.
ARITY = {
    "XIC": 1, "XIO": 1, "OTE": 1, "OTL": 1, "OTU": 1, "ONS": 1, "OSR": 2, "OSF": 2,
    "TON": 3, "TOF": 3, "RTO": 3, "CTU": 3, "CTD": 3, "RES": 1,
    "MOV": 2, "MOVE": 2, "COP": 3, "CPS": 3, "FLL": 3, "CLR": 1,
    "ADD": 3, "SUB": 3, "MUL": 3, "DIV": 3, "MOD": 3, "CPT": 2,
    "EQU": 2, "NEQ": 2, "GRT": 2, "GEQ": 2, "LES": 2, "LEQ": 2,
    "EQ": 2, "NE": 2, "GT": 2, "GE": 2, "LT": 2, "LE": 2,
    "LIM": 3, "LIMIT": 3, "MEQ": 3, "CMP": 1,
    "JMP": 1, "LBL": 1, "AFI": 0, "NOP": 0, "TND": 0, "MCR": 0, "UID": 0, "UIE": 0,
    "GSV": 4, "SSV": 4, "MSG": 1, "PSC": 0, "PCMD": 3,
}
# `NAME(`, found at the start of an identifier run (leading digits skipped). Without the lookbehind every
# position of a long run would rescan it for a `(`.
_INSTR = re.compile(r"(?<![A-Za-z0-9_])[0-9]*([A-Za-z_][A-Za-z0-9_]*)\(")


def _instructions(t: str) -> list[tuple[str, int, str | None]]:
    """(mnemonic, operand count, first operand) for each `NAME(` in the neutral text, in order.

    The operands are the comma-separated parts, at bracket depth 0, between the instruction's
    parentheses; a missing `)` runs to the end of the text less its last character. The count is 0
    when every part is blank. The first operand is "" when there is none, and None when it holds
    another instruction (a `NAME(`): that is a call, not a tag, and keeping a copy of it for every
    instruction around it would grow with the square of the nesting depth. A bare `(` does not
    count, so `Arr[(i+1)]` stays an operand.

    One pass over the text: parentheses matched with a stack, commas kept by bracket depth, and the
    operands of each instruction read from those, so no instruction rescans its own operand text.
    """
    n = len(t)
    depth_before = [0] * (n + 1)  # bracket depth ( [ ) ] before each character
    text_before = [0] * (n + 1)  # non-whitespace characters before each character
    close: dict[int, int] = {}  # index of each `(` -> index of its `)`
    commas: dict[int, list[int]] = {}  # bracket depth -> indexes of the commas at that depth
    opened: list[int] = []
    depth = chars = 0
    for k, ch in enumerate(t):
        depth_before[k], text_before[k] = depth, chars
        if ch == ",":
            commas.setdefault(depth, []).append(k)
        elif ch == "(":
            opened.append(k)
            depth += 1
        elif ch == ")":
            if opened:
                close[opened.pop()] = k
            depth -= 1
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if not ch.isspace():
            chars += 1
    depth_before[n], text_before[n] = depth, chars
    found: list[tuple[str, int, str | None]] = []
    # Each match is paired with the next. Matches do not overlap, so only the next one can lie inside this one's operands.
    current, following = tee(_INSTR.finditer(t))
    next(following, None)
    for m, after in zip_longest(current, following):
        start = m.end()
        end = close.get(start - 1, n - 1)
        top = commas.get(depth_before[start], [])  # a comma at the depth the operands start at is a separator
        first, last = bisect_left(top, start), bisect_left(top, end)
        separators = max(last - first, 0)
        has_operand = end > start and text_before[end] - text_before[start] > separators
        first_operand: str | None = ""
        if has_operand:
            stop = top[first] if separators else end
            first_operand = None if after is not None and after.end() <= stop else t[start:stop].strip()
        found.append((m.group(1).upper(), separators + 1 if has_operand else 0, first_operand))
    return found


def check_rung(text: str, line: int, ctx: str) -> tuple[list[Finding], list[str]]:
    """Neutral-text rung: brackets, terminating ';', operand counts. Returns OTE operands."""
    out: list[Finding] = []
    t = text.strip()
    if not t:
        return out, []
    if not t.endswith(";"):
        out.append(error("LX020", "rung text must end with ';'", line, ctx))
    paren = bracket = 0
    for ch in t:
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[" and paren == 0:
            bracket += 1
        elif ch == "]" and paren == 0:
            bracket -= 1
        elif ch == "," and paren == 0 and bracket == 0:
            out.append(error("LX021", "',' outside a branch '[ … ]'", line, ctx))
        if paren < 0 or bracket < 0:
            break
    if paren:
        out.append(error("LX021", "unbalanced parentheses", line, ctx))
    if bracket:
        out.append(error("LX021", "unbalanced branch brackets", line, ctx))
    otes: list[str] = []
    for mnem, count, first_operand in _instructions(t):
        if mnem in ARITY and count != ARITY[mnem]:
            out.append(warning("LX022", f"{mnem} takes {ARITY[mnem]} operand(s), found {count}", line, ctx))
        if mnem == "OTE" and count and first_operand is not None:
            otes.append(first_operand)
    return out, otes


def _own_rungs(routine: Node):
    """Rung elements of this routine in document order, not descending into a nested <Routines>.

    A nested <Routines> is visited by the caller as a scope of its own. Iterating the whole subtree
    per routine would check a nested rung once for every routine around it.
    """
    stack = list(reversed(routine.children))
    while stack:
        node = stack.pop()
        if node.tag == "Rung":
            yield node
        if node.tag != "Routines":
            stack.extend(reversed(node.children))


def check_l5x(root: Node) -> list[Finding]:
    out: list[Finding] = []
    if root.tag != "RSLogix5000Content":
        return [error("LX001", f"root element is <{root.tag}>, expected <RSLogix5000Content>", root.line)]
    for attr in ("SchemaRevision", "SoftwareRevision", "TargetType"):
        if root.get(attr) is None:
            out.append(error("LX002", f"<RSLogix5000Content> lacks {attr}", root.line))
    if root.get("TargetType") == "Controller" and root.find("Controller") is None:
        out.append(error("LX003", "TargetType is Controller but there is no <Controller>", root.line))

    for tags in root.iter("Tags"):
        seen: dict[str, int] = {}
        for tag in tags.findall("Tag"):
            key = (tag.get("Name") or "").upper()
            if key in seen:
                out.append(error("LX011", f"tag '{tag.get('Name')}' defined twice in one scope (first at line {seen[key]})", tag.line))
            seen[key] = tag.line

    for routines in root.iter("Routines"):
        seen = {}
        owner = routines.parent.get("Name") if routines.parent is not None else ""
        coils: dict[str, list[int]] = {}
        for r in routines.findall("Routine"):
            rname = r.get("Name") or ""
            ctx = f"{owner}/{rname}"
            if rname.upper() in seen:
                out.append(error("LX010", f"routine '{rname}' defined twice", r.line, ctx))
            seen[rname.upper()] = r.line
            rtype = r.get("Type")
            if rtype not in ROUTINE_TYPES:
                out.append(warning("LX010", f"unknown routine Type '{rtype}'", r.line, ctx))
            if rtype == "RLL":
                for rung in _own_rungs(r):
                    text_node = rung.find("Text")
                    if text_node is None:
                        continue
                    f, otes = check_rung(text_node.text, text_node.text_line or text_node.line, f"{ctx} rung {rung.get('Number')}")
                    out.extend(f)
                    for op in otes:
                        coils.setdefault(op.upper(), []).append(text_node.line)
            elif rtype == "ST":
                content = r.find("STContent")
                if content is None:
                    continue
                lines = sorted(content.findall("Line"), key=lambda n: int(n.get("Number", "0") or 0))
                src = "\n".join(n.text for n in lines)
                f, _ = lint_st(src, "body")
                first = lines[0].line if lines else r.line
                out.extend(with_context(f, f"{ctx} (ST)", first - 1))
        for op, lines in coils.items():
            if len(lines) > 1:
                out.append(warning("LX040", f"OTE({op}) is written on {len(lines)} rungs (lines {', '.join(map(str, lines))}); the last one wins", lines[1], owner))
    return out


L5K_BLOCKS = {"CONTROLLER", "PROGRAM", "ROUTINE", "ST_ROUTINE", "FBD_ROUTINE", "TAG", "DATATYPE",
              "MODULE", "TASK", "ADD_ON_INSTRUCTION_DEFINITION", "PARAMETERS", "LOCAL_TAGS", "CONFIG"}


def check_l5k(text: str) -> list[Finding]:
    """L5K text (RM014D): END_x closes the nearest open x (several may share a line);
    rungs are `N: neutral text;`; ST routine lines start with a single quote."""
    out: list[Finding] = []
    stack: list[tuple[str, int]] = []
    open_words: Counter[str] = Counter()  # open frames per keyword, so "is X open" is not a stack scan
    ends = set(re.findall(r"\bEND_([A-Z][A-Z0-9_]*)\b", text))
    st_lines: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("'"):
            if stack and stack[-1][0] == "ST_ROUTINE":
                st_lines.append((lineno, line[1:]))
            continue
        rung = re.match(r"N:\s*(.*)$", line)
        if rung:
            f, _ = check_rung(rung.group(1), lineno, "L5K rung")
            out.extend(f)
            continue
        code = re.sub(r'"(?:[^"]|"")*"', '""', line)  # descriptions may contain keywords
        for end, word in re.findall(r"\b(END_)?([A-Z][A-Z0-9_]*)\b", code):
            if not end:
                if word in L5K_BLOCKS or word in ends:
                    stack.append((word, lineno))
                    open_words[word] += 1
                continue
            if not open_words[word]:  # else the scan would walk the whole stack to find nothing
                out.append(error("LX050", f"END_{word} without an open {word}", lineno))
                continue
            pos = next(k for k in range(len(stack) - 1, -1, -1) if stack[k][0] == word)
            for kw, ln in stack[pos + 1:]:
                out.append(error("LX050", f"{kw} opened at line {ln} is not closed before END_{word}", ln))
            closed = stack[pos]
            for kw, _ in stack[pos:]:
                open_words[kw] -= 1
            del stack[pos:]
            if closed[0] == "ST_ROUTINE" and st_lines:
                f, _ = lint_st("\n".join(t for _, t in st_lines), "body", st_lines[0][0])
                out.extend(with_context(f, "L5K ST routine"))
                st_lines = []
    for kw, ln in stack:
        out.append(error("LX050", f"{kw} opened here is never closed", ln))
    return out
