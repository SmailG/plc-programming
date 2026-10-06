---
description: M262 remanence on download (only PERSISTENT survives; %MW not implicitly retained).
tags: [knowledge, schneider]
max_turns: 10
allowed_tools: [Skill, Read, Glob, Grep]
---

On our Modicon M262 (Machine Expert) the production counters are declared VAR_GLOBAL RETAIN and the recipe number sits in %MW100. After I download a new application from Machine Expert, both are back to 0. Why, and what should I change so they survive downloads?
