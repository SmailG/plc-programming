# Reusable FB patterns (IEC 61131-3 ST)

These are written in vendor-neutral Ed.3 ST. The dialect adjustments are at the end of
this file, and the test suite lints every `iecst` block. Adapt names to the project's scheme.

## Device interface convention

Each device FB takes **commands** (`xCmd…`, `xAuto…`), **permissives** (allow a start),
**interlocks** (force a stop; TRUE = healthy), **feedback** and **config**. It returns
**status**, **alarms** and **outputs**. The HMI writes only commands, and the PLC decides.

## Motor, direct on line, with feedback supervision

```iecst
FUNCTION_BLOCK FB_Motor
VAR_INPUT
    xAutoMode      : BOOL;          // TRUE = sequence controls, FALSE = operator (manual)
    xAutoRun       : BOOL;          // run request from the sequence
    xManStart      : BOOL;          // operator start (edge)
    xManStop       : BOOL;          // operator stop (edge)
    xPermissive    : BOOL := TRUE;  // start allowed
    xInterlockOk   : BOOL := TRUE;  // FALSE forces stop (e.g. overload healthy, guard closed)
    xRunFeedback   : BOOL;          // contactor auxiliary contact
    xReset         : BOOL;          // fault reset (edge)
    tFeedbackTime  : TIME := T#3S;  // max time for feedback after start/stop
END_VAR
VAR_OUTPUT
    xRunCmd        : BOOL;          // to the contactor
    xRunning       : BOOL;
    xFault         : BOOL;
    wFaultCode     : WORD;          // 16#0001 no feedback on start, 16#0002 feedback lost, 16#0003 feedback while stopped
END_VAR
VAR
    xManLatch      : BOOL;
    rtManStart     : R_TRIG;
    rtManStop      : R_TRIG;
    rtReset        : R_TRIG;
    tonStartSup    : TON;
    tonStopSup     : TON;
END_VAR

rtManStart(CLK := xManStart);
rtManStop(CLK := xManStop);
rtReset(CLK := xReset);

// manual latch (stop-dominant)
IF rtManStop.Q OR xAutoMode THEN
    xManLatch := FALSE;
ELSIF rtManStart.Q THEN
    xManLatch := TRUE;
END_IF;

// run request -> command, gated by fault, interlock and permissive (permissive only for starting)
xRunCmd := NOT xFault AND xInterlockOk
           AND ((xAutoMode AND xAutoRun) OR (NOT xAutoMode AND xManLatch))
           AND (xPermissive OR xRunCmd);

// feedback supervision (timers called every scan, inputs gated)
tonStartSup(IN := xRunCmd AND NOT xRunFeedback, PT := tFeedbackTime);
tonStopSup(IN := NOT xRunCmd AND xRunFeedback, PT := tFeedbackTime);

IF NOT xFault THEN
    IF tonStartSup.Q THEN
        xFault := TRUE;
        wFaultCode := 16#0001;
    ELSIF tonStopSup.Q THEN
        xFault := TRUE;
        wFaultCode := 16#0003;
    END_IF;
ELSIF rtReset.Q AND xInterlockOk THEN
    xFault := FALSE;
    wFaultCode := 16#0000;
END_IF;

IF xFault THEN
    xRunCmd := FALSE;
    xManLatch := FALSE;
END_IF;

xRunning := xRunCmd AND xRunFeedback;
END_FUNCTION_BLOCK
```

Notes:

- **The permissive gates only the start.** `(xPermissive OR xRunCmd)` keeps a running
  motor running when a start-only permissive drops. The interlock stops it.
- **Fault 16#0002 is left to the caller.** It means feedback was lost while running, and
  whether to trip at once or after a debounce is a process decision. Ask, rather than
  choosing silently.

## On/off valve with travel supervision

```iecst
FUNCTION_BLOCK FB_Valve
VAR_INPUT
    xOpenReq      : BOOL;
    xInterlockOk  : BOOL := TRUE;   // FALSE drives the valve to its safe position (closed here)
    xOpenedLS     : BOOL;           // limit switch open
    xClosedLS     : BOOL;           // limit switch closed
    xReset        : BOOL;
    tTravel       : TIME := T#10S;
END_VAR
VAR_OUTPUT
    xOpenCmd      : BOOL;
    xIsOpen       : BOOL;
    xIsClosed     : BOOL;
    xFault        : BOOL;
END_VAR
VAR
    tonTravel     : TON;
    rtReset       : R_TRIG;
    xLastCmd      : BOOL;
END_VAR

rtReset(CLK := xReset);
xOpenCmd := xOpenReq AND xInterlockOk AND NOT xFault;

// in position = command matches exactly one limit switch
xIsOpen := xOpenedLS AND NOT xClosedLS;
xIsClosed := xClosedLS AND NOT xOpenedLS;
// travel timer: runs while not in the commanded position, restarts when the command reverses
tonTravel(IN := ((xOpenCmd AND NOT xIsOpen) OR (NOT xOpenCmd AND NOT xIsClosed)) AND (xOpenCmd = xLastCmd),
          PT := tTravel);
xLastCmd := xOpenCmd;

IF tonTravel.Q OR (xOpenedLS AND xClosedLS) THEN
    xFault := TRUE;             // did not reach position, or both switches made (wiring or switch fault)
ELSIF rtReset.Q THEN
    xFault := FALSE;
END_IF;
END_FUNCTION_BLOCK
```

## Analog input: scaling, clamping, wire break and limit alarms with hysteresis

```iecst
FUNCTION_BLOCK FB_AnalogIn
VAR_INPUT
    iRaw          : INT;            // module value
    iRawMin       : INT := 0;       // raw value at 0 % of range (platform-specific; see the platform skill)
    iRawMax       : INT := 27648;   // raw value at 100 % (27648 is the Siemens S7 nominal range)
    rEuMin        : REAL := 0.0;    // engineering value at iRawMin
    rEuMax        : REAL := 100.0;  // engineering value at iRawMax
    rHiHi         : REAL := 95.0;
    rLoLo         : REAL := 5.0;
    rHyst         : REAL := 1.0;
    tAlarmDelay   : TIME := T#2S;
END_VAR
VAR_OUTPUT
    rValue        : REAL;
    xWireBreak    : BOOL;
    xHiHi         : BOOL;
    xLoLo         : BOOL;
END_VAR
VAR
    rSpan         : REAL;
    xHiHiRaw      : BOOL;
    xLoLoRaw      : BOOL;
    tonHiHi       : TON;
    tonLoLo       : TON;
END_VAR

rSpan := INT_TO_REAL(iRawMax - iRawMin);
IF rSpan <> 0.0 THEN
    rValue := rEuMin + (INT_TO_REAL(iRaw - iRawMin) / rSpan) * (rEuMax - rEuMin);
END_IF;
// out of range below the live zero -> wire break; the threshold is signal-type specific
xWireBreak := iRaw < iRawMin - (iRawMax - iRawMin) / 10;
rValue := LIMIT(rEuMin, rValue, rEuMax);

// hysteresis: set above the limit, clear below the limit minus hysteresis
IF rValue >= rHiHi THEN
    xHiHiRaw := TRUE;
ELSIF rValue < rHiHi - rHyst THEN
    xHiHiRaw := FALSE;
END_IF;
IF rValue <= rLoLo THEN
    xLoLoRaw := TRUE;
ELSIF rValue > rLoLo + rHyst THEN
    xLoLoRaw := FALSE;
END_IF;

tonHiHi(IN := xHiHiRaw AND NOT xWireBreak, PT := tAlarmDelay);
tonLoLo(IN := xLoLoRaw AND NOT xWireBreak, PT := tAlarmDelay);
xHiHi := tonHiHi.Q;
xLoLo := tonLoLo.Q;
END_FUNCTION_BLOCK
```

**Raw ranges are platform- and module-specific.** For example, Siemens S7 analog modules
use a nominal 0…27648. Take the real numbers from the module documentation, not from
this template.

## Latched alarm with acknowledge

```iecst
FUNCTION_BLOCK FB_Alarm
VAR_INPUT
    xCondition : BOOL;   // alarm condition (already debounced/delayed)
    xAck       : BOOL;   // operator acknowledge (edge)
END_VAR
VAR_OUTPUT
    xActive    : BOOL;   // condition present
    xUnacked   : BOOL;   // came in and not yet acknowledged
    xLatched   : BOOL;   // show on HMI until condition gone AND acknowledged
END_VAR
VAR
    rtCond     : R_TRIG;
    rtAck      : R_TRIG;
END_VAR

rtCond(CLK := xCondition);
rtAck(CLK := xAck);
xActive := xCondition;
IF rtCond.Q THEN
    xUnacked := TRUE;
ELSIF rtAck.Q THEN
    xUnacked := FALSE;
END_IF;
xLatched := xActive OR xUnacked;
END_FUNCTION_BLOCK
```

**First-out:** in a group of trips, record the index of the first alarm whose `rtCond.Q`
fires while the group's first-out register is 0. Clear the register on the group reset.

## Sequence skeleton with step timer and timeout supervision

```iecst
FUNCTION_BLOCK FB_FillHeatDrain
VAR_INPUT
    xStart, xStop, xReset : BOOL;
    xLevelHigh, xLevelLow : BOOL;
    rTemp                 : REAL;
    rTempSetpoint         : REAL := 60.0;
END_VAR
VAR_OUTPUT
    xFillValve, xHeater, xDrainValve : BOOL;
    xFault                           : BOOL;
    nStep                            : INT;   // for HMI/diagnostics
END_VAR
VAR
    eStep       : E_FhdStep := E_FhdStep#Idle;
    eLastStep   : E_FhdStep := E_FhdStep#Idle;
    tonStep     : TON;
    rtStart     : R_TRIG;
    rtReset     : R_TRIG;
    tTimeout    : TIME;
END_VAR

rtStart(CLK := xStart);
rtReset(CLK := xReset);

// step timer restarts on every step change (IN drops for one scan)
tonStep(IN := eStep = eLastStep, PT := T#24H);
eLastStep := eStep;

CASE eStep OF
    E_FhdStep#Idle:
        tTimeout := T#0S;
        IF rtStart.Q AND NOT xFault THEN
            eStep := E_FhdStep#Filling;
        END_IF;
    E_FhdStep#Filling:
        tTimeout := T#5M;
        IF xLevelHigh THEN
            eStep := E_FhdStep#Heating;
        END_IF;
    E_FhdStep#Heating:
        tTimeout := T#30M;
        IF rTemp >= rTempSetpoint THEN
            eStep := E_FhdStep#Draining;
        END_IF;
    E_FhdStep#Draining:
        tTimeout := T#5M;
        IF xLevelLow THEN
            eStep := E_FhdStep#Idle;
        END_IF;
    E_FhdStep#Faulted:
        tTimeout := T#0S;
        IF rtReset.Q THEN
            xFault := FALSE;
            eStep := E_FhdStep#Idle;
        END_IF;
ELSE
    eStep := E_FhdStep#Faulted;
END_CASE;

// supervision: every waiting step has a timeout
IF tTimeout > T#0S AND tonStep.ET > tTimeout THEN
    xFault := TRUE;
    eStep := E_FhdStep#Faulted;
END_IF;
IF xStop AND eStep <> E_FhdStep#Faulted THEN
    eStep := E_FhdStep#Idle;
END_IF;

// outputs derived from the step (written once)
xFillValve := eStep = E_FhdStep#Filling;
xHeater := (eStep = E_FhdStep#Heating) AND NOT xLevelLow; // never heat an empty vessel
xDrainValve := eStep = E_FhdStep#Draining;
nStep := E_FHD_TO_INT(eStep);   // replace with the platform's enum-to-int conversion
END_FUNCTION_BLOCK
```

The `E_FhdStep` enum is not declared here, and `E_FHD_TO_INT` is a placeholder for the
platform's enum conversion:

- TwinCAT: `TO_INT(eStep)`
- Siemens: an enum is an `Int`-typed constant set
- Control Expert: an explicit `CASE`

## Dialect adjustments (summary; details in the platform skills)

| Construct | IEC / CODESYS / Machine Expert | TwinCAT | Siemens SCL | Logix ST |
|---|---|---|---|---|
| Enum literal | `E_X#Idle` (Ed.3) or `E_X.Idle` (CODESYS) | `E_X.Idle` | constants or an Int; no IEC enums in classic S7 | DINT constants |
| Local / global access | `x` / `GVL.x` | `x` / `GVL.x` | `#x` / `"DB".x` | tag names |
| Timer | `ton(IN := …, PT := …)` | same | `#ton(IN := …, PT := …)` with a TON_TIME/IEC_TIMER multi-instance | `TONR(t);` with an FBD_TIMER tag, PRE in ms |
| Block end | `END_FUNCTION_BLOCK` | none (in the XML) | `END_FUNCTION_BLOCK` after `BEGIN` | routine or AOI |
