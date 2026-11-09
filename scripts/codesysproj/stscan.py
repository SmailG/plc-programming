"""Scanning ST source text for identifier paths: noise removal and a path scanner.

Used by xref.py. The scanner reads text, not a grammar: it finds `a.b[c].d` style paths, skips numbers,
typed literals and addresses, and reports each path with its position. What a path means is decided by
the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LITERAL_TAIL_RE = re.compile(r"[A-Za-z0-9_#.]*")
_ADDRESS_RE = re.compile(r"%[A-Za-z0-9_.]*")


@dataclass
class NameRef:
    segments: List[str]  # as written, indexes removed
    start: int
    end: int
    in_index: bool


def strip_noise(text: str) -> str:
    """Comments (`(* *)` nest, `//`), pragmas `{ }` and string literals become spaces; newlines and
    every position stay, so an offset in the result is an offset in the text. Unterminated ones run to the end."""
    out = list(text)
    n, i, depth = len(text), 0, 0
    while i < n:
        two = text[i:i + 2]
        if two == "(*":
            depth += 1
            start, i = i, i + 2
            while i < n and depth:
                if text.startswith("(*", i):
                    depth, i = depth + 1, i + 2
                elif text.startswith("*)", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            _blank(out, start, i)
        elif two == "//":
            start = i
            i = text.find("\n", i)
            i = n if i == -1 else i
            _blank(out, start, i)
        elif text[i] == "{":
            start = i
            i = text.find("}", i)
            i = n if i == -1 else i + 1
            _blank(out, start, i)
        elif text[i] in "'\"":
            start, quote = i, text[i]
            i += 1
            while i < n and text[i] != quote:
                i += 2 if text[i] == "$" else 1
            i = min(i + 1, n)
            _blank(out, start, i)
        else:
            i += 1
    return "".join(out)


def _blank(out: List[str], start: int, end: int) -> None:
    for k in range(start, min(end, len(out))):
        if out[k] != "\n":
            out[k] = " "


def _matching_bracket(code: str, at: int) -> int:
    depth = 0
    for k in range(at, len(code)):
        depth += code[k] == "["
        depth -= code[k] == "]"
        if depth == 0:
            return k
    return len(code) - 1


def scan_paths(code: str, base: int = 0, in_index: bool = False) -> List[NameRef]:
    """Every identifier path in (noise-free) code: `a.b[c].d` is one path `a.b.d` plus the path `c`
    found inside the index. Numbers, typed literals (`T#5s`, `16#FF`) and addresses are skipped."""
    paths: List[NameRef] = []
    n, i = len(code), 0
    while i < n:
        c = code[i]
        if c.isdigit():
            i = _skip_number(code, i)
        elif c == "%":
            i = _ADDRESS_RE.match(code, i).end()
        elif c.isalpha() or c == "_":
            i = _scan_one_path(code, i, base, in_index, paths)
        else:
            i += 1
    return paths


def _skip_number(code: str, i: int) -> int:
    while i < len(code):
        if code[i].isalnum() or code[i] in "_#":
            i += 1
        elif code[i] == "." and code[i + 1:i + 2].isdigit():
            i += 1
        else:
            break
    return i


def _scan_one_path(code: str, i: int, base: int, in_index: bool, paths: List[NameRef]) -> int:
    start, segments = i, []
    nested: List[NameRef] = []
    while True:
        match = IDENT_RE.match(code, i)
        segments.append(match.group())
        i = match.end()
        while i < len(code) and code[i] in "[^":
            if code[i] == "[":
                close = _matching_bracket(code, i)
                nested += scan_paths(code[i + 1:close], base + i + 1, True)
                i = close + 1
            else:
                i += 1
        if code[i:i + 1] == "#":  # a typed literal such as REAL#1.0, not a variable
            return _LITERAL_TAIL_RE.match(code, i).end()
        follows = code[i + 1:i + 2]
        if code[i:i + 1] == "." and (follows.isalpha() or follows == "_"):
            i += 1
            continue
        break
    paths.append(NameRef(segments, base + start, base + i, in_index))
    paths.extend(nested)
    return i
