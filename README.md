# plc-programming: a Claude Code & Antigravity plugin

This plugin lets AI coding assistants (Claude Code, Antigravity / Gemini) **design, write, extend, convert, review and debug PLC programs**
through conversation, backed by standards knowledge that was checked against sources
(September 2026) and by a validator that uses only the Python standard library.

**The focus is Siemens (TIA Portal / S7) and Schneider Electric (Machine Expert / M2xx,
Control Expert / M340–M580).** It also covers the vendor-neutral standards and the other
major platforms.

## Install

### Claude Code

```bash
claude plugin marketplace add SmailG/plc-programming
claude plugin install plc-programming@plc-programming
```

For development without installing, run `claude --plugin-dir .` from a checkout of this
repository.

### Antigravity / Gemini

Install globally across all workspaces:

```bash
git clone https://github.com/SmailG/plc-programming.git ~/.gemini/config/plugins/plc-programming
```

Or for a single workspace:

```bash
git clone https://github.com/SmailG/plc-programming.git .agents/plugins/plc-programming
```

## What is inside

| Component | Invocation | Purpose |
|---|---|---|
| `develop` skill | automatic, or `/plc-programming:develop` | frame → requirements → design → code → validate → test plan; changing existing code safely |
| `debug` skill | automatic, or `/plc-programming:debug` | evidence-first diagnosis, with a catalogue of PLC failure patterns |
| `convert` skill | automatic, or `/plc-programming:convert` | port between languages, dialects and exchange formats without changing behaviour per scan |
| `siemens` skill | automatic | TIA Portal, S7-1200/1500, SCL/LAD/FBD/STL/GRAPH, SimaticML, SIMATIC SD, AX, PROFINET/S7/OPC UA, Safety Integrated |
| `schneider` skill | automatic | Machine Expert (M241/M251/M262), Control Expert (M340/M580), Automation Expert, Modbus, EtherNet/IP, OPC UA |
| `iec-61131-3` skill | automatic | Ed.2–Ed.4, the five languages, POUs, OOP, data types, the standard library, PLCopen guidelines, Motion and Safety |
| `exchange-formats` skill | automatic | PLCopen XML (TC6 v2.0/v2.01), IEC 61131-10, AutomationML (IEC 62714), DEXPI / ISO 15926 |
| `other-platforms` skill | automatic | Beckhoff TwinCAT, CODESYS, ABB Freelance (PRT/CSV) / AC500 / 800xA, Rockwell L5X/L5K |
| `iec-61499` skill | automatic | event-driven FBs, ECC, 4diac file formats |
| `packml-isa88-opcua` skill | automatic | PackML states and PackTags, ISA-88 / IEC 61512, OPC UA (OPC 30000/30001/30050) |
| `/plc-programming:new-pou` | user only | scaffold a POU for a chosen platform and format |
| `/plc-programming:review` | user only | ranked review by the `plc-reviewer` agent |
| `/plc-programming:validate` | user only | run the validator and explain the findings |
| `plc-reviewer` agent | delegated | read-only review against the checklist in `skills/develop/references/review-checklist.md` |
| PostToolUse hook | automatic | validates every PLC file written or edited (Claude Code and Antigravity); errors are fed back. Set `PLC_VALIDATE_HOOK=0` to disable it |

## The validator

```bash
python3 scripts/plc_validate.py <files-or-dirs> [--format FMT] [--xsd schema.xsd] [--json] [--strict]
```

It needs Python 3.9 or later and nothing else. It is a **structural** check, not a
compiler: it resolves no types and no symbols across files.

| Prefix | Format | Examples of what it catches |
|---|---|---|
| `ST` | IEC ST, Siemens SCL sources, TwinCAT/CODESYS ST, Logix ST | unbalanced blocks (ST002), IF without THEN (ST003), EXIT outside a loop (ST005), `=` used as assignment (ST010), REAL equality (ST020), timer/edge/counter instances not called exactly once per scan (ST030–ST033), duplicate declarations (ST040) |
| `PX` | PLCopen XML v2.0/v2.01, IEC 61131-10 | required headers, duplicate `localId`, dangling `refLocalId`, SFC initial step, qualifier and duration rules, POUs hidden in vendor addData |
| `SM` / `SD` | SimaticML / SIMATIC SD | namespace version against the TIA version, duplicate `ID`/`UId`, dangling wires, invalid interface sections |
| `TC` | TwinCAT `.TcPOU/.TcDUT/.TcGVL/.TcIO` | declaration name against object name and file name, duplicate GUIDs, embedded ST |
| `LX` | Rockwell L5X / L5K | rung syntax, operand counts (old and v36 IEC mnemonics), duplicate tags, OTE on the same bit in several rungs |
| `CX` | Control Expert XEF/XSY | duplicate variables, shared addresses, embedded ST |
| `FB` | IEC 61499 `.fbt/.adp` | WITH targets, ECC states, algorithms, events, network connections |
| `AM` / `DX` / `CS` | AutomationML, DEXPI, CSV tag lists | IDs, links, refURI targets, duplicate names |

The official XSDs (PLCopen TC6, IEC 61131-10) are **not bundled** because their licences
do not clearly permit redistribution. Download them from
<https://www.plcopen.org/downloads/> and pass `--xsd`.

## Tests and evals

```bash
python3 -m unittest discover -s tests                   # validator, templates, skill integrity
claude plugin eval . --trust-plugin --allow-tools Write Edit "Bash(python3 *)" --no-publish
```

- **Unit tests:** every validator rule is exercised by an input it must catch and by a
  valid control it must pass. Every shipped template and every `iecst` code block in the
  skills must lint clean.
- **Evals:** they compare the plugin against a no-plugin baseline on edition facts, SFC
  semantics, a classic scan-cycle bug, PLCopen XML generation, SimaticML namespaces,
  ABB Freelance PRT, and the Logix v36 mnemonics.
- **`plcopen-generate` does not separate plugin from baseline.** Both arms score 1.00:
  the baseline already writes the namespace and headers its regex graders check, and no
  grader type can run `plc_validate.py` on the output. Its with-only `validated` grader
  shows the plugin makes Claude run the validator; the score shows nothing more.
- **On macOS, Bash-granting cases refuse to start** while `~/.docker` holds symlinks, which
  Docker Desktop creates. `DOCKER_CONFIG` does not help. Quit Docker Desktop, then
  `mv ~/.docker ~/.docker.eval-bak`, run the eval, and move it back. On Linux, install
  `bubblewrap` and `socat` instead.

## Accuracy policy

The reference files state what was verified and cite sources. Anything that could not be
verified is marked as such, not stated as fact. Examples:

- the internal layout of an ABB Freelance `.prt`;
- the SimaticML namespaces for TIA V21;
- the current version of EcoStruxure Automation Expert.

When a user's version is newer than the one documented here, the skills tell Claude to
ask, not to assume.

## Contributing and licence

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). Report
security issues privately, as described in [SECURITY.md](SECURITY.md).

[MIT](LICENSE). Siemens, Schneider Electric, Rockwell, Beckhoff, CODESYS, ABB and the other
product names are trademarks of their owners; this plugin is not affiliated with or endorsed by
any of them.
