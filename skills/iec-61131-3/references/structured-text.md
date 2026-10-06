# Structured Text (ST)

## Operator precedence

From highest to lowest, per Ed.3 Table 71:

| # | Operator | Notes |
|---|---|---|
| 1 | `( … )` | |
| 2 | function / method call `f(args)` | |
| 3 | dereference `^` | Ed.3 |
| 4 | unary `-`, unary `+`, `NOT` | **CODESYS ranks `**` above these** |
| 5 | `**` | same as `EXPT(A, B)` |
| 6 | `*` `/` `MOD` | |
| 7 | `+` `-` | |
| 8 | `<` `>` `<=` `>=` | |
| 9 | `=` `<>` | |
| 10 | `&` / `AND` | |
| 11 | `XOR` | |
| 12 | `OR` | |

Rules:

- Operators of equal precedence apply left to right.
- Short-circuit evaluation of `AND`/`OR` is **permitted but not required**. Never guard
  an index or a pointer with `a AND b` and assume that `b` is skipped. Nest an `IF`
  instead, or use `AND_THEN` on CODESYS.

## Statements

```text
x := expr;                                   // assignment (never '=')
inst(IN := a, PT := T#5S, Q => q);           // FB call: ':=' binds inputs, '=>' binds outputs
y := inst.Q;                                 // read an output after the call
RETURN;
IF c1 THEN … ELSIF c2 THEN … ELSE … END_IF;
CASE sel OF
    1, 5:      …;
    4, 6..10:  …;
    E_State#Idle: …;
ELSE       …;
END_CASE;
FOR i := 1 TO 10 BY 2 DO … END_FOR;
WHILE c DO … END_WHILE;
REPEAT … UNTIL c END_REPEAT;
EXIT;       // leave the innermost loop
CONTINUE;   // next iteration (Ed.3)
;           // empty statement
```

- **`FOR` rules:**
  - The control variable, the start and the end must share one integer type.
  - Do not modify the control variable inside the loop.
  - `BY` defaults to 1.
  - The value of the control variable after the loop is **implementation-dependent**.
- **`WHILE`/`REPEAT` must not wait for a process event.** A loop that blocks the scan
  starves every other task and trips the watchdog. Wait across scans with a state
  machine or SFC instead.
- **A `CASE` selector** must be an integer or an enumeration, not REAL or STRING.
- **Runtime errors** include division by zero, operands of the wrong type, and numeric
  overflow. Guard divisors and array indices explicitly.

## Assignment attempt and references (Ed.3)

```iecst
VAR
    itfDevice : I_Device;
    refMotor  : REF_TO FB_Motor;
END_VAR
refMotor ?= itfDevice;          // NULL if itfDevice is not an FB_Motor
IF refMotor <> NULL THEN
    refMotor^.Start();
END_IF;
```

## Literals

- **Integers:** `-12`, `123_456`, `16#FF`, `2#1010_1010`, and typed forms such as
  `INT#-5` and `UINT#16#9AF`.
- **REAL:** `1.34E-12` and `0.5`.
- **Durations:** `T#14ms`, `T#1h2m3s`, `TIME#25h_15m`, `T#-14ms`, and in Ed.3 `LT#…`
  with the units `us` and `ns`.
- **Dates and times:** `D#2026-09-27`, `TOD#15:36:55.36`, `DT#2026-09-27-15:36:55`, and
  the long forms `LD#`, `LTOD#` and `LDT#`.
- **Strings:** `'single-byte'` and `"double-byte"`, with the escapes `$$ $' $L $N $P $R $T $"`
  and `$hh` (in Ed.4 also `${hex}`).
- **Enumerated values:** `E_Color#Red`.

## Idioms that pass review

**Edge detection:** call the FB every scan, then use its pulse.

```iecst
rtStart(CLK := xStartButton);
IF rtStart.Q THEN
    eState := E_State#Starting;
END_IF;
```

**Timer:** call it unconditionally and gate its `IN`, never its call.

```iecst
tonFill(IN := eState = E_State#Filling, PT := T#30S);
IF tonFill.Q THEN
    eState := E_State#FillTimeout;
END_IF;
```

**REAL comparison:** use a tolerance (PLCopen CP8).

```iecst
IF ABS(rLevel - rSetpoint) < 0.01 THEN
    xAtSetpoint := TRUE;
END_IF;
```

**Division guard:**

```iecst
IF rDenominator <> 0.0 THEN
    rRatio := rNumerator / rDenominator;
ELSE
    rRatio := 0.0;
    xDivError := TRUE;
END_IF;
```

The comparison against exactly `0.0` is the one exception PLCopen CP8 allows.

**State machine:** use an enum-typed state and assign exactly one next state per branch.
Keep outputs out of the transition code and derive them from the state after the
`CASE`. This makes every output a function of the state, which is easy to review and
monitor.

```iecst
CASE eState OF
    E_State#Idle:
        IF rtStart.Q AND xPermissive THEN
            eState := E_State#Running;
        END_IF;
    E_State#Running:
        IF NOT xPermissive OR xStopReq THEN
            eState := E_State#Stopping;
        END_IF;
    E_State#Stopping:
        IF xStopped THEN
            eState := E_State#Idle;
        END_IF;
ELSE
    eState := E_State#Idle;   // defensive: an unknown value goes to a safe state
END_CASE;

xMotorOn := (eState = E_State#Running);
```
