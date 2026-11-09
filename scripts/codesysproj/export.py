"""dump-st: write every ST object's declaration and implementation as text files."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from .project import KIND_DUT, KIND_GVL, KIND_ST, ObjectRecord, Project

MAX_STEM_PART = 80
_UNSAFE = re.compile(r"[^\w.\- ]", re.UNICODE)


def safe_filename_part(text: str) -> str:
    """Make untrusted text usable as one path component: no separators, no leading dot."""
    cleaned = _UNSAFE.sub("_", text).strip(". ")[:MAX_STEM_PART]
    return cleaned or "_"


def _stem(rec: ObjectRecord) -> str:
    if rec.name is None:
        return "unnamed_" + rec.guid
    return "%s_%s" % (safe_filename_part(rec.device or "root"), safe_filename_part(rec.name))


def dump_st(project: Project, outdir: str) -> List[Tuple[ObjectRecord, List[str]]]:
    """Write `<Device>_<Name>.decl.st` / `.impl.st` for every ST POU, and `.decl.st` alone for every GVL
    and DUT (they have no implementation); return what was written.

    Names that collide (two devices with the same POU name, case-insensitively) all get
    `_<first 8 of the guid>`, so no file is overwritten within a run.
    """
    st_objects = [r for r in project.records() if r.kind in (KIND_ST, KIND_GVL, KIND_DUT)]
    groups: Dict[str, int] = defaultdict(int)
    for rec in st_objects:
        groups[_stem(rec).lower()] += 1
    os.makedirs(outdir, exist_ok=True)
    written: List[Tuple[ObjectRecord, List[str]]] = []
    for rec in st_objects:
        stem = _stem(rec)
        if groups[stem.lower()] > 1:
            stem = "%s_%s" % (stem, rec.guid[:8])
        files = []
        parts = [(".decl.st", rec.declaration)] + ([(".impl.st", rec.implementation)] if rec.kind == KIND_ST else [])
        for suffix, text in parts:
            target = os.path.join(outdir, stem + suffix)
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(text or "")
            files.append(target)
        written.append((rec, files))
    return written
