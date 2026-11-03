# Decisions

Changes to the process itself: what changed, why, and what result would undo it. Newest first.
Each entry names the decision it feeds and its removal condition, per
[adding a rule, a field or a gate](scorecard-and-test-set.md#adding-a-rule-a-field-or-a-gate).
Rules live in their own pages; this page records why they are there.

## 2026-11-03: the Coach runs itself, and its feedback is delivered and scored

Austin's rule: the Coach "runs when ever anything else is running and for a bit after", and it
can only observe and give feedback. Checking the kit showed neither half was wired: only the
Coordinator started the Coach, once per round, and no role template read its feedback.

| Change | Why | Feeds | Undo when |
|---|---|---|---|
| [`scripts/coach/watch.py`](../scripts/coach/watch.py): launchers register agents (`run`, `begin`/`end`); publishes and maintainer actions count through watched files; it starts one Coach while anything is active and for `COOLDOWN_MIN` after. `mech.py` uses it when `STATE_DIR` is set | Scans, repairs and publishes between rounds were never watched | When the Coach runs | The agent runtime itself can start an observer for every agent |
| Numbered items in `coach/items.jsonl`, each to one role; every template reads its open items and replies through [`items.py`](../scripts/coach/items.py) | Feedback reached nobody unless a human relayed it | What each role does differently next run | Replies show no `applied` item helped in 10 rounds: drop items and keep only the round report and human proposals |
| The Coach scores replies (helped, did not help, disputed and right, not delivered) and reports its hit rate | Coach advice was never checked | Whether Coach feedback is worth reading | Never removed while items exist; it is how items are judged |

## 2026-11-03: hardening from an operating-knowledge review

Source: a full read of the operator's agent-operations notes (governance, operating guides, evidence
and archive), checked against this kit's code and docs. Every code finding below was confirmed
in the driver before it was changed, and each change has a test.

| Change | Why | Feeds | Undo when |
|---|---|---|---|
| Strict approval check, text digests, attempted-before-write ledger, untracked and dropped-commit refusals, body sections checked, secret-free suite env ([publishing.md](publishing.md)) | The driver accepted duplicate-key verdicts, 7-character heads and `not_checked` approvals; title and body could change after review; a crash between `gh pr create` and the ledger write left no record; the docs claimed a body check the code did not do | Publish or refuse | Never removed as a group. A single gate goes if the [gate-removal check](publishing.md#tests-for-the-driver) shows no test depends on it and no refusal has used it in 10 rounds |
| Kit checker and contract tests ([check_kit.py](../scripts/check_kit.py)) | Two drifts were found by hand: `publishing.md` described `review<N>.md` files the driver no longer reads, and the Decider's output shape matched no schema. The public scrub depended on memory | Whether a kit change can be pushed | A check that has not fired in 6 months of kit changes is reviewed for removal |
| [Decision schema](../templates/decision.schema.json) with verbatim claim, root-cause key, prediction, reported claims, search depth, history and fix level | Outcomes could not be matched to one root cause; tests could assert a nearby, easier claim; "already fixed" was believed without a check; predictions were not recorded, so learning was after the fact | Decider routing and scorecard counting | A field nobody has read in a routing or scoring decision for 5 rounds |
| [Partial is never clean](process.md#partial-is-never-clean) | A finder that errored or was cut off could count as "found nothing", resetting staleness and closing a round as `done` | Round `end_state`, area staleness | No `partial` round in 10 rounds and no unclean run found by the Coach |
| [Sealed answers, held-out cases, `no_signal`, run baselines, the evidence rule](scorecard-and-test-set.md) | Expected answers sat where agents could read them; nothing was held back from tuning; a tie counted as "not worse"; the 10-PR sample was never drawn | Adopting prompt, model or tool changes | Never removed: without it the test set cannot tell better from worse |
| [Tool-enforced limits and `dispatch.json`](roles.md#enforced-by-tools-not-by-prompts) | "Never merges" was a prompt rule. A worker shown a short tool list can receive the full set | Whether an agent may start | The runtime itself enforces per-role tools and records them |
| [Independent evidence](evidence-bar.md#independent-evidence) | Agreement between checks that shared a source, or a model, was counted as two | Confirmation | Never removed; it defines what confirmation means |
| Test-quality and receipt rules ([quality-gates.md](quality-gates.md)), repair limits ([repair-rounds.md](repair-rounds.md)) | Tests could assert a flag the fix added; receipts named a script but not its version; a threshold could be picked per run; repairs could start before checks finished | Gate results, repair starts | Per rule, after 10 rounds where it never changed an outcome |
| [Health-data probes](regression-review.md#health-data-probes) | Recurring bug shapes in health code (real zeros, unit scales, paired values, timezone dates) | Finder coverage | A probe that finds nothing in 10 scans of health code is dropped |
| [Coach failure stages, predictions, removal tracking](../agents/coach.md) | Feedback fixed the last visible symptom; Coach advice was never scored; nothing proposed removals | Coach proposals | Coach predictions score no better than chance for 5 rounds |
| [Impact follows the data](prioritization.md#scoring-an-area), per-area `expected` | Shared converters and parsers scored low by folder while clinical values passed through them | Round plan | The trace changes no area's score for 5 rounds |

The opposite risk was weighed: the operator's notes record retired systems that passed every check
of their own and never changed a real decision. That is why every row has an undo condition, and
why [adding a rule](scorecard-and-test-set.md#adding-a-rule-a-field-or-a-gate) now requires one.
