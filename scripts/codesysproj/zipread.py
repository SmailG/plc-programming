"""Open the `.project` zip and read one entry, with every failure as a FormatError.

The reader is handed files it did not write, so a damaged, encrypted or oversized entry must
become a message, not a traceback: a CRC error, a corrupt deflate stream, an encrypted entry and
an entry that inflates past ENTRY_CAP all raise FormatError here. The caller decides whether that
is fatal (the string table) or one object's problem.
"""

from __future__ import annotations

import zipfile
import zlib
from typing import Optional

from .binary import FormatError

# The largest entry the reader touches in the projects it was checked on is under 3 MB; the cap
# leaves wide headroom and stops a small zip that inflates to gigabytes (a zip bomb).
ENTRY_CAP = 256 * 1024 * 1024
_READ_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError,
                OverflowError, OSError)


def open_archive(path: str) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError, ValueError) as exc:  # ValueError covers a bad UTF-8 entry name
        raise FormatError("%s: not a readable zip archive (%s)" % (path, exc))


def read_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo, cap: Optional[int] = None) -> bytes:
    """The entry's bytes, read at most `cap` (default ENTRY_CAP) + 1 bytes far, so a lying size
    field cannot make it allocate more."""
    limit = ENTRY_CAP if cap is None else cap
    try:
        with archive.open(info) as stream:
            data = stream.read(limit + 1)
    except _READ_ERRORS as exc:
        raise FormatError("entry %s could not be read (%s: %s)" % (info.filename, type(exc).__name__, exc))
    if len(data) > limit:
        raise FormatError("entry %s inflates past %d bytes; not read" % (info.filename, limit))
    return data


def entry_name(info: zipfile.ZipInfo) -> str:
    """Entry name as text: the zip flag says UTF-8, otherwise cp437, with a GBK retry."""
    raw = info.filename.encode("utf-8") if info.flag_bits & 0x800 else info.filename.encode("cp437")
    try:
        name = raw.decode("utf-8")
    except UnicodeDecodeError:
        name = raw.decode("gbk", "replace")
    return name.replace("\\", "/").rsplit("/", 1)[-1]
