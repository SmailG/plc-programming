# PLC code review checklist

Severity guide:

- **Critical**: can cause unsafe motion or damage, or defeat an interlock.
- **High**: wrong behaviour in normal operation or on faults.
- **Medium**: latent bug, restart or diagnostic gap.
- **Low**: style or maintainability.

Where a rule has an ID, cite it: validator `STxxx`/`PXxxx`, `PLCopen CPnn`, or a vendor rule.

## A. Scan-cycle semantics

- [ ] Every timer, edge and counter instance is called **once per scan, unconditionally**,
  with its input gated (ST030–ST033, PLCopen CP20).
- [ ] No FB instance is called at two places, or inside a loop.
- [ ] Every output is written once per scan (PLCopen CP12; Logix rule LX040 for OTE).
  In LD there are no double coils.
- [ ] S/R pairs have an explicit priority: the later rung wins, or use SR/RS.
- [ ] No logic depends on a value computed later in the same scan (a one-scan delay)
  unless that is intended and commented.
- [ ] No blocking `WHILE`/`REPEAT` waits for the process. Every loop is bounded.
- [ ] Pulses shorter than the task cycle are latched at the source or read from a
  hardware counter.

## B. State machines and sequences

- [ ] The state is an enum or named constant, not bare magic numbers.
- [ ] Each `CASE` has an `ELSE` that falls back to a safe state.
- [ ] Every waiting state has a timeout that leads to a fault state with a reset path.
- [ ] Stop, abort and fault override normal transitions: they are evaluated last, or they
  are guarded.
- [ ] SFC: exactly one initial step, simultaneous branches converge, and stored actions
  (`S`/`SD`/`DS`/`SL`) have a matching `R`.
- [ ] Outputs are derived from the state, not set and reset across many states.

## C. Interlocks and safety

- [ ] **Safety functions live in the safety program or hardware**, not in this code. If
  the code claims safety, flag it as Critical.
- [ ] Stop and trip inputs are read as TRUE = healthy (fail-safe wiring).
- [ ] Interlocks sit in or next to the device FB, so that no mode or sequence can bypass
  them. Manual mode still honours trips.
- [ ] Mutually exclusive outputs (forward/reverse, open/close) are software-interlocked,
  and hardware-interlocked as well (note this if it cannot be verified).
- [ ] Nothing restarts automatically after a power return, reset or mode change without
  an explicit, intended command.
- [ ] Writes from HMI or OPC UA are validated: range, state and permission.

## D. Numerics

- [ ] No `=`/`<>` on REAL (ST020, PLCopen CP8). Use tolerances.
- [ ] Division by zero is guarded. Array indices are range-checked, using the platform's
  out-of-range behaviour as a backstop, not a design.
- [ ] Integer overflow is prevented or checked: narrowing conversions (DINT→INT,
  REAL→INT), counters and TIME wrap.
- [ ] The rounding of REAL→INT is understood: it rounds half to even; `TRUNC` truncates.
- [ ] Analog scaling uses the module's documented raw range, and clamps. Wire break is
  handled.

## E. Data, memory and restart

- [ ] No uninitialised reads, especially temp or stack variables (PLCopen CP3; Siemens
  non-optimized TEMP).
- [ ] Retain and persistent storage is chosen deliberately. Commands and run requests do
  not persist.
- [ ] The effect of a download or interface change is understood: instance
  re-initialisation, and loss of persistent data.
- [ ] Cross-task data is copied consistently.
- [ ] No pointer arithmetic, dynamic allocation or unchecked references (PLCopen E1–E3).

## F. Communications

- [ ] Every remote value has a quality or freshness indication (a heartbeat or
  timestamp), and the logic reacts to stale data safely.
- [ ] Modbus register numbering is correct: a 1-based "4xxxx" reference against the
  0-based PDU address, word order for 32-bit values, and scaling.
- [ ] Communication FBs follow the Execute/Done/Busy/Error pattern correctly: a new
  request is issued only after Done or Error, and errors are latched and reported.

## G. Diagnostics and maintainability

- [ ] Every fault sets an identifiable code or alarm. First-out is used where several
  trips can cascade.
- [ ] Names follow the project scheme. Units and ranges are stated in comments.
- [ ] Comments state intent (PLCopen C1/C2). Commented-out dead code is removed.
- [ ] There are no magic numbers: use named constants or configuration.
- [ ] Vendor extensions in otherwise portable code are marked.

## H. Deliverable

- [ ] The validator ran with no errors, and each warning was addressed or justified.
- [ ] A test plan exists that covers the normal flow, each interlock, each timeout and
  fault, mode changes, and restart.
- [ ] Anything not verified is stated, for example "not compiled in TIA V20".
