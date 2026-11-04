<!--
Loop PR body template. Explained in docs/pr-description-template.md.
Replace every <...>. Delete optional sections that are empty.
Before publishing: no "VERDICT:" string anywhere, no local paths, no tokens,
no account identifiers, no secret-shaped test values, synthetic examples only,
every SHA and count matches the receipts at the current head.
Leave the CI line as "CI at `<12-char head>`: pending". After every check passes on
the pushed head, the publisher changes that line to "all checks passed (link)". The
base is a fresh upstream/main and the AC number is the next one free on main.
-->

<!-- Round sections go here, newest first, for repair rounds only:
## Round <N>
- <maintainer comment, short> → <what changed>; pinned by `<test name>` (<file>)
- Gates at `<new head>`: <one line>.
- CI at `<new head 12 chars>`: pending
-->

## Summary

<What the user saw, in one or two sentences.> <Why it happened.> <What this
change does.> Restores <US-xx ACyy>.

Prepared by an automated bug-fix loop that Austin runs. One fix per PR.

## Testing

- **Failing test first:** `<test name>` in `<file>` failed on unchanged code at
  `<base sha>`: <assertion it failed on, in words>.
- **Passes after the fix** at `<head sha>`.
- **Controls kept passing:** <neighbouring behaviours>.
- **Gates:** tsc <clean / no new errors> (<n> configs); incremental review: <no
  new Medium+>; CRAP <function base→head, new function score>; <k>/<n>
  changed-line mutants killed<; equivalent: <line, reason>>.
- **Targeted tests** at `<head sha>`: <files> files (the PR's tests, importers of each
  changed file, files that name a changed file, user-stories tests): <passed> passed,
  <skipped> skipped, <failed> failed.
- **CI** at `<head sha, 12 chars>`: pending
- **Known limits:** <each residual from adversary.md, in the same words as the AC; or
  "none found by the adversarial pass">.
- **Live check:** <evidence level and one line, or "not run: reason">.
- **Not tested:** <surfaces the evidence does not reach>.

## Risk

**<low | medium | high>**: <what the change touches that sets this level>.

## How to revert

`git revert <merge commit>`. <What reverting brings back.> <Any migration,
stored-format or config change that makes a revert not enough; any dependent
PR. Or "No data or config change; a plain revert is complete.">

## Needs your decision

<Optional. A choice the fix did not make, with options.>

## Further testing needed

<Optional. Suspected findings not confirmed; touched dimensions that got worse
and the concrete cost.>
