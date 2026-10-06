"""Schneider EcoStruxure Control Expert exchange files: XEF (FEFExchangeFile) and XSY
(VariablesExchangeFile). Machine Expert exchanges PLCopenXML, handled by plcopen.py."""

from __future__ import annotations

from .findings import Finding, error, warning, with_context
from .st import lint_st
from .xmlutil import Node

ROOTS = {"FEFExchangeFile", "VariablesExchangeFile"}


def check_control_expert(root: Node) -> list[Finding]:
    out: list[Finding] = []
    if root.tag not in ROOTS:
        return [error("CX001", f"root element is <{root.tag}>, expected <FEFExchangeFile> or <VariablesExchangeFile>", root.line)]
    if root.find("fileHeader") is None:
        out.append(error("CX002", "missing <fileHeader>", root.line))

    for block in root.iter("dataBlock"):
        seen: dict[str, int] = {}
        addrs: dict[str, str] = {}
        for var in block.findall("variables"):
            name = var.get("name") or ""
            if name.upper() in seen:
                out.append(error("CX010", f"variable '{name}' declared twice (first at line {seen[name.upper()]})", var.line))
            seen[name.upper()] = var.line
            addr = var.get("topologicalAddress")
            if addr:
                if addr.upper() in addrs:
                    out.append(warning("CX011", f"'{name}' and '{addrs[addr.upper()]}' share address {addr}", var.line))
                addrs.setdefault(addr.upper(), name)

    for fb in root.iter("FBSource"):
        ctx = f"DFB {fb.get('nameOfFBType')}"
        seen = {}
        for section in fb.children:
            for var in section.findall("variables"):
                name = var.get("name") or ""
                if name.upper() in seen:
                    out.append(error("CX012", f"DFB parameter/variable '{name}' declared twice", var.line, ctx))
                seen[name.upper()] = var.line
        for st in fb.iter("STSource"):
            f, _ = lint_st(st.text, "body")
            out.extend(with_context(f, f"{ctx} (ST)", (st.text_line or st.line) - 1))

    for prog in root.findall("program"):
        ident = prog.find("identProgram")
        ctx = f"section {ident.get('name')} ({ident.get('task')})" if ident is not None else "section"
        for st in prog.iter("STSource"):
            f, _ = lint_st(st.text, "body")
            out.extend(with_context(f, f"{ctx} (ST)", (st.text_line or st.line) - 1))
    return out
