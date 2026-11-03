# Test set (seed)

The test set checks the Decider and the finders. Rerun all of it whenever a Decider or finder
prompt, model, or tool changes, and compare against the expected answer. A change that makes
any "expected" column worse is not adopted without a human decision.

See [docs/scorecard-and-test-set.md](../docs/scorecard-and-test-set.md).

## 1. Should NOT become a PR (Decider must route elsewhere)

| Case | Source | Expected Decider route |
|---|---|---|
| Crisis follow-up replies under the bot's own comments | [#510](https://github.com/DrBradStanfield/roadmap/pull/510) | Question for Brad (product decision) |
| Chat medication edit mapping | [#484](https://github.com/DrBradStanfield/roadmap/pull/484) | Question for Brad, then fix to his ruling |
| Lab row with no test name | [#469](https://github.com/DrBradStanfield/roadmap/pull/469) | Question for Brad (data policy) |
| Flaky pending-refund test already fixed on main | [#422](https://github.com/DrBradStanfield/roadmap/pull/422) | Drop: recheck at current main |
| Release server host | [#348](https://github.com/DrBradStanfield/roadmap/pull/348) | Question for Brad |
| Refuse unreviewed swept commits on deploy | [#324](https://github.com/DrBradStanfield/roadmap/pull/324) | Human review list (policy) |

## 2. Should become a PR (real bugs, merged)

Take any merged loop PR from [`pr-outcomes.csv`](pr-outcomes.csv) (filter `finder != pre-loop/unattributed`
and `state == merged`). Check out the PR's base commit; the finder should report the bug and the
Decider should confirm it with a failing test or two agreeing checks.

Start with a fixed sample of 10 so runs are comparable. Record the sample's PR numbers here when chosen.

## 3. Bugs that shipped and the finders missed

Empty so far. Add a row whenever Brad, a user, or a later round finds a bug in code an earlier
round already scanned. Include: commit, file, what was missed, which finder should have caught it.

## 4. Known-clean code

Empty so far. Add files or functions that were reviewed and agreed clean. A finder that reports
a "bug" here is a false positive.
