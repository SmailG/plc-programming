# SCL language details and Siemens data types

## SCL beyond IEC ST

- **Names:**
  - `#local` for locals and parameters. The editor adds `#`; it is optional for locals
    in external sources.
  - `"Global"` for global tags and DBs, as in `"DB".member`.
  - `#C` for local constants and `"C"` for global constants.
- **Operators:**
  - `**`, `MOD`, `AND`/`&`, `XOR`, `OR`, `NOT`.
  - Combined assignments: `+=`, `-=`, `*=`, `/=`.
  - References: `REF`, `^`, `?=`.
- **Control flow:**
  - `REGION name … END_REGION`.
  - `GOTO label;` works only within the block, and cannot jump into a loop.
  - `CONTINUE`, `EXIT` and `RETURN`.
  - `CASE` with value lists and ranges (`1, 3..5:`) and `ELSE`. Style guide DA017
    requires the `ELSE`.
- **Slice access:**
  - `#w.%X0` (bit), `.%B1` (byte), `.%W0` (word), `.%D0` (dword).
  - It works on bit strings. On integers it compiles only with the IEC check off.
  - It cannot be used on structures, constants or AT-overlaid tags.
- **Absolute and peripheral access:**
  - `%I0.0`, `%MW10`, and `%DB10.DBW2` (standard DBs only).
  - `"Tag":P` reads or writes the peripheral directly. Avoid writing `:P` several times
    in one cycle.
- **Typed literals:**
  - Times: `T#200ms`, `LT#…`, `S5T#10s`.
  - Dates: `DT#1990-01-01-00:00:00`, `DTL#2008-12-16-20:30:20.250`, `LDT#…`, `TOD#…`, `D#…`.
  - Numbers: `16#7000`, `2#0000_0011`, `INT#16#7FFF`, `REAL#40.5`.
  - Strings: `WSTRING#'x'`, single quotes, and the escapes `$L $N $R $T $$ $'`.
- **Calls:**
  - Single instance: `"IEC_Timer_0_DB".TON(IN := …, PT := T#5S, Q => …, ET => …);`
  - Multi-instance: `#instTimer(IN := …, PT := …);`
  - FB with its own DB: `"FB_X_DB"(…);`
  - An FC's return value is assigned as `#FcName := …`.
- **Breakpoints** exist only in SCL/STL on S7-1500 (and 300/400), and never at an `END_…`.
  They exclude a call environment on FW ≥ 2.5.

## External source rules

- One file can hold several UDTs, DBs and blocks. Declare types before the blocks that
  use them; exports do this, but whether generation requires it is unverified.
- Keywords are case-insensitive. Every statement and declaration ends with `;`.
- Allowed encodings are ANSI, or UTF-8/16/32 **with BOM**.
- **"Generate blocks from source" overwrites existing blocks.** Errors refer to source
  line numbers.
- Know-how-protected blocks cannot be sources. STL sources work only for S7-300/400/1500.
- Header and attribute keywords seen in real exports:
  - Headers: `TITLE`, `AUTHOR`, `FAMILY`, `NAME`, `VERSION`.
  - `{ S7_Optimized_Access := 'TRUE' }`.
  - Per-variable attributes: `{ ExternalAccessible := 'False'; ExternalVisible := 'False'; ExternalWritable := 'False'}`,
    `S7_SetPoint`, `S7_HiddenAssignment`.
  - `{InstructionName := 'TON_TIME'; LibVersion := '1.0'}` on system-FB multi-instances.
    It is optional when hand-writing.
- Sections: `VAR_INPUT`, `VAR_OUTPUT`, `VAR_IN_OUT`, `VAR`, `VAR RETAIN`, `VAR_TEMP`,
  `VAR CONSTANT`.
- **An instance DB** is `DATA_BLOCK "Inst" { … } VERSION : 0.1 NON_RETAIN "FB_Type" BEGIN END_DATA_BLOCK`.
- **A DB derived from a UDT** is `DATA_BLOCK "Settings" … "typeX" BEGIN member := value; END_DATA_BLOCK`.
- **VCI export formats (V20):**
  - LAD, FBD, GRAPH, F-DB, technology objects and tag tables: **XML only**.
  - SCL: `.xml` or `.scl`. STL: `.xml` or `.stl`. DB: `.xml` or `.db`. UDT: `.xml` or `.udt`.
  - V21 adds SD for SCL, FBD, LAD, DB, F-DB, UDT and F-UDT.

## Data types beyond IEC

| Type | Where | Size / notes |
|---|---|---|
| `DTL` | S7-1200/1500 | 12 bytes: Year UINT, Month, Day, Weekday (1 = Sunday), Hour, Minute, Second (USINT), Nanosecond UDINT; 1970 to 2262 |
| `DATE_AND_TIME` / `DT` | 300/400/1500 | 8 bytes BCD, years 1990–2089 |
| `LDT`, `LTIME`, `LTOD`, `LWORD`, `LINT`, `ULINT` | S7-1500 | 64-bit; LDT is ns since 1970 |
| `S5TIME` | 300/400/1500 | 16-bit BCD, time base 10 ms / 100 ms / 1 s / 10 s; maximum `S5T#2H_46M_30S` |
| `STRING[n]` / `WSTRING[n]` | | n + 2 bytes / n + 2 words; default 254 characters (WSTRING maximum: the sources say 16382 characters or 65534 words) |
| `VARIANT`, `DB_ANY` | 1200/1500 | see platform-and-structure.md |
| `POINTER` (6 B), `ANY` (10 B, `P#DB11.DBX20.0 INT 10`) | 300/400/1500 | **on S7-1500, ANY can point only to standard-access memory** |
| `HW_ANY`, `HW_IO`, `HW_DEVICE`, `HW_SUBMODULE`, `HW_INTERFACE`, `HW_HSC`, `HW_PTO`, `OB_*`, `CONN_OUC`, `CONN_ANY` … | 1200/1500 | hardware identifiers (UINT); their constants are under "System constants" |
| `REF_TO`, NVT, `IEC_LTIMER`, `IEC_LCOUNTER` | S7-1500 | – |

**Timers and counters:**

- **IEC timers** are `TP`, `TON`, `TOF` and `TONR`.
  - The instance is an `IEC_TIMER`/`IEC_LTIMER` DB (single instance) or a
    `TON_TIME`/`TOF_TIME`/`TP_TIME`/`TONR_TIME` (or `*_LTIME`) Static tag
    (multi-instance, preferred by style guide AL001).
  - **They update only when called, and they start on a rising edge of IN.** Do not
    pre-write `IN` on a multi-instance timer.
- **S5 timers** (`S_ODT`, `S_PULSE` and the rest) are numbered timers on
  S7-300/400/1500, **not S7-1200**. They are less accurate; avoid them in new code.
- **Counters** use `IEC_COUNTER`, `IEC_SCOUNTER`, `IEC_DCOUNTER` and similar types.
