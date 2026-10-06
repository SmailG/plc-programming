# Schneider exchange files

## EcoStruxure Machine Expert (M241/M251/M262): CODESYS-based

- **Exchange:** Machine Expert has the CODESYS commands *Project › Export PLCopenXML… /
  Import PLCopenXML…* and the same Python ScriptEngine. The XML is the CODESYS flavour
  (`tc6_0200`), with methods, properties, folders and task settings in
  `http://www.3s-software.com/plcopenxml/…` addData. See the `exchange-formats` skill.
- **Known limitation:** a GVL cannot carry both `VAR_GLOBAL` and `VAR_GLOBAL CONSTANT`
  through PLCopenXML, so the constants come back as plain globals. Plain-text declarations
  in an import file override the structured ones. Both points come from Schneider help,
  seen only as a search snippet, so treat them as partially verified.
- **Practical authoring path:** generate ST that the user pastes into POU editors, or a
  PLCopenXML file with standard `<pous>` for import. **Always test-import into a scratch
  project first.** Device configuration, I/O mapping and the symbol configuration are not
  carried by plain POU exchange.

## EcoStruxure Control Expert (ex-Unity Pro; M340/M580/Quantum/Premium)

The manuals dated 06–07/2026 are "updated for **Control Expert 16.4**". V16.2 replaced V16.1 in June 2025, and the full 16.x release history is unverified.

| Extension | Content |
|---|---|
| `.STU` | working project; **does not move between Control Expert versions** |
| `.STA` | archive, created only after the project has been built |
| **`.XEF`** | full application exchange in XML, possible "at any stage". Use this to move between versions |
| `.ZEF` | the XEF plus the global DTM configuration (zipped) |
| `.XHW` | I/O configuration |
| `.XDB` / `.XDD` | DFB (derived FB) / DDT (derived data type) |
| `.XSY` (also `.SCY`, `.TXT`, `.XVM`) | variables |
| `.XST` `.XLD` `.XBD` `.XSF` `.XIL` | ST / LD / FBD / SFC / IL section exports |
| `.XTB` `.XCM` `.XCR` `.XFM` | animation table / communication network / runtime screen / functional module |
| `.ASC` / `.FEF` | Concept / PL7 project imports |

Schneider says an `.XLD` "is not intended to be edited by the user". Renaming variables
inside one breaks DDT aliases.

### XEF skeleton

This is abridged from a real V15 export. It uses no namespaces, and the time literals
look like `date_and_time#…` and `dt#…`.

```text
<FEFExchangeFile>
  <fileHeader company="Schneider Automation" product="Control Expert V15.0 - 201016B" dateTime="date_and_time#2021-4-1-17:47:9" content="…" DTDVersion="41"/>
  <contentHeader name="Projet" version="1.1.11" dateTime="…"/>
  <IOConf><PLC …><partItem family="Micro Basic" partNumber="BMXP342000" …/></PLC></IOConf>
  <DDTSource DDTName="…">…</DDTSource>
  <FBSource nameOfFBType="DFBTYPE1" version="0.06" …>
    <inputParameters><variables name="IN1" typeName="BOOL"><comment>…</comment><attribute name="PositionPin" value="1"/></variables></inputParameters>
    <inOutParameters/> <publicLocalVariables/> <privateLocalVariables/>
    <FBProgram …><STSource>…</STSource></FBProgram>
  </FBSource>
  <dataBlock><variables name="OBJ1" typeName="DFBTYPE1"/></dataBlock>
  <program>
    <identProgram name="Progr1" type="section" task="MAST" SectionOrder="1"/>
    <STSource>OBJ1 (IN1 := BIT0, OUT1 =&gt; BIT1);</STSource>
  </program>
  <program><identProgram name="Progr2" type="section" task="MAST" SectionOrder="2"/>
    <FBDSource nbRows="24" nbColumns="36"><networkFBD><FFBBlock instanceName="OBJ2" typeName="DFBTYPE1" …>…</FFBBlock></networkFBD></FBDSource>
  </program>
</FEFExchangeFile>
```

- **XSY** uses the root `<VariablesExchangeFile>`, containing `<dataBlock><variables name
  typeName topologicalAddress="%MW500">` and `<DDTSource>`.
- **Validator:** rules CX0xx check for duplicate variables and DFB members and for shared
  `topologicalAddress`, and lint the ST in `STSource`.
- **Editing policy:**
  - Read XEF/XSY freely for analysis, variable lists and cross-references.
  - Generate XSY variable lists and ST section text when the user has a same-version
    sample to mirror.
  - **Do not generate graphical sections** (`.XLD`/`.XBD`/`.XSF`) by hand.
  - Always import into a copy of the project.

## Machine Expert – Basic (M221)

This is a separate tool, not based on CODESYS. Projects are `.smbp`.

- The Operating Guide EIO0000003281.04 (09/2025) is "updated for ME-Basic V1.4".
- Its languages are Ladder, Instruction List, Grafcet (List) and Grafcet (SFC).
- Reference TM221CE24T shows "discontinued 2026-09-24, end of service 2026-12-31". The
  status of the rest of the range is unverified.
