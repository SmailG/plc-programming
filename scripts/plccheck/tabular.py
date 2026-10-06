"""CSV tag / variable lists (bulk engineering: Freelance BDM, TIA tag tables, I/O lists).

Multi-record exports (for example a whole ABB Freelance project CSV) legitimately mix
row widths, so width differences are warnings, never errors.
"""

from __future__ import annotations

import csv
import io
from collections import Counter

from .findings import Finding, error, warning


def decode(data: bytes) -> tuple[str | None, str]:
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if data.startswith(bom):
            return data.decode(enc), enc
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), "cp1252 (guessed)"


def check_csv(data: bytes) -> list[Finding]:
    out: list[Finding] = []
    text, enc = decode(data)
    if text is None:
        return [error("CS001", "cannot decode file", None)]
    if "�" in text:
        out.append(warning("CS001", f"undecodable bytes; read as {enc}", None))
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
    except csv.Error:  # ragged files defeat the sniffer; the header line decides
        header_line = sample.splitlines()[0] if sample else ""
        delim = max(";,\t|", key=header_line.count)
        dialect = type("HeaderDialect", (csv.excel,), {"delimiter": delim})
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if not rows:
        return out
    widths = Counter(len(r) for r in rows)
    common, _ = widths.most_common(1)[0]
    if len(widths) > 1:
        odd = [i + 1 for i, r in enumerate(rows) if len(r) != common][:5]
        out.append(warning("CS002", f"rows have {len(widths)} different widths (most have {common}); first odd rows: {odd}. Normal for multi-record exports, a defect for a single table", None))
        return out
    header = [h.strip().upper() for h in rows[0]]
    dup_cols = [h for h, n in Counter(header).items() if n > 1 and h]
    if dup_cols:
        out.append(warning("CS003", f"duplicate column names: {', '.join(dup_cols)}", 1))
    if header and header[0].replace(" ", "").replace("_", "") in NAME_COLUMNS:
        keys: dict[str, int] = {}
        dups = 0
        for i, r in enumerate(rows[1:], start=2):
            k = r[0].strip().upper() if r else ""
            if k and k in keys:
                dups += 1
                if dups <= 20:
                    out.append(warning("CS004", f"name '{r[0].strip()}' in data row {i} repeats row {keys[k]}", None))
            keys.setdefault(k, i)
        if dups > 20:
            out.append(warning("CS004", f"{dups - 20} further duplicate names not listed", None))
    return out


NAME_COLUMNS = {"NAME", "TAG", "TAGNAME", "SYMBOL", "SYMBOLNAME", "VARIABLE", "VARIABLENAME", "IDENTIFIER"}
