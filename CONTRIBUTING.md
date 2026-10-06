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
| `scripts/plccheck/` | One module per format (`st.py`, `plcopen.py`, `simaticml.py`, `twincat.py`, `logix.py`, `schneider.py`, `iec61499.py`, `aml.py`, `dexpi.py`, `tabular.py`); `findings.py` holds the finding type, `xmlutil.py` the line-numbered XML parser |
| `tests/` | `test_st.py`, `test_formats.py` (validator rules), `test_skills.py` (frontmatter, templates, every `iecst` block lints clean) |
| `evals/` | `claude plugin eval` cases comparing the plugin against a no-plugin baseline |

## Rules

- **The validator uses only the Python standard library** and must run on Python 3.9 (CI runs
  3.9 and 3.12). Optional tools such as `xmllint` or `lxml` are allowed only behind `--xsd`.
- **Every validator rule needs two tests:** an input it must catch and a valid control it must
  accept. A rule tested only on bad input cannot show it is not firing on everything.
- **Every fact in a reference file is sourced or marked unverified.** Name the manual, standard
  or document number and its version. When a newer product version may differ, tell Claude to
  ask the user rather than assume.
- **The hook must never break a session:** non-PLC files and unreadable events exit 0, and a
  validator bug exits 1, which Claude Code shows but does not block on. Only real errors exit 2.
- **Bump the version** in `.claude-plugin/plugin.json` on every change; `claude plugin update`
  does nothing while it is unchanged.
- Do not bundle vendor schemas or manuals whose licence does not clearly permit redistribution.

## Tests

```bash
python3 -m unittest discover -s tests
claude plugin validate .
claude plugin eval . --trust-plugin --allow-tools Write Edit "Bash(python3 *)" --no-publish
```

Read an eval's `Δ` (with plugin minus without), not its score: a case the baseline already
passes shows nothing about the plugin. See the README for the macOS eval workaround.
