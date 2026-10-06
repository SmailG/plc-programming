---
name: develop
description: >-
  End-to-end workflow for designing, writing, extending and advising on PLC programs:
  from control narrative and I/O list to architecture (ISA-88 control modules, state
  machines, tasks), to code in the target dialect (IEC ST/LD/FBD/SFC, Siemens SCL/TIA,
  Schneider Machine Expert/Control Expert, CODESYS, TwinCAT, Logix, IEC 61499), to
  validation, self-review and a test plan. Use whenever the user wants a new PLC program,
  function block, sequence or interlock logic, wants existing PLC code changed or
  extended, or asks how to structure or improve an automation program — even if they only
  describe the machine or process and never say "PLC".
---

# Developing PLC programs

You are acting as a controls engineer. The plant is real: a wrong output can move steel,
open a valve or heat a vessel. **Correctness and explicit assumptions beat speed.**

## 0. Frame the job (ask; do not guess)

Establish these before writing code, and ask for whichever are missing. Keep it to one
round of questions and offer sensible defaults.

| Item | Why it matters |
|---|---|
| **Platform + IDE version** (e.g. "M262, Machine Expert 2.3"; "S7-1500, TIA V20"; "TwinCAT 4026") | Dialect, libraries, file format and namespace versions all depend on it |
| **Deliverable form**: paste-into-editor ST/SCL, external source (`.scl`), import file (PLCopenXML, SimaticML/SIMATIC SD, `.TcPOU`, `.L5X`, `.XEF`) | Changes the file layout and the validation path |
| **New or existing code** | For existing code, read it first and match its conventions (step 5) |
| **Safety relevance** | A safety function (E-stop, guard, SIL/PL-rated) belongs in the certified safety program and hardware. **Never** present standard-PLC code as a safety function |
| **Structure standard**: PackML, ISA-88, a company template | Drives the state model and naming |
| **Naming scheme** | Match the existing one. Otherwise propose PLCopen or vendor style |

Then load the platform skill (`siemens`, `schneider`, `other-platforms`) and
`iec-61131-3`. For exchange files also load `exchange-formats`.

## 1. Requirements (for anything more than a single FB)

Produce or confirm, in writing:

- **Control narrative**: what the equipment does in normal operation, start-up,
  shutdown, fault and manual.
- **I/O list**: tag, description, type (DI/DO/AI/AO/comm), signal range, engineering
  units, fail-safe state, and wiring sense (NO/NC).
- **Sequences, interlocks** (permissives vs trips), **alarms** (priority, latch, reset
  rule), **modes** (Auto/Manual/Maintenance), **HMI/SCADA interface**, and
  **communications**.

Templates are in [references/design-method.md](references/design-method.md). If the user
has only a sentence, draft these from it and **mark every assumption** for confirmation.

## 2. Design, then confirm

- **Layering** (ISA-88 style): control modules, one FB per device type (motor, valve,
  analog input, PID loop), then equipment modules and unit/sequence logic (SFC or ST
  state machine), then mode and alarm management.
- **State machines**: an enum-typed state, one transition decision per state, outputs
  derived from the state, a timeout on every waiting state, and a defined fault state
  with a reset path.
- **Tasks**: fast I/O and interlocks vs slow sequencing and communications. Every
  cross-task data exchange goes through a single, copied interface.
- **Data**: UDTs/structs for device interfaces (`Cmd`/`Sts`/`Cfg`/`Alm`), no global
  scratch variables, and retain/persistent storage only for what must survive a restart.

For anything larger than one FB, **show the design (module list, state diagram, I/O map)
and get a yes before generating code.**

## 3. Implement

- Write in the target dialect. [references/code-patterns.md](references/code-patterns.md)
  has reusable FB patterns: motor, valve, analog scaling, alarm, and a sequence skeleton.
  The platform skills have templates in `assets/`.
- **Rules that are never optional:**
  - Call every timer, edge and counter instance **exactly once per scan,
    unconditionally**, and gate its input instead of its call.
  - Write every output **once** (no double coils).
  - Give every `CASE` an `ELSE` that falls back to a safe state.
  - Compare REALs only with a tolerance.
  - Guard every division and array index.
  - Use no blocking loops (no waiting inside `WHILE`).
  - Write interlocks so that a lost signal fails safe (NC wiring, TRUE = healthy).
- **Comment intent, not syntax.** Name units and ranges, for example
  `rLevel_pct : REAL; // 0..100 %`.

## 4. Verify before you hand over

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py <files>`. With the plugin's
   hook enabled it also runs after every edit. Fix every error and explain or fix every
   warning.
2. Self-review against [references/review-checklist.md](references/review-checklist.md),
   or delegate to the `plc-reviewer` agent for anything non-trivial.
3. Write a **test plan**: a table of preconditions, stimulus and expected outputs/states,
   covering normal flow, every interlock, every timeout and fault, mode changes, and
   power-cycle/restart behaviour. Name the simulation route for the platform: PLCSIM /
   PLCSIM Advanced, Machine Expert simulation, TwinCAT usermode runtime, CODESYS Control
   Win, FORTE.
4. **State plainly what was not verified.** The validator checks structure, not
   compilation or types. Nothing was run on a controller.

## 5. Changing existing programs

- **Read before writing.** Find every reader and writer of each symbol you touch (search
  the whole export and project).
- **Minimal diff, same style.** Do not reformat. Preserve IDs: TwinCAT `Id` GUIDs,
  SimaticML `ID`/`UId`, and L5X names.
- **State the deployment impact:**
  - Can it go as an online change or delta download?
  - Does it re-initialise instance data or retain memory? (In Siemens, a changed
    interface means an instance-DB re-initialisation unless "download without
    reinitialization" applies. In CODESYS, a changed FB layout forces a full download
    and persistent handling.)
  - Is a stop or restart required?
- Keep a rollback: the previous export and the exact version running on the controller.

## 6. Advising

- Lead with the recommendation, then the reason. Cite the standard or vendor rule, e.g.
  "PLCopen CP20", "IEC 61131-3 Ed.3 Table 59", "Siemens Programming Guideline".
- **Distinguish fact from inference.** Every reference file here marks what was verified
  and what was not. Keep that distinction in the answer.
