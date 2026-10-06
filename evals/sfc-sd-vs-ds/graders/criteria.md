---
type: llm
---

PASS if the answer states that SD (stored and delayed) starts the action after the delay even if the step has become inactive, that DS (delayed and stored) starts it only if the step is still active when the delay expires, that both then stay active until reset with R, and therefore recommends DS for the user's case.
FAIL if SD and DS are swapped, if either is described as not needing a reset, or if it recommends SD.
