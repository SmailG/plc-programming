# Design method: from narrative to program structure

## 1. Control narrative (outline)

1. **Purpose and scope**: what the equipment does and its boundaries (what it controls
   and what it only reports).
2. **Equipment list**: devices and their IDs, following the P&ID or electrical drawings.
3. **Operating modes**: Auto / Manual / Maintenance / Out of service, and who can switch
   between them, and how.
4. **Normal sequence**, step by step, with the transition condition for each step.
5. **Start-up**, including cold start, warm restart and power return. Decide what may
   restart automatically. **By default, nothing restarts on its own after a power loss.**
6. **Shutdown**: normal stop, fast stop, and emergency stop. The emergency stop is
   hardware and safety-program territory; the standard program only reacts to it.
7. **Interlocks**:
   - **Permissives**: conditions that must be true before a start.
   - **Trips**: conditions that force a stop while running.
   - For each one, state whether it latches and how it is reset.
8. **Alarms**: condition, priority, delay, latching, and operator action.
9. **Interfaces**: HMI/SCADA, other PLCs, MES/cloud (OPC UA, Modbus, MQTT), and what is
   read-only.

## 2. I/O list columns

| Tag | Description | Type (DI/DO/AI/AO/comm) | Signal (24 VDC, 4–20 mA, …) | Range / EU | Fail-safe state | Wiring (NO/NC) | Module / channel / address | Notes |
|---|---|---|---|---|---|---|---|---|

**Rules:**

- Every safety-relevant or stop signal is wired **NC** and read as TRUE = healthy.
- Every analog signal has its range and units stated. Never assume a raw range.
- Addresses come from the hardware configuration, not from memory.

## 3. Interlock matrix (cause and effect)

Rows are causes (a tag and its condition). Columns are effects (devices), and each cell
says **P** (permissive), **T** (trip) or **TL** (trip, latched). Siemens TIA has a
Cause-Effect-Matrix language (CEM) on S7-1200 FW ≥ 4.2 and S7-1500 FW ≥ 2.6. CEM blocks
cannot go through VCI and cannot be downloaded without reinitialization. Elsewhere the matrix is implemented as
explicit Boolean expressions per device, with one line per cause and a comment naming
the matrix row.

## 4. Architecture (ISA-88 flavoured)

```text
Unit / machine (PackML or ISA-88 phase state machine)
 ├─ Equipment modules (dosing, heating, conveying) – coordinate control modules
 │   └─ Control modules = one FB instance per device (FB_Motor, FB_Valve, FB_AnalogIn, FB_Pid…)
 ├─ Mode manager (Auto/Manual/Maintenance), alarm manager (first-out, horn, ack)
 └─ Interfaces (HMI structs, comms, OPC UA symbol set)
```

- **One FB type per device type.** Each instance holds its own supervision and alarms.
  Sequences talk to devices only through their command and status interface.
- **Keep sequence logic and device logic apart.** A sequence requests a state ("valve
  open"), and the device FB decides whether that is allowed (interlocks) and reports
  whether it happened (feedback).
- **Keep interlocks close to the device** (in the device FB call) so that no sequence
  can bypass them.

## 5. State machine design procedure

1. List the states. Name each one as a condition that holds, such as Filling or Heating,
   not as an action.
2. For each state, write down its entry actions, what it outputs while active, its exit
   conditions (each leading to exactly one next state), and its **timeout** (leading to
   a fault state).
3. Add Stop, Abort and Fault as global overrides evaluated after the normal transition,
   so that they win.
4. Implement it as an enum plus `CASE` (see [code-patterns.md](code-patterns.md)), or as
   SFC where the platform and team prefer it.
5. Derive outputs from the state, and write each output once.
6. Expose the state number and the step timer to the HMI for diagnostics.

## 6. Tasks and timing

- **Cycle time budget:** measure it, do not guess. Typical splits are:
  - Fast (1–10 ms): high-speed counting, motion.
  - Normal (10–100 ms): I/O, interlocks, device FBs.
  - Slow (100 ms–1 s): sequences, communications, historian or cloud packing.
- **Watchdog:** loops over large arrays, string handling and communication blocks are
  the usual causes of an overrun. Bound every loop.
- **Cross-task data:** a value written in one task and read in another can be observed
  half-updated. Copy the data into a local struct at the start of the reader, use the
  platform's consistent-copy mechanism, or use a sequence counter.

## 7. Restart and retain

Decide per variable:

- **RETAIN:** survives a power cycle (warm start).
- **PERSISTENT** (CODESYS/TwinCAT/Machine Expert) or **"retain in the instance DB with
  download without reinitialization"** (Siemens): survives a download.
- **Neither:** re-initialises.

Totalisers, recipes and calibration usually persist. **Commands and run requests must
never persist**, or the machine restarts on power return.

## 8. Commissioning checklist (hand to the user)

1. I/O check (point to point): every input seen, every output driven, with the loop
   powered and the field device isolated as needed.
2. Analog scaling verified at 0 %, 50 % and 100 % of each range.
3. Every interlock and trip tested by forcing the **cause**, never the effect.
4. Every sequence step and timeout exercised, including the fault paths.
5. Power-fail, restart and download behaviour tested (retain/persistent values).
6. Communication loss tested (the PLC reacts safely and flags stale data).
7. **All forces removed**, and the final version archived with its checksum and version.
