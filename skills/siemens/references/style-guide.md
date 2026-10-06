# Siemens programming guidelines (paraphrased)

**Licence note.** The Siemens *Programming style guide* PDF says its application examples
may not be used for training or enhancing AI models. This file therefore contains **only
rule IDs and short summaries in our own words**, for citation. It contains no Siemens
text or code. Read the originals for the wording:

- *Programming style guide for S7-1200/S7-1500*, **V2.1.0 (04/2025)**, SIOS entry
  81318674: <https://support.industry.siemens.com/cs/attachments/109478084/81318674_Programming_Styleguide_DOC_V2_1_0_en.pdf>.
  A TIA Portal Test Suite rule set that implements it is SIOS 109779806.
- *Programming Guideline for S7-1200/S7-1500*, **V1.6 (12/2018)**, SIOS 90885040.
- Library Guideline: SIOS 109747503. LGF (Library of General Functions): SIOS 109479728.
  Safety Programming Guideline: SIOS 109750255.

## Rule families (style guide V2.1.0)

| Family | Gist |
|---|---|
| **ES001–009** TIA settings | English UI, international mnemonics, two-space indent with no tabs, symbolic operand display, IEC check on, HMI/OPC UA/Web access **off by default**, ENO evaluation on, runtime array-bounds evaluation on |
| **GL001–003** globalization | one consistent language; editing language English (US) |
| **NF001–014** naming and formatting | **UpperCamelCase** for objects (blocks, units, TOs, tables); **lowerCamelCase** for variables, UDTs, NVTs, structs and parameters; **UPPER_SNAKE_CASE** for constants; characters `a–z A–Z 0–9 _`, at most 24; initialise in the type's own format (`16#0001` for a WORD); hide optional parameters |
| **NF007** prefixes | none on parameters, PLC tags or global DBs; `temp`, `stat` (internal static), `ext` (static exposed to HMI/MES), `inst` (multi or parameter instance), `Inst` (single-instance DB), `type` (UDT), `nvt` (NVT) |
| **NF004** libraries | prefix `L` plus at most 7 characters (for example `LGF_`); constants `LNAME_STATUS_*` / `…_ERR_*` / `…_WARN_*`; a block header in a `REGION` with version `001.000.000` |
| **RU001–008** reuse | version through libraries; use only local variables inside library blocks; symbolic constants; no hardware dependence |
| **AL001–004** | prefer multi-instances; arrays run `0..CONSTANT`; `ARRAY[*]` parameters as InOut; explicit string lengths |
| **SE001–007** robustness | validate inputs; initialise temps; handle ENO; grant HMI/OPC UA access selectively; **evaluate every error code**; write real handlers in OB80/82/83/86/121/122; **never use `=` on REAL** (use ranges or `IN_RANGE`) |
| **DA001–019** design | UDTs for interfaces; exchange data only through formal parameters; statics private except `ext*`; more than 10 parameters become a UDT passed as InOut; **write outputs once and never read your own outputs**; no dead or commented-out code; **asynchronous blocks follow PLCopen** (`enable`/`valid`/`busy`/`error` or `execute`/`done`/`busy`/`error`) with `status` (WORD) and `error`; **CASE with ELSE**; avoid jumps |
| **PE001–017** performance | turn off "Create extended status info" in production; avoid "Set in IDB"; pass structures by reference; avoid VARIANT; use DINT loop indices; cache array, I/O and TO values; keep `Serialize`, file, DataLog and symbol functions out of the cycle; prefer SCL/LAD/FBD to GRAPH for time-critical code |

## Status word convention (DA014; the same scheme Siemens system blocks and the LGF use)

| Value | Meaning |
|---|---|
| `16#0000` | done, no details |
| `16#0001`–`0FFF` | done, with details |
| **`16#7000`** | no job active (the initial value) |
| `16#7001` | first call after a new job |
| `16#7002` | busy (subsequent calls) |
| `16#7003`–`7FFF` | busy with details, or a warning |
| `16#8001`–`81FF` | wrong operation |
| `16#8200`–`83FF` | wrong parameterisation |
| `16#8400`–`85FF` | external error (I/O, axis not homed) |
| `16#8600`–`87FF` | internal error |
| `16#9000`–`FFFF` | user-defined |

Bit 15 set means error. DA015 adds a `diagnostics` struct (`status`,
`subfunctionStatus`, `stateNumber`) that keeps the underlying error.

**When generating Siemens code, follow this naming and the status scheme unless the
project already uses something else.** When reviewing, cite the rule ID.
