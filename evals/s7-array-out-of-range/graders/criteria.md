---
type: llm
---

PASS if the answer says the S7-1500 goes to STOP (a programming error handled by OB121, which is missing) unless the error is handled locally (GET_ERROR/GET_ERR_ID) or by OB121, says the S7-1200 records the error in the diagnostic buffer and stays in RUN, and recommends validating the index explicitly before the access (optionally also adding OB121 or local error handling).
FAIL if it claims both CPUs behave the same, claims the S7-1500 silently continues without OB121, or relies only on ENO to catch it.
