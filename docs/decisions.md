# Decisions

Changes to the process itself: what changed, why, and what result would undo it. Newest first.
Each entry names the decision it feeds and its removal condition, per
[adding a rule, a field or a gate](scorecard-and-test-set.md#adding-a-rule-a-field-or-a-gate).
Rules live in their own pages; this page records why they are there.

## 2026-11-03: the loop as an agent skill

| Change | Why | Feeds | Undo when |
|---|---|---|---|
| `skills/roadmap-bugfix-loop/SKILL.md`: a thin launcher in the Agent Skills format that gets the kit, records its commit as a config change, checks for another running copy, starts the Coordinator watched, and repeats the hard nevers; it copies no rules | One reliable way to start, in Claude Code and Hermes Agent, and installable by Brad's agent | How every run starts | The skill and the kit disagree twice: shrink the skill further |
| `check_kit.py` validates every skill against both formats | A skill that only one runtime can load, or that links out of its folder, breaks when installed on its own | CI | Never removed |

## 2026-11-03: open questions settled by Austin

Numbers are the ones in [open-questions.md](open-questions.md).

| # | Question | Settled answer | Where it lives |
|---|---|---|---|
| 1 | Does a maintainer review count as "addressed"? | Yes. Any maintainer action counts; CI and bots never do. | [process.md](process.md) |
| 2 | Do reviews by Brad's own agent start a repair? | Yes, when Brad asked for them. Its merges and closes always count. Brad may revise this. | [coordination-with-brads-agent.md](coordination-with-brads-agent.md) |
| 4 | CRAP on changed functions | 10 or less everywhere. A function already over 10 at base may stay no worse; it is flagged in `cleanup.md` for a later cleanup PR the owner asks for. Chosen after old fix logs showed at least 6 of 43 fixes touched functions over 10 (one scores about 27,000). | [quality-gates.md](quality-gates.md#tiers-strict-and-ratchet) |
| 5 | Repair cap | One pre-PR repair, then up to 3 maintainer-requested repairs; the operator may set 2. | [human-review-and-escalation.md](human-review-and-escalation.md) |
| 9 | Whole-file mutation ratchet as well as changed-line mutants | Both apply. | [quality-gates.md](quality-gates.md) |
| 12 | Who approves sending a private security report | Nobody: reports go to Brad's agent through the private channel he named, with a one-line notice to the operator. | [human-review-and-escalation.md](human-review-and-escalation.md#security-findings) |

Undo for 4: cleanup items pile up unrequested for 10 rounds; then stop flagging and keep only "no worse".
Undo for 12: a report reaches anyone other than Brad's side, or Brad asks for a different route.

## 2026-11-04: the owner starts the loop and agrees what it works on

Austin's rules: the Coordinator talks with the user (Austin; Brad through Austin) about what
to scan; an automated mode that runs on its own after that talk "but does not start without
the user or the users agent starting the process"; a manual mode that does one pass agreed
with the user, such as only the iPhone app code or only security issues; and "when the user
asks the coordinator delegates". Separately: "the coach should observe everything".

| Change | Why | Feeds | Undo when |
|---|---|---|---|
| [`scripts/coordinator/session.py`](../scripts/coordinator/session.py): a session (mode, scope, the owner's words) is required to open a round; only owners start, stop or request; a manual pass ends when it closes; a stopped session still follows up on open PRs | Nothing stopped a schedule or a stray message from starting rounds, and the owner had no way to aim the loop | Which rounds run and what they cover | Never removed; a loop that starts itself is the failure this prevents |
| The Coordinator's start talk, requests and plan notices, logged in `owner-talk.jsonl` | The most important code is what the owner says it is; the scores are a fallback | The round plan | Owner requests are never taken in 5 rounds: drop the per-round plan notice, keep the start talk |
| The Coordinator is registered with the Coach watch before its first step; owner talk counts as activity | The Coach missed the start gate, the planning and the owner talk | What the Coach can see | Never removed |
| Out-of-scope findings in a manual pass are parked, not dropped | A narrow pass must not lose real bugs it happens to see | The parked list | Never removed |

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
