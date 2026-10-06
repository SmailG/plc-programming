"""Rockwell Studio 5000 Logix Designer exports: L5X (XML) and L5K (text)."""

from __future__ import annotations

import re

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
_INSTR = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\(")


def _split_operands(s: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts] if any(p.strip() for p in parts) else []


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
    for m in _INSTR.finditer(t):
        start, depth, i = m.end(), 1, m.end()
        while i < len(t) and depth:
            depth += {"(": 1, ")": -1}.get(t[i], 0)
            i += 1
        ops = _split_operands(t[start:i - 1])
        mnem = m.group(1).upper()
        if mnem in ARITY and len(ops) != ARITY[mnem]:
            out.append(warning("LX022", f"{mnem} takes {ARITY[mnem]} operand(s), found {len(ops)}", line, ctx))
        if mnem == "OTE" and ops:
            otes.append(ops[0])
    return out, otes


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
                for rung in r.iter("Rung"):
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
                continue
            pos = next((k for k in range(len(stack) - 1, -1, -1) if stack[k][0] == word), None)
            if pos is None:
                out.append(error("LX050", f"END_{word} without an open {word}", lineno))
                continue
            for kw, ln in stack[pos + 1:]:
                out.append(error("LX050", f"{kw} opened at line {ln} is not closed before END_{word}", ln))
            closed = stack[pos]
            del stack[pos:]
            if closed[0] == "ST_ROUTINE" and st_lines:
                src = "\n" * (st_lines[0][0] - 1) + "\n".join(t for _, t in st_lines)
                f, _ = lint_st(src, "body")
                out.extend(with_context(f, "L5K ST routine"))
                st_lines = []
    for kw, ln in stack:
        out.append(error("LX050", f"{kw} opened here is never closed", ln))
    return out
