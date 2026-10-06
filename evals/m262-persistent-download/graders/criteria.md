---
type: llm
---

PASS if the answer states that on a download from Machine Expert only PERSISTENT variables (VAR_GLOBAL PERSISTENT RETAIN, listed in the Persistent Variables object) are kept while RETAIN variables are reinitialised, that the M262 does not retain %MW implicitly (it must be declared retain/persistent, e.g. VAR_GLOBAL PERSISTENT RETAIN ... AT %MW100), and warns that renaming or changing the type of a persistent variable (or downloading from SD card / reset origin) still loses the value.
FAIL if it claims RETAIN survives a download, or that %MW is retained automatically on the M262.
