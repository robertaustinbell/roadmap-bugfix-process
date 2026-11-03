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
| Brad's comment outcomes: fixed / rejected / intentional / didn't matter | Which feedback matters, and what to turn into rules |

Current numbers: [data/scorecard-baseline.md](../data/scorecard-baseline.md). Raw rows: [data/pr-outcomes.csv](../data/pr-outcomes.csv).

Regenerate the raw rows:

```sh
python3 scripts/data/pr_outcomes.py --author <your-github-login> --maintainer DrBradStanfield > data/pr-outcomes.csv
```

## Test set

Seed list: [data/test-set-seed.md](../data/test-set-seed.md). It holds:

1. PRs Brad closed or reverted (the Decider should route these away from PRs).
2. Real bugs that were merged (finders should find them; the Decider should confirm them).
3. Bugs that shipped that the finders missed.
4. Known-clean code (any finding there is a false positive).

Rerun the Decider and all finders on the whole set whenever their prompts, model, or tools change.
Do not adopt a change that does worse on any section without a human decision.

## Turning repeated feedback into rules

When Brad makes the same kind of comment twice, the Coach proposes a durable rule: a lint rule,
a test, or a line in the code standard ([code-standard.md](code-standard.md)). A human approves it
before it lands. The Coach never edits anything itself.

The same applies to the loop's own finds: when the same kind of bug is confirmed three
times, the Coach proposes a check (lint rule, test or CI check) that stops that kind from
coming back. Track repeat kinds per round; they should fall toward zero.
