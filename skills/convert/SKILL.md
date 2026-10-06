---
name: convert
description: >-
  Translate PLC logic between languages, dialects and exchange formats: IL→ST,
  LD↔ST, Siemens STL/AWL→SCL, SCL↔IEC ST↔TwinCAT/CODESYS/Machine Expert↔Logix ST,
  Control Expert (Unity) sections/DFBs↔Machine Expert, Rockwell RLL neutral text↔ST,
  61131-3→61499, and into import files (PLCopen XML, SimaticML / SIMATIC SD / .scl sources,
  .TcPOU, L5X). Use when the user wants code ported, migrated, rewritten in another
  language or vendor, or packaged for import into another tool.
---

# Converting PLC logic

**The rule:** a conversion must preserve *behaviour per scan*, not just syntax. Timers,
edges, execution order, retain and data types all hide semantics.

## Procedure

1. **Identify the source dialect and version exactly.** For example, S7-300 STL is not
   S7-1500 SCL, and Logix v35 mnemonics are not v36. Ask for the export if you only have
   screenshots.
2. **Inventory the semantics that do not carry over automatically** (table below), and
   decide on each item with the user.
3. **Translate one POU at a time.** Keep the original structure unless the user asks for
   a redesign, so that the port can be reviewed line by line.
4. **Package** in the target format (see the platform skills and `exchange-formats`), then
   run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py`.
5. **Deliver an equivalence test plan**: identical stimuli on the old and new code with
   compared outputs, especially at timer edges, restart and fault paths.

## Semantics that do not map 1:1

| Topic | Watch for |
|---|---|
| Timers | IEC `TON(IN, PT → Q, ET)` with TIME. Siemens: multi-instance `TON_TIME`/`IEC_TIMER`, or a single-instance DB; legacy S5 timers `S_ODT` have different semantics. Logix: ladder `TON(timer,pre,acc)` with **ms DINT**; in ST, `TONR` on `FBD_TIMER`. Control Expert: `TON` EFB |
| Edges | `R_TRIG` instances vs Logix `ONS`/`OSR` (a storage bit per use) vs LD `P`/`N` contacts. One edge instance per signal and per use |
| Execution model | LD rung order and ST statement order are the same scan semantics. **IEC 61499 is event-driven.** Siemens OB priorities vs CODESYS task priorities |
| Local variables | Siemens `#local`, `"global"` and TEMP-before-write rules (non-optimized). CODESYS `VAR_TEMP` is re-initialised every call |
| Data types | Siemens `S5TIME`, `DTL`, `Variant`, `DB_ANY`. Logix DINT-centric, with no `%` addresses. Control Expert `%MW` located variables. Sizes: Siemens `Char` 8-bit / `WChar` 16-bit, `String[n]` |
| Instances | Siemens instance DBs vs FB instance variables. Logix AOI instance tags. The TwinCAT `FB_init` lifecycle |
| Enums | Classic S7 has no IEC enums (use constants). TwinCAT/CODESYS `E.Member`. IEC Ed.3 `E#Member` |
| Arithmetic | overflow behaviour, REAL→INT rounding (IEC: half-to-even; check the vendor), integer division |
| Retain | Siemens retain per variable in optimized DBs. CODESYS `RETAIN`/`PERSISTENT`. Logix: every tag retains |
| IL / STL accumulator logic | the current result and status bits carry across lines. Siemens STL has status bits RLO, OS/OV, CC0/CC1, which is **not** IEC IL. Translate by data flow, not line by line |
| Graphical → text | LD branches become `OR`, series becomes `AND`, coils become assignments. **Keep one assignment per coil.** S/R coils become explicit priority |

## Target-format notes

- **Siemens:** author SCL as an **external source** (`.scl`, imported through "Generate
  blocks from source"), or, from TIA V20 Update 4 on, as **SIMATIC SD** (`.s7dcl`). Do not
  hand-write tokenised SCL SimaticML. Details are in the `siemens` skill.
- **TwinCAT:** `.TcPOU` with ST only. Graphical languages go through PLCopenXML import.
- **CODESYS / Machine Expert / AC500:** PLCopenXML (`tc6_0200`) or text pasted into the
  editor.
- **Logix:** L5X component export with a `Rung` or `Routine` target. Use the v36+
  mnemonics when targeting v36 or later.
- **Control Expert:** XEF sections (`.XST`) are tool-generated. Prefer generating ST
  that the user pastes, unless you have a sample export of the same version to mirror.
- **IEC 61499:** see the `iec-61499` skill. Scan idioms become events.
