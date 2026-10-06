# Data types and variables

## Elementary types

| Type | Bits | Notes |
|---|---|---|
| `BOOL` | 1 | |
| `SINT` / `INT` / `DINT` / `LINT` | 8 / 16 / 32 / 64 | signed |
| `USINT` / `UINT` / `UDINT` / `ULINT` | 8 / 16 / 32 / 64 | unsigned |
| `REAL` / `LREAL` | 32 / 64 | IEC 60559. REAL has about 7 significant digits, so summing small increments into a large total loses them |
| `BYTE` / `WORD` / `DWORD` / `LWORD` | 8 / 16 / 32 / 64 | bit strings: no arithmetic without conversion |
| `TIME`, `DATE`, `TIME_OF_DAY`/`TOD`, `DATE_AND_TIME`/`DT` | implementation-dependent | often 32-bit ms for TIME (for example CODESYS), so it wraps after about 49.7 days as UDINT |
| `LTIME`, `LDATE`, `LTOD`, `LDT` | 64 | Ed.3; nanoseconds (LDATE/LDT count from 1970-01-01) |
| `STRING` / `WSTRING` | 8 / 16 per char | default length is implementation-dependent (CODESYS: 80); write `STRING(255)` |
| `CHAR` / `WCHAR` | 8 / 16 | Ed.3 |
| `USTRING` / `UCHAR` | UTF-8 | Ed.4 |

**Default initial values:** 0, 0.0, `FALSE`, `T#0S`, `D#0001-01-01`, `TOD#00:00:00` and
empty strings. Vendors vary for DT and DATE, so initialise explicitly (PLCopen CP3).

## Generic types

These may be used only by standard or vendor functions. User POUs may not use them in
the standard, although TwinCAT and CODESYS relax this with `ANY`.

`ANY` ⊃ `ANY_DERIVED`, `ANY_ELEMENTARY` ⊃ `ANY_MAGNITUDE` (⊃ `ANY_NUM` (⊃ `ANY_REAL`,
`ANY_INT`), `TIME`), `ANY_BIT`, `ANY_STRING`, `ANY_DATE`.

Ed.3 refines the tree with `ANY_SIGNED`, `ANY_UNSIGNED`, `ANY_DURATION`, `ANY_CHAR` and
`ANY_CHARS`. That list comes from secondary sources and was not verified in the
standard's text.

## Derived types

```iecst
TYPE
    E_State : (Idle, Running, Faulted);                             // enumeration: E_State#Running
    E_Cmd   : WORD (None := 0, Start := 1, Stop := 2) := None;      // Ed.3 typed enum with named values
    T_Pct   : INT (0..100);                                          // subrange
    T_Buf   : ARRAY[1..16] OF REAL;
    ST_Axis : STRUCT
        rPos : LREAL;
        xRef : BOOL;
    END_STRUCT;
    T_Freq  : REAL := 50.0;                                          // directly derived with default
END_TYPE
```

- **Variable-length arrays (Ed.3):** `VAR_IN_OUT aData : ARRAY[*] OF REAL; END_VAR`,
  bounded with `LOWER_BOUND(aData, 1)` and `UPPER_BOUND(aData, 1)`.
- **References (Ed.3):** `REF_TO T`, `REF(x)`, `r^` and `NULL`. Vendors also offer
  `POINTER TO` and `REFERENCE TO` (CODESYS/TwinCAT), `VARIANT`/`DB_ANY` (Siemens), and
  `ANY` pointers (S7 classic).
- **Naming:** PLCopen N10 recommends type prefixes: `E_` enum, `ST_` struct, `T_`/`A_`,
  `FB_`, `I_`, `REF_`. Siemens uses `typ` for UDTs; see the `siemens` skill.

## Variable sections

| Section | Visibility / direction | Notes |
|---|---|---|
| `VAR` | internal | FB/PROGRAM state |
| `VAR_INPUT` | caller → POU | read-only inside the POU |
| `VAR_OUTPUT` | POU → caller | readable after the call as `inst.out` |
| `VAR_IN_OUT` | by reference | must be connected. RETAIN/NON_RETAIN are not allowed |
| `VAR_EXTERNAL` | refers to a `VAR_GLOBAL` | `CONSTANT` must match |
| `VAR_GLOBAL` | global | PLCopen and TR 61131-8 discourage heavy use |
| `VAR_TEMP` | per call | **re-initialised every call; never assume it holds its value** |
| `VAR_ACCESS` | access paths for communication | |
| `VAR_CONFIG` | instance-specific init and addresses | completes `%I*` |
| `VAR_STAT` / `VAR_INST` | CODESYS extensions | static in functions or methods |

**Qualifiers:**

- `CONSTANT`.
- `RETAIN` and `NON_RETAIN`: a warm restart keeps RETAIN values, and a cold restart
  re-initialises them. CODESYS/TwinCAT also have `PERSISTENT`, which survives downloads.
- `AT %IX0.0`, and `R_EDGE`/`F_EDGE` on BOOL inputs.
- `RETAIN` on an FB or struct instance applies to all of its members. It **cannot be
  applied to individual struct members** in the standard.

## Direct addresses

Form: `%` + `I` | `Q` | `M` + size (`X` or none, `B`, `W`, `D`, `L`) + dotted unsigned
integers.

- Valid: `%IX0.0`, `%QX75`, `%IW215`, `%QB7`, `%MD48`, `%IW2.5.7.1`.
- Partially specified `%I*` must be completed in `VAR_CONFIG`.
- **Vendor addressing differs:**
  - Siemens: `%I0.0`, `%DB1.DBX0.0`.
  - Schneider Control Expert: `%MW100`, `%M10`, `%KW`, `%S`, `%SW`.
  - Rockwell: tag-based, with no % addresses.
  
  Whether `%MW` and `%MD` alias each other, and how, depends on whether the memory is
  byte-addressed or word-addressed, and differs between platforms. Check the platform's
  addressing rules before mixing access widths on one area.
