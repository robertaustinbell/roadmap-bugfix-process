# Publishing

Every finder's fixes reach GitHub through one deterministic publish driver ([`scripts/publish/driver.py`](../scripts/publish/driver.py)). It has no AI in it. It checks approved fixes one at a time, opens or updates PRs, and then waits for CI on the exact head it pushed. It never merges.

This page covers what the driver needs, what it checks, and how to deal with its refusals. The loop rules in [process.md](process.md) decide what may be published at all; the gates a fix must pass before review are in [quality-gates.md](quality-gates.md) and [independent-review.md](independent-review.md).

## Hard rules

- **The loop never merges.** Merging, merge queues, staged rollout and auto-merge are the maintainer's decisions. The driver has no merge command.
- **Our approvals are local files.** A review is a local `review-<k>.json` ([schema](../templates/review-verdict.schema.json)). It is never posted to GitHub. The maintainer's auto-ship workflow treats a bot comment with a `VERDICT: APPROVE <sha>` line as an approval, so a stray `VERDICT:` in a PR body or comment could trigger a merge. The driver refuses any body, title or comment that contains `VERDICT:`, including disguised forms (`VERDICT :`, a full-width colon, a zero-width space inside the word).
- **Our bot comments never count as approval,** and neither do CI results. Only the maintainer approves.
- **Any approval is void after a new commit, or after the text changes.** The driver publishes only when the latest review's `head` equals the folder's current head (all 40 characters) and its `text_sha256` matches the exact bytes of every title, body and comment it will post. Editing `pr-body.md` after review means a new review.
- **The approval itself is checked, not just its verdict word.** Duplicate keys, unknown fields, a short head, a `not_checked` on any of the five required checks, a blocking finding or anything in `still_open` all mean "not approved". `python -O` cannot remove a gate: the driver has no `assert` statements, and a test proves it.
- **Every git and gh call is an argument list,** never a shell string. Post bodies with `--body-file`.

## Inputs

### New PR: a fix folder under `FIXES_DIR`

| File | Written by | Content |
|---|---|---|
| `STATE.json` | fixer (last) | `{"worktree": path, "branch": "fix/ocr...", "head": sha}` |
| `review-<k>.json` | independent reviewer | [review-verdict.schema.json](../templates/review-verdict.schema.json): `verdict`, full `head`, the checks, findings, and `text_sha256` of `pr-title.txt` and `pr-body.md` |
| `pr-title.txt`, `pr-body.md` | fixer | title under 200 characters; body with Testing, Risk, How to revert |
| `WAIT-FOR` | optional | PR numbers that must be MERGED first (open is not enough) |
| Any stop file: `HOLD.md`, `HELD-FOR-HUMAN.md`, `DECISION-NEEDED.md`, `NOT-REPRODUCED.md`, `PARKED.md`, `PUSH-REFUSED.md` | anyone | the driver skips the folder ([list](human-review-and-escalation.md)) |

### Repair to an existing PR: `ROUND_DIR/pr<N>/`

Same `STATE.json` and review rule, plus `meta.json` (`head_at_start`: the PR head when the repair began; `addressed_comment_at`: time of the maintainer comment being answered), `comment.md` (the reply), and optional `body.md` and `title.txt`. A repair is pushed only if the PR is still open, its head on GitHub has not moved, and nobody has commented since the repair started.

Who may start a repair and the round cap are in [repair-rounds.md](repair-rounds.md). By default a repair must be a fast-forward of the pushed head. Set `ALLOW_FORCE_WITH_LEASE=1` only if you deliberately amend instead.

## What the driver does

`driver.py run --round-dir R --fixes-dir F` loops until `R/stop-driver` exists (or `R/_done-round` exists, nothing is left and no CI is pending). For each ready folder, in order:

1. **Merge pre-check.** `git merge-tree` against current `upstream/main`. A conflict refuses at once.
2. **No local full suite by default.** The maintainer's CI runs the whole suite (in shards), typechecks, builds, gitleaks, the dependency audit and the user-stories check on every push, so the local full suite is not a publish gate. With `LOCAL_SUITE=shared` the driver still runs it, serially and load-gated, when the change touches `SHARED_SUITE_PATHS` (shared record, sync and storage code). Then real failures are rerun alone (still failing: `PUSH-REFUSED.md`; passing alone: the suite runs again) and known-flaky files get up to 3 solo reruns.
3. **Dry run, then go.** The same script is called as `publish <folder>` (or `repair`) without and then with `--go`. The checks:
   - worktree at head with nothing uncommitted **or untracked** (a test that passes only because of a local file never pushed did not test the PR);
   - the latest review approves this head and this exact text (above);
   - merges clean with current `main`;
   - **the fix commits are still there**: the branch is ahead of `main` with a non-empty diff. A rebase can silently drop them, and pushing an empty branch closes the PR. If this refuses, restore the previous tip from the reflog;
   - no conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) or tool truncation markers (the ones `ARTIFACT_RE` in the driver lists) in the added lines, title, body or comment;
   - with `LOCAL_SUITE=shared` and shared code touched: the suite passed at head;
   - gitleaks passes (missing gitleaks refuses);
   - **no secret-shaped fixtures**: the [secret-fixture check](#the-secret-fixture-check) finds nothing in the added lines;
   - for a repair, **the in-review guard**: the PR's head is not in the maintainer's batch review ([below](#the-in-review-guard));
   - the body has exactly one filled **Testing**, **Risk** and **How to revert** section outside comments and code blocks, and no unfilled `<placeholder>`;
   - optional `ATTRIBUTION` text present; no `VERDICT:` anywhere.
4. **Record the attempt, publish, read back.** Before the first GitHub write the driver appends `status: attempted` to the ledger (`published.jsonl` for new PRs, `pushed.jsonl` for repairs). Then it pushes, runs `gh pr create` (or push, comment, edit), reads the PR back and compares author, base, head, title and body, and appends `observed_succeeded` or `observed_failed`. Only `observed_succeeded` counts as published; a read-back mismatch exits non-zero.
5. **The CI gate** on the head just pushed ([below](#the-ci-gate)).
6. **A crash between steps is recoverable.** If a run dies after `attempted`, the next run looks for the PR on GitHub (`gh pr list --head`). An open PR at the same head is adopted, not opened twice. Anything else (closed, a different head, two PRs) refuses for a human. An unfinished repair always refuses until a human checks the PR and records the outcome. A crash while waiting for CI leaves `CI-PENDING`, which the next pass polls.

Anything that runs code from the repo under review (the optional suite, the secret-fixture check) gets an environment with no push token, API key or other secret.

One publication per pass, then it scans the folders again from the top.

Run one driver per machine. The driver takes a lock per round folder and writes `driver.pid`; the OCR mechanics job uses that pid to keep one driver running.

## The CI gate

After every push the driver runs `driver.py ci <folder>`, which reads the check runs of the exact pushed head (`gh api repos/<upstream>/commits/<head>/check-runs`) every `CI_POLL_SEC` (60) until all are complete or `CI_WAIT_MIN` (20) passes:

| Result | Files | Next |
|---|---|---|
| Every run `success`, `skipped` or `neutral` | `CI-GREEN` (first line: the head), a `green` line in `ci.jsonl` beside the ledger, and `PR #N ready, head <sha>` appended to `$STATE_DIR/report-outbox.txt` | The Coordinator posts each new outbox line to the maintainer's agent ([coordination](coordination-with-brads-agent.md#brads-batch-process)) |
| Any failure, cancel, timeout or unknown result | `CI-RED.md` (first line: the head) with each failing job's name, link and the end of its log, token-shaped text masked; a `red` line in `ci.jsonl` | The PR goes back to a repair fixer in a `pr<N>/` folder; push again only after repair, an adversarial pass and review. Never reported |
| Still running at the timeout | `CI-PENDING` | Polled once on every driver pass until it turns green or red |

No check runs yet counts as still running, and green checks on any other commit do not count. Run it by hand with `driver.py ci <folder> [--wait-min N]`.

After green, if the PR body has the line ``CI at `<12-char head>`: pending``, the driver changes `pending` to `all checks passed ([checks](<link>))` and reads the body back. That line is the only body text the driver writes itself; a body without it is left alone.

## The secret-fixture check

The maintainer's batch tool (`tools/merge-batch.mjs`) refuses a batch whose added lines hold secret-shaped text (its exit 5), which holds up every PR in the batch. The driver runs the same check before every push: [`secret_check.mjs`](../scripts/publish/secret_check.mjs) loads `PATTERNS` from the roadmap repo's `tools/secret-rules.mjs` as it is on `upstream/main` (read through `WORKDIR`, so a PR cannot loosen the rules that check it), adds the generic key rule from `merge-batch.mjs`, and scans `git diff -U0 upstream/main...<head>`. A hit refuses with `file:line rule`, never the value. A missing rules file or a check that cannot run refuses; it is never skipped.

## The in-review guard

The maintainer reviews loop PRs in batches of at most three, grouped by shared files, and pins each PR's head in the body of an open `claude/batch-*` or `claude/group-*` PR on the roadmap repo. A push to a pinned PR moves its head and voids that review. Before pushing a repair, the driver lists open PRs on the upstream repo and refuses (`PUSH-REFUSED.md`, "in Brad's review") if the PR's current head SHA, in full or as a 7+ character prefix, appears in any of those bodies. Wait for the batch result, then repair on top of it.

## Refusals and how to clear them

The driver writes `PUSH-REFUSED.md` and skips the folder from then on. Read it, then:

- **"in Brad's review".** Do nothing to that PR until the batch is merged or sent back. Then rename the refusal and requeue if the repair is still wanted.
- **"secret-shaped text in the added lines".** Replace the fixture with a plain string (`test-token-good`), commit, and get the change reviewed again. Never allowlist it.
- **"tools/secret-rules.mjs is missing".** Fetch `upstream` in `WORKDIR` and check the file is on `main`. If the maintainer renamed it, update the kit; do not skip the check.
- **"Real failures (fail again when run alone)"** (optional local suite only). One solo run is not proof. If the failing file is not touched by the PR and is identical to `main`, rerun that test alone at the same head many times (for example 25 runs with `-t`). If it passes, it is an intermittent test: rename `PUSH-REFUSED.md` to `PUSH-REFUSED-<n>-<reason>.md`, delete `suite-head.txt`, note the test and the evidence, and requeue every folder the same flake refused. If it fails, fix the test's fixture rather than requeueing.
- **"CONFLICT with current upstream/main".** First check the PR or branch on GitHub: the maintainer often merges a PR himself (resolving the conflict) or closes it in favour of his own branch. MERGED or CLOSED gets `HOLD.md` and nothing else. Also check whether the maintainer's side asked that nothing more be pushed to that PR.
- **Requeue needs the driver to start again.** It keeps its per-head try count in memory, so renaming `PUSH-REFUSED.md` alone is refused again at once. Touch `stop-driver`, wait for the process to exit (it finishes the current item), rename the refusal, remove `suite-head.txt` if there is one, remove `stop-driver`, and let the mechanics job (or you) launch it again.

With the optional local suite on, stop the driver only between suites (no vitest child running), and do not run a second suite by hand while the driver runs one.

## A published PR goes red

`CI-RED.md` says which jobs failed. Read the log first: when `main` changes a storage shape, the PR's test reader is often what broke, not the PR's code. Repair it in a `pr<N>/` folder as a fast-forward from the pushed head, with targeted tests, an adversarial pass and a delta review, and let the driver push it and wait for CI again. Check the in-review guard first: never push to a PR whose head is in a batch.

## The restart rule

The next round starts only after every PR from the previous round has been addressed: any maintainer action (merge, close, review, or a comment asking for a fix). CI success or bot activity does not count. The requested repair does not have to land first; it runs alongside the next round.

```
python3 scripts/publish/driver.py addressed FIXES_DIR/published.jsonl ROUND_DIR/pushed.jsonl
```

prints each PR and the first action found, and exits 0 only when all are addressed. It ignores bots and our own account (`GH_FORK_OWNER`). Set `MAINTAINER_LOGINS` to count only the maintainer's accounts. It cannot tell who closed a PR, so check by hand if our own account might have closed one. The Coordinator runs this before `st.py round open`.

## Tests for the driver

```sh
python3 -m unittest discover -s tests      # hostile verdicts, bodies, rebases, crashes, reruns, CI results, batch pins, secret fixtures
python3 scripts/mutation_check.py          # removes each gate in turn; every removal must fail a test
```

A gate that no test notices when it is removed is either untested or ceremony. Run both before changing the driver, and add a mutation for every new gate.

What these tests do not prove: that GitHub behaves like the fake `gh` used in them, that the maintainer's auto-ship workflow matches only the forms checked here, or that a review's `yes` checks are true. They prove the driver refuses the cases listed.

Configuration and examples: [scripts/publish/README.md](../scripts/publish/README.md).
