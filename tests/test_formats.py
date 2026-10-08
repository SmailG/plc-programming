"""Format checkers: each valid sample is clean, each targeted breakage is caught.

Valid samples follow the skeletons of real exports (Beremiz PLCopen XML, TIA V18
SimaticML, TwinCAT 4026 .TcPOU, Rockwell v36 L5X, Control Expert V15 XEF, 4diac .fbt).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import plc_validate  # noqa: E402

PLCOPEN = """<?xml version="1.0" encoding="utf-8"?>
<project xmlns="http://www.plcopen.org/xml/tc6_0201" xmlns:xhtml="http://www.w3.org/1999/xhtml">
  <fileHeader companyName="c" productName="p" productVersion="1" creationDateTime="2026-09-27T12:00:00"/>
  <contentHeader name="demo">
    <coordinateInfo><fbd><scaling x="1" y="1"/></fbd><ld><scaling x="1" y="1"/></ld><sfc><scaling x="1" y="1"/></sfc></coordinateInfo>
  </contentHeader>
  <types>
    <dataTypes/>
    <pous>
      <pou name="CounterST" pouType="functionBlock">
        <interface>
          <inputVars><variable name="Reset"><type><BOOL/></type></variable></inputVars>
          <localVars>
            <variable name="Cnt"><type><INT/></type></variable>
            <variable name="tDelay"><type><derived name="TON"/></type></variable>
          </localVars>
        </interface>
        <body>
          <ST>
            <xhtml:p><![CDATA[tDelay(IN := NOT Reset, PT := T#1S);
IF Reset THEN
  Cnt := 0;
ELSIF tDelay.Q THEN
  Cnt := Cnt + 1;
END_IF;]]></xhtml:p>
          </ST>
        </body>
      </pou>
      <pou name="Rung" pouType="program">
        <body>
          <LD>
            <leftPowerRail localId="1"><position x="10" y="10"/><connectionPointOut formalParameter=""/></leftPowerRail>
            <contact localId="2" edge="rising"><position x="60" y="20"/>
              <connectionPointIn><connection refLocalId="1"/></connectionPointIn><connectionPointOut/><variable>Start</variable></contact>
            <coil localId="3" storage="set"><position x="140" y="20"/>
              <connectionPointIn><connection refLocalId="2"/></connectionPointIn><connectionPointOut/><variable>Motor</variable></coil>
            <rightPowerRail localId="4"><position x="220" y="10"/>
              <connectionPointIn><connection refLocalId="3"/></connectionPointIn></rightPowerRail>
          </LD>
        </body>
      </pou>
    </pous>
  </types>
  <instances><configurations/></instances>
</project>
"""

SIMATICML = """<?xml version="1.0" encoding="utf-8"?>
<Document>
  <Engineering version="V18" />
  <SW.Blocks.FC ID="0">
    <AttributeList>
      <Interface><Sections xmlns="http://www.siemens.com/automation/Openness/SW/Interface/v5">
        <Section Name="Input"><Member Name="In1" Datatype="Bool" /></Section>
        <Section Name="Output" />
        <Section Name="InOut" />
        <Section Name="Temp" />
        <Section Name="Constant" />
        <Section Name="Return"><Member Name="Ret_Val" Datatype="Void" /></Section>
      </Sections></Interface>
      <MemoryLayout>Optimized</MemoryLayout>
      <Name>FC_Demo</Name>
      <Number>1</Number>
      <ProgrammingLanguage>LAD</ProgrammingLanguage>
    </AttributeList>
    <ObjectList>
      <SW.Blocks.CompileUnit ID="3" CompositionName="CompileUnits">
        <AttributeList>
          <NetworkSource><FlgNet xmlns="http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v4">
            <Parts>
              <Access Scope="LocalVariable" UId="21"><Symbol><Component Name="In1" /></Symbol></Access>
              <Part Name="Coil" UId="22" />
            </Parts>
            <Wires>
              <Wire UId="23"><IdentCon UId="21" /><NameCon UId="22" Name="operand" /></Wire>
            </Wires>
          </FlgNet></NetworkSource>
          <ProgrammingLanguage>LAD</ProgrammingLanguage>
        </AttributeList>
      </SW.Blocks.CompileUnit>
    </ObjectList>
  </SW.Blocks.FC>
</Document>
"""

TCPOU = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4026.12">
  <POU Name="FB_Demo" Id="{516536b5-0000-4000-8000-000000000001}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Demo
VAR
    tonWait : TON;
    bGo     : BOOL;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[tonWait(IN := bGo, PT := T#2S);]]></ST>
    </Implementation>
    <Method Name="Reset" Id="{a81886a0-0000-4000-8000-000000000002}">
      <Declaration><![CDATA[METHOD Reset : BOOL
]]></Declaration>
      <Implementation><ST><![CDATA[bGo := FALSE;
Reset := TRUE;]]></ST></Implementation>
    </Method>
  </POU>
</TcPlcObject>
"""

L5X = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="36.00" TargetName="Demo" TargetType="Controller" ContainsContext="false">
<Controller Use="Target" Name="Demo" ProcessorType="1756-L85E">
  <Tags><Tag Name="Start" TagType="Base" DataType="BOOL"/><Tag Name="T1" TagType="Base" DataType="TIMER"/></Tags>
  <Programs><Program Name="Main"><Routines>
    <Routine Name="R01" Type="RLL"><RLLContent>
      <Rung Number="0" Type="N"><Text><![CDATA[XIC(Start)[,XIC(Run) ]XIO(Stop)OTE(Run);]]></Text></Rung>
      <Rung Number="1" Type="N"><Text><![CDATA[XIC(Run)TON(T1,5000,0);]]></Text></Rung>
    </RLLContent></Routine>
    <Routine Name="R02" Type="ST"><STContent>
      <Line Number="0"><![CDATA[IF Run THEN]]></Line>
      <Line Number="1"><![CDATA[  Count := Count + 1;]]></Line>
      <Line Number="2"><![CDATA[END_IF;]]></Line>
    </STContent></Routine>
  </Routines></Program></Programs>
</Controller>
</RSLogix5000Content>
"""

XEF = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<FEFExchangeFile>
  <fileHeader company="Schneider Automation" product="Control Expert V15.0" dateTime="date_and_time#2021-4-1-17:47:9" content="Fichier source projet" DTDVersion="41"></fileHeader>
  <contentHeader name="Projet" version="1.1.11"></contentHeader>
  <FBSource nameOfFBType="DFB_Pump" version="0.06">
    <inputParameters><variables name="IN1" typeName="BOOL"/></inputParameters>
    <FBProgram name="Main"><STSource>OUT1 := IN1;</STSource></FBProgram>
  </FBSource>
  <dataBlock>
    <variables name="Pump1" typeName="DFB_Pump"/>
    <variables name="Level" typeName="INT" topologicalAddress="%MW100"/>
  </dataBlock>
  <program>
    <identProgram name="Progr1" type="section" task="MAST" SectionOrder="1"></identProgram>
    <STSource>Pump1 (IN1 := TRUE);</STSource>
  </program>
</FEFExchangeFile>
"""

FBT = """<?xml version="1.0" encoding="UTF-8"?>
<FBType Name="E_Toggle" Comment="demo">
  <Identification Standard="61499-2"/>
  <InterfaceList>
    <EventInputs><Event Name="REQ" Type="Event"><With Var="IN"/></Event></EventInputs>
    <EventOutputs><Event Name="CNF" Type="Event"><With Var="OUT"/></Event></EventOutputs>
    <InputVars><VarDeclaration Name="IN" Type="BOOL"/></InputVars>
    <OutputVars><VarDeclaration Name="OUT" Type="BOOL"/></OutputVars>
  </InterfaceList>
  <BasicFB>
    <ECC>
      <ECState Name="START" x="0" y="0"/>
      <ECState Name="RUN" x="0" y="0"><ECAction Algorithm="Toggle" Output="CNF"/></ECState>
      <ECTransition Source="START" Destination="RUN" Condition="REQ" x="0" y="0"/>
      <ECTransition Source="RUN" Destination="START" Condition="1" x="0" y="0"/>
    </ECC>
    <Algorithm Name="Toggle"><ST Text="OUT := NOT IN;"/></Algorithm>
  </BasicFB>
</FBType>
"""

AML = """<?xml version="1.0" encoding="utf-8"?>
<CAEXFile xmlns="http://www.dke.de/CAEX" SchemaVersion="3.0" FileName="plant.aml">
  <SuperiorStandardVersion>AutomationML 2.10</SuperiorStandardVersion>
  <SourceDocumentInformation OriginName="t" OriginID="t" OriginVersion="1.0" LastWritingDateTime="2026-09-27T12:00:00Z"/>
  <InstanceHierarchy Name="Plant">
    <InternalElement Name="PLC_Program" ID="e1">
      <ExternalInterface Name="MainPOU" ID="i1" RefBaseClassPath="AMLBase@AutomationMLInterfaceClassLib/AutomationMLBaseInterface/ExternalDataConnector/PLCopenXMLInterface">
        <Attribute Name="refURI" AttributeDataType="xs:anyURI"><Value>file:///plc.xml#Main</Value></Attribute>
      </ExternalInterface>
    </InternalElement>
  </InstanceHierarchy>
</CAEXFile>
"""

DEXPI = """<?xml version="1.0" encoding="utf-8"?>
<PlantModel>
  <PlantInformation Application="Dexpi" ApplicationVersion="1.3" SchemaVersion="4.1" Discipline="PID" Is3D="no"><UnitsOfMeasure/></PlantInformation>
  <Equipment ID="pump1" ComponentClass="Pump"/>
  <ProcessInstrumentationFunction ID="pif1" ComponentClass="ProcessInstrumentationFunction">
    <Association Type="is located in" ItemID="pump1"/>
  </ProcessInstrumentationFunction>
</PlantModel>
"""


def run(files: dict[str, str]):
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for name, content in files.items():
            p = Path(d) / name
            p.write_text(content, encoding="utf-8")
            paths.append(p)
        results = {p.name: plc_validate.check_file(p, None) for p in paths}
    return results


def codes(files: dict[str, str], name: str | None = None):
    res = run(files)
    name = name or next(iter(files))
    fmt, findings = res[name]
    return fmt, sorted(f.code for f in findings)


class DetectionAndValidSamples(unittest.TestCase):
    def test_valid_samples_are_clean(self):
        samples = {
            "a.xml": (PLCOPEN, "plcopen"), "FC_Demo.xml": (SIMATICML, "simaticml"),
            "FB_Demo.TcPOU": (TCPOU, "twincat"), "demo.L5X": (L5X, "l5x"),
            "demo.xef": (XEF, "control-expert"), "E_Toggle.fbt": (FBT, "iec61499"),
            "dexpi.xml": (DEXPI, "dexpi"),
        }
        for name, (content, fmt) in samples.items():
            with self.subTest(name=name):
                self.assertEqual(codes({name: content}), (fmt, []))

    def test_aml_link_resolves(self):
        plc = PLCOPEN.replace('<pou name="CounterST"', '<pou name="CounterST" globalId="Main"')
        res = run({"plant.aml": AML, "plc.xml": plc})
        self.assertEqual(res["plant.aml"], ("aml", []))

    def test_unrelated_xml_is_ignored(self):
        self.assertEqual(codes({"pom.xml": '<project xmlns="http://maven.apache.org/POM/4.0.0"/>'}), (None, []))


class PLCopenBreakage(unittest.TestCase):
    def test_duplicate_local_id_and_dangling_connection(self):
        bad = PLCOPEN.replace('<coil localId="3"', '<coil localId="2"').replace('refLocalId="3"', 'refLocalId="9"')
        self.assertEqual(codes({"a.xml": bad})[1], ["PX020", "PX021"])

    def test_missing_coordinate_info(self):
        bad = PLCOPEN.replace("<sfc><scaling x=\"1\" y=\"1\"/></sfc>", "")
        self.assertEqual(codes({"a.xml": bad})[1], ["PX004"])

    def test_st_body_errors_are_reported_with_file_line(self):
        bad = PLCOPEN.replace("END_IF;]]>", "]]>")
        res = run({"a.xml": bad})["a.xml"][1]
        self.assertEqual([f.code for f in res], ["ST002"])
        self.assertEqual(res[0].line, 21)  # the IF line in the file, not in the CDATA

    def test_conditional_timer_in_st_body(self):
        bad = PLCOPEN.replace("tDelay(IN := NOT Reset, PT := T#1S);\nIF Reset THEN",
                              "IF Reset THEN\n  tDelay(IN := TRUE, PT := T#1S);")
        self.assertEqual(codes({"a.xml": bad})[1], ["ST030"])

    def test_sfc_rules(self):
        sfc = PLCOPEN.replace("<LD>", "<SFC>").replace("</LD>", """
            <step localId="10" name="Init" initialStep="true"/>
            <step localId="11" name="Fill" initialStep="true"/>
            <actionBlock localId="12"><action localId="13" qualifier="L"><reference name="Open"/></action>
              <action localId="14" qualifier="X"><reference name="Other"/></action></actionBlock>
          </SFC>""")
        self.assertEqual(codes({"a.xml": sfc})[1], ["PX030", "PX031", "PX032"])

    def test_vendor_addData_only(self):
        vendor = PLCOPEN.replace(PLCOPEN[PLCOPEN.index("<pous>"):PLCOPEN.index("</pous>") + 7], "<pous/>").replace(
            "<instances>", '<addData><data name="http://www.3s-software.com/plcopenxml/pou" handleUnknown="implementation"/></addData><instances>')
        self.assertIn("PX050", codes({"a.xml": vendor})[1])


class SimaticBreakage(unittest.TestCase):
    def test_namespace_version_mismatch(self):
        bad = SIMATICML.replace("FlgNet/v4", "FlgNet/v5")
        self.assertEqual(codes({"b.xml": bad})[1], ["SM003"])

    def test_dangling_wire_and_duplicate_uid(self):
        bad = SIMATICML.replace('<IdentCon UId="21" />', '<IdentCon UId="99" />').replace('<Part Name="Coil" UId="22" />', '<Part Name="Coil" UId="21" />')
        self.assertEqual(codes({"b.xml": bad})[1], ["SM020", "SM021", "SM021"])

    def test_invalid_section_and_missing_return(self):
        bad = SIMATICML.replace('<Section Name="Return"><Member Name="Ret_Val" Datatype="Void" /></Section>', '<Section Name="Static" />')
        self.assertEqual(codes({"b.xml": bad})[1], ["SM013", "SM013"])

    def test_simatic_sd_balance(self):
        good = '{ S7_Language := "LAD" }\nNETWORK\n    RUNG wire#powerrail\n        Coil( #Out )\n    END_RUNG\nEND_NETWORK\n'
        self.assertEqual(codes({"x.s7dcl": good}), ("simatic-sd", []))
        self.assertEqual(codes({"x.s7dcl": good.replace("    END_RUNG\n", "")})[1], ["SD001"])


class TwinCatBreakage(unittest.TestCase):
    def test_name_mismatch_and_file_name(self):
        bad = TCPOU.replace("FUNCTION_BLOCK FB_Demo", "FUNCTION_BLOCK FB_Other")
        self.assertEqual(codes({"FB_Demo.TcPOU": bad})[1], ["TC011"])
        self.assertEqual(codes({"Wrong.TcPOU": TCPOU})[1], ["TC012"])

    def test_duplicate_id(self):
        bad = TCPOU.replace("{a81886a0-0000-4000-8000-000000000002}", "{516536b5-0000-4000-8000-000000000001}")
        self.assertEqual(codes({"FB_Demo.TcPOU": bad})[1], ["TC005"])

    def test_timer_called_only_in_method_conditionally(self):
        bad = TCPOU.replace("tonWait(IN := bGo, PT := T#2S);", "").replace(
            "bGo := FALSE;", "IF bGo THEN tonWait(IN := TRUE, PT := T#2S); END_IF;")
        self.assertEqual(codes({"FB_Demo.TcPOU": bad})[1], ["ST030"])


class LogixBreakage(unittest.TestCase):
    def test_rung_errors_and_double_coil(self):
        bad = L5X.replace("OTE(Run);]]>", "OTE(Run)]]>").replace("TON(T1,5000,0);", "TON(T1,5000);OTE(Run);")
        self.assertEqual(codes({"d.L5X": bad})[1], ["LX020", "LX022", "LX040"])

    def test_duplicate_tag(self):
        bad = L5X.replace('<Tag Name="T1"', '<Tag Name="Start"')
        self.assertEqual(codes({"d.L5X": bad})[1], ["LX011"])

    def test_l5k_balance(self):
        good = "CONTROLLER Demo (ProcessorType := \"1756-L85E\")\n\tPROGRAM Main\n\t\tROUTINE R01\n\t\t\tN: XIC(a)OTE(b);\n\t\tEND_ROUTINE\n\tEND_PROGRAM\nEND_CONTROLLER\n"
        self.assertEqual(codes({"d.L5K": good}), ("l5k", []))
        self.assertEqual(codes({"d.L5K": good.replace("\t\tEND_ROUTINE\n", "")})[1], ["LX050"])


L5K_RM014D = """CONTROLLER example_controller (Description := "controller description",
    ProcessorType := "1756-L73", Major := 22, TimeSlice := 20)
  MODULE Local (Parent := "Local", CatalogNumber := "1756-L73") END_MODULE
  TAG
  END_TAG
  PROGRAM MainProgram (MAIN := "MainRoutine", MODE := 0, DisableFlag := 0)
    TAG
    END_TAG
    ROUTINE MainRoutine
      RC: "This is a rung comment for the first rung.";
      N: XIC(input1)XIC(input2)OTE(output1)OTE(output2);
    END_ROUTINE
    ST_ROUTINE Calc
      'IF input1 THEN
      '  count := count + 1;
      'END_IF;
    END_ST_ROUTINE
  END_PROGRAM
  TASK MainTask (Type := CONTINUOUS, Rate := 10, Priority := 10, Watchdog := 500)
    MainProgram;
  END_TASK
  CONFIG CST(SystemTimeMasterID := 0) END_CONFIG
END_CONTROLLER
"""

E_SR_4DIAC = """<?xml version="1.0" encoding="UTF-8"?>
<FBType Name="E_SR" Comment="Event-driven bistable">
  <Identification Standard="61499-1 Annex A"/>
  <VersionInfo Version="3.0" Author="x" Date="2025-04-14"/>
  <InterfaceList>
    <EventInputs><Event Name="S" Type="Event"/><Event Name="R" Type="Event"/></EventInputs>
    <EventOutputs><Event Name="EO" Type="Event"><With Var="Q"/></Event></EventOutputs>
    <OutputVars><VarDeclaration Name="Q" Type="BOOL"/></OutputVars>
  </InterfaceList>
  <BasicFB>
    <ECC>
      <ECState Name="START"/>
      <ECState Name="SET"><ECAction Algorithm="SET" Output="EO"/></ECState>
      <ECState Name="RESET"><ECAction Algorithm="RESET" Output="EO"/></ECState>
      <ECTransition Source="START" Destination="SET" Condition="S"/>
      <ECTransition Source="SET" Destination="RESET" Condition="R"/>
      <ECTransition Source="RESET" Destination="SET" Condition="S"/>
    </ECC>
    <Algorithm Name="SET"><ST><![CDATA[Q := TRUE;]]></ST></Algorithm>
    <Algorithm Name="RESET"><ST><![CDATA[Q := FALSE;]]></ST></Algorithm>
  </BasicFB>
</FBType>
"""

E_TRAIN_LIKE = """<?xml version="1.0" encoding="UTF-8"?>
<FBType Name="E_TRAIN_LIKE">
  <InterfaceList>
    <EventInputs><Event Name="START" Type="Event"><With Var="N"/></Event></EventInputs>
    <EventOutputs><Event Name="EO" Type="Event"/></EventOutputs>
    <InputVars><VarDeclaration Name="N" Type="UINT"/></InputVars>
    <Plugs><AdapterDeclaration Name="TMR" Type="ATimeOut"/></Plugs>
  </InterfaceList>
  <FBNetwork>
    <FB Name="CTR" Type="iec61499::events::E_CTU"/>
    <EventConnections>
      <Connection Source="START" Destination="CTR.R"/>
      <Connection Source="TMR.TimeOut" Destination="EO"/>
    </EventConnections>
    <DataConnections><Connection Source="N" Destination="CTR.PV"/></DataConnections>
  </FBNetwork>
</FBType>
"""


class GroundedSamples(unittest.TestCase):
    def test_rm014d_l5k_example_is_clean(self):
        self.assertEqual(codes({"x.L5K": L5K_RM014D}), ("l5k", []))

    def test_l5k_st_routine_is_linted(self):
        bad = L5K_RM014D.replace("      'END_IF;\n", "")
        self.assertEqual(codes({"x.L5K": bad})[1], ["ST002"])

    def test_4diac_cdata_algorithm(self):
        self.assertEqual(codes({"E_SR.fbt": E_SR_4DIAC}), ("iec61499", []))
        bad = E_SR_4DIAC.replace("Q := TRUE;", "Q = TRUE;")
        self.assertEqual(codes({"E_SR.fbt": bad})[1], ["ST010"])

    def test_composite_with_adapter_plug(self):
        self.assertEqual(codes({"E_T.fbt": E_TRAIN_LIKE}), ("iec61499", []))
        bad = E_TRAIN_LIKE.replace('Destination="CTR.PV"', 'Destination="CTX.PV"')
        self.assertEqual(codes({"E_T.fbt": bad})[1], ["FB020"])

    def test_logix_v36_mnemonics(self):
        v36 = L5X.replace("TON(T1,5000,0);", "GT(Count,10)MOVE(1,Flag)LIMIT(0,Count,9)TON(T1,?,?);")
        self.assertEqual(codes({"d.L5X": v36}), ("l5x", []))
        bad = L5X.replace("TON(T1,5000,0);", "GT(Count)MOVE(1,Flag,X);")
        self.assertEqual(codes({"d.L5X": bad})[1], ["LX022", "LX022"])


class OtherBreakage(unittest.TestCase):
    def test_control_expert_duplicates_and_st(self):
        bad = XEF.replace('name="Level"', 'name="Pump1"').replace("Pump1 (IN1 := TRUE);", "IF x THEN y := 1;")
        self.assertEqual(codes({"e.xef": bad})[1], ["CX010", "ST002"])

    def test_iec61499_ecc(self):
        bad = FBT.replace('Algorithm="Toggle"', 'Algorithm="Nope"').replace('<With Var="IN"/>', '<With Var="X"/>').replace(
            'Source="RUN" Destination="START"', 'Source="RUN" Destination="GONE"')
        self.assertEqual(codes({"E_Toggle.fbt": bad})[1], ["FB005", "FB012", "FB014"])

    def test_aml_rules(self):
        bad = AML.replace('ID="i1"', 'ID="e1"').replace("<SourceDocumentInformation", "<X").replace("<Value>file:///plc.xml#Main</Value>", "<Value>file:///missing.xml</Value>")
        self.assertEqual(codes({"plant.aml": bad})[1], ["AM003", "AM004", "AM011"])

    def test_dexpi_rules(self):
        bad = DEXPI.replace('ID="pif1"', 'ID="pump1"').replace('ItemID="pump1"', 'ItemID="nothing"')
        self.assertEqual(codes({"dexpi.xml": bad})[1], ["DX003", "DX004"])

    def test_csv(self):
        self.assertEqual(codes({"t.csv": "Name;Type\nA;BOOL\nB;INT\n"}), ("csv", []))
        self.assertEqual(codes({"t.csv": "Name;Type\nA;BOOL\nA;INT\n"})[1], ["CS004"])
        self.assertEqual(codes({"t.csv": "Name;Type\nA;BOOL\nB;INT;extra\nC;INT\n"})[1], ["CS002"])

    def test_broken_xml(self):
        self.assertEqual(codes({"x.TcPOU": "<TcPlcObject><POU></TcPlcObject>"})[1], ["XML001"])


class ShippedTemplates(unittest.TestCase):
    """Every template a skill hands to the model must itself pass the validator."""

    def test_all_assets_are_clean(self):
        assets = sorted((HERE.parent / "skills").glob("*/assets/*"))
        self.assertTrue(assets, "no templates found; the glob is wrong")
        for path in assets:
            with self.subTest(asset=str(path.relative_to(HERE.parent))):
                fmt, findings = plc_validate.check_file(path, None)
                self.assertIsNotNone(fmt, "template format not recognised")
                self.assertEqual([f.format(path.name) for f in findings], [])


class CliAndHook(unittest.TestCase):
    SCRIPT = HERE.parent / "scripts" / "plc_validate.py"

    def _hook(self, path: Path) -> subprocess.CompletedProcess:
        event = {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": str(path)}}
        return subprocess.run([sys.executable, str(self.SCRIPT), "--hook"], input=json.dumps(event), capture_output=True, text=True)

    def test_hook_blocks_on_errors_and_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "p.st"
            bad.write_text("IF a THEN\n  b := 1;\n")
            r = self._hook(bad)
            self.assertEqual(r.returncode, 2)
            self.assertIn("ST002", r.stderr)
            warn = Path(d) / "w.st"
            warn.write_text("IF r = 1.5 THEN x := 1; END_IF;\n")
            r = self._hook(warn)
            self.assertEqual(r.returncode, 0)
            self.assertIn("ST020", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])
            other = Path(d) / "readme.md"
            other.write_text("IF without THEN")
            r = self._hook(other)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
            csvf = Path(d) / "t.csv"
            csvf.write_text("Name\nA\nA\n")
            self.assertEqual(self._hook(csvf).returncode, 0)

    def test_hook_antigravity_payload(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "p.st"
            bad.write_text("IF a THEN\n  b := 1;\n")
            event_bad = {
                "conversationId": "test-123",
                "toolCall": {"name": "write_to_file", "args": {"TargetFile": str(bad)}},
            }
            r_bad = subprocess.run([sys.executable, str(self.SCRIPT), "--hook"], input=json.dumps(event_bad), capture_output=True, text=True)
            self.assertEqual(r_bad.returncode, 2)
            self.assertIn("ST002", r_bad.stderr)

            good = Path(d) / "g.st"
            good.write_text("x := 1;\n")
            event_good = {
                "conversationId": "test-123",
                "toolCall": {"name": "write_to_file", "args": {"TargetFile": str(good)}},
            }
            r_good = subprocess.run([sys.executable, str(self.SCRIPT), "--hook"], input=json.dumps(event_good), capture_output=True, text=True)
            self.assertEqual(r_good.returncode, 0)
            self.assertEqual(r_good.stdout.strip(), "{}")

            replace_good = {
                "conversationId": "test-123",
                "toolCall": {"name": "replace_file_content", "args": {"TargetFile": str(good)}},
            }
            r_replace = subprocess.run([sys.executable, str(self.SCRIPT), "--hook"], input=json.dumps(replace_good), capture_output=True, text=True)
            self.assertEqual(r_replace.returncode, 0)
            self.assertEqual(r_replace.stdout.strip(), "{}")

    def test_cli_exit_codes_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            good = Path(d) / "g.st"
            good.write_text("x := 1;\n")
            r = subprocess.run([sys.executable, str(self.SCRIPT), "--json", d], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(json.loads(r.stdout)["checked"], 1)
            (Path(d) / "b.st").write_text("END_IF;\n")
            r = subprocess.run([sys.executable, str(self.SCRIPT), d], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
