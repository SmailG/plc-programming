---
name: validate
description: Run the plugin's structural validator on PLC files or directories (ST/SCL, PLCopen XML, IEC 61131-10, SimaticML, SIMATIC SD, TwinCAT, L5X/L5K, Control Expert XEF, IEC 61499, AutomationML, DEXPI, CSV) and explain the findings.
argument-hint: "[paths...] [--xsd schema.xsd] [--strict]"
disable-model-invocation: true
allowed-tools: Bash(python3 *plc_validate.py*)
---

# Validate PLC files

Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-scripts}/plc_validate.py" $ARGUMENTS
```

If `$ARGUMENTS` is empty, use the current directory.

Then:

1. **Group the findings by file.** For each error, explain the cause in one line and give
   the fix. Rule families:
   - `ST` Structured Text
   - `PX` PLCopen XML / IEC 61131-10
   - `SM` SimaticML, `SD` SIMATIC SD
   - `TC` TwinCAT
   - `LX` Logix
   - `CX` Control Expert
   - `FB` IEC 61499
   - `AM` AutomationML
   - `DX` DEXPI
   - `CS` CSV
   - `XS` XSD
2. **Say plainly that this is a structural check, not a compile.** Types, library symbols
   and cross-file references are not resolved.
3. **XSD validation:** if the user wants it and has no schema, point them to
   <https://www.plcopen.org/downloads/> ("XML Exchange"). The schemas cannot be bundled
   because of their licences. Then re-run with `--xsd <path>`.
4. **Offer to fix the errors**, one file at a time.
