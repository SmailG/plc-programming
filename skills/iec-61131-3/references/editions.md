# IEC 61131-3 editions, and what changed

| Ed. | Designation | Published | Withdrawn |
|---|---|---|---|
| 1 | IEC 61131-3:1993 (originally IEC 1131-3) | 1993-03-22 | 2003-01-21 |
| 2 | IEC 61131-3:2003 | 2003-01-21 | 2013-02-20 |
| 3 | IEC 61131-3:2013 | 2013-02-20 | 2025-05-22 |
| 4 | IEC 61131-3:2025 | **2025-05-22** | current |

Sources: IEC webstore publications
[19080](https://webstore.iec.ch/en/publication/19080),
[19081](https://webstore.iec.ch/en/publication/19081),
[4552](https://webstore.iec.ch/en/publication/4552) and
[68533](https://webstore.iec.ch/en/publication/68533).

## Ed.3 (2013): "a compatible extension of the second edition"

Its foreword names the main additions: "new data types and conversion functions,
references, name spaces and the object oriented features of classes and function blocks".

- **OOP:** `CLASS`, `METHOD`, `INTERFACE`, `EXTENDS`, `IMPLEMENTS`, `THIS`, `SUPER`,
  `ABSTRACT`, `FINAL`, `OVERRIDE`, and the access specifiers `PUBLIC`, `PRIVATE`,
  `PROTECTED` and `INTERNAL`.
- **References:** `REF_TO`, `REF()`, `^`, `NULL`. Assignment attempt `?=`.
- **Namespaces:** `NAMESPACE … END_NAMESPACE`, `USING`, `INTERNAL`.
- **Types:** `LTIME`, `LDATE`, `LTOD`, `LDT` (64-bit, ns resolution), `CHAR`, `WCHAR`,
  variable-length `ARRAY[*]` with `LOWER_BOUND`/`UPPER_BOUND`, and typed enumerations
  with named values.
- **Statements and FBs:** `CONTINUE`, overloaded `TO_xxx` and `TRUNC_xxx` conversions,
  `ATAN2`, endianness conversions, `DAY_OF_WEEK`, and compare contacts in LD.
- **Deprecated:** Instruction List, octal literals, untyped `TRUNC`, and the action-block
  indicator variable in SFC.

## Ed.4 (2025)

Its foreword lists the significant changes as "a) inclusion of UTF-8 strings and their
associated functions" and "b) Annex B contains a comprehensive list of features that have
been added, removed or deprecated". The Ed.4 preview confirms the table of contents and
the definitions. The detailed feature list below comes from a secondary source,
[Henneken's comparison](https://stefanhenneken.net/2025/06/11/iec-61131-3-comparison-of-edition-3-and-edition-4/).

- **Removed:** Instruction List (clause 7.2 is now ST only), octal literals, and untyped
  `TRUNC`.
- **Added:**
  - `USTRING`/`UCHAR` (UTF-8), written as the literal `USTRING#'…'` or `U#'…'`.
  - `LEN_MAX` and `LEN_CODE_UNIT`.
  - String↔byte-array conversions, such as `STRING_TO_ARRAY_OF_BYTE`.
  - Character codes written `'${1F579}'`.
  - `ASSERT`.
  - `PROPERTY_GET`/`PROPERTY_SET`.
  - Clause 6.9, synchronisation, with a `MUTEX` (`LOCK`/`UNLOCK`/`TRYLOCK`) and
    `SEMA` (`ACQUIRE`/`RELEASE`/`TRY_ACQUIRE`), in both function and OO forms.
  - A pseudo-code reference implementation for the timers.
- **Deprecated:** the BCD functions (`IS_VALID_BCD`, `*_BCD_TO_*`, `*_TO_BCD_*`).
- **Not verified from the primary text:** the full Annex B, the changes to generic types
  such as `ANY_CHARS`, and the exact encoding of `STRING`.

## Practical consequences in 2026

- Most IDEs implement Ed.3 plus their own extensions. Before using an Ed.4-only feature,
  check the target IDE's release notes.
- Several IDEs still offer IL for legacy projects. Never write new IL. When maintaining
  IL, consider migrating it to ST; see [instruction-list.md](instruction-list.md).
- IEC 61131-10 (PLCopen XML as an IEC standard, 2019) still targets Ed.3, so it still
  contains IL.

## IEC TR 61131-8: guidelines for application and implementation

- The current edition is **IEC TR 61131-8:2017 (Ed.3.0)**, published 2017-11-22 and based
  on 61131-3:2013. No Ed.4-aligned revision had been published as of 2026-09
  ([webstore 33021](https://webstore.iec.ch/en/publication/33021)).
- Section 7.15 lists **deprecated programming practices**:
  - global variables
  - jumps in FBD/LD
  - dynamic modification of task properties
  - execution control of FB instances by tasks
  - `WHILE`/`REPEAT` used for synchronisation between processes
  - expecting programs of one task to run sequentially

## Sources

- The Ed.3 and Ed.4 previews on the IEC webstore (front matter and table of contents).
- Siemens, "Standards compliance according to IEC 61131-3 (3rd Edition)", A5E35932122-AA
  (2015). Its feature tables are the evidence for the Ed.3 feature names:
  <https://cache.industry.siemens.com/dl/files/748/109476748/att_845621/v1/IEC_61131_compliance_en_US.pdf>
- PLCopen's standard-status page:
  <https://www.plcopen.org/standards/logic/iec-61131-3/status-iec-61131-3-standard/>
