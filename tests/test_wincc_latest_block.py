"""The latest-block SQL helper and the dump truncation check. No archive bytes."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import wincc_latest_block as L  # noqa: E402


class LatestBlockSql(unittest.TestCase):
    def test_one_row_per_id_newest_timebegin(self):
        sql = L.latest_block_sql("Segment_A", [171, 170])
        self.assertIn(
            "ROW_NUMBER() OVER (PARTITION BY t.ValueID ORDER BY t.Timebegin DESC)", sql
        )
        self.assertIn("WHERE x.rn = 1", sql)
        self.assertIn("[Segment_A].dbo.TagCompressed", sql)
        self.assertIn("IN (171, 170)", sql)
        self.assertIn("CONVERT(varchar(max), x.BinValues, 2)", sql)

    def test_rejects_a_bracket_in_the_database_name(self):
        with self.assertRaises(L.DumpError):
            L.latest_block_sql("Seg]ment", [1])

    def test_rejects_an_empty_id_list(self):
        with self.assertRaises(L.DumpError):
            L.latest_block_sql("Segment_A", [])


class DumpCheck(unittest.TestCase):
    def test_accepts_a_complete_line(self):
        line = "2024-01-01 06:00:00.000|7|4|AABBCCDD\n"
        blocks = L.parse_dump(line)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].value_id, 7)
        self.assertTrue(blocks[0].complete)

    def test_rejects_a_wrapped_line(self):
        line = "2024-01-01 06:00:00.000|7|4|AABB\n"
        with self.assertRaises(L.DumpError) as caught:
            L.parse_dump(line)
        self.assertIn("cut", str(caught.exception))

    def test_skips_the_sqlcmd_header(self):
        text = "Timebegin|ValueID|length|hex\n--------|------|------|---\n2024-01-01 06:00:00.000|3|1|AA\n"
        blocks = L.parse_dump(text)
        self.assertEqual([block.value_id for block in blocks], [3])


class Cli(unittest.TestCase):
    def test_check_exits_1_on_a_short_block(self):
        script = HERE.parent / "scripts" / "wincc_latest_block.py"
        result = subprocess.run(
            [sys.executable, str(script), "check", "-"],
            input="2024-01-01 06:00:00.000|1|2|AA\n",
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("cut", result.stderr)
