# Siemens file formats: SimaticML, external sources, SIMATIC SD, AX

Pick the format by what the user will do with it:

| Goal | Format | Why |
|---|---|---|
| Hand-author or generate **SCL** for TIA | **External source `.scl`** (TIA: *External source files* → *Generate blocks from source*) | plain text; TIA itself writes it with "Generate source from blocks" |
| Git-friendly round trip of LAD/FBD/SCL/DB/UDT | **SIMATIC SD** (`.s7dcl` + `.s7res`), TIA **V20 Update 3+** (LAD/UDT/DB), **Update 4+** (SCL, FBD, F-FBD, F-DB, mixed) | the official text format for VCI/Openness; **no STL** |
| Automated import/export of any block, including LAD/FBD graphs and GRAPH | **SimaticML** `.xml` (TIA Openness / VCI) | the complete format. SCL inside it is **tokenised**, so do not hand-write it |
| TIA-independent ST with OOP, namespaces, unit tests and Git | **SIMATIC AX** `.st` + `apax.yml` | a different dialect from SCL (no `#`, has `CLASS`/`NAMESPACE`) |

## External source syntax

These forms come from genuine TIA-generated files: UTF-8 with BOM, 3-space indentation.

```text
FUNCTION_BLOCK "FB_Conveyor"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 0.1
   VAR_INPUT
      start : Bool;
      stop { ExternalAccessible := 'False'; ExternalVisible := 'False'; ExternalWritable := 'False'} : Bool;
   END_VAR
   VAR_OUTPUT
      running : Bool;
   END_VAR
   VAR
      tonStart : TON_TIME;
   END_VAR

BEGIN
   REGION Start delay
      #tonStart(IN := #start AND NOT #stop, PT := T#2S);
   END_REGION
   #running := #tonStart.Q AND NOT #stop;
END_FUNCTION_BLOCK
```

- **Header:** `FUNCTION "Name" : Void` (or a return type), `FUNCTION_BLOCK "Name"`,
  `ORGANIZATION_BLOCK`, `DATA_BLOCK "Name"`, `TYPE "Name"`. Then the optional
  `TITLE = …`, `{ S7_Optimized_Access := 'TRUE' }`, `AUTHOR :`, `FAMILY :` and
  `VERSION : 0.1`.
- **Sections:** `VAR_INPUT`, `VAR_OUTPUT`, `VAR_IN_OUT`, `VAR` (static), `VAR_TEMP`,
  `VAR CONSTANT`, each closed by `END_VAR`. Code follows `BEGIN`.
- **Per-variable attributes** go in `{ … }` between the name and the colon.
- **A DB** is `DATA_BLOCK "DB_X" { S7_Optimized_Access := 'TRUE' } VERSION : 0.1 NON_RETAIN
  VAR … END_VAR BEGIN <start values> END_DATA_BLOCK`. For an instance DB, the FB name
  follows in quotes (`NON_RETAIN "FB_X"`).
- **A UDT** is `TYPE "typName" VERSION : 0.1 STRUCT … END_STRUCT; END_TYPE`.
- **Several blocks may share one file.** Blocks must appear after the blocks they call.

## SCL vs IEC ST

| SCL | IEC / CODESYS |
|---|---|
| `#local` inside code; declarations have no `#` | bare name |
| `"GlobalDB".member`, `"FC_X"(…)` (quoted global symbols) | `GVL.member` / bare |
| `REGION name … END_REGION` (V14+) | `{region}` pragma (CODESYS) |
| `BEGIN` between declarations and code | – |
| `{ S7_Optimized_Access := 'TRUE' }` block attribute | `{attribute '…'}` |
| multi-instance timer: `#t(IN := …, PT := …)` with `TON_TIME` or `IEC_TIMER` (`#t.TON(…)`); single instance: `"IEC_Timer_0_DB".TON(…)` | instance variable |
| typed literals such as `B#16#39`, `LT#…`, `WSTRING#'…'` | `BYTE#16#39` |

The plugin's validator lints `.scl` sources (rules ST0xx) and understands `#`, quoted
names, `REGION`, `BEGIN` and attributes.

## SIMATIC SD (V20 Update 3/4, V21)

This is quoted from the V20 Update 4 readme:

```text
{
    S7_Optimized := "TRUE";
    S7_PreferredLanguage := "FBD";
    S7_Version := "0.1"
}
…
{ S7_Language := "LAD" }
NETWORK
    RUNG wire#powerrail
        Contact( #Tag_Input1 )
        Contact( #Tag_Input2 )
        Coil( #Tag_Output )
    END_RUNG
END_NETWORK
```

- An FBD rung looks like `RUNG #Tag_Input1  A( in2 := #Tag_Input2 )  Coil( #Tag_Output )  END_RUNG`.
  Branches are named wires (`wire#w1`), and FBD has no power rail.
- **Multilingual texts** go in `.s7res`, and are referenced with `{ S7_MLC := "MLC_myID" }`.
- **STL is not supported**: exporting a block that contains STL networks fails. LAD
  blocks created before V20 Update 4 must be regenerated because the format changed.
- **V21** (announced 2025-11-11) extends SD to FBD, SCL and mixed-language blocks.
  - **SCL keeps its native syntax.** LAD and FBD get the text rung syntax.
  - Mixed blocks switch language per network with `{ S7_Language := "SCL" } NETWORK … END_NETWORK`.
  - SD is integrated into VCI and Openness, and supports library types.
  - **Not supported:** know-how-protected or write-protected blocks, supervisions and
    alarms, SiVArc definitions, AT, and octal display.
  - **Importing overwrites blocks of the same name.**
  - Supported CPUs: S7-1200, S7-1500 and S7-1200 G2. The scope split for tag tables and
    hardware is unverified.
- The validator checks `NETWORK`/`RUNG` nesting and braces only (rules SD001/SD002).

## SimaticML (Openness/VCI XML)

**Skeleton,** abridged from a genuine V18 export. A complete, validator-clean FC is in
[../assets/FC_LadDemo_V18.xml](../assets/FC_LadDemo_V18.xml).

```text
<Document>
  <Engineering version="V18" />
  <SW.Blocks.FC ID="0">
    <AttributeList>
      <Interface><Sections xmlns="http://www.siemens.com/automation/Openness/SW/Interface/v5">
        <Section Name="Input"><Member Name="In1" Datatype="Bool" /></Section> …
        <Section Name="Return"><Member Name="Ret_Val" Datatype="Void" /></Section>
      </Sections></Interface>
      <MemoryLayout>Optimized</MemoryLayout> <Name>FC_Demo</Name> <Number>1</Number>
      <ProgrammingLanguage>LAD</ProgrammingLanguage>
    </AttributeList>
    <ObjectList>
      <SW.Blocks.CompileUnit ID="3" CompositionName="CompileUnits"> … NetworkSource/FlgNet … </SW.Blocks.CompileUnit>
    </ObjectList>
  </SW.Blocks.FC>
</Document>
```

**Root block elements:** `SW.Blocks.OB` (with `SecondaryType`, e.g. `ProgramCycle`),
`SW.Blocks.FB`, `SW.Blocks.FC`, `SW.Blocks.GlobalDB`, `SW.Blocks.InstanceDB`
(`InstanceOfName`), `SW.Types.PlcStruct` (a UDT; its members sit in `Section Name="None"`),
and `SW.Tags.PlcTagTable` (`SW.Tags.PlcTag` with `LogicalAddress` such as `%M90.0`,
`SW.Tags.PlcUserConstant`).

**Interface sections by block type** (observed):

| Block type | Sections |
|---|---|
| FC | Input, Output, InOut, Temp, Constant, Return |
| FB | Input, Output, InOut, Static, Temp, Constant; GRAPH FBs add `Base` |
| OB | Input, Temp, Constant |
| Global DB | Static |

**IDs:**

- `ID` on the `ObjectList` children is **hexadecimal** and unique in the document.
- `UId` inside a network is decimal and unique **per network**. Generators start at 21.
- `IdentCon`/`NameCon UId` in `<Wires>` must point to a part in the same network.
- The validator checks all three (rules SM004, SM020, SM021).

**Namespace versions depend on the TIA version** (observed in genuine exports). TIA
rejects a namespace it does not expect, so rule SM003 flags a mismatch.

| TIA | `Interface` | `NetworkSource/FlgNet` (LAD/FBD) | `NetworkSource/StructuredText` (SCL) | Other |
|---|---|---|---|---|
| V14 SP1 | v2 | – | – | Graph v1 |
| V15.1 | v3 | v3 | – | |
| V16 | v4 | – | v3 | |
| V17 | v5 | v4 | v3 | |
| V18 | v5 | v4 | v3 | Graph v5 |
| V19 | v5 | v5 | v4 | |
| V20 | v5 | v5 | v4 | |
| V21 | **unverified** | **unverified** | **unverified** | |

All namespaces take the form `http://www.siemens.com/automation/Openness/SW/<family>/vN`.
Siemens documents a "Version Specific Simatic ML Import", but its rules could not be read.
**For V21, or for importing an older namespace into a newer TIA, ask for a sample export
from the user's TIA and mirror it.**

**Payloads:**

- **LAD/FBD** use `FlgNet`: `<Parts>` holds `Access Scope="GlobalVariable|LocalVariable|LiteralConstant"`,
  `Part Name="Contact|Coil|…"` and `Call/CallInfo`. `<Wires>` holds `Powerrail`,
  `IdentCon`, `NameCon` and `OpenCon`.
- **SCL** uses `StructuredText` and is **tokenised** (`<Token Text="IF"/>`,
  `<Blank Num="4"/>`, `<Access Scope=…>`). Author SCL as an external source or as SD
  instead.
- **GRAPH** uses `Graph` (`Sequence/Steps/Step Number Init Name`, `Transitions`,
  `Supervisions`, `Interlocks`, each wrapping a `FlgNet`).
- **STL** uses `StatementList` (`StlStatement/StlToken`).

## SIMATIC AX

- VS Code-based engineering with Git, the **apax** package manager (`apax.yml`: `name`,
  `version`, `type: lib`, `targets: [s7, "llvm"]`, `registries`) and unit tests.
- Sources are `.st` files using `NAMESPACE … CLASS … METHOD PUBLIC … END_METHOD … END_CLASS
  … END_NAMESPACE`.
- It targets S7-1500 variants and software controllers. TIA Portal still does the
  hardware configuration and technology objects.
- Status: "Early Access for selected productive use cases".
- **AX ST is not TIA SCL. Never mix the two dialects.**

## Sources

- Genuine exports in public repositories, including Amadeusz97/TIA_H4 (V18),
  wd133456/RGV_PLC (V19) and lingisbad/SICAR_TEST (V20). Files that were AI- or
  hand-authored were excluded.
- TIA Portal V20 Update 4 readme (SIMATIC SD):
  <https://cache.industry.siemens.com/dl/files/851/109963851/att_1332651/v2/ReadMe_TIA_V20_UPD4_enUS.pdf>
- TIA V21 press release (2025-11-11):
  <https://press.siemens.com/global/en/pressrelease/tia-portal-v21-combines-engineering-efficiency-higher-plant-availability>
- SIMATIC AX: <https://www.siemens.com/en-us/products/simatic-ax/> and the
  `simatic-ax/template-library` repository.
