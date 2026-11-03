# Prioritization: the Coordinator decides what gets worked on

A full pass of every finder over a large repo, followed by confirmation, fixes, review and
repair, can take a week. So each round works on a **budget**, not on the whole repo, and
the Coordinator chooses what the budget is spent on, so the most important code is
handled first.

The Coordinator decides **order and scope**. It does not decide whether a finding is
real or how it is routed; that stays with the Decider.

## Round plan

Before the finders start, the Coordinator writes `$STATE_DIR/rounds/<round>/plan.json`:

```json
{
  "round": "R20261110-1",
  "budget": {"finder_tokens": 1500000, "fix_slots": 8, "wall_clock_hours": 24},
  "areas": [
    {"area": "health-core", "score": 7, "share": "focus",
     "reasons": ["clinical impact", "14 commits since last scan"],
     "finders": ["trail-of-bits", "fmsm", "open-code-review"],
     "expected": "at least one confirmed unit or reference-range bug"},
    {"area": "docs", "score": 1, "share": "exploration",
     "reasons": ["not scanned for 4 rounds (coverage floor)"], "finders": ["open-code-review"]}
  ],
  "deferred": [{"area": "ci-config", "rounds_since_scan": 2, "why": "low score"}],
  "owner_pins": [], "owner_excludes": []
}
```

The plan is written down so it can be audited and checked against outcomes later. A plan
the Coordinator cannot explain in its `reasons` list is a bad plan.

`expected` is optional: what the Coordinator thinks the focus area will yield, written before the
finders run. At round close it is scored as met, not met or no signal, and never edited afterwards.
A Coordinator whose expectations are rarely met is scoring areas badly, which is worth knowing
before outcomes arrive. Commit `plan.json` at round open so later edits show in history.

## Scoring an area

An area is a part of the repo (the same part list Open Code Review uses). Start with
three signals, each scored 0 to 3, and add them:

| Signal | Scores high when |
|---|---|
| Impact | Wrong behaviour could harm users: clinical meaning, data loss, privacy, payment, auth. Score shared code by the worst user outcome it feeds, not by its folder (below) |
| Change | Many commits or lines changed since the area was last scanned |
| Staleness | Many rounds since the last scan (grows every round, so nothing waits forever) |

Skip areas that are generated, vendored or scheduled for removal.

**Impact follows the data, not the folder.** A unit converter, a reference-range table or a lab
parser can sit in a folder that looks low-stakes while every clinical number passes through it.
Trace each user-critical outcome (a value shown, a reminder sent, a record saved or erased) back to
the shared code it depends on, and give that code the outcome's Impact. Record the trace in
`reasons`. This refines Impact; it is not a fourth signal.

Keep it this small until real rounds say otherwise. Each extra signal or setting is one
more thing to tune, test and explain. Add a signal (for example past bug yield, how many
users the code runs for, weak tests, or bugs reported from outside the loop) only when at
least two rounds of results show it would have changed which areas were scanned. Log
the reason when you add one.

**Do not score by past finds alone.** You only find bugs where you look, so "bugs found
here before" mostly measures where the loop already looked. Merged PRs also reflect what
the maintainer likes to review, not only where bugs are. And the top-scored area may be
the one whose noisy findings happened to look best. If past yield is added as a signal,
check it against the exploration share (see below).

## Spending the budget

1. **Owner pins first.** Areas the owner pins are in; areas the owner excludes are out.
2. **Coverage floor.** Any area not scanned for 4 rounds is in.
3. **Focus share** (about 80% of the finder budget): highest scores first. The precise
   finders (Trail of Bits, FMSM, tech-debt) go here.
4. **Exploration share** (about 20%): the least recently scanned areas, regardless of
   score. Open Code Review's breadth fits here. This is how the loop finds bugs in places
   nobody expected, and it is the fair comparison for the scoring: it is not chosen by
   score, so it shows what the scoring is missing.
5. **Stop at the budget.** A round ends when the budget is spent, not when the repo is
   covered. What did not fit goes to `deferred` with its staleness counter.

## Caution where the stakes are highest

The loop does not pay for its mistakes; the maintainer and the app's users do. Sending
the most effort to the highest-impact code also means the riskiest changes come first,
so caution has to rise with impact. For a `fix` in an area with Impact 3:

- The change is limited to the confirmed bug's sites. No refactor or clean-up rides along.
- The failing test shows the wrong result the user would get, not only an internal value.
- The reviewer runs on a different model where one is available. If not, the PR says the
  review was same-model.
- If the right fix would change anything a user sees beyond correcting the confirmed
  wrong result, route it as `question` or `human-review` instead, or offer a test-only
  PR that pins the bug and let the maintainer choose the fix.

## Ordering the fix queue

After the Decider routes findings, the Coordinator orders the fix queue:

0. **Broken loop fixes come first.** A loop change that was reverted, needed a fix-forward,
   or caused a reported problem goes to the front, ahead of every new find. Its PR says
   plainly which earlier PR caused it and what went wrong, and the case is added to the
   test set.
1. **Questions for the owner go out first**, in one batch, because answers unblock or
   cancel fixes.
2. Then fixes by severity, then user impact, then confidence, then size (smaller first
   when the rest ties).
3. Fixes to the same code are queued so they do not run in parallel (see sequencing in
   [process.md section 3.5](process.md#35-fix)).
4. `fix_slots` caps how many fixes start in a round. Set it from how many PRs the
   maintainer actually addresses per round, so the queue matches what can be reviewed.

## When a round stops early

A round ends in one of these states, written to `round.json` as `end_state`:

| State | Meaning |
|---|---|
| `done` | Budget spent or plan covered, PRs opened |
| `nothing_found` | The planned areas produced no confirmed bug, and every finder run was clean. A valid result, not a failure |
| `partial` | At least one finder run was not clean (error, timeout, truncated, unparseable output). Its areas keep their staleness ([process.md](process.md#partial-is-never-clean)) |
| `stalled` | The focus areas confirmed nothing for two rounds in a row. Stop, re-plan, and tell the operator; the scoring may be wrong |
| `out_of_budget` | Tokens or time ran out mid-plan. Record where each finder stopped |
| `blocked` | A finder, tool or gate failed in a way a retry will not fix |
| `waiting_on_owner` | The fixes left depend on owner answers |

## Checking that prioritization works

Each round, the Coach and the scorecard compare the plan with what happened:

- The goal is a safer app for little of the maintainer's time, not a count of bugs. So
  the main measure is fixes that held (`held_30d`) per hour of maintainer review time,
  with finder tokens as the cost. Confirmed bugs are an early signal only, used before
  outcomes are in.
- Compare focus against exploration on that measure (or on confirmed bugs, while
  outcomes are pending). Count bugs after merging duplicates of the same underlying
  problem, so splitting one finding into several cannot improve a score. If exploration
  matches or beats focus for two rounds, the scoring is not working.
- Bugs found from outside the loop, and whether their area was deferred. A miss in a
  deferred area is evidence for adding or reweighting a signal.
- Rounds per area: no area may exceed the coverage floor.
- Days from round open to PRs opened.
