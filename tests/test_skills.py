"""Skill and agent integrity: frontmatter, cross-references, and every ```iecst example lints clean.

`claude plugin validate` checks agents but accepted a deliberately broken SKILL.md
(invalid YAML, a name with spaces) without a word, so skills are checked here instead.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from plccheck.st import check_st_file, lint_st  # noqa: E402

SKILL_KEYS = {
    "name", "description", "when_to_use", "argument-hint", "arguments", "disable-model-invocation",
    "user-invocable", "allowed-tools", "disallowed-tools", "model", "effort", "context", "agent",
    "background", "hooks", "paths", "shell", "metadata", "license", "compatibility",
}
AGENT_KEYS = {
    "name", "description", "tools", "disallowedTools", "model", "maxTurns", "skills", "memory",
    "background", "effort", "isolation", "color", "omitClaudeMd", "experimental",
}


def frontmatter(path: Path) -> dict[str, object]:
    """Parse the YAML subset used here: scalars, folded (>-) blocks and '- item' lists."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise AssertionError(f"{path}: no frontmatter")
    data: dict[str, object] = {}
    key = None
    for line in m.group(1).splitlines():
        if re.match(r"[A-Za-z_-]+:", line):
            key, _, value = line.partition(":")
            value = value.strip()
            data[key] = [] if value == "" else ("" if value in (">-", ">", "|") else value.strip('"'))
        elif key and line.startswith("  - "):
            assert isinstance(data[key], list), f"{path}: mixed list/scalar for {key}"
            data[key].append(line[4:].strip())
        elif key and line.startswith("  "):
            data[key] = (str(data[key]) + " " + line.strip()).strip()
        elif line.strip():
            raise AssertionError(f"{path}: unparsed frontmatter line {line!r}")
    return data


class SkillFrontmatter(unittest.TestCase):
    def test_skills(self):
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 11)
        for path in skills:
            with self.subTest(skill=path.parent.name):
                fm = frontmatter(path)
                self.assertLessEqual(set(fm) - SKILL_KEYS, set(), "unknown frontmatter keys")
                self.assertEqual(fm.get("name"), path.parent.name, "name must match the directory")
                self.assertRegex(str(fm["name"]), r"^[a-z0-9]+(-[a-z0-9]+)*$")
                desc = str(fm.get("description", "")) + str(fm.get("when_to_use", ""))
                self.assertTrue(desc.strip(), "description required")
                self.assertLessEqual(len(desc), 1536, "description + when_to_use is truncated at 1536 chars")
                body = path.read_text(encoding="utf-8")
                self.assertLess(body.count("\n"), 500, "keep SKILL.md under 500 lines")

    def test_agents(self):
        for path in sorted((ROOT / "agents").glob("*.md")):
            with self.subTest(agent=path.name):
                fm = frontmatter(path)
                self.assertLessEqual(set(fm) - AGENT_KEYS, set(), "unknown frontmatter keys")
                self.assertEqual(fm.get("name"), path.stem)
                for skill in fm.get("skills", []):
                    name = skill.split(":", 1)[-1]
                    target = ROOT / "skills" / name / "SKILL.md"
                    self.assertTrue(target.exists(), f"preloaded skill {skill} does not exist")
                    self.assertNotEqual(frontmatter(target).get("disable-model-invocation"), "true",
                                        f"{skill} has disable-model-invocation and cannot be preloaded")


class ExamplesLintClean(unittest.TestCase):
    FENCE = re.compile(r"```iecst\n(.*?)```", re.S)

    def test_every_iecst_block(self):
        blocks = 0
        for md in sorted(ROOT.rglob("*.md")):
            for m in self.FENCE.finditer(md.read_text(encoding="utf-8")):
                blocks += 1
                code = m.group(1)
                line = md.read_text(encoding="utf-8")[: m.start()].count("\n") + 2
                has_pou = re.search(r"^\s*(FUNCTION_BLOCK|FUNCTION|PROGRAM|INTERFACE|TYPE|CONFIGURATION)\b", code, re.M)
                findings = check_st_file(code) if has_pou else lint_st(code, "body")[0]
                with self.subTest(block=f"{md.relative_to(ROOT)}:{line}"):
                    self.assertEqual([f"{f.code} l{f.line}: {f.message}" for f in findings], [])
        self.assertGreater(blocks, 10, "no iecst blocks found; the fence pattern is wrong")


class CrossReferences(unittest.TestCase):
    def test_relative_links_resolve(self):
        link = re.compile(r"\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")
        for md in sorted(ROOT.rglob("*.md")):
            for m in link.finditer(md.read_text(encoding="utf-8")):
                target = m.group(1)
                if "://" in target or target.startswith("mailto:"):
                    continue
                with self.subTest(file=str(md.relative_to(ROOT)), link=target):
                    self.assertTrue((md.parent / target).exists())

    def test_skills_named_in_text_exist(self):
        names = {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}
        mention = re.compile(r"`(siemens|schneider|other-platforms|exchange-formats|iec-61131-3|iec-61499|"
                             r"packml-isa88-opcua|develop|debug|convert|new-pou|review|validate)` skill")
        for md in sorted(ROOT.rglob("*.md")):
            for m in mention.finditer(md.read_text(encoding="utf-8")):
                with self.subTest(file=str(md.relative_to(ROOT)), skill=m.group(1)):
                    self.assertIn(m.group(1), names)


if __name__ == "__main__":
    unittest.main()
