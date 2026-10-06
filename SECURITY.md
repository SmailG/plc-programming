# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub:
**Security** tab → **Report a vulnerability**
([private vulnerability reporting](https://github.com/SmailG/plc-programming/security/advisories/new)).
Do not open a public issue for a vulnerability.

You can expect a first response within a week.

## Scope

plc-programming is skills, an agent and a validator. The only code that runs on its own is the
PostToolUse hook: after Claude writes or edits a file, it runs `scripts/plc_validate.py` on that
file with the Python standard library. The validator reads files; it never writes them, never
fetches external entities or DTDs, and makes no network requests. `--xsd` (never used by the hook)
calls `xmllint` or `lxml` on a schema you pass.

Relevant reports include a crafted PLC or XML file that makes the validator hang, exhaust memory,
read or write outside the file it was given, or execute code, and anything that makes the hook
block or break a Claude Code session.

Out of scope: the correctness of a PLC program the plugin helped write. The validator is a
structural check, not a compiler or a safety assessment; test generated code on the target before
it runs a machine.

Only the latest release is supported.
