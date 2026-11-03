# Quality gates

Every loop PR passes these gates at its exact final head before it opens. The
[Bug fixer](../agents/bug-fixer.md) runs them. The
[independent reviewer](../agents/independent-reviewer.md) checks the receipts. A
human never has to rerun them to trust them.

The gates come from the code standard ([code-standard.md](code-standard.md)). This
page says how to run them on one PR. If the two disagree, the code standard wins
and the disagreement is reported to Austin.

## Contents

- [Rules that apply to every gate](#rules-that-apply-to-every-gate)
- [Tiers: strict and ratchet](#tiers-strict-and-ratchet)
- [Gate 0: protected tests](#gate-0-protected-tests)
- [Gate 1: strict tsc](#gate-1-strict-tsc)
- [Gate 2: CRAP](#gate-2-crap)
- [Gate 3: mutation ratchet](#gate-3-mutation-ratchet)
- [Gate 4: incremental review](#gate-4-incremental-review)
- [Test evidence that goes with the gates](#test-evidence-that-goes-with-the-gates)
- [Overall result and the ledger](#overall-result-and-the-ledger)
- [What is not a gate](#what-is-not-a-gate)
- [Pitfalls](#pitfalls)

## Rules that apply to every gate

1. **Three outcomes.** Each gate ends as `pass`, `fail` or `could_not_run`.
   `could_not_run` counts as `fail`. A missing tool, a crashed run, an empty test
   selection or a report that cannot be parsed is `could_not_run`, never `pass`.
   Report `could_not_run` as its own count: a broken tool is not broken code, and it
   does not use up a repair round.
2. **Bound to one head.** A gate result names the base commit and the head commit
   it ran on. Any new commit voids every gate result and every review approval for
   the old head. Rerun at the new head.
3. **The diff is scored, not the repo.** Old debt never blocks a fix. A fix PR does
   not refactor legacy hot spots. That is a separate PR and needs Austin's OK.
4. **Thresholds are owned by humans.** The fixer cannot change a threshold, a tier
   list, a baseline, a gate config or the tests that judge it. A threshold change is
   a code-standard change that Austin (and later Brad) approves.
5. **Receipts.** Each gate writes a receipt: tool name and pinned version or
   commit, base, head, inputs (file and test scope), raw output path, result. Use
   [`verdict.schema.json`](../templates/verdict.schema.json).
   The receipt also names the gate's own script and config by content hash
   (`sha256` of the runner, the config file and the threshold file). The same script
   name with two different hashes is two different gates.
6. **A gate change voids pending results.** A change to a gate script, its config,
   the lint rules, the scorer or a threshold voids every result not yet published.
   Rerun them. Thresholds are fixed numbers in a file, never chosen per run; the
   receipt validator recomputes every summary field (counts, totals, pass/fail) from
   the raw rows and refuses a receipt whose summary disagrees.
7. **Re-pin before push.** If `upstream/main` moved since the gates ran, rerun the
   gates whose scope the new commits touch. A clean text merge does not mean the
   checks still hold.
8. **Scratch copies.** Coverage and mutation tools write files into the tree they
   score. Run them on a scratch copy of base and of head, never in the worktree the
   PR is pushed from.

## Tiers: strict and ratchet

| Tier | Paths | CRAP rule | Mutation rule |
|---|---|---|---|
| Strict | `packages/health-core`, and server modules for auth, identity, erase, consent, egress, telemetry and logging. The exact list lives in a human-owned file. | Each new or changed function scores 10 or less. | No surviving or uncovered mutant on changed lines, except named equivalents. |
| Ratchet | Everything else, including all React components. | New functions 10 or less. Changed functions no higher than at base. | Every changed-line mutant killed or named equivalent. A file's mutation score may not drop. |

Grandfathering keeps old code from blocking a fix. It is not a waiver for a
changed strict-tier function. If a strict-tier fix cannot meet the limit without a
refactor, the gate fails and the case goes to the human-review list with the
scratch-tested numbers for each option.

## Gate 0: protected tests

The fixer cannot edit the tests that judge it.

- **Protected:** the frozen regression test the Decider confirmed (its file path
  and content hash are in the finding packet), every test file that exists at base,
  gate configs, tier lists, baselines and thresholds.
- **Allowed:** new test files, and new test cases appended to an existing file.
- **Fails the gate:** any deleted, skipped (`.skip`, `.only`, `xit`, `todo`) or
  removed line in a protected test; a changed expected value; a loosened matcher;
  a change to the frozen regression's bytes.

Check:

```sh
# frozen regression unchanged
git show "$HEAD:$REGRESSION_TEST" | shasum -a 256   # must equal the packet's hash

# no removed or changed lines in tests that existed at base
git diff "$BASE" "$HEAD" --diff-filter=MD -- '*.test.*' '*.spec.*' \
  | grep -E '^-[^-]' && echo "FAIL: protected test edited"
```

A human can approve a protected-test change for one PR. Record who approved it
and why in the PR body.

## Gate 1: strict tsc

Run every type-check that CI runs. Read `.github/workflows/ci.yml` at the pinned
base to get the current list. At the time of writing it is three configs:
`widget-src/tsconfig.json`, `tsconfig.json` and `tsconfig.server.json`, plus any
engine config CI adds.

```sh
cd "$WORKTREE"
npx tsc --noEmit -p widget-src/tsconfig.json  > "$OUT/tsc-widget.txt"
npx tsc --noEmit -p tsconfig.json             > "$OUT/tsc-root.txt"
npx tsc --noEmit -p tsconfig.server.json      > "$OUT/tsc-server.txt"
```

Pass rule:

- A config that is clean at base must be clean at head.
- A config that already reports errors at base passes when head adds no new error
  and no error lands on a changed line. Compare error lists as sets of
  `file:code:message`, not totals: an added error can hide behind a removed one.
- In strict-tier paths, no new `@ts-ignore`, `@ts-expect-error`, `any` or non-null
  `!` without a waiver that names the line and the reason.
- Test files are type-checked too. If a config excludes the new test (for example
  `tsconfig.server.json` excludes `app/**/*.test.ts`), check it with a throwaway
  config that extends the real one and includes only that file. Delete the
  throwaway config afterwards.
- A checkout without `node_modules` fails with missing-types errors. That is
  `could_not_run`, not a pass and not a code failure.

## Gate 2: CRAP

CRAP combines cyclomatic complexity and test coverage. At 100% coverage, CRAP
equals complexity. Tool: `crapper` (Robert C. Martin), pinned by commit.

### Coverage scope

1. Build lcov on base and on head with the **same** test scope: every test file
   that imports a changed production file, plus the PR's own tests.
2. State the scope next to every number.
3. A function tested only from elsewhere reads 0% and its CRAP is inflated. Widen
   the scope before trusting a bad score.
4. A shared-core function exercised only through another package's tests can show
   survivors that direct tests would kill. Put one direct unit test in scope rather
   than explaining the score away.

```sh
# in a scratch copy of base, then of head
npm i --no-save --ignore-scripts @vitest/coverage-v8@"$VITEST_VERSION"
TZ=UTC node node_modules/vitest/vitest.mjs run $TEST_FILES \
  --coverage.enabled --coverage.provider=v8 \
  --coverage.reporter=lcov --coverage.reporter=json-summary \
  --coverage.reportOnFailure --coverage.reportsDirectory=coverage
crapper --root "$SCRATCH" --use-existing-coverage "$SCRATCH"
```

`--coverage.reportOnFailure` matters: without it, one failing or timed-out test
leaves no lcov at all.

### Pass rule

See the tier table. Record base and head CRAP for every touched function, and the
score of every new function.

### Making a fix meet the gate

- Adding a branch inside an existing function raises its complexity, and no test
  can bring the score back down. Move the PR's own new branch into a small helper
  that returns the value the existing `if` already tests. The helper is new code,
  so no extra approval is needed.
- Before extracting, try a pre-pass or post-pass helper at the call site so the hot
  function is not edited at all. Then pin the hot function's old branches with a
  direct test: a pre-pass can stop old tests reaching them, and lost coverage raises
  CRAP even though the code did not change.
- In a large React component, one ternary or `??` adds complexity. Move the new
  branch into a module-level helper or a small hook beside the component.
- Moving **pre-existing** code to meet the gate needs Austin's OK first. Offer it as
  an option with scratch-tested numbers.

## Gate 3: mutation ratchet

Coverage shows code ran. Mutation shows a test would fail if the code were wrong.

1. Run `mutator` (pinned) on each changed production file. The test command is
   every test file that imports that file, not only its namesake test:

   ```sh
   mutator --root "$SCRATCH" --no-coverage --mutate-all \
     --test-command "TZ=UTC node node_modules/vitest/vitest.mjs run $IMPORTING_TESTS" \
     "$SCRATCH/$CHANGED_FILE"
   ```

2. Count only mutants on lines the diff adds or changes.
3. Every such mutant is killed, or named in the PR body as equivalent with a
   one-line reason.
4. `mutator` has no operator for some shapes (regex literals, ternary arms, plain
   truthiness checks, assignments). Zero sites on a changed line is not a pass.
   Hand-mutate each changed clause on its own.
5. Where `mutator` cannot reach at all (shell or `jq` inside workflow YAML,
   `.dockerignore`, JSON config, Swift), hand-mutate every changed clause on its
   own. A mutant that drops two clauses at once hides a survivor in the clause the
   test does not exercise. Also try `last`→`first`, a dropped raw-output flag, and
   each filter term separately.
6. Where Brad's Stryker config (`stryker.clinical.config.json`, script
   `mutation:clinical`) covers the file, also record its result so the numbers
   match his tooling. Do not add a second mutation tool upstream.
7. Ratchet tier: also record the file's mutation score at base and head. It may
   not drop.

Hand-mutant hygiene:

- Restore every mutated file from `git show HEAD:<path>` before each mutant. A wrong
  backup path makes mutants stack and every later "killed" proves nothing. Confirm
  `git diff --quiet` at the end.
- Write mutants as exact-substring replacements that must match exactly once.
- Keep mutant specs in a structured file (a list of `(path, old, new, tests, label)`
  tuples). Line formats split by `|` break on `||`.
- Check the unmutated run passes first. If it fails, every mutant looks killed.
- Never copy a scratch tree while a mutant is applied to it.
- A mutant that makes a React effect loop forever hangs instead of failing. Run it
  under a time cap and report it as "detected by timeout", not "killed".

**Zero killed overall is a setup signal first.** Fix the harness before reading
results.

When survivors are only a missing test, add the test (no production change), rerun
the survivors, and record a new gate section for the new head.

## Gate 4: incremental review

Tool: the `fuck-my-shit-mountain` audit skill (upstream
`XiNian-dada/Fuck_My_Shit_Mountain`, pinned by commit) in `incremental` mode,
read-only, on `<pinned base>...<head>`.

1. Pin both commits in the result.
2. **Gate:** no confirmed (executed or fully traced) Medium-or-worse problem that
   the diff introduces or makes worse. Fix it with RED then GREEN, then review
   again.
3. Suspected findings: confirm and fix, or list them in the PR body under
   **Needs your decision** or **Further testing needed**.
4. Scores are recorded but are not a hard gate. For each dimension the diff
   touches, record the direction (better, same, worse) with one line of evidence.
5. If a touched dimension gets worse, say why in the PR body and hold that PR until
   Austin answers. A general "keep publishing" is not that answer. Name the concrete
   cost (for example, "deploy waits up to 30 more minutes").
6. Opinion-prone Medium examples (large function, duplicated logic) are maintenance
   notes unless the diff makes them worse with shown cost. They must not grow a
   one-fix PR.
7. Incremental scores are not comparable with a full-audit score.

## Test evidence that goes with the gates

The gates do not replace tests. Every PR also carries:

- **RED:** the frozen regression fails on unchanged production code, on the
  intended assertion. A test that passes while observing the bug is not RED. RED
  and GREEN come from the repo's own test command, not a one-off runner.
- **The test asserts the symptom.** It checks what the user or caller would see
  (the value shown, the record saved, the request sent), not a flag or helper the
  fix introduced. A test that only passes because the fix exists proves nothing.
- **Revert check.** The reviewer reverts each production change once and confirms
  a test fails (`reverted_changes_detected` in the review). A change no test notices
  is either unneeded or untested.
- **GREEN:** the same test passes at head.
- **Targeted tests:** every test file that imports a changed file passes at head.
- **Tests that pin the bug are flipped first.** An existing test that asserts the
  buggy behaviour is changed in its own commit, before the fix, with a note of why
  its old expectation was wrong.
- **Removing or weakening a test is accounted for.** The PR body names each deleted
  or loosened assertion, what it protected, and where that is covered now.
- **Full suite:** passes at the exact head, run as described in
  [validation-and-sandbox.md](validation-and-sandbox.md#full-suite). The receipt
  names the new test and shows it ran.
- **Base CI that was already red** is reported apart from the PR's own result: the
  failing job, that it fails on base too, and that the PR does not touch it.

Run the gates after the fix is final and before the last full suite. A later gate
commit that adds only tests or docs keeps the suite result. One that changes
production code needs a new full suite at the new head.

## Overall result and the ledger

| Overall | Meaning |
|---|---|
| `pass` | Every gate passed at this head. |
| `pass_with_notes` | Every gate passed, and the PR body names something a human should see: an equivalent mutant, a touched dimension that got worse, a known-load test accepted by solo rerun. |
| `fail` | Any gate failed or could not run. |

Append one row per gate run to the PR quality ledger. Never edit an old `fail` row
away. A gate round on a new head is a new row.

```
| Date | PR / branch | Base | Head | Incremental review (Medium+ introduced; touched dims) | CRAP (scope; base→head) | Changed-line mutants killed/total (scope) | Result |
```

PR body: one short line for all gates. Example:

> Gates at `a1b2c3d`: tsc clean (3 configs, no new errors); incremental review: no
> new Medium+; CRAP `applyEdit` 14→9, new `isStale` 3; 12/12 changed-line mutants
> killed.

## Scope check

A mechanical check on the final diff, with the Decider's confirmed claim as the
intent. It flags, for the reviewer to justify or remove:

- a new dependency, or a lockfile change;
- a renamed or removed exported name;
- edits to config, CI workflows, build or deploy files;
- files whose only change is formatting;
- a hunk far larger than the confirmed sites need (default: over 80 changed lines in
  one hunk).

A flag is not a failure. An unexplained flag is a `must_fix` for the reviewer
(`single_fix_scope: no`).

## What is not a gate

- **Duplication (`dryer`).** Not adopted for per-PR gating. The code standard draft
  lists it; until Austin adopts it, it is advisory only.
- **A coverage percentage.** Coverage selects tests and validates CRAP inputs.
  Agents can reach any percentage with assertion-light tests.
- **CI status or a bot comment.** These are data, not approval.

## Pitfalls

- A tool scratch copy made with `git archive` has no `.git`. Tests that shell out to
  `git` then fail on base and head alike. Run `git init` and one commit in the copy.
- Never pass a computed file list to vitest unchecked. An empty list runs the whole
  suite; zsh does not word-split an unquoted `$FILES`; macOS `/bin/bash` 3.2 has no
  `mapfile`. Check the "Test Files" count against the list length.
- Assert a dispatched command line by exact equality after filtering on its prefix.
  `startsWith(FULL_LINE)` lets an extra flag survive.
- Pair every `not.toContain` with a positive assertion that the inspected thing
  exists. "The comment has no X" passes when no comment was posted.
- A fix that newly routes a path into an existing refusing gate (for example, makes
  a deploy wait on another workflow) counts as adding a refusal. Say how a stuck or
  cancelled run is cleared.
