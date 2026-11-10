"""A finding's message and context are cut to MAX_FINDING_TEXT, in the one place every finding is built.

A name from the file is quoted in the context of every finding under it (a Logix program name in
every rung finding), so a 2,000-character name over 40 rungs printed 85 KB and a 20,000-character
one over 400 rungs printed 8 MB, growing with the square of the file size.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

from linear_support import xml_root  # noqa: E402
from plccheck import findings  # noqa: E402
from plccheck.logix import check_l5x  # noqa: E402
from plccheck.st import check_st_file  # noqa: E402


def l5x(program: str, rungs: int) -> str:
    body = "".join(f'<Rung Number="{i}"><Text>XIC(a)</Text></Rung>' for i in range(rungs))
    return ('<RSLogix5000Content SchemaRevision="1" SoftwareRevision="1" TargetType="Controller"><Controller><Programs>'
            f'<Program Name="{program}"><Routines><Routine Name="r" Type="RLL"><RLLContent>{body}</RLLContent></Routine></Routines>'
            "</Program></Programs></Controller></RSLogix5000Content>")


def formatted(program: str, rungs: int) -> str:
    return "\n".join(f.format("a.L5X") for f in check_l5x(xml_root(l5x(program, rungs))))


class FindingClip(unittest.TestCase):
    MAX = findings.MAX_FINDING_TEXT

    def assert_clipped(self, text: str):
        self.assertEqual(len(text), self.MAX)
        self.assertTrue(text.endswith(findings.ELLIPSIS))
        self.assertEqual(text[:-1], "x" * (self.MAX - 1))

    def test_a_text_up_to_the_limit_is_kept_and_a_longer_one_is_cut_to_it(self):
        exact, over = "x" * self.MAX, "x" * (self.MAX + 1)
        f = findings.error("ST002", exact, 3, exact)
        self.assertEqual((f.message, f.context), (exact, exact))
        f = findings.error("ST002", over, 3, over)
        self.assert_clipped(f.message)
        self.assert_clipped(f.context)

    def test_message_and_context_are_cut_on_their_own(self):
        over = "x" * (self.MAX + 1)
        only_message = findings.warning("ST002", over, 3, "short")
        self.assert_clipped(only_message.message)
        self.assertEqual(only_message.context, "short")
        only_context = findings.warning("ST002", "short", 3, over)
        self.assertEqual(only_context.message, "short")
        self.assert_clipped(only_context.context)
        self.assertIsNone(findings.error("ST002", "short").context)

    def test_a_real_long_message_is_kept_whole(self):
        src = ("PROGRAM P\nVAR\n tonWaitForTheBelt : TON;\n x : BOOL;\nEND_VAR\n"
               "IF x THEN\n tonWaitForTheBelt(IN := TRUE, PT := T#5S);\nEND_IF;\nEND_PROGRAM\n")
        [f] = check_st_file(src)
        self.assertEqual((f.code, len(f.message)), ("ST030", 203))
        self.assertTrue(f.message.endswith("gate its input instead"))

    def test_the_limit_is_well_above_the_messages_the_checkers_write(self):
        # The longest message from an ordinary name is 203 characters (ST030 with a 17-character
        # instance name, pinned above); the longest template is 183 before its two names. A limit
        # near them would cut real findings.
        self.assertGreaterEqual(self.MAX, 300)

    def test_a_context_added_by_with_context_is_cut(self):
        inner = findings.error("ST002", "m", 4, "y" * 300)
        [out] = findings.with_context([inner], "x" * 300, 10)
        self.assertEqual((out.line, len(out.context)), (14, self.MAX))
        self.assertTrue(out.context.endswith(findings.ELLIPSIS))

    def test_the_formatted_and_dict_forms_carry_the_cut_text(self):
        f = findings.error("ST002", "x" * 1000, 3, "y" * 1000)
        self.assertEqual(len(f.format("p")), len("p:3: error ST002:  []") + 2 * self.MAX)
        d = f.as_dict("p")
        self.assertEqual((len(d["message"]), len(d["context"])), (self.MAX, self.MAX))

    def test_a_short_name_gives_the_same_output_as_before(self):
        self.assertEqual(formatted("p", 2), "\n".join(
            f"a.L5X:1: error LX020: rung text must end with ';' [p/r rung {i}]" for i in range(2)))

    def test_a_long_program_name_does_not_make_the_output_grow_with_it(self):
        short, long_, longer = formatted("p" * 10, 40), formatted("p" * 2_000, 40), formatted("p" * 4_000, 40)
        self.assertEqual(len(long_), len(longer))  # the same output for any name over the limit
        self.assertLess(len(long_), 40 * (self.MAX + 100))  # was 85 KB for 40 rungs
        self.assertGreater(len(long_), len(short))
        self.assertEqual(long_.splitlines()[0].count(findings.ELLIPSIS), 1)

    def test_the_output_grows_linearly_with_the_rung_count_for_a_long_name(self):
        small, big = len(formatted("p" * 2_000, 20)), len(formatted("p" * 2_000, 80))
        self.assertLess(big, 4.2 * small)  # not exactly 4x: the rung numbers have more digits


if __name__ == "__main__":
    unittest.main()
