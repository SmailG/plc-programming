# Contributing

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report security issues
privately, as described in [SECURITY.md](SECURITY.md). Pull requests use the template in
`.github/`; a maintainer reviews and merges them.

## Layout

| Path | Role |
|---|---|
| `skills/<name>/SKILL.md` | One skill each; `references/` holds the detail a skill loads on demand, `assets/` the templates |
| `agents/plc-reviewer.md` | Read-only reviewer used by `/plc-programming:review` |
| `hooks/hooks.json` | PostToolUse hook that runs the validator on every file Claude writes or edits |
| `scripts/plc_validate.py` | Validator CLI and hook entry point |
| `scripts/codesys_project.py` | Offline reader for CODESYS 3.5 / Machine Expert `.project` files (`list`, `st`, `dump-st`, `graph`, `info`, `diff`, `xref`); `scripts/codesysproj/` holds `binary.py` (varint, string table), `project.py` (objects, kinds, text), `graph.py` (LD/FBD records) and `graphview.py` (their text and JSON), `export.py` (`dump-st`), `buildinfo.py` (`info`), `diff.py` (`diff`), `xref.py` and `stscan.py` (`xref`) |
| `scripts/plccheck/` | One module per format (`st.py`, `plcopen.py`, `simaticml.py`, `twincat.py`, `logix.py`, `schneider.py`, `iec61499.py`, `aml.py`, `dexpi.py`, `tabular.py`); `findings.py` holds the finding type, `xmlutil.py` the line-numbered XML parser |
| `tests/` | `test_st.py`, `test_formats.py` (validator rules), `test_codesys_project.py` and `test_codesys_tools.py` (the `.project` reader and its `info`, `diff` and `xref`, on synthetic projects only), `test_codesys_hardening.py` (hostile and damaged `.project` input and the reader's CLI contracts, synthetic projects only), `test_linear_xml.py`, `test_linear_aml.py` and `test_linear_text.py` (CPU-time scaling and ordering of the format checkers on crafted input; `linear_support.py` holds their ratio helper and XML builders), `test_xml_limits.py` (the namespace URI cap of the shared XML parser), `test_skills.py` (frontmatter, templates, every `iecst` block lints clean) |
| `evals/` | `claude plugin eval` cases comparing the plugin against a no-plugin baseline |

## Rules

- **The validator and the `.project` reader use only the Python standard library** and must
  run on Python 3.9 (CI runs 3.9 and 3.12). Optional tools such as `xmllint` or `lxml` are allowed only behind `--xsd`.
- **Every validator rule needs two tests:** an input it must catch and a valid control it must
  accept. A rule tested only on bad input cannot show it is not firing on everything.
- **Every fact in a reference file is sourced or marked unverified.** Name the manual, standard
  or document number and its version. When a newer product version may differ, tell Claude to
  ask the user rather than assume.
- **The hook must never break a session:** non-PLC files and unreadable events exit 0, and a
  validator bug exits 1, which Claude Code shows but does not block on. Only real errors exit 2.
- **Bump the version** in both `.claude-plugin/plugin.json` and the root `plugin.json` on every
  change, to the same value (a test checks it); `claude plugin update` does nothing while it is
  unchanged.
- Do not bundle vendor schemas or manuals whose licence does not clearly permit redistribution.
- **Test fixtures for the `.project` reader are synthetic.** Never commit a real `.project`,
  or names, text or guids taken from one: it is someone's program.

## Tests

```bash
python3 -m unittest discover -s tests
claude plugin validate .
claude plugin eval . --trust-plugin --allow-tools Write Edit "Bash(python3 *)" --no-publish
```

Read an eval's `Δ` (with plugin minus without), not its score: a case the baseline already
passes shows nothing about the plugin. See the README for the macOS eval workaround.

### Mutation tests

Run mutation tests (by hand or with an AI agent) one at a time, each as
`timeout -k 10 300 <cmd>`: an external wrapper, because a timeout inside the runner dies with
it. That is GNU `timeout` (macOS: `brew install coreutils`, then `gtimeout`). Check for
leftover processes at the end: `ps -eo pid,etime,pcpu,command | grep <your scratch path>`.
