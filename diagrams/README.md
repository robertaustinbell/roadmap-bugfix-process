# Diagrams

| File | What |
|---|---|
| [bug-fix-loop.png](bug-fix-loop.png) | Still of the whole loop |
| [bug-fix-loop-animated.mp4](bug-fix-loop-animated.mp4) | 14-second animation of one round |
| [stageshow-src/](stageshow-src/) | Source for the animation ([Stageshow](https://github.com/benjitaylor/skills) example; drop into its `examples/` folder) |
| Mermaid below | Editable text version; GitHub renders it |

The numbers in the still and animation (7 findings, PRs #41 to #43) are illustrative, not real.
Real numbers are in [../data/](../data/).

Austin's working copy of the graph is an Apple Freeform board. If you change the process, update
the Mermaid diagram below first; it is the version anyone can edit and the most complete one. The
still and the animation are simplified: they show the round, not the Coach's feedback arrows or
the publish driver.

```mermaid
flowchart LR
  subgraph WATCHED["Coach watch: the Coach runs while anything in here runs, and for 30 minutes after"]
    C[Coordinator<br/>starts a round only when every<br/>PR from the last round is addressed]
    PL["Round plan<br/>impact, recent change, staleness<br/>top areas first, coverage floor"]
    subgraph F[Finders on one pinned commit]
      F1[Trail of Bits skills]
      F2[fuck-my-shit-mountain]
      F3[tech-debt-audit]
      F4["Open Code Review<br/>next part each round<br/>until usage runs out"]
    end
    D["Decider<br/>merges duplicates, ALWAYS confirms:<br/>failing test / repro, or 2 independent checks<br/>records its prediction before any fix"]
    H["Human review list<br/>suspected, policy, clinical,<br/>schema, product decisions"]
    S[Private security report]
    B["Bug fixer<br/>one fix per PR, code standard<br/>gates: strict tsc, CRAP,<br/>mutation, incremental review"]
    R[Fresh reviewer<br/>approves one commit<br/>plus the PR text]
    PUB["Publish driver<br/>refuses unless approval, gates,<br/>suite and scrub all match<br/>never merges"]
    P["PRs<br/>Testing / Risk / How to revert<br/>no PR limit"]
    M["Brad<br/>merge / close / ask for a fix"]
  end
  CO[Coach<br/>changes nothing<br/>writes numbered feedback items]
  SC[(Scorecard)]
  TS[("Test set<br/>held-out cases, sealed answers")]
  C --> PL --> F1 & F2 & F3 & F4
  F1 & F2 & F3 & F4 -- "run status + coverage<br/>partial is never clean" --> D
  D -- confirmed --> B
  D -- "below bar / needs decision" --> H
  D -- security --> S
  H -- "Austin or Brad decides" --> B
  B -- gates pass --> R -- approve --> PUB --> P --> M
  R -- changes --> B
  M -- "fix requested: repair, max 2-3 rounds, new changes only" --> B
  M -- "outcomes + reasons" --> D
  M -- all addressed --> C
  B -. "pre-existing bug found" .-> F
  M --> SC & TS
  WATCHED -. observed .-> CO
  SC -. read .-> CO
  CO -- "feedback items, one role each" --> C & D & B
  C & D & B -- "reply: applied / not applied / disputed" --> CO
  CO -. "rule and process proposals" .-> H
  TS -. "rerun on any prompt/model/tool change" .-> D
```

The Coach's arrows to and from the Coordinator, Decider and Bug fixer stand for every role:
finders, the reviewer, repair and the OCR agent read and answer their items the same way
([roles.md](../docs/roles.md#how-coach-feedback-reaches-a-role)).
