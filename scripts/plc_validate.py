#!/usr/bin/env python3
"""Structural validator for PLC source and exchange files. Standard library only.

    plc_validate.py FILE_OR_DIR... [--format FMT] [--xsd SCHEMA.xsd] [--json] [--strict]
    plc_validate.py --hook      (Claude Code PostToolUse hook: reads the event on stdin)

Recognised: IEC ST / Siemens SCL (.st .scl), SIMATIC SD (.s7dcl), PLCopen XML TC6
v2.0/v2.01, IEC 61131-10, SimaticML, TwinCAT (.TcPOU .TcDUT .TcGVL .TcIO), Rockwell
L5X/L5K, Control Expert XEF/XSY, IEC 61499 (.fbt .adp .sub), AutomationML (.aml),
DEXPI, CSV tag lists.

A clean result means "structurally plausible". It is not a compile: no type checking,
no cross-file symbol resolution. Say so when reporting results.

Exit: 0 no errors, 1 errors (or warnings with --strict), 2 usage problem.
In --hook mode: exit 2 with the errors on stderr so Claude sees them; warnings are
returned as additionalContext; files that are not PLC files are ignored silently.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plccheck.aml import check_aml  # noqa: E402
from plccheck.dexpi import check_dexpi  # noqa: E402
from plccheck.findings import Finding, error, warning  # noqa: E402
from plccheck.iec61499 import ROOTS as FB_ROOTS, check_iec61499  # noqa: E402
from plccheck.logix import check_l5k, check_l5x  # noqa: E402
from plccheck.plcopen import IEC_61131_10_NS, TC6_NAMESPACES, check_iec61131_10, check_plcopen  # noqa: E402
from plccheck.schneider import ROOTS as CX_ROOTS, check_control_expert  # noqa: E402
from plccheck.simaticml import check_simatic_sd, check_simaticml  # noqa: E402
from plccheck.st import check_st_file  # noqa: E402
from plccheck.tabular import check_csv, decode  # noqa: E402
from plccheck.twincat import check_twincat  # noqa: E402
from plccheck.xmlutil import XmlError, parse_bytes, sniff_root  # noqa: E402

FORMATS = ("st", "simatic-sd", "plcopen", "iec61131-10", "simaticml", "twincat", "l5x", "l5k",
           "control-expert", "iec61499", "aml", "dexpi", "csv")
TEXT_EXT = {".st": "st", ".scl": "st", ".iecst": "st", ".s7dcl": "simatic-sd", ".l5k": "l5k", ".csv": "csv"}
XML_EXT = {".xml", ".tcpou", ".tcdut", ".tcgvl", ".tcio", ".l5x", ".fbt", ".adp", ".sub", ".aml",
           ".xef", ".xsy", ".sys", ".res", ".dev", ".seg"}
# In hook mode, never judge files that are ambiguous outside PLC work.
HOOK_SKIP = {"csv"}


def detect(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in TEXT_EXT:
        return TEXT_EXT[ext]
    if ext not in XML_EXT:
        return None
    root = sniff_root(path)
    if root is None:
        return "xml-broken" if ext not in (".sys", ".res", ".dev", ".seg") else None
    ns, tag = root
    if tag == "project" and ns in TC6_NAMESPACES:
        return "plcopen"
    if tag == "Project" and ns == IEC_61131_10_NS:
        return "iec61131-10"
    if tag == "Document":
        return "simaticml"
    if tag == "TcPlcObject":
        return "twincat"
    if tag == "RSLogix5000Content":
        return "l5x"
    if tag in CX_ROOTS:
        return "control-expert"
    if tag in FB_ROOTS:
        return "iec61499"
    if tag == "CAEXFile":
        return "aml"
    if tag == "PlantModel":
        return "dexpi"
    return None


def run_xsd(path: Path, xsd: Path) -> list[Finding]:
    if shutil.which("xmllint"):
        proc = subprocess.run(["xmllint", "--noout", "--schema", str(xsd), str(path)], capture_output=True, text=True)
        out = []
        for line in proc.stderr.splitlines():
            if " validates" in line or not line.strip():
                continue
            parts = line.split(":", 2)
            lineno = int(parts[1]) if len(parts) > 2 and parts[1].strip().isdigit() else None
            out.append(error("XS001", line.split(":", 2)[-1].strip() if lineno else line.strip(), lineno))
        return out
    try:
        from lxml import etree  # type: ignore
    except ImportError:
        return [warning("XS000", "XSD validation skipped: neither xmllint nor lxml is available")]
    schema = etree.XMLSchema(etree.parse(str(xsd)))
    doc = etree.parse(str(path))
    if schema.validate(doc):
        return []
    return [error("XS001", e.message, e.line) for e in schema.error_log]


def check_file(path: Path, fmt: str | None, xsd: Path | None = None) -> tuple[str | None, list[Finding]]:
    fmt = fmt or detect(path)
    if fmt is None:
        return None, []
    data = path.read_bytes()
    if fmt == "xml-broken":
        try:
            parse_bytes(data)
        except XmlError as exc:
            return fmt, [error("XML001", str(exc), exc.line)]
        return None, []
    if fmt in ("st", "simatic-sd", "l5k"):
        text, _ = decode(data)
        findings = {"st": check_st_file, "simatic-sd": check_simatic_sd, "l5k": check_l5k}[fmt](text)
        return fmt, findings
    if fmt == "csv":
        return fmt, check_csv(data)
    try:
        root = parse_bytes(data)
    except XmlError as exc:
        return fmt, [error("XML001", str(exc), exc.line)]
    checker = {
        "plcopen": lambda r: check_plcopen(r),
        "iec61131-10": lambda r: check_iec61131_10(r),
        "simaticml": lambda r: check_simaticml(r),
        "twincat": lambda r: check_twincat(r, path),
        "l5x": lambda r: check_l5x(r),
        "control-expert": lambda r: check_control_expert(r),
        "iec61499": lambda r: check_iec61499(r),
        "aml": lambda r: check_aml(r, path),
        "dexpi": lambda r: check_dexpi(r),
    }[fmt]
    findings = checker(root)
    if xsd is not None:
        findings = run_xsd(path, xsd) + findings
    return fmt, findings


def iter_paths(args: list[str]):
    for a in args:
        p = Path(a)
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and ".git" not in child.parts:
                    yield child
        else:
            yield p


def hook_main() -> int:
    if os.environ.get("PLC_VALIDATE_HOOK", "1") == "0":
        return 0
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    tool_input = event.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return 0
    path = Path(raw)
    if not path.is_absolute() and event.get("cwd"):
        path = Path(event["cwd"]) / path
    if not path.is_file():
        return 0
    fmt = detect(path)
    if fmt is None or fmt in HOOK_SKIP:
        return 0
    try:
        fmt, findings = check_file(path, fmt)
    except Exception as exc:  # a validator bug must never break the user's edit loop
        print(f"plc_validate internal error on {path.name}: {exc!r}", file=sys.stderr)
        return 1
    errors = [f for f in findings if f.severity == "error"]
    warnings_ = [f for f in findings if f.severity == "warning"]
    if errors:
        lines = [f.format(path.name) for f in errors + warnings_]
        print(f"plc_validate ({fmt}) found {len(errors)} error(s) in {path.name}:\n" + "\n".join(lines), file=sys.stderr)
        return 2
    if warnings_:
        ctx = f"plc_validate ({fmt}) warnings for {path.name}:\n" + "\n".join(f.format(path.name) for f in warnings_)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ctx}}))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--format", choices=FORMATS, help="skip auto-detection")
    ap.add_argument("--xsd", type=Path, help="also validate XML against this schema (xmllint or lxml)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="warnings fail the run")
    ap.add_argument("--hook", action="store_true", help="run as a Claude Code PostToolUse hook")
    args = ap.parse_args(argv)
    if args.hook:
        return hook_main()
    if not args.paths:
        ap.print_usage(sys.stderr)
        return 2
    results = []
    checked = 0
    for path in iter_paths(args.paths):
        if not path.exists():
            print(f"{path}: not found", file=sys.stderr)
            return 2
        fmt, findings = check_file(path, args.format, args.xsd)
        if fmt is None:
            continue
        checked += 1
        results.append((path, fmt, findings))
    n_err = sum(f.severity == "error" for _, _, fs in results for f in fs)
    n_warn = sum(f.severity == "warning" for _, _, fs in results for f in fs)
    if args.json:
        print(json.dumps({
            "checked": checked, "errors": n_err, "warnings": n_warn,
            "files": [{"path": str(p), "format": fmt, "findings": [f.as_dict(str(p)) for f in fs]} for p, fmt, fs in results],
        }, indent=2))
    else:
        for path, fmt, findings in results:
            for f in findings:
                print(f.format(str(path)))
        print(f"{checked} file(s) checked: {n_err} error(s), {n_warn} warning(s). Structural checks only, not a compile.")
    if checked == 0:
        print("no recognised PLC files", file=sys.stderr)
        return 2
    return 1 if n_err or (args.strict and n_warn) else 0


if __name__ == "__main__":
    sys.exit(main())
