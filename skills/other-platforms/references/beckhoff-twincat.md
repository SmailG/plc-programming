# Beckhoff TwinCAT 3

## Versions

- **3.1 Build 4026** is the current mainline. It brought package-managed setup and a
  VS 2022 shell. Build 4024 was its predecessor.
- **TwinCAT PLC++** was announced for the end of 2025. It stores code "in plain text at
  file level", adds a command-line compiler, is "almost fully compliant with the fourth
  edition of IEC 61131-3", ships a converter, and runs alongside the classic PLC. Its GA
  status, file extensions and name are unverified, so check with the user before assuming it.

## Project files (Infosys "Project Files")

| File | Content |
|---|---|
| `.sln`, `.tsproj`, `.xti` | solution, TwinCAT project, split-out parts |
| `.plcproj` | MSBuild XML: one `<Compile Include="POUs\X.TcPOU"><SubType>Code</SubType>` per object |
| `.TcPOU` / `.TcDUT` / `.TcGVL` / `.TcIO` / `.TcTTO` | POU / DUT / GVL / interface / task |
| `.TcTLO`, `.TcVis`, `.TcGTLO` | text list / visualisation / global text list |
| `.tmc` / `.tpy` | module class / third-party symbol file |
| `.library` / `.compiled-library` | libraries |

## `.TcPOU` structure (from a real 4026 file)

```xml
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4026.12">
  <POU Name="FB_X" Id="{GUID}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_X EXTENDS FB_Base
VAR … END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[…]]></ST></Implementation>
    <Method Name="M" Id="{GUID}"><Declaration><![CDATA[METHOD M : BOOL …]]></Declaration>
      <Implementation><ST><![CDATA[…]]></ST></Implementation></Method>
    <Property Name="P" Id="{GUID}"><Declaration>…</Declaration>
      <Get Name="Get" Id="{GUID}"><Declaration>…</Declaration><Implementation>…</Implementation></Get>
    </Property>
  </POU>
</TcPlcObject>
```

**Rules:**

- **The declaration has no `END_FUNCTION_BLOCK`.** The implementation sits in a separate CDATA.
- **The name in the declaration must equal the `Name` attribute and the file name.**
  Validator rules TC011 and TC012 check both.
- Each `Id` is a unique `{GUID}`, checked by TC004 and TC005. Generate fresh GUIDs for
  new objects.
- **Methods, properties, actions and transitions are child elements**, sorted by name by
  default.
- **`LineIds`** go in `LineIDs.dbg` or in the file itself, depending on the write options.
  When editing by hand, keep the existing convention.
- **Only ST is plain text.** LD, FBD and IL are stored as `<NWL><XmlArchive>`, SFC as
  `<SFC><XmlArchive>` and CFC as `<CFC><XmlArchive>`. **Never hand-generate these.**
- **Sibling roots:**
  - `.TcIO`: `<Itf>` with abstract methods.
  - `.TcDUT`: `<DUT>` holding `TYPE … END_TYPE`.
  - `.TcGVL`: `<GVL>` holding `VAR_GLOBAL`.
  - `.TcTTO`: `<Task>` with `<CycleTime>` in µs, `<Priority>` and `<PouCall>`.

## Language extensions you will meet

| Extension | Meaning |
|---|---|
| `{attribute 'qualified_only'}` | GVL and enum members must be qualified: `GVL.x`, `E_X.Member` |
| `{attribute 'strict'}` (enums) | no implicit integer conversion |
| `{attribute 'hide'}` | hidden from the UI and input assistant; no ADS symbol; cannot be persistent |
| `FB_init` / `FB_reinit` / `FB_exit` | lifecycle methods. `METHOD FB_init : BOOL VAR_INPUT bInitRetains : BOOL; bInCopyCode : BOOL; END_VAR`. Never call them explicitly |
| `__NEW` / `__DELETE` | dynamic memory. The type needs `{attribute 'enable_dynamic_creation'}`; memory comes from the router pool; **you must free it**. PLCopen E1 says to avoid it |
| `REFERENCE TO`, `__ISVALIDREF`, `POINTER TO`, `ADR()` | references and pointers. **Check validity before every dereference** |
| `ANY`, `ANY_<type>` inputs | in functions; in methods and FBs from Build 4026 |
| `METHOD`, `PROPERTY` (Get/Set), `INTERFACE`, `EXTENDS`, `IMPLEMENTS`, `SUPER^`, `THIS^`, `UNION` | OOP |
| `PERSISTENT` | survives a download, unlike RETAIN. Needs the persistent-data mechanism configured |

**Naming:** Beckhoff's own libraries use `b` BOOL, `n` integer, `f` REAL/LREAL, `s` STRING,
`t` TIME, `e` enum, `st` struct, `fb` FB instance, `a` array, `I_`/`FB_`/`E_`/`ST_`/`T_`.
Match the project's scheme.

## Exchange

- **PLCopenXML:** *Export PLCopenXML…* / *Import PLCopenXML…* in the context menu.
  Beckhoff says a "subset" is supported; "100% compatibility is not ensured".
- **TwinCAT to TwinCAT:** use the ZIP export.
- **Automation:** the Automation Interface `ITcPlcIECProject` scripts import and export.
- **Import pitfall:** the TwinCAT importer **rejects `t#10ms` task intervals**; they must
  be ISO durations.

## OPC UA (TF6100)

`{attribute 'OPC.UA.DA' := '1'}` above a variable exposes it.
`{attribute 'OPC.UA.DA.Access' := '1'}` makes it read-only (2 = write-only, 3 = read/write).
See the `packml-isa88-opcua` skill.

## Sources

- Beckhoff Infosys pages for project files, attributes, FB_init, __NEW and TF6100:
  <https://infosys.beckhoff.com/>
- Real `.TcPOU` files: Beckhoff-USA-Community XTS_Base, and TcUnit.
