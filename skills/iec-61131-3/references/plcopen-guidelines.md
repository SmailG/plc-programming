# PLCopen conventions

## Coding Guidelines v1.0 (2016-04-20)

The document runs to 127 pages and draws on 61131-3 Ed.2 and Ed.3:
<https://www.plcopen.org/download_file/force/ff60e817-eee5-442d-b718-a357a7279c7e/342/>

Every rule carries an ID, an importance (high/medium/low), the languages it targets,
and a description, guideline and reasoning. The rules fall into five categories:
**N** naming (N1–N10), **C** comments (C1–C6), **CP** coding practice (CP1–CP28),
**L** languages (L1–L17), and **E** vendor extensions (E1–E3). The table below is a
**sample of the rules**, not the full set. When a review needs a rule that is not
listed here, read the document.

| ID | Imp. | Rule |
|---|---|---|
| N1 | High | Avoid physical addresses; declare a variable |
| N2 | Low | Define type prefixes for variables, if used |
| N3 | High | Names to avoid: IEC types, keywords, and meaningless names (`Info`, `Data`, `Temp`) |
| N4 | High | Consistent case. The proposal is UPPER_SNAKE_CASE for constants, types and keywords, and UpperCamelCase for everything else |
| N5 | High | Local names must not shadow global names |
| N10 | Low | Prefixes for user-defined types, in capitals |
| C1 / C2 | High | Comments describe intent; every element is commented |
| C5 | Low | Use `//` single-line comments |
| CP3 | High | Initialise variables before use |
| CP8 | High | No `=` / `<>` on floating point; use ranges (comparing with 0.0 is allowed) |
| CP12 | High | Write physical outputs once per PLC cycle |
| CP13 | High | No direct or indirect recursion |
| CP14 | High | Single point of exit; use `RETURN` only to return a function value |
| CP16 | High | Tasks call only PROGRAM POUs, not FBs |
| CP20 | Medium | Call each FB instance once per cycle |
| CP27 | Low | Avoid deprecated features: BCD, JUMP, task-to-FB association |
| L5 | Medium | In LD, a coil should not be followed by a contact |
| L7 | High | Close simultaneous divergent SFC paths correctly |
| L10 | Medium | Avoid `CONTINUE`/`EXIT` |
| L17 | Low (High in critical code) | Every `IF` has an `ELSE` |
| E1 | High | No dynamic memory allocation |
| E2 | High | No pointer arithmetic |
| E3 | High | Only `=`/`<>` on pointers and references |

## Naming prefixes proposed in N2 (optional; follow the project's own scheme first)

| Type | Prefix | Type | Prefix |
|---|---|---|---|
| BOOL | `x` | REAL / LREAL | `r` / `lr` |
| SINT / INT / DINT / LINT | `si` / `i` / `di` / `li` | TIME / LTIME | `tim` / `ltim` |
| USINT / UINT / UDINT / ULINT | `usi` / `ui` / `udi` / `uli` | STRING / WSTRING | `str` / `wstr` |
| BYTE / WORD / DWORD / LWORD | `by` / `w` / `dw` / `lw` | enum / array / struct | `e` / `a` / `st` |
| FB instance | `fb` | reference | `ref` |

- **Safety types** add a trailing `s`, for example `xs` for SAFEBOOL.
- **Scope prefixes** are optional: `g` global, `l` local, `p` parameter, `tmp` temporary.
- **Type-name prefixes (N10):** `E_`, `ST_`, `A_`, `FB_`, `FU_`, `PRG_`, `CLS_`, `I_`,
  `REF_`, plus domain prefixes such as `MC_` and `SF_`.
- **In practice** many shops use `b` for BOOL (Beckhoff style), `n` for integers and `f`
  for REAL. **Match the existing codebase** before imposing any scheme.

## Motion Control FBs (MC_*)

- The axis type is `AXIS_REF`, passed as `VAR_IN_OUT`.
- The axis state machine has these states: Disabled, Standstill, Homing,
  Discrete Motion, Continuous Motion, Synchronized Motion, Stopping and ErrorStop.
  `MC_Power` moves the axis from Disabled to Standstill, and `MC_Reset` from ErrorStop
  to Standstill.
- **Execute pattern:** outputs `Done`, `Busy`, `Active`, `CommandAborted`, `Error` and
  `ErrorID`.
  - Parameters are latched on the rising edge of `Execute`.
  - `Busy`, `Done`, `Error` and `CommandAborted` are mutually exclusive.
  - The outputs reset on the falling edge of `Execute`, **but the motion does not
    stop**.
  - A result output is held for at least one cycle even if `Execute` has already
    dropped.
- **Enable pattern:** `Enable` is level-sensitive. `Valid` is TRUE while the outputs are
  valid.
- **BufferMode:** Aborting (the default), Buffered, BlendingLow, BlendingPrevious,
  BlendingNext or BlendingHigh.
- Part 4 (Coordinated Motion) v2.0 was released in May 2026.

## Safety FBs (SF_*)

- Names start with `SF_`. Safety-typed pins start with `S_`, for example
  `S_EStopIn : SAFEBOOL`.
- **Common pins:**
  - Inputs: `Activate`, `S_StartReset`, `S_AutoReset`, and `Reset`, which acts on its
    rising edge.
  - Outputs: `Ready`, `Error` and `DiagCode` (WORD). `16#0000` means idle, `16#8xxx`
    means an active state, and `16#Cxxx` means an error.
- **Example, `SF_EmergencyStop` (v2.01):**
  - Inputs: `Activate`, `S_EStopIn`, `S_StartReset`, `S_AutoReset`, `Reset`.
  - Outputs: `Ready`, `S_EStopOut`, `SafetyDemand`, `ResetRequest`, `Error`, `DiagCode`.
- **Safety logic belongs in a certified safety program** (Siemens F-program,
  CODESYS Safety, M580 Safety) under IEC 61508, IEC 62061 or ISO 13849. It never goes
  in a standard task. Never generate safety logic for a standard PLC as though it were
  safe.

## Sources

- Coding Guidelines v1.0: the link at the top of this file.
- Motion Control: <https://www.plcopen.org/standards/motion-control/>, and the Part 1
  v2.0 Appendix B.
- Safety: <https://www.plcopen.org/standards/safety/>. The CODESYS general rules for
  safety FBs:
  <https://content.helpme-codesys.com/en/CODESYS%20Safety%20SIL2/plcopen_fbspecrules.html>
