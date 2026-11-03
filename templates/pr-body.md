<!--
Loop PR body template. Explained in docs/pr-description-template.md.
Replace every <...>. Delete optional sections that are empty.
Before publishing: no "VERDICT:" string anywhere, no local paths, no tokens,
no account identifiers, synthetic examples only, every SHA and count matches
the receipts at the current head.
-->

<!-- Round sections go here, newest first, for repair rounds only:
## Round <N>
- <maintainer comment, short> → <what changed>; pinned by `<test name>` (<file>)
- Gates at `<new head>`: <one line>. Full suite at `<new head>`: <passed>/<skipped>/<failed>.
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
- **Full suite** at `<head sha>`: <passed> passed, <skipped> skipped, <failed>
  failed.<If a known load-sensitive file was accepted by solo rerun, name it.>
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
