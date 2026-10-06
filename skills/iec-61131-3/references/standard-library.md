# Standard functions and function blocks

## Conversions

- **Typed:** `INT_TO_REAL`, `REAL_TO_DINT`, and so on.
- **Overloaded (Ed.3):** `TO_INT(x)`, `TRUNC_INT(x)`.
- **REAL → integer rounds to nearest, ties to even:** `REAL_TO_INT(2.5) = 2` and
  `REAL_TO_INT(-1.5) = -2`. `TRUNC` truncates toward zero.
- **Narrowing** (DINT→INT, REAL→INT) can overflow. Either `LIMIT` first or check the
  range.
- **BCD:** `*_BCD_TO_*` and `*_TO_BCD_*` are deprecated in Ed.4.
- **Vendor names differ.** Siemens uses `CONVERT`/`INT_TO_REAL` plus `ROUND`/`TRUNC`
  with typed results, and Logix uses `MOV` with implicit conversion. Check before porting.

## Numeric, bit and selection functions

| Group | Functions |
|---|---|
| numeric | `ABS SQRT LN LOG EXP SIN COS TAN ASIN ACOS ATAN ATAN2`(Ed.3) |
| arithmetic | `ADD MUL` (extensible), `SUB DIV MOD EXPT MOVE` |
| bit shift | `SHL(IN, N)`, `SHR` (zero-fill), `ROL`, `ROR`. A negative N is an error |
| bitwise | `AND OR XOR NOT` on `ANY_BIT` |
| selection | `SEL(G, IN0, IN1)`, `MAX`, `MIN`, `LIMIT(MN, IN, MX)`, `MUX(K, IN0…)` (K out of range is an error) |
| comparison | `GT GE EQ LE LT` (extensible), `NE` |

## Strings (positions are 1-based)

| Function | Result |
|---|---|
| `LEN(s)` | length |
| `LEFT(s, L)` / `RIGHT(s, L)` | first / last L chars |
| `MID(s, L, P)` | L chars starting at P |
| `CONCAT(a, b, …)` | concatenation |
| `INSERT(s1, s2, P)` | insert s2 after position P |
| `DELETE(s, L, P)` | delete L chars from P |
| `REPLACE(s1, s2, L, P)` | replace L chars at P with s2 |
| `FIND(s1, s2)` | position of s2 in s1, or 0 |

The Ed.4 additions `LEN_MAX`, `LEN_CODE_UNIT` and the string↔byte-array conversions
apply only to Ed.4 toolchains.

## Standard FBs

| FB | Inputs | Outputs | Behaviour |
|---|---|---|---|
| `SR` | `S1`, `R` | `Q1` | **set-dominant** bistable |
| `RS` | `S`, `R1` | `Q1` | **reset-dominant** bistable |
| `R_TRIG` | `CLK` | `Q` | Q is TRUE for one call after CLK rises (`Q := CLK AND NOT M; M := CLK;`) |
| `F_TRIG` | `CLK` | `Q` | one call after CLK falls |
| `CTU` | `CU`↑, `R`, `PV` | `Q`, `CV` | counts rising edges of CU; `Q := CV >= PV` |
| `CTD` | `CD`↑, `LD`, `PV` | `Q`, `CV` | `LD` loads PV; `Q := CV <= 0` |
| `CTUD` | `CU`↑, `CD`↑, `R`, `LD`, `PV` | `QU`, `QD`, `CV` | |
| `TP` | `IN`, `PT` | `Q`, `ET` | pulse of length PT on IN↑; not retriggerable while running |
| `TON` | `IN`, `PT` | `Q`, `ET` | Q goes TRUE after IN has been TRUE for PT. **IN FALSE resets it** |
| `TOF` | `IN`, `PT` | `Q`, `ET` | Q stays TRUE for PT after IN falls |

Typed counter variants (`CTU_DINT`, `CTU_UDINT`, …) and LTIME timers exist in Ed.3. The
exact typed timer names vary by vendor; Siemens, for example, uses `TON_TIME` and
`TON_LTIME`.

**All of these FBs work by being called.** A timer measures elapsed time only while it
is being called with its current `IN`, and an edge detector compares against the value
from its previous call. If the call is skipped, the output freezes. That is the most
common PLC bug in generated code; see the `debug` skill and validator rules
ST030–ST033.
