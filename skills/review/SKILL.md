---
name: review
description: Review PLC code or exports (files, directories or pasted code) with the plc-reviewer agent and report ranked findings.
argument-hint: "[paths...] [focus]"
disable-model-invocation: true
---

# Review PLC code

The target is `$ARGUMENTS`. If it is empty, review the PLC files changed in the working
tree (`git status` / `git diff --name-only`). If there are none, ask what to review.

1. **List the files in scope and their detected formats:**
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plc_validate.py --json <paths>`.
2. **Delegate to the `plc-reviewer` agent.** Pass the file list, the platform and version
   if known, any focus the user named (for example "interlocks" or "Modbus"), and the
   validator's JSON output. For large projects, split by program or area and run the
   reviews in parallel.
3. **Merge and de-duplicate the findings. Present them most-severe first**, as a table:
   severity, location `file:line`, rule, finding, fix.
4. **Offer to apply the fixes. Do not apply them unasked.** For each fix, state the
   deployment impact (online change or download, re-initialisation).
