# Scorecard and test set

These two sit outside the loop. The loop never edits them to look better. The Coach reads them
and gives feedback; humans decide what changes.

Adapted from Addy Osmani, ["How the Claude Code team does code review"](https://x.com/addyosmani/status/2114604912520921136)
(Oct 2026). That article reports one team's results; we treat its ideas as plausible, not proven,
and check them against our own numbers.

## Scorecard

Human time has two sides: time Brad spends reviewing, and time anyone spends fixing bugs our PRs
introduced. Cutting the first while raising the second is not a win.

Measure per PR, then per finder and per round:

| Measure | Why |
|---|---|
| Brad's comments per PR | Review effort we cost him |
| Repair rounds per PR | How often the first version was not good enough |
| Wait on Brad (opened to first maintainer action) | Queue pressure; drives when the next round can start |
| Merged and held 30 days, no revert or fix-forward | **Guardrail.** If this drops, faster is worse |
| Decider precision (confirmed findings that became merged fixes) | Whether confirmation is working |
| Decider confirm rate (candidates confirmed / candidates seen), beside precision | Precision can rise just by confirming less. Read the two together |
| Human-review and park rate | Sending everything to a human is a failure too, not caution |
| Brad's comment outcomes: fixed / rejected / intentional / didn't matter | Which feedback matters, and what to turn into rules |

Current numbers: [data/scorecard-baseline.md](../data/scorecard-baseline.md). Raw rows: [data/pr-outcomes.csv](../data/pr-outcomes.csv).

Regenerate the raw rows:

```sh
python3 scripts/data/pr_outcomes.py --author <your-github-login> --maintainer DrBradStanfield > data/pr-outcomes.csv
```

### Which rows count

- **An outcome counts only when it matches a published record.** Match on PR number, head SHA and
  `fix_id` against `published.jsonl` rows with `status: observed_succeeded`. Rows that match
  nothing are listed as `uncorrelated` and never enter a rate.
- **Credit comes only from events the loop did not write**: a maintainer merge, close, review or
  comment, or CI. Our own comments, labels and ledger lines are never evidence that a fix was good.
- **One root cause counts once.** Two PRs split from one confirmed bug (same `root_cause_key` in
  `decisions.json`) are one success or one failure.
- **Each outcome gets one label:** `correct` (merged and held), `incorrect` (closed as not a bug, or
  reverted), `partial` (merged after the maintainer changed what it does), or `unresolvable` (closed
  with no reason, or superseded). Report `unresolvable` instead of guessing.
- **Judge the decision apart from the outcome.** A Decider call made on the evidence available is
  not wrong because Brad later ruled the other way on a product choice. For each rejected PR, ask:
  was evidence missing, or was known evidence misjudged? Only the second is a Decider miss.
- **Correct for selection.** Brad only sees what the Decider approved, so outcomes say nothing about
  what it dropped. Each round, the Coordinator picks 3 dropped or parked items at random and has a
  fresh agent re-check them blind (no Decider reasoning). A dropped item that turns out real is a
  miss. The Coach reports the miss rate; it does not run the re-check.

## Test set

Seed list: [data/test-set-seed.md](../data/test-set-seed.md). It holds:

1. PRs Brad closed or reverted (the Decider should route these away from PRs).
2. Real bugs that were merged (finders should find them; the Decider should confirm them).
3. Bugs that shipped that the finders missed.
4. Known-clean code (any finding there is a false positive).
5. Fixtures for every end state, including planted instructions that must not change a route.

Rerun the Decider and all finders on the whole set whenever their prompts, model, or tools change.
Do not adopt a change that does worse on any section without a human decision.

## Sealed answers and held-out cases

An agent that can read the expected answer is not being tested.

- **The expected answers for held-out cases are never in this repo**, and never anywhere the agent
  under test can read. The operator keeps them in a private folder outside every agent's
  workspace. The cases in `data/test-set-seed.md` are the tuning set: public, and used to develop
  prompts.
- **Replay in a sealed clone.** For each case, make a fresh clone cut at the case's base commit with
  no later refs (`git clone --no-tags --single-branch`, then reset to base and drop the remote).
  The agent gets no network access to GitHub and no copy of this kit's `data/` folder. A run that
  cannot show how it was isolated is void, not a pass.
- **Hold cases back.** Choose a held-out set with the same rule as the tuning sample
  ([test-set-seed.md](../data/test-set-seed.md#2-should-become-a-pr-real-bugs-merged)), using a
  private seed. Nobody tunes against it. Report tuning and held-out results side by side; a gain on
  tuning cases that does not show on held-out cases is overfitting.
- **Held-out prompts must not leak the target.** The task text for a held-out case says what to scan,
  never which bug to look for or which file it is in.

## Running an evaluation

- **Write the expected change down first.** Before the run: which cases should change, in which
  direction, and what result would show the change is worse. Store it with the run.
- **A tie is `no_signal`, not a pass.** When the baseline and the change both get every case right,
  the set cannot tell them apart. Record `no_signal` and add a case that separates them before
  claiming anything.
- **Run nondeterministic agents k = 3 times** per case and compare medians. One lucky run is not a
  result.
- **Small numbers get a label.** Any rate with fewer than 10 resolved cases behind it is printed with
  "too few to act on", and no adoption decision rests on it alone.
- **The baseline is run, not imagined.** "Better than before" needs the old prompt, model and tools
  actually run on the same cases. A remembered or estimated baseline counts as no evidence.
- **Expected answers are versioned.** Changing an expected answer after seeing a result makes a new
  test-set version. Results on different versions are not compared.

## What counts as evidence

A result counts toward a claim that the loop, or a change to it, works only when it has:

1. a prediction recorded **before** the result was known;
2. an observable result someone else could check (a PR state, a test log, a commit);
3. an effect on a decision (it changed, or could have changed, what was adopted or routed).

**Failures count the same as passes.** A run that went against the prediction is reported with the
same weight and in the same place as one that went for it. **Matching a result to a claim after the
fact earns no credit**: if the prediction was not written first, the result is an anecdote.

Natural cases (real rounds on the real repo) and synthetic cases (fixtures written for the test set)
are reported separately. A high synthetic pass rate with zero natural cases supports no claim of
value, and sets no quota or target.

## Adding a rule, a field or a gate

Most proposed improvements add something. Adding is cheap; carrying it is not. A rule, schema
field, check or gate is added only when its proposal says:

- **the decision it feeds**: which route, adoption or refusal reads it;
- **what it would have changed**: a real incident it would have caught, or, for a new failure
  mode, a recorded prediction of what it will catch;
- **its removal condition**: what result, or how long without firing, retires it;
- **one thing to remove or merge**, or why nothing can go.

A gate that has never changed an outcome after its review period is removed. The gate-removal check
for the publish driver ([publishing.md](publishing.md#tests-for-the-driver)) applies the same idea
to code: a gate no test notices is ceremony.

## Turning repeated feedback into rules

When Brad makes the same kind of comment twice, the Coach proposes a durable rule: a lint rule,
a test, or a line in the code standard ([code-standard.md](code-standard.md)). A human approves it
before it lands. The Coach never edits anything itself.

The same applies to the loop's own finds: when the same kind of bug is confirmed three
times, the Coach proposes a check (lint rule, test or CI check) that stops that kind from
coming back. Track repeat kinds per round; they should fall toward zero.
