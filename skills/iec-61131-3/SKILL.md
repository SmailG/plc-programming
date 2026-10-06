---
name: iec-61131-3
description: >-
  Reference for IEC 61131-3 PLC programming (Ed.2 2003, Ed.3 2013, Ed.4 2025) and PLCopen
  conventions. Covers the five languages: Structured Text (ST), Instruction List (IL,
  deprecated in Ed.3 and removed in Ed.4), Ladder Diagram (LD), Function Block Diagram (FBD)
  and Sequential Function Chart (SFC). Also covers POUs (PROGRAM, FUNCTION_BLOCK, FUNCTION,
  CLASS, METHOD, INTERFACE, NAMESPACE), variable sections, data types, the standard functions
  and FBs (TON/TOF/TP, R_TRIG, CTU, SR/RS), configuration/resource/task, the PLCopen Coding
  Guidelines v1.0 and naming prefixes, and the PLCopen Motion and Safety FB patterns. Use
  whenever you write, read, explain, translate or check vendor-neutral PLC code, or when a
  question depends on what the standard allows or on which edition introduced a feature.
---

# IEC 61131-3 and PLCopen

The standard is the common ground. Vendor dialects (Siemens SCL, CODESYS/TwinCAT,
Schneider, Logix) add to it or deviate from it, so check this skill first and the
platform skill second.

## Facts you must get right

| Question | Answer |
|---|---|
| Current edition | **Ed.4, IEC 61131-3:2025, published 2025-05-22.** Ed.3 (2013-02-20) was withdrawn on that date |
| IL status | **Deprecated in Ed.3 and removed in Ed.4.** Keep IL only for legacy maintenance. Never choose it for new code |
| Languages in Ed.4 | ST (textual), and LD and FBD (graphical). SFC is the structuring element on top of them |
| OOP (CLASS, METHOD, INTERFACE, EXTENDS, IMPLEMENTS, THIS/SUPER, access specifiers) | Added in **Ed.3** |
| `REF_TO` / `REF()` / `^` / `NULL`, `ARRAY[*]`, `LTIME`/`LDATE`/`LTOD`/`LDT`, `CHAR`/`WCHAR`, `CONTINUE`, `NAMESPACE`/`USING`, `?=` assignment attempt | Added in **Ed.3** |
| `USTRING`/`UCHAR` (UTF-8), `ASSERT`, mutex/semaphore, `PROPERTY_GET`/`PROPERTY_SET` | Added in **Ed.4** |
| `PROPERTY` before Ed.4 | A CODESYS/TwinCAT extension, not in Ed.3 |
| Octal literals `8#…`, untyped `TRUNC(x)` | Deprecated in Ed.3 and removed in Ed.4 |
| BCD conversion functions | Deprecated in Ed.4 |
| REAL→INT conversion | Rounds to nearest, **ties to even**: `REAL_TO_INT(2.5) = 2`. `TRUNC` truncates toward zero |
| String positions (`MID`, `FIND`, `INSERT`…) | **1-based** |
| Short-circuit evaluation of AND/OR | Permitted, **not required**. Never rely on it. CODESYS offers `AND_THEN`/`OR_ELSE` for the guaranteed form |
| Precedence of `-`/`NOT` vs `**` | The standard ranks unary `-`/`NOT` **above** `**`, while CODESYS ranks `**` above them. Parenthesise |

State the edition whenever it matters, for example "`USTRING` needs an Ed.4 toolchain".
Most shipping IDEs in 2026 implement Ed.3 plus vendor extensions.

## Choosing a language

| Part of the program | Best fit | Why |
|---|---|---|
| Sequences with steps and waits (fill → heat → drain, homing, recipes) | **SFC**, or an ST `CASE` state machine | Shows the state explicitly, and SFC step flags `s.X` and `s.T` come for free |
| Interlocks, permissives, simple discrete logic that maintenance must read online | **LD** | Electricians can follow power flow when monitoring online |
| Signal flow and continuous control (scaling, PID, filters) | **FBD** | Mirrors a block diagram |
| Algorithms, maths, string/array handling, state machines, OOP | **ST** | Compact and diffable. It is also the only textual language left in Ed.4 |
| Anything new | Never **IL** | It is gone from Ed.4 |

## POU rules (short form)

- `FUNCTION` has no memory between calls and returns a value. It may not instantiate
  FBs that need state, and it must be deterministic.
- `FUNCTION_BLOCK` is instantiated and keeps state in its instance. **Call each instance
  exactly once per scan** (PLCopen CP20), and gate its inputs instead of its call. See
  the TON trap in the `debug` skill.
- `PROGRAM` is the top level and is associated with a `TASK`. PLCopen CP16 says tasks
  call only PROGRAMs.
- `VAR_IN_OUT` is by reference. RETAIN/NON_RETAIN are not allowed on it.
- `VAR_INPUT` must not be written inside the POU. `VAR_TEMP` is re-initialised on every call.
- `R_EDGE`/`F_EDGE` on a BOOL `VAR_INPUT` creates the edge detector implicitly.
- `%I`, `%Q` and `%M` addresses have the form `%` + I/Q/M + size (X or none, B, W, D, L)
  + dotted numbers, for example `%IX0.0`, `%QW4`, `%MD48`. `%I*` must be completed in
  `VAR_CONFIG`. PLCopen N1: declare a symbol instead of using addresses in code.

## Reference files

Load only the file the task needs:

- [references/editions.md](references/editions.md): edition history, what each edition
  added, removed or deprecated, and IEC TR 61131-8.
- [references/structured-text.md](references/structured-text.md): ST syntax, precedence,
  statements, literals and idioms.
- [references/instruction-list.md](references/instruction-list.md): IL operators and
  modifiers, for reading and migrating legacy code.
- [references/ladder-and-fbd.md](references/ladder-and-fbd.md): LD contacts and coils,
  FBD rules, EN/ENO.
- [references/sfc.md](references/sfc.md): steps, transitions, divergence rules, action
  qualifiers (N R S L D P P0 P1 SD DS SL) and the final-scan rule.
- [references/pous-oop-config.md](references/pous-oop-config.md): POU types, OOP,
  namespaces, and CONFIGURATION/RESOURCE/TASK.
- [references/data-types-and-variables.md](references/data-types-and-variables.md):
  elementary, generic and derived types, variable sections and qualifiers.
- [references/standard-library.md](references/standard-library.md): conversion, numeric,
  bit, selection, comparison and string functions, and the standard FBs with their pins.
- [references/plcopen-guidelines.md](references/plcopen-guidelines.md): PLCopen Coding
  Guidelines v1.0 rules, naming prefixes, and the Motion (MC_*) and Safety (SF_*) patterns.

## How to use this when writing code

1. Name the target platform and edition first. If the user has not said, ask, because
   vendor dialects differ in ways that fail compilation.
2. Write standard ST unless the platform skill says otherwise. Mark any vendor extension
   you use (`PROPERTY`, `POINTER TO`, `{attribute}`, `AND_THEN`).
3. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py <file>` on what you wrote.
   It catches structural errors, not type errors, so say that it is not a compile.
