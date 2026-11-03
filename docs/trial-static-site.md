# Trial: running the loop on a different repo

In November 2026 the full loop was run once, by hand, against a small static business
website (HTML, CSS, a little JavaScript, Python build and tests, a shell deploy script).
It is not the repo this kit was written for, which made it a good test of what in the kit
is general and what is roadmap-specific. Everything stayed local: no pushes, PRs or
deploys during the trial.

## Funnel

| Stage | Count |
|---|---|
| Finder candidates | 68, plus 5 structural notes |
| Decision records after dedupe | 50 |
| Routed to fix by the Decider | 11 |
| Questions for the owner | 7 (the owner's answers added 9 fixes and 5 clean-ups) |
| Fix branches committed | 22 |
| Branches that conflicted when combined | 3 pairs, all resolved |
| Cross-fix breakage found only by the combined run | 1 |

## Finder precision on this repo

| Finder | Candidates | Real | Worth a fix |
|---|---:|---:|---:|
| Trail of Bits skills | 6 | 100% | 83% |
| fuck-my-shit-mountain | 14 | 93% | 93% |
| tech-debt-audit | 12 | 92% | 75% |
| Open Code Review | 36 | 47% | 36% |

Open Code Review's hit rate matched its rate on the roadmap repo (about half). Its value
is breadth; the Decider's confirm step is what makes it usable.

## What changed in the kit because of it

- [process.md section 3.5](process.md#35-fix): a **round integration check** (merge all of
  the round's branches and run the suite before PRs open) and a **sequencing** rule for
  structural clean-ups.
- [process.md section 7](process.md#7-common-finding-schema): finder output and Decider
  output are now two named schemas,
  [candidate.schema.json](../templates/candidate.schema.json) and
  [finding.schema.json](../templates/finding.schema.json). They used to read as one.
- [process.md section 10](process.md#10-implementation-notes): **expect agents to die
  mid-task**, commit early, resume from worktrees; and write a **repo profile** before
  running the loop on a repo the templates were not written for.
- [Bug fixer](../agents/bug-fixer.md) and [Coordinator](../agents/coordinator.md): commit
  early; a resume step; run the integration check.
- [Open Code Review pipeline](open-code-review-pipeline.md): no dependency on the GNU
  `timeout` command; how to treat a usage-limit stop.

## Smaller lessons

- Owner answers are part of the Decider's calibration. Record them where the next round's
  Decider reads them, so a platform limitation (for example a listing site's fixed category
  URL) is not flagged again.
- A test that found its module by package name (`tests.<module>`) failed when another
  `tests` package was on `PYTHONPATH`. Load tests by path.
- A witness test copied into the repo kept its old relative paths. Check copied tests from
  their new location.
- Automated screenshots are evidence, not truth: full-page captures can show sticky headers
  and off-screen skip links in the wrong place. Confirm odd results with a normal viewport.
