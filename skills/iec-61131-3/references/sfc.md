# Sequential Function Chart (SFC)

## Elements

- **Step:** `STEP s: … END_STEP`, or `INITIAL_STEP s: … END_STEP`, drawn with a double
  border. **Each SFC network has exactly one initial step.**
- **Step flags:**
  - `s.X` (BOOL) is TRUE while the step is active.
  - `s.T` (TIME) is the elapsed time since the step was activated. It holds its value
    after the step deactivates and resets to `T#0s` on reactivation.
  - Writing to either flag is an error.
- **Transition:** a condition in ST, LD or FBD, a connector, the textual form
  `TRANSITION FROM s1 TO s2 := cond; END_TRANSITION`, or a named transition.
  **A condition that has side effects is an error.**
- **Retention:** a step's state is retentive if its containing POU instance is retentive.

## Rules of evolution

- A transition is **enabled** when all of its preceding steps are active. It **clears**
  when it is enabled and its condition is TRUE. Clearing deactivates all preceding
  steps, then activates all succeeding steps.
- Steps and transitions **must alternate**: two steps are never linked directly, and
  neither are two transitions.
- **Selection divergence** (OR-branch, a single horizontal line). Priority is given in
  one of three ways:
  - `*`, left to right;
  - user-numbered priorities;
  - mutual exclusion that the programmer guarantees.
  
  In every case it is an error if non-prioritised branches can be TRUE together.
  A **selection convergence** closes the branch.
- **Simultaneous divergence** (AND-branch, double horizontal lines) has one common
  transition above the divergence and one below the convergence. PLCopen L7 says to
  close these paths correctly: every branch must reach the same simultaneous
  convergence.
- **Unsafe SFC** (tokens proliferate) and **unreachable SFC** (it locks up) cannot be
  prevented by the syntax rules alone, and the standard treats both as errors. Review
  every jump for either condition.

## Action qualifiers (Ed.3 Table 59)

| Qualifier | Meaning | Time value |
|---|---|---|
| `N` / none | non-stored: active while the step is active | – |
| `R` | overriding reset of a stored action | – |
| `S` | set (stored): stays active until `R` | – |
| `L` | time-limited: active while the step is active, at most T | required |
| `D` | time-delayed: starts after T if the step is still active | required |
| `P` | pulse | – |
| `SD` | stored and delayed: starts after T **even if the step has gone inactive**, runs until `R` | required |
| `DS` | delayed and stored: set only if the step is **still active** after T, runs until `R` | required |
| `SL` | stored and time-limited: runs for T or until `R` | required |
| `P1` | pulse on the rising edge (step activation) | – |
| `P0` | pulse on the falling edge (step deactivation) | – |

**Action control rules:**

- **Final scan.** An action executes one extra time after its Q output falls, with
  `ActionName.Q = FALSE`. That is why TwinCAT says a `P` action "executes precisely
  twice". Write actions so that this last call cleans up, for example by writing outputs
  from `ActionName.Q` rather than setting them unconditionally.
- `P1`/`P0` actions run once, with Q always FALSE.
- Errors:
  - more than one active time-qualified association (`L`, `D`, `SD`, `DS`, `SL`) for the
    same action;
  - `SD` and `SL` active together.
- Ed.3 deprecates the Boolean indicator variable in the action block.
- **PLCopen XML** accepts the qualifiers `P1 N P0 R S L D P DS DL SD SL` (the schema
  list), with the time value in the `duration` attribute.

## Design guidance

- One SFC per independent sequence. Put interlocks and output logic outside the chart
  and let the chart own the sequence only.
- Every waiting step needs a **timeout supervision**, for example
  `TRANSITION … := s.T > T#30S`, leading to a fault step. Otherwise a missing sensor
  hangs the chart silently.
- Plan how to reset or initialise the chart, for example a vendor `SFCInit`/`SFCReset`
  or a jump back to the initial step. A stop or abort must be able to reach the initial
  step from every state.
- Vendor names differ, so identify the dialect before converting:
  - Siemens calls SFC **GRAPH** (S7-1500), with supervision and interlock conditions per step.
  - Schneider Control Expert calls it SFC.
  - Machine Expert, CODESYS and TwinCAT call it SFC and add step flags such as
    `SFCCurrentStep`.
  - Rockwell has SFC routines.
