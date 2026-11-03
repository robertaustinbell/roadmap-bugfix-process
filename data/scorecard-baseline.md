# Scorecard baseline

Snapshot taken 2026-11-02 from public GitHub data for PRs by `robertaustinbell` on
[DrBradStanfield/roadmap](https://github.com/DrBradStanfield/roadmap). Raw rows are in
[`pr-outcomes.csv`](pr-outcomes.csv). Regenerate with [`scripts/data/pr_outcomes.py`](../scripts/data/pr_outcomes.py).

The Coach reads this. See [docs/scorecard-and-test-set.md](../docs/scorecard-and-test-set.md) for what each measure means.

## PRs by finder

| Finder | Merged | Closed | Open | Open but already addressed | Median days to merge/close |
|---|---:|---:|---:|---:|---:|
| Open Code Review | 31 | 4 | 38 | 0 | 1.1 |
| tech-debt-audit | 38 | 2 | 2 | 2 | 0.2 |
| fuck-my-shit-mountain (FMSM) | 17 | 1 | 2 | 2 | 0.6 |
| Trail of Bits | not tracked separately (its fixes landed in earlier rounds) | | | | |
| Before the loop / unattributed | 50 | 11 | 1 | 1 | 1.0 |

Notes:

- "Addressed" means any maintainer action: merge, close, or a comment asking for a change. CI and bot activity do not count.
- Open Code Review PRs are the newest, so many have not been looked at yet. Its merge rate is not comparable to the older finders yet.
- The "held 30 days without a revert or fix-forward" guardrail can only be measured from early December 2026 for most loop PRs.

## Every closed loop PR and why

None of these were closed because the bug was fake. They teach the Decider two lessons.

| PR | Finder | Maintainer reason (public comment, shortened) | Lesson |
|---|---|---|---|
| [#510](https://github.com/DrBradStanfield/roadmap/pull/510) | Open Code Review | Bot should not answer crisis replies under its own comments, they can be used to game it. | Product decision. Ask first. |
| [#484](https://github.com/DrBradStanfield/roadmap/pull/484) | Open Code Review | Superseded by #647, which follows Brad's ruling on how to map the user's words. Thanks for finding the bug. | Real bug, Brad chose the design. Ask first. |
| [#469](https://github.com/DrBradStanfield/roadmap/pull/469) | Open Code Review | Brad's rule is that unreadable rows stay in the file. | Product decision. Ask first. |
| [#422](https://github.com/DrBradStanfield/roadmap/pull/422) | Open Code Review | Main already fixed the flake; PR conflicted. | Recheck against current main right before publishing. |
| [#348](https://github.com/DrBradStanfield/roadmap/pull/348) | tech-debt-audit | (closed without comment) Release host is Brad's decision. | Product decision. Ask first. |
| [#346](https://github.com/DrBradStanfield/roadmap/pull/346) | tech-debt-audit | (closed without comment) | Docs-only pointer change; low value. |
| [#324](https://github.com/DrBradStanfield/roadmap/pull/324) | FMSM | Process changed the same day (every change ships through its own branch and PR). | Policy change. Human review list. |

**Decider rule derived from this:** if a fix depends on a product or policy decision Brad has not made, send it to him as a question (issue) first, not as a PR.
