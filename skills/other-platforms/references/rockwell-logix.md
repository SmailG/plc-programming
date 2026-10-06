# Rockwell Studio 5000 Logix Designer (L5X / L5K)

**Primary sources, September 2025:**

- 1756-RM014D, *Import/Export Reference Manual*
- 1756-RM018A, *General Instructions*
- 1756-RM094N, *Design Considerations*

**Current version:** v38.00 (Sept 2025). Import/export version 2.29 corresponds to v38,
and 2.27 to v36. v39 is unverified.

## Model: this is not IEC 61131-3

- **Structure:** Controller → **Tasks** (CONTINUOUS / PERIODIC / EVENT) → **Programs** →
  **Routines**, with one language per routine: RLL, ST, FBD or SFC.
- **No IEC POUs:**
  - The FB analogue is the **Add-On Instruction** (AOI), with instance tags.
  - Routines are called with `JSR` and receive parameters through `SBR`/`RET`.
  - No user function that returns a value was found; this is inferred from the
    documentation, not stated by Rockwell.
- **Tag-based memory:**
  - Tags are controller-scoped or program-scoped. There are no `%I`/`%Q`.
  - I/O appears as module tags (`Local:3:I.Data`), usually used through **alias** tags.
- **DINT preferred.** Every standalone tag takes at least 4 bytes, so pack BOOLs into
  DINT arrays or UDT members. The 5380/5580/5590 controllers add unsigned types, LREAL
  and TIME/LTIME/DT/LDT.
- **`TIMER` is a structure:** `.PRE`/`.ACC` are DINT in **ms**, and `.EN`/`.TT`/`.DN`
  are bits. The L5K literal is `[status,PRE,ACC]`.

## L5X skeleton

This comes from Rockwell's own v36 CI/CD repository.

```xml
<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="36.00" TargetName="…" TargetType="Controller"
  ContainsContext="false" ExportDate="…" ExportOptions="NoRawData L5KData DecoratedData ForceProtectedEncoding AllProjDocTrans">
<Controller Use="Target" Name="…" ProcessorType="1756-L85E" MajorRev="36" MinorRev="11">
  <DataTypes/> <Modules/> <AddOnInstructionDefinitions/> <Tags/>
  <Programs><Program Name="MainProgram" MainRoutineName="MainRoutine"><Tags/><Routines>
    <Routine Name="MainRoutine" Type="RLL"><RLLContent>
      <Rung Number="0" Type="N"><Comment><![CDATA[…]]></Comment><Text><![CDATA[XIC(a)XIC(b)OTE(c);]]></Text></Rung>
    </RLLContent></Routine>
  </Routines></Program></Programs>
  <Tasks><Task Name="MainTask" Type="CONTINUOUS" Priority="10" Watchdog="500">
    <ScheduledPrograms><ScheduledProgram Name="MainProgram"/></ScheduledPrograms></Task></Tasks>
</Controller></RSLogix5000Content>
```

- **Component exports** use `TargetType="AddOnInstructionDefinition"`, `"Routine"`,
  `"Rung"` and so on, with `ContainsContext="true"`. Wrapper elements carry
  `Use="Context"`, and the exported item carries `Use="Target"`.
- **Tag attributes:**
  - `Name`, `TagType` (Base / Alias / Produced / Consumed), `DataType`, `Dimensions`,
    `Radix`, `AliasFor`, `Constant`
  - `ExternalAccess` (Read/Write / Read Only / None), `OpcUaAccess`
- **`<Data>` formats**, in order: raw (no Format), `Format="L5K"`, `Format="Decorated"`.
  Decorated data is recommended.
- **ST routines** are stored as `<STContent><Line Number="0"><![CDATA[…]]></Line>…`.
- **AOIs:**
  - `EnableIn` and `EnableOut` are system parameters.
  - The routines are **Logic** (mandatory) plus **Prescan**, **Postscan** and
    **EnableInFalse**, each gated by its `Execute…` attribute.
  - Input and output parameters must be atomic types; use InOut for structures.
  - A nested AOI must appear earlier in the file.

## RLL neutral text

- Instructions are concatenated (`XIC(a)XIO(b)OTE(c);`), and every rung ends with `;`.
- **Branches** use `[` leg `,` leg `]`. `[,XIC(x)]` puts an empty first leg in parallel.
- **Exports print timer and counter presets as `?`**: `TON(T1,?,?)`. The values live in
  the tag.

| Group | Signatures (RM014D) |
|---|---|
| Bit | `XIC(b)` `XIO(b)` `OTE(b)` `OTL(b)` `OTU(b)` `ONS(storage)` `OSR(storage,out)` `OSF(storage,out)` |
| Timer / counter (ladder only) | `TON(timer,pre,acc)` `TOF(…)` `RTO(…)` `CTU(counter,pre,acc)` `CTD(…)` `RES(struct)` |
| Move | `MOV(src,dst)` `COP(src,dst,len)` `CPS(src,dst,len)` `FLL(src,dst,len)` `CLR(dst)` |
| Math | `ADD`/`SUB`/`MUL`/`DIV`/`MOD(a,b,dst)` `CPT(dst,expr)` |
| Compare | `EQU`/`NEQ`/`GRT`/`GEQ`/`LES`/`LEQ(a,b)` `LIM(low,test,high)` `MEQ(src,mask,cmp)` `CMP(expr)` |
| Program control | `JSR(routine,in…,ret…)` `SBR(…)` `RET(…)` `JMP(lbl)` `LBL(lbl)` `AFI()` `NOP()` `TND()` `MCR()` |
| System | `GSV(class,instance,attr,dst)` `SSV(…)` `MSG(ctrl)` |

**v36 renamed instructions to IEC names**, and old names are converted on import:

| v35 and earlier | v36 and later |
|---|---|
| EQU / NEQ / GRT / GEQ / LES / LEQ | EQ / NE / GT / GE / LT / LE |
| LIM | LIMIT |
| MOV | MOVE |
| ACS / ASN / ATN | ACOS / ASIN / ATAN |
| SQR | SQRT |
| TRN | TRUNC |
| XPY | EXPT |
| TOD / FRD | TO_BCD / BCD_TO |

- **Emit the new names when targeting v36 or later.** Match the existing project when
  editing.
- RM014D (Sept 2025) still lists the old names, while the v36 release note and real v36
  exports use the new ones.

## ST in Logix

- `IF … ELSIF … ELSE … END_IF;`, `CASE`, `FOR`, `WHILE`, `REPEAT`, `EXIT` are supported,
  and so are the `//`, `(* *)` and `/* */` comments.
- `:=` assigns. **`[:=]` is a non-retentive assignment**, reset on entry to Run and on
  SFC step exit with auto-reset.
- **Timers in ST and FBD** use `TONR` / `TOFR` / `RTOR` / `CTUD` on **`FBD_TIMER`** or
  `FBD_COUNTER` tags, for example `TONR(MyTon);`. The members are `TimerEnable`, `PRE`,
  `Reset`, `ACC`, `EN`, `TT` and `DN`. **Ladder `TON`/`TOF`/`RTO`/`CTU`/`CTD` do not
  exist in ST.**

## L5K

This is RM014D's example, trimmed:

```
CONTROLLER example_controller (ProcessorType := "1756-L73", Major := 22)
  MODULE Local (Parent := "Local", CatalogNumber := "1756-L73") END_MODULE
  TAG
  END_TAG
  PROGRAM MainProgram (MAIN := "MainRoutine")
    ROUTINE MainRoutine
      RC: "rung comment";
      N: XIC(input1)XIC(input2)OTE(output1);
    END_ROUTINE
  END_PROGRAM
  TASK MainTask (Type := CONTINUOUS, Rate := 10, Priority := 10, Watchdog := 500)
    MainProgram;
  END_TASK
END_CONTROLLER
```

- ST routines are written `ST_ROUTINE name … END_ST_ROUTINE`, with **every line
  prefixed by `'`**.
- The `IE_VER` header line is unverified.

## Traps

- **An OTE on the same bit in several rungs:** the last rung wins. Validator rule LX040
  flags it.
- **Opening an L5X or L5K creates a new project.** The project cannot go online to the
  previously downloaded controller without an upload or download.
- **Double-byte characters** survive only through the `.TXT` tag/comment export, not
  `.CSV`.
