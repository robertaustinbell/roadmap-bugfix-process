# Diagrams

| File | What |
|---|---|
| [bug-fix-loop.png](bug-fix-loop.png) | Still of the whole loop |
| [bug-fix-loop-animated.mp4](bug-fix-loop-animated.mp4) | 16-second animation of one round |
| [stageshow-src/](stageshow-src/) | Source for the animation ([Stageshow](https://github.com/benjitaylor/skills) example; drop into its `examples/` folder) |
| Mermaid below | Editable text version; GitHub renders it |

The numbers in the still and animation (7 findings, PRs #41 to #43) are illustrative, not real.
Real numbers are in [../data/](../data/).

Austin's working copy of the graph is an Apple Freeform board. If you change the process, update
the Mermaid diagram below first; it is the version anyone can edit.

```mermaid
flowchart LR
  subgraph COACH["Coach sees everything inside this box (read-only)"]
    C[Coordinator<br/>starts a round only when every<br/>PR from the last round is addressed]
    subgraph F[Finders]
      F1[Trail of Bits skills]
      F2[fuck-my-shit-mountain]
      F3[tech-debt-audit]
      F4[Open Code Review<br/>new part each round<br/>until usage runs out]
    end
    D[Decider<br/>dedups, ALWAYS confirms:<br/>failing test / repro, or 2 agreeing checks]
    H[Human review list<br/>suspected, policy, behavior,<br/>clinical, schema, security policy,<br/>needs a product decision]
    S[Private security report]
    B[Bug fixer<br/>one fix per PR, code standard<br/>gates: strict tsc, CRAP,<br/>mutation ratchet, FMSM incremental<br/>never merges]
    P[PRs<br/>Testing / Risk / Revert<br/>no PR limit]
    M[Brad<br/>merge / close / ask for fix]
  end
  SC[(Scorecard)]
  TS[(Test set)]
  C --> F1 & F2 & F3 & F4
  F1 & F2 & F3 & F4 --> D
  D -- confirmed --> B
  D -- below bar / needs decision --> H
  D -- security --> S
  H -- Austin or Brad decides --> B
  B -- gates pass --> P --> M
  M -- fix requested: repair, max 2-3 rounds, new changes only --> B
  M -- outcomes + reasons --> D
  M -- all addressed --> C
  B -. pre-existing bug found .-> F
  M --> SC & TS
  SC -. Coach reads .-> COACH
  TS -. rerun on any prompt/model/tool change .-> D
```
