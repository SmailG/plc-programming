# Siemens diagnostics, debugging, Safety Integrated, motion and PID

## Debugging tools

- **Program status (online monitoring).** For a multi-instance FB, set the **call
  environment** (an instance DB or call path) so that you see *that* instance. On S7-1500
  FW ≥ 2.5 the call environment and breakpoints are mutually exclusive.
- **Watch tables** can modify values, optionally with a trigger.
- **Force tables** force **only peripheral I/O.**
  - **A force stays active after you go offline** and must be ended with "Stop forcing".
  - Forcing is impossible while "Enable peripheral outputs" is active.
  - Always check the force list when behaviour makes no sense.
- **Breakpoints** exist in SCL and STL on S7-1500.
- **Trace and logic analyzer** (S7-1500 CPU traces): sample signals over time. This is the
  right tool for sub-cycle and intermittent timing questions.
- **Diagnostic buffer:** read it first. The program writes to it with **`Gen_UsrMsg`**.
  `Program_Alarm` must be called inside an FB and carries up to 10 associated values.
- **ProDiag** supervisions (S7-1500).

## Error handling

- **Local handling:** EN/ENO, the `RET_VAL`/`STATUS`/`ERROR` outputs, and
  `GET_ERROR`/`GET_ERR_ID`.
- **Global handling:** OB121 (programming error) and OB122 (I/O access error) on
  S7-1200/1500, and OB85 on S7-300/400.
- **Inserting `GET_ERR_ID` into a block disables the system reaction for that block.**
  It reports only the **first** error. Examples:
  - `16#2522`: read error, operand out of range.
  - `16#2503`: invalid pointer.
  - `16#2533`: invalid reference.
  
  The failed read returns 0 and execution continues. Evaluate the error; do not just
  suppress the STOP.

## S7-specific review checklist

1. **Array index out of range.** The S7-1500 goes to **STOP** (unless OB121 or local
   `GET_ERROR` handles it). The S7-1200 logs it and stays in RUN. ENO is **not** cleared
   on either.
2. **Cycle time exceeded.** This calls OB80, and means STOP if OB80 is missing or on a
   second overrun in one cycle. Look for unbounded loops, `Serialize`, file and symbol
   instructions, or large VARIANT loops in the cycle.
3. **A Temp read before it is written.** It holds garbage in standard blocks and a
   silent 0 in optimized ones.
4. **Instance DB re-initialisation** after an interface change downloaded without the
   reinitialization-free option.
5. **Mixing optimized and standard blocks**, which causes copies, temp overflow and slow
   execution.
6. **Reading your own FB outputs, or writing outputs several times** (DA008).
7. **A TON call skipped, or one instance shared by two calls, or `IN` pre-written** on a
   multi-instance timer so that it never sees a rising edge.
8. **REAL compared with `=`** (SE007).
9. **Data wider than a word** written by an interrupt OB and read in OB1 without
   `UMOVE_BLK`.
10. **CASE without ELSE**, or a state variable in Temp instead of Static.
11. **Modbus register off by one:** the buffer offset is 0-based, while clients count
    from 40001.
12. **A force left active** after the session ends.
13. **A NULL reference dereferenced** (a programming error).

## Safety Integrated (F-CPU)

**Program structure:**

- There are one or two **F-runtime groups**. Each is an F-OB (a cyclic interrupt) that
  calls the **main safety block** (an F-FB or F-FC), which calls further F-blocks.
- Supporting blocks: F-DBs, F-I/O DBs, and the F-runtime group information DB
  (`F_SYSINFO.F_PROG_SIG`).
- The two groups exchange data only through F-runtime group communication.

**Language restrictions:**

- **F-LAD and F-FBD only; no SCL.**
- Allowed types: BOOL, INT, WORD, DINT, TIME, F-compliant UDTs and NVTs.
  **No REAL, BYTE, STRING, STRUCT or slice access.**
- Arrays of INT/DINT are allowed only in F-DBs, read through `RD_ARRAY_I`/`RD_ARRAY_DI`.
- EN cannot be wired. ENO exists only on ADD, SUB, MUL, DIV, NEG, ABS and CONVERT.
- **An overflow can put the F-CPU into STOP.**
- F-I/O inputs are read-only and outputs write-only.
- Bit memory and standard DBs may be used only to exchange data with the standard
  program. Every value read that way needs a plausibility check.

**Other rules:**

- The **standard program may read** F-DBs and the F-I/O process image, but it has no
  integrity guarantee on that path.
- The **Safety Administration Editor** covers safety mode, the **collective
  F-signature** (program identification: compare the online signature with the expected
  one), F-runtime groups, access protection and Flexible F-Link.
- **PROFIsafe:** each F-I/O has an F-destination address, and V21 adds a PROFIsafe
  Base ID.
- **Standards:** IEC 61508 (SIL), IEC 62061 (SIL, machinery), ISO 13849-1 (PL/Category).
- **Never present generated F-code as validated.** Acceptance is the user's safety
  validation, with the signature recorded.

## Motion (technology objects) and PID

- **Technology objects:** `TO_SpeedAxis`, `TO_PositioningAxis`, `TO_SynchronousAxis`,
  `TO_ExternalEncoder`. **Absolute moves need a homed axis.** The motion OBs are 91 and 92.
- **`MC_Power`:**
  - `Axis` is InOut. `Enable` is level-sensitive.
  - `StopMode`: 0 = emergency ramp, 1 = immediate, 2 = maximum dynamics.
  - **Disabling it aborts every job.**
- **`MC_MoveAbsolute`:**
  - It starts on the **rising edge of `Execute`**.
  - For Velocity, Acceleration, Deceleration and Jerk, **a value below 0 means "use the
    TO's dynamic defaults", and 0 is not allowed.**
  - It is aborted by Halt, by other Move jobs, and by `MC_Power.Enable := FALSE`.
  - It follows the PLCopen Execute/Done/Busy/CommandAborted/Error/ErrorID pattern.
- **PID:**
  - `PID_Compact` V2 (S7-1500, S7-1200 V4) and V3 (S7-1500 ≥ 3.1, S7-1200 G2),
    `PID_3Step` and `PID_Temp`. The instance DB is the technology object, with
    pretuning and fine tuning.
  - The classic `CONT_C`/`CONT_S`/`TCONT_*` exist on S7-1500/300/400.
  - Calling PID instructions from a cyclic interrupt OB is common practice; that it is
    required was not verified.
