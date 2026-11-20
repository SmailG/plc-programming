#!/usr/bin/env python3
"""SQL for the newest WinCC fast-archive block of each tag, and a truncation check.

    wincc_latest_block.py sql --database SEGMENT --id 171 --id 170
    wincc_latest_block.py check dump.txt

`sql` prints one SELECT. Run it with sqlcmd on the machine that holds the segment and
write the file with sqlcmd's own `-o`, not by piping into another tool. `check` reads
that file and fails when a block's hex is shorter than the length column, which is what
a wrapped line looks like. Decoding is `wincc_binvalues.py`.

The archive format is undocumented. This script does not decode values. A live WinCC
SQL instance already has the segment attached; do not attach that file a second time.
See skills/other-platforms/references/wincc-tag-logging-archive.md.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

EXIT_OK, EXIT_BAD, EXIT_USAGE = 0, 1, 2


class DumpError(ValueError):
    pass


def _database(name: str) -> str:
    if not name or "]" in name or "[" in name:
        raise DumpError("database name must be non-empty and contain no brackets")
    return "[" + name + "]"


def latest_block_sql(database: str, value_ids: list[int]) -> str:
    """One row per value id: the block with the greatest Timebegin."""
    if not value_ids:
        raise DumpError("at least one value id is required")
    ids = []
    for value_id in value_ids:
        if isinstance(value_id, bool) or not isinstance(value_id, int) or value_id < 0:
            raise DumpError("value id must be a non-negative integer")
        ids.append(str(value_id))
    db = _database(database)
    id_list = ", ".join(ids)
    return (
        "SET NOCOUNT ON;\n"
        "SELECT CONVERT(varchar(23), x.Timebegin, 121), x.ValueID, "
        "DATALENGTH(x.BinValues), CONVERT(varchar(max), x.BinValues, 2)\n"
        "FROM (\n"
        "  SELECT t.Timebegin, t.ValueID, t.BinValues,\n"
        "         ROW_NUMBER() OVER (PARTITION BY t.ValueID ORDER BY t.Timebegin DESC) AS rn\n"
        f"  FROM {db}.dbo.TagCompressed t\n"
        f"  WHERE t.ValueID IN ({id_list})\n"
        ") x\n"
        "WHERE x.rn = 1\n"
        "ORDER BY x.ValueID;\n"
    )


@dataclass(frozen=True)
class DumpBlock:
    timebegin: str
    value_id: int
    data_length: int
    hex_text: str

    @property
    def complete(self) -> bool:
        return len(self.hex_text) == 2 * self.data_length


def parse_dump(text: str) -> list[DumpBlock]:
    """sqlcmd `-s '|'` lines. A header or a separator is skipped. A short hex fails."""
    blocks: list[DumpBlock] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip().lstrip("\ufeff")
        if not line or set(line) <= set("-| ") or line.lower().startswith("timebegin"):
            continue
        if "rows affected" in line.lower():
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            raise DumpError(f"line {line_no}: expected 4 |-fields, got {len(parts)}")
        timebegin, value_id, data_length, hex_text = parts
        if not value_id.isdigit() or not data_length.isdigit():
            raise DumpError(f"line {line_no}: value id and length must be integers")
        block = DumpBlock(timebegin, int(value_id), int(data_length), hex_text)
        if not block.complete:
            raise DumpError(
                f"line {line_no}: value {block.value_id} hex has {len(hex_text)} chars, "
                f"length column says {block.data_length} bytes ({2 * block.data_length} hex chars). "
                "The line was cut. Re-run sqlcmd with -y 0 and -o, and do not pipe it."
            )
        blocks.append(block)
    return blocks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wincc_latest_block.py", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sql = sub.add_parser(
        "sql", help="print the SELECT for the newest block of each value id"
    )
    sql.add_argument("--database", required=True)
    sql.add_argument("--id", dest="ids", type=int, action="append", required=True)
    check = sub.add_parser(
        "check", help="fail if any dumped block is shorter than its length column"
    )
    check.add_argument("dump", nargs="?", help="sqlcmd file; omit or '-' for stdin")
    args = parser.parse_args(argv)
    try:
        if args.command == "sql":
            sys.stdout.write(latest_block_sql(args.database, args.ids))
            return EXIT_OK
        text = (
            sys.stdin.read()
            if args.dump in (None, "-")
            else open(args.dump, encoding="utf-8-sig").read()
        )
        blocks = parse_dump(text)
    except DumpError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_BAD
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    if not blocks:
        print("no blocks in the dump", file=sys.stderr)
        return EXIT_BAD
    for block in blocks:
        print(f"{block.value_id}\t{block.timebegin}\t{block.data_length}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
