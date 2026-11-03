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
    {"area": "health-core", "score": 8.4, "share": "focus",
     "reasons": ["clinical impact", "14 commits since last scan", "2 confirmed bugs last round"],
     "finders": ["trail-of-bits", "fmsm", "open-code-review"]},
    {"area": "docs", "score": 1.1, "share": "exploration",
     "reasons": ["not scanned for 4 rounds (coverage floor)"], "finders": ["open-code-review"]}
  ],
  "deferred": [{"area": "ci-config", "rounds_since_scan": 2, "why": "low score"}],
  "owner_pins": [], "owner_excludes": []
}
```

The plan is written down so it can be audited and checked against outcomes later. A plan
the Coordinator cannot explain in its `reasons` list is a bad plan.

## Scoring an area

An area is a part of the repo (the same part list Open Code Review uses). Score each one
from signals that can be checked. Weights live in `$STATE_DIR/priority-weights.json` and
change only with a logged reason.

| Signal | Raises the score when |
|---|---|
| Impact | Wrong behaviour could harm users: clinical meaning, data loss, privacy, payment, auth |
| Change | Many commits or lines changed since the area was last scanned |
| Yield | Earlier rounds confirmed bugs here; maintainers merged fixes here |
| Exposure | Code runs for every user or on every request, not a dev-only path |
| Weak tests | Low coverage, or tests that only check text rather than behaviour |
| Outside reports | A user, maintainer or issue reported a bug here that the loop missed |
| Staleness | Rounds since the last scan (grows every round, so nothing waits forever) |

Lower the score when maintainers closed or declined fixes from the area, or when the area
is generated, vendored or scheduled for removal.

## Spending the budget

1. **Owner pins first.** Areas the owner pins are in; areas the owner excludes are out.
2. **Coverage floor.** Any area not scanned for `$MAX_GAP` rounds (default 4) is in.
3. **Focus share** (about 80% of the finder budget): highest scores first. The precise
   finders (Trail of Bits, FMSM, tech-debt) go here.
4. **Exploration share** (about 20%): the least recently scanned areas, regardless of
   score. Open Code Review's breadth fits here. This is how the loop finds bugs in places
   nobody expected; in the static-site trial, the most visible bug was in a file nobody
   would have ranked highly.
5. **Stop at the budget.** A round ends when the budget is spent, not when the repo is
   covered. What did not fit goes to `deferred` with its staleness counter.

## Ordering the fix queue

After the Decider routes findings, the Coordinator orders the fix queue:

1. **Questions for the owner go out first**, in one batch, because answers unblock or
   cancel fixes.
2. Then fixes by severity, then user impact, then confidence, then size (smaller first
   when the rest ties).
3. Fixes to the same code are queued so they do not run in parallel (see sequencing in
   [process.md section 3.5](process.md#35-fix)).
4. `fix_slots` caps how many fixes start in a round. Set it from how many PRs the
   maintainer actually addresses per round, so the queue matches what can be reviewed.

## Checking that prioritization works

Each round, the Coach and the scorecard compare the plan with what happened:

- Confirmed bugs per million finder tokens, focus share against exploration share. If
  exploration keeps winning, the scoring is wrong.
- Bugs found from outside the loop, and whether their area was deferred. A miss in a
  deferred area raises that area's weight for its signal.
- Rounds per area: no area may exceed `$MAX_GAP`.
- Days from round open to PRs opened.
