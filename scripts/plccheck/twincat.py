"""Beckhoff TwinCAT 3 PLC object files (.TcPOU/.TcDUT/.TcGVL/.TcIO)."""

from __future__ import annotations

import re
from pathlib import Path

from .findings import Finding, error, warning, with_context
from .st import lint_st, scan_call_findings
from .xmlutil import Node

GUID_RE = re.compile(r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$")
OBJECT_KINDS = {"POU", "DUT", "GVL", "Itf"}
HEADER_FOR = {
    "POU": {"PROGRAM", "FUNCTION_BLOCK", "FUNCTION"},
    "Itf": {"INTERFACE"},
    "Method": {"METHOD"},
    "Property": {"PROPERTY"},
}
_FIRST_KW = re.compile(r"\b(PROGRAM|FUNCTION_BLOCK|FUNCTION|INTERFACE|METHOD|PROPERTY|TYPE|VAR_GLOBAL)\b", re.I)


def _blank_spans(text: str, opener: str, closer: str) -> str:
    """Replace each non-nested `opener ... closer` span by one space.

    Single pass with str.find. The closer is searched after the opener's own characters, so
    `(*)` is not a comment. An opener with no closer after it ends the scan: a later opener has
    none either, and retrying from each one (as a lazy regex does) is quadratic.
    """
    parts: list[str] = []
    pos = 0
    while True:
        start = text.find(opener, pos)
        if start < 0:
            break
        end = text.find(closer, start + len(opener))
        if end < 0:
            break
        parts.append(text[pos:start])
        parts.append(" ")
        pos = end + len(closer)
    parts.append(text[pos:])
    return "".join(parts)


def _blank_line_comments(text: str) -> str:
    """Replace each `//` up to, not including, the end of its line by one space."""
    parts: list[str] = []
    pos = 0
    while True:
        start = text.find("//", pos)
        if start < 0:
            break
        end = text.find("\n", start + 2)
        parts.append(text[pos:start])
        parts.append(" ")
        if end < 0:
            pos = len(text)
            break
        pos = end
    parts.append(text[pos:])
    return "".join(parts)


def _strip_comments(text: str) -> str:
    text = _blank_spans(text, "(*", "*)")
    text = _blank_spans(text, "/*", "*/")
    text = _blank_line_comments(text)
    return _blank_spans(text, "{", "}")


def check_twincat(root: Node, path: Path | None = None) -> list[Finding]:
    out: list[Finding] = []
    if root.tag != "TcPlcObject":
        return [error("TC001", f"root element is <{root.tag}>, expected <TcPlcObject>", root.line)]
    if root.get("Version") is None:
        out.append(warning("TC002", "<TcPlcObject> has no Version attribute", root.line))
    objects = [c for c in root.children if c.tag in OBJECT_KINDS]
    if not objects:
        return out  # Task, TextList, Visu…: nothing we check
    ids: dict[str, int] = {}
    for node in root.iter():
        if node is root or node.get("Id") is None:
            continue
        nid = node.get("Id")
        if not GUID_RE.match(nid):
            out.append(warning("TC004", f"Id '{nid}' is not a {{GUID}}", node.line))
        if nid.lower() in ids:
            out.append(error("TC005", f"duplicate Id {nid} (first at line {ids[nid.lower()]})", node.line))
        ids[nid.lower()] = node.line
    for obj in objects:
        out.extend(_check_object(obj, path))
    return out


def _decl(node: Node) -> Node | None:
    return node.find("Declaration")


def _impl_st(node: Node) -> Node | None:
    impl = node.find("Implementation")
    return impl.find("ST") if impl is not None else None


def _check_object(obj: Node, path: Path | None) -> list[Finding]:
    out: list[Finding] = []
    name = obj.get("Name")
    ctx = f"{obj.tag} {name}"
    if not name or obj.get("Id") is None:
        out.append(error("TC004", f"<{obj.tag}> needs Name and Id", obj.line))
    if path is not None and name and path.stem.lower() != name.lower():
        out.append(warning("TC012", f"file name '{path.name}' does not match object name '{name}'", obj.line))

    analyses = []
    parts: list[tuple[Node, str, str]] = [(obj, obj.tag, ctx)]
    for child in obj.children:
        if child.tag in ("Method", "Property", "Action", "Transition"):
            parts.append((child, child.tag, f"{ctx}.{child.get('Name')}"))
            for acc in child.children:
                if acc.tag in ("Get", "Set"):
                    parts.append((acc, acc.tag, f"{ctx}.{child.get('Name')}.{acc.tag}"))
    for node, kind, pctx in parts:
        decl = _decl(node)
        if decl is None and kind not in ("Action", "Transition"):
            out.append(error("TC006", f"<{kind}> has no <Declaration>", node.line, pctx))
        if decl is not None:
            out.extend(_check_header(kind, node, decl, pctx))
            f, an = lint_st(decl.text, "declaration")
            out.extend(with_context(f, f"{pctx} declaration", (decl.text_line or decl.line) - 1))
            analyses.append(an.shifted((decl.text_line or decl.line) - 1))
        st = _impl_st(node)
        if st is not None:
            f, an = lint_st(st.text, "body")
            out.extend(with_context(f, f"{pctx} implementation", (st.text_line or st.line) - 1))
            analyses.append(an.shifted((st.text_line or st.line) - 1))
    out.extend(with_context(scan_call_findings(analyses), ctx))
    return out


def _check_header(kind: str, node: Node, decl: Node, ctx: str) -> list[Finding]:
    text = _strip_comments(decl.text)
    m = _FIRST_KW.search(text)
    line = decl.text_line or decl.line
    if kind == "DUT":
        return [] if (m and m.group(1).upper() == "TYPE") else [error("TC010", "DUT declaration must start with TYPE", line, ctx)]
    if kind == "GVL":
        return [] if (m and m.group(1).upper() == "VAR_GLOBAL") else [error("TC010", "GVL declaration must contain VAR_GLOBAL", line, ctx)]
    expected = HEADER_FOR.get(kind)
    if not expected:
        return []
    if not m or m.group(1).upper() not in expected:
        return [error("TC010", f"{kind} declaration must start with {' / '.join(sorted(expected))}", line, ctx)]
    after = text[m.end():]
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", after)
    words = [w for w in words if w.upper() not in ("PUBLIC", "PRIVATE", "PROTECTED", "INTERNAL", "ABSTRACT", "FINAL")]
    declared = words[0] if words else ""
    if declared.lower() != (node.get("Name") or "").lower():
        return [error("TC011", f"declaration names '{declared}' but the object is '{node.get('Name')}'", line, ctx)]
    return []
