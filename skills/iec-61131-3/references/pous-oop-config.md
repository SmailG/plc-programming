# POUs, OOP, namespaces and configuration

## POU types

| POU | State | Returns | Can call | Typical use |
|---|---|---|---|---|
| `FUNCTION` | none; deterministic | a value, plus `VAR_OUTPUT` | functions | maths, conversions, pure checks |
| `FUNCTION_BLOCK` | kept in the instance | outputs | functions, FBs | devices, controllers, state machines |
| `PROGRAM` | kept (one instance) | – | functions, FBs | top level, bound to a task |
| `CLASS` (Ed.3) | kept | – | methods only; **no body** | pure OOP; rare in IDEs, which prefer FBs with methods |

```iecst
FUNCTION_BLOCK FB_Valve
VAR_INPUT
    xOpenCmd : BOOL;
END_VAR
VAR_OUTPUT
    xOpened  : BOOL;
    xFault   : BOOL;
END_VAR
VAR
    tonTravel : TON;
END_VAR
    tonTravel(IN := xOpenCmd AND NOT xOpened, PT := T#10S);
    xFault := tonTravel.Q;
END_FUNCTION_BLOCK
```

## OOP (Ed.3)

```iecst
INTERFACE I_Device
    METHOD Start : BOOL
    END_METHOD
END_INTERFACE

FUNCTION_BLOCK ABSTRACT FB_DeviceBase IMPLEMENTS I_Device
VAR
    xRunning : BOOL;
END_VAR
    METHOD PUBLIC Start : BOOL
        xRunning := TRUE;
        Start := TRUE;
    END_METHOD
END_FUNCTION_BLOCK

FUNCTION_BLOCK FB_Pump EXTENDS FB_DeviceBase
    METHOD PUBLIC OVERRIDE Start : BOOL
        Start := SUPER^.Start();
    END_METHOD
END_FUNCTION_BLOCK
```

- **Keywords:**
  - `EXTENDS` gives single inheritance.
  - `IMPLEMENTS` can name several interfaces.
  - `ABSTRACT` and `FINAL` apply to classes, FBs and methods.
  - `OVERRIDE`, `THIS`, `SUPER`, and `SUPER()` to call the base body.
  - Access specifiers: `PUBLIC`, `PRIVATE`, `PROTECTED` and `INTERNAL`.
- **An interface can be a variable type.** Use it for polymorphic calls, together with
  `?=` to cast.
- **Properties:** `PROPERTY` with Get/Set is a CODESYS/TwinCAT extension. Ed.4
  standardises `PROPERTY_GET`/`PROPERTY_SET`.
- **Default access** when no specifier is written: CODESYS/TwinCAT use `PUBLIC`, but the
  standard's rule was not verified, so write specifiers explicitly.
- **Vendor syntax differs.** In TwinCAT and CODESYS, methods are separate objects in the
  project tree, and `SUPER^.Start()` and `THIS^` use pointer syntax. Siemens S7 classic
  blocks have no OOP, and SIMATIC AX uses `CLASS`/`NAMESPACE`.

## Namespaces (Ed.3)

- Declare with `NAMESPACE Plant.Utilities … END_NAMESPACE`, nested or fully qualified.
- `USING Plant.Utilities;` works globally, inside a namespace, or inside a POU.
- `INTERNAL` limits visibility to the namespace.
- Library namespaces in CODESYS/TwinCAT are a different mechanism: the library's default
  namespace, as in `Tc2_Standard.TON`.

## Configuration, resource, task

```iecst
CONFIGURATION Cell_1
    VAR_GLOBAL w : UINT; END_VAR
    RESOURCE Station_1 ON PROCESSOR_TYPE_1
        TASK Slow_1 (INTERVAL := T#20MS, PRIORITY := 2);
        TASK Int_2  (SINGLE := z2, PRIORITY := 1);
        PROGRAM P1 WITH Slow_1 : F(x1 := %IX1.1);
    END_RESOURCE
END_CONFIGURATION
```

This is modelled on the configuration example in the standard.

- **Task triggers:**
  - `SINGLE` runs the task on a rising edge.
  - `INTERVAL` runs it periodically.
  - A program with no task runs at the lowest priority, continuously.
- **Priority 0 is the highest.** Scheduling may be preemptive or not, depending on the
  implementation.
- **Associating tasks with FB instances directly is deprecated** (TR 61131-8 7.15 and
  PLCopen CP16/CP27). Associate tasks with PROGRAMs.
- **Data consistency.** Data shared between tasks of different priorities can tear:
  values wider than the CPU's atomic width, and multi-variable consistency. Copy the
  data at the start of the consuming task, or use Ed.4's mutex/semaphore or the vendor's
  equivalent.
- **Real IDEs** replace this textual configuration with a task configuration dialog, but
  the concepts map one to one.
