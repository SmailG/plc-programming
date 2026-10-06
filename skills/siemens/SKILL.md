---
name: siemens
description: >-
  Siemens SIMATIC PLC programming with TIA Portal (V20, V21) and SIMATIC AX: S7-1200/1500
  (and legacy S7-300/400), OB/FB/FC/DB structure, optimized vs standard blocks,
  SCL/LAD/FBD/STL/GRAPH, SCL external sources (.scl/.db/.udt), SimaticML Openness/VCI XML
  (namespace versions per TIA version), SIMATIC SD (.s7dcl), instruction and data-type
  specifics (TON_TIME/IEC_TIMER, DTL, Variant), PROFINET/S7/OPC UA/Modbus communication,
  diagnostics, and Safety Integrated context. Use whenever the target is a Siemens PLC or
  TIA Portal, the code uses #local/"global" SCL syntax, or the file is a TIA export.
---

# Siemens TIA Portal / SIMATIC S7

## Versions (as of 2026-09)

- **TIA Portal V21** was announced on 2025-11-11. **V20** had reached Update 5 by 03/2026.
- **SIMATIC SD** (`.s7dcl`/`.s7res`) is the new Git-friendly text format:
  - LAD, UDT and DB from V20 Update 3.
  - SCL, FBD, F-FBD, F-DB and mixed blocks from V20 Update 4.
  - V21 extends it further.
  - It does **not** support STL.
- **SIMATIC AX** is a VS Code-based ST toolchain with apax, OOP and unit tests. It is
  "Early Access for selected productive use cases". **AX ST is not SCL.**

Always ask for the exact TIA version and the CPU family, for example "S7-1500, V20 Upd 4".
Formats, namespaces and the available instructions all depend on them.

## Choosing the deliverable

| User wants | Deliver |
|---|---|
| SCL code to paste or import | an **external source `.scl`**, imported via *External source files → Generate blocks from source*. Template: [assets/FB_Conveyor.scl](assets/FB_Conveyor.scl) |
| a Git round-trip of LAD/FBD/SCL (V20 Update 4 or later) | **SIMATIC SD** |
| automated generation of LAD/FBD blocks or tag tables | **SimaticML**, matching the namespace to the TIA version. Template: [assets/FC_LadDemo_V18.xml](assets/FC_LadDemo_V18.xml) |
| STL (AWL) | SimaticML or an `.awl` source; SD cannot carry it |

Full format detail, the namespace-version table and the SCL-vs-IEC differences are in
[references/simaticml-and-sources.md](references/simaticml-and-sources.md).

## SCL rules you must follow

- **Locals and globals:**
  - Inside code, locals take `#` (`#start`). Declarations do not.
  - Global symbols are double-quoted: `"DB_Line".speed`, `"FC_Scale"(…)`.
- **Structure:** code follows `BEGIN`. Blocks end with `END_FUNCTION_BLOCK`,
  `END_FUNCTION`, `END_DATA_BLOCK` or `END_TYPE`. `REGION … END_REGION` groups code.
- **Timers:**
  - Prefer **multi-instances** in the FB's static area: `tonX : TON_TIME;`, called as
    `#tonX(IN := …, PT := …);`. An `IEC_TIMER` variable is called as `#t.TON(…)`.
  - Call them **every cycle** and gate `IN` (validator rules ST030–ST033 understand
    `#inst(` and `#inst.TON(`).
- **Optimized access** (`{ S7_Optimized_Access := 'TRUE' }`) is the default on S7-1200
  and S7-1500. Do not rely on absolute offsets into optimized DBs.
- **Enums:** classic S7 has no IEC enums. Use named constants (a local or global
  constant) or an `Int` state with documented values.

## Traps that cost the most on site

1. **An FB interface change re-initialises its instance DBs on download.** Setpoints and
   counters go back to their start values. Plan for download without reinitialization
   (memory reserve), or, on V21 with S7-1500 FW 4.1, "Keep actual values". Otherwise back
   up actual values first.
2. **Array index out of range:** the S7-1500 goes to STOP unless OB121 or local
   `GET_ERROR` handles it, while the S7-1200 stays in RUN. ENO is not cleared, so check
   indices explicitly.
3. **Cycle overrun:** OB80 is called. The CPU stops if OB80 is missing, or on a second
   overrun in the same cycle.
4. **Temps:** in standard blocks they are undefined until written. Write before you read.
5. **In SCL, "Set ENO automatically" is off by default.** Programming and I/O access
   errors never reach ENO.
6. **Forces survive going offline**, and only peripheral I/O can be forced.
7. **Modbus TCP server:** register 0 is the first word of `MB_HOLD_REG`, which clients
   call 40001. Each connection needs its own instance DB and ID.
8. **PUT/GET** has to be explicitly permitted, and it has no security of its own.
9. **Safety programs are F-LAD/F-FBD only**, with no REAL. Never present generated
   F-code as validated.

## References

- [references/platform-and-structure.md](references/platform-and-structure.md): versions,
  controller families and languages, the OB table, optimized vs standard access,
  parameter passing, references and arrays, and download impact.
- [references/scl-and-data-types.md](references/scl-and-data-types.md): SCL syntax beyond
  IEC, external-source rules, DTL/S5TIME/ANY/VARIANT/HW types, and timers.
- [references/simaticml-and-sources.md](references/simaticml-and-sources.md): the `.scl`
  / SD / SimaticML / AX formats and the namespace table.
- [references/style-guide.md](references/style-guide.md): style-guide rule IDs (ES, NF,
  SE, DA, PE…), naming, and the `status` WORD convention. Paraphrased, for licence reasons.
- [references/communication.md](references/communication.md): PROFINET, PUT/GET and
  S7comm-plus, OUC/`TCON_IP_v4`, Modbus TCP/RTU, the OPC UA server and client with
  licences, and data consistency.
- [references/diagnostics-safety-motion.md](references/diagnostics-safety-motion.md):
  monitoring, force, trace and the diagnostic buffer, `GET_ERR_ID`, the S7 review
  checklist, Safety Integrated, `MC_*`, and PID.

## Validate

Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py <file>`.

| File | Rules |
|---|---|
| `.scl` / `.st` | ST0xx |
| SimaticML `.xml` | SM0xx: namespace vs TIA version, hex `ID`, per-network `UId`, wires, sections |
| `.s7dcl` | SD0xx: `NETWORK`/`RUNG` nesting only |

None of these is a TIA compile. Tell the user to compile in TIA and to fix what it reports.
