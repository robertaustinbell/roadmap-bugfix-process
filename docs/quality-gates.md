# Quality gates

Every loop PR passes these gates at its exact final head before it opens, and the
CI gate after the push. The [Bug fixer](../agents/bug-fixer.md) runs them, the
[adversary](../agents/adversary.md) tries to break the change, and the
[independent reviewer](../agents/independent-reviewer.md) checks the receipts. A
human never has to rerun them to trust them.

The order, before opening or pushing: confirmed bug (a test that fails on a fresh
`upstream/main` for the stated reason, then passes with the fix); targeted tests;
typechecks; changed-line mutants and CRAP; the incremental review; the secret-fixture
check; the adversarial pass; the independent review. The publisher then checks the
in-review guard, pushes, and waits for CI on the pushed head. The local full suite is
no longer a gate: the maintainer's CI runs the whole suite on every push (about three
minutes), and the PRs he sent back had all passed a local full suite. What he found
were logic gaps and ACs that promised more than the code did, which is what the
adversarial pass is for.

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
- [Secret-shaped fixtures](#secret-shaped-fixtures)
- [Adversarial pass](#adversarial-pass)
- [CI gate (after the push)](#ci-gate-after-the-push)
- [Test evidence that goes with the gates](#test-evidence-that-goes-with-the-gates)
- [Overall result and the ledger](#overall-result-and-the-ledger)
- [Quality tally](#quality-tally)
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
| Strict | `packages/health-core`, and server modules for auth, identity, erase, consent, egress, telemetry and logging. The exact list lives in a human-owned file. | Every new or changed function scores 10 or less. A function already over 10 at base may stay no worse than base; it is then flagged for a later cleanup PR. | No surviving or uncovered mutant on changed lines, except named equivalents. |
| Ratchet | Everything else, including all React components. | Every new or changed function scores 10 or less. A function already over 10 at base may stay no worse than base; it is then flagged for a later cleanup PR. | Every changed-line mutant killed or named equivalent. A file's mutation score may not drop. |

The CRAP rule is the same in both tiers (settled 2026-11-03). A changed function
that scored 10 or less at base must still score 10 or less. A function already over
10 at base may stay over 10 if the fix leaves it no worse; it is never split inside a
bug fix. The Bug fixer marks it `cleanup: true` in `verdict.json` and adds a line to
`$STATE_DIR/cleanup.md` (path, function, base and head scores, PR). The Coordinator
offers cleanup items to the owner; a cleanup PR is its own PR, opened only when the
owner asks for it. A fix that makes such a function worse fails the gate.

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

## Secret-shaped fixtures

No test value may look like a real credential: no `ghp_`, `github_pat_`, `sk-...` or
`"Key..., 'x'"`-style fixtures. Use plain strings such as `test-token-good`. The
maintainer's batch tool refuses a batch whose added lines hold one, so a single
fixture stalls every PR grouped with it.

The publisher checks this before every push, with the roadmap repo's own rules:
`tools/secret-rules.mjs` (its `PATTERNS`) as it is on `upstream/main`, plus the generic
key rule from `tools/merge-batch.mjs`, run on the lines the change adds compared with
`upstream/main` ([`secret_check.mjs`](../scripts/publish/secret_check.mjs)). A hit
refuses and names `file:line` and the rule, never the value. If the rules file is
missing, the publisher refuses rather than skipping the check. The Bug fixer runs the
same check as a gate so the publisher never has to refuse.

## Adversarial pass

A fresh agent with its own context, not the fixer and not the reviewer, reviews the
diff against the roadmap repo's `docs/review-format.md` (the maintainer's review
contract) and tries to break the fix: other tabs, other devices, stalled or partial
network bodies, quoted or odd inputs, older Safari, erase during save, retries.
Template: [adversary.md](../agents/adversary.md). It writes `adversary.md` in the fix
folder, naming the head, with findings in two groups:

- **Blocking**: back to the fixer. Fix with RED then GREEN, rerun the affected gates,
  and run a new adversarial pass at the new head.
- **Residual**: a case the fix does not cover. It stays only if it is written into the
  AC text and the PR body's **Known limits** line, so no AC promises more than the
  code does.

The independent reviewer checks that `adversary.md` exists for the reviewed head and
that every residual appears in the AC and the body. A repair gets an adversarial pass
on its delta too.

## CI gate (after the push)

The publisher waits for every check run on the exact head it pushed (polling, usually
3 to 15 minutes; `CI_WAIT_MIN`, default 20):

| Result | What happens |
|---|---|
| Every run `success`, `skipped` or `neutral` | `CI-GREEN` in the folder, a line in `ci.jsonl`, and "PR #N ready, head `<sha>`" in `$STATE_DIR/report-outbox.txt` for the Coordinator to post |
| Any other result | `CI-RED.md` with the failing job names and a short log excerpt (token-shaped text masked). The PR goes back to a repair fixer; push again only after repair and review |
| Still running at the timeout | `CI-PENDING`, polled again on every driver pass |

Never report a red head. CI is a gate for reporting a head as ready; it is never an
approval. Details: [publishing.md](publishing.md#the-ci-gate).

The optional local full suite (`LOCAL_SUITE=shared`, default off) runs only when the
change touches shared record, sync or storage code (`SHARED_SUITE_PATHS`; by default
health-core merge, sync and record-session files and widget-src storage files).

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
- **Targeted tests:** the PR's own tests, every test file that imports a changed file,
  every test file that **names** a changed file (a plain text search: some tests read a
  file by name and import nothing), and the user-stories tests, all passing at head.
  Count the files before running; an empty list runs the whole suite. `--maxWorkers=1`
  or `2`, `TZ=UTC`, CI's Node version.
- **Typechecks** for every project the change touches (widget-src, health-core,
  server, engine).
- **Tests that pin the bug are flipped first.** An existing test that asserts the
  buggy behaviour is changed in its own commit, before the fix, with a note of why
  its old expectation was wrong.
- **Removing or weakening a test is accounted for.** The PR body names each deleted
  or loosened assertion, what it protected, and where that is covered now.
- **CI on the pushed head:** every check passes
  ([CI gate](#ci-gate-after-the-push)). The local full suite is not part of the
  evidence unless the operator turned it on for shared code
  ([validation-and-sandbox.md](validation-and-sandbox.md#optional-local-full-suite)).
- **Base CI that was already red** is reported apart from the PR's own result: the
  failing job, that it fails on base too, and that the PR does not touch it.

Run the gates after the fix is final. A later commit that adds only tests or docs
needs its targeted tests rerun; one that changes production code needs every gate and
an adversarial pass again at the new head. CI runs again on every push.

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

## Quality tally

The real quality measure is what the maintainer's review finds. After each review
result (merged, or sent back with findings), record one line in the PR quality ledger
with [`scripts/data/quality_ledger.py`](../scripts/data/quality_ledger.py):

```sh
python3 scripts/data/quality_ledger.py record --pr 812 --head <full sha he reviewed> \
  --outcome sent_back --findings 2 --category ac_overpromise --category cross_tab
python3 scripts/data/quality_ledger.py tally
```

Fields: PR, head reviewed, outcome (`merged`, `sent_back`, `closed`), number of
findings, and their categories: `ac_overpromise`, `cross_tab`, `stalled_body`,
`input_parsing`, `secret_fixture`, `ac_number_reuse`, `other`. The file is
`$STATE_DIR/pr-quality.jsonl`. `tally` gives the counts per outcome and category and
the share of reviewed PRs merged with no findings. A category that keeps coming back
names the gate to strengthen.

## What is not a gate

- **Duplication (`dryer`).** Not adopted for per-PR gating. The code standard draft
  lists it; until Austin adopts it, it is advisory only.
- **A coverage percentage.** Coverage selects tests and validates CRAP inputs.
  Agents can reach any percentage with assertion-light tests.
- **A bot comment, or CI status as approval.** CI on the pushed head is a gate for
  reporting the head as ready; it never approves anything, and neither does a bot.

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
