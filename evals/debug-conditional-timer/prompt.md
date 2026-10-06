---
description: Classic scan-cycle bug - a TON called only inside an IF.
tags: [debug]
max_turns: 8
allowed_tools: [Skill, Read, Glob, Grep]
---

Our fill timeout alarm is weird. Filling normally takes about 40 s and the timeout is 60 s, but sometimes the alarm fires only a few seconds after a NEW fill starts. This is the code (runs every cycle):

```
IF eState = E_State#Filling THEN
    tonFill(IN := TRUE, PT := T#60S);
    IF tonFill.Q THEN
        xFillTimeout := TRUE;
    END_IF;
END_IF;
```

What is wrong and how do I fix it?
