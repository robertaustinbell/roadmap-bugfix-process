# Publish driver

Sanitized from a working implementation; review before running. `driver.py` needs Python 3, `git`, an authenticated `gh`, `node` (for [`secret_check.mjs`](secret_check.mjs), and for the optional local suite with the repo's dependencies installed in each fix worktree), and `gitleaks`. Its tests are in [`tests/`](../../tests/).

What it does and why: [docs/publishing.md](../../docs/publishing.md).

**It never merges.** It refuses to post any title, body or comment containing `VERDICT:`, because the maintainer's auto-ship workflow reads that token in bot comments as an approval. Our bot comments never count as approval.

## Commands

```sh
# the loop (normally launched and kept running by scripts/ocr/mech.py)
python3 -I scripts/publish/driver.py run --round-dir /path/to/round --fixes-dir /path/to/fixes

# one folder by hand: dry run, then for real
python3 -I scripts/publish/driver.py publish /path/to/fixes/ocr05-some-fix
python3 -I scripts/publish/driver.py publish /path/to/fixes/ocr05-some-fix --go

# a repair to an existing PR (folder named pr<N>)
python3 -I scripts/publish/driver.py repair /path/to/round/pr812 [--go]

# the CI gate on the head the driver pushed for a folder (the loop runs this after every push)
python3 -I scripts/publish/driver.py ci /path/to/fixes/ocr05-some-fix [--wait-min 20]

# restart rule: have all last round's PRs had a maintainer action?
python3 scripts/publish/driver.py addressed /path/to/fixes/published.jsonl /path/to/round/pushed.jsonl
```

Stop the loop: `touch /path/to/round/stop-driver`. It finishes the current item first.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `GH_FORK_OWNER` | none (required to publish) | account whose fork holds the branches; also "our own account" for `addressed` |
| `UPSTREAM_REPO` | `DrBradStanfield/roadmap` | where PRs go |
| `UPSTREAM_REMOTE` / `PUSH_REMOTE` | `upstream` / `origin` | git remotes in each worktree |
| `ATTRIBUTION` | empty | text every body and repair comment must contain (your sign-off line) |
| `WORKDIR` | none (required to push) | the roadmap clone; the secret-fixture check reads `tools/secret-rules.mjs` from its `upstream/main` |
| `STATE_DIR` | next to the ledger | where `report-outbox.txt` gets its "PR #N ready, head <sha>" lines |
| `CI_WAIT_MIN` / `CI_POLL_SEC` | 20 / 60 | how long the CI gate waits, and how often it polls |
| `LOCAL_SUITE` | `off` | `shared`: run the local full suite only when the change touches `SHARED_SUITE_PATHS` |
| `SHARED_SUITE_PATHS` | health-core merge, sync, record-session; widget-src storage | comma-separated globs for `LOCAL_SUITE=shared` |
| `NODE_BIN_DIR` | empty | put first on PATH, so node runs CI's Node version |
| `EXTRA_PATH` | empty | more PATH entries (for example an OpenSSL 3 bin folder; some tests need OpenSSL 3 and macOS ships LibreSSL) |
| `KNOWN_FLAKY` | four timing-sensitive test files | comma-separated; failures here need passing solo reruns, not a refusal |
| `DRIVER_MAX_LOAD` | 4 x CPU count | wait while the 1-minute load average is above this |
| `SUITE_TIMEOUT_MIN` / `SUITE_MAX_WORKERS` | 45 / 4 | local suite limits (`LOCAL_SUITE=shared` only) |
| `GITLEAKS_BIN` | `gitleaks` | secret scan; missing means refuse |
| `KEEP_AWAKE` | `caffeinate -ims` if present | prefix for the suite |
| `MAINTAINER_LOGINS` | empty (any non-bot, non-owner account) | whose actions count for `addressed` |
| `ALLOW_FORCE_WITH_LEASE` | unset | `1` lets `repair` replace an amended commit; default is fast-forward only |

## Folder contract

New PR folder: `STATE.json`, `review-<k>.json` (an approval per `templates/review-verdict.schema.json`: full `head`, all five required checks `yes`, and `text_sha256` of `pr-title.txt` and `pr-body.md`), `pr-title.txt`, `pr-body.md`; optional `WAIT-FOR`, `HOLD.md`, `NOT-REPRODUCED.md`. The driver adds `push-dry.log`, `push-go.log`, `PUSH-REFUSED.md` on refusal, and after the push `CI-PENDING`, `CI-GREEN` or `CI-RED.md` (first line: the head) and `ci.log`; with the optional local suite also `suite.json`, `suite-head.txt`, `suite.log` and `rerun-*.log`. Ledgers: `published.jsonl` and `ci.jsonl` in the fixes folder.

Repair folder `pr<N>/`: the same plus `meta.json` (`head_at_start`, `addressed_comment_at`), `comment.md`, optional `body.md` and `title.txt`; the review's `text_sha256` covers each of those that exists. Ledgers: `pushed.jsonl` and `ci.jsonl` in the round folder.

Ledger records carry `status`: `attempted` (written before the first GitHub call), then `observed_succeeded` or `observed_failed`. Records from before this field existed are read by their `verified` flag.

## Tests

`python3 -m unittest discover -s tests` and `python3 scripts/mutation_check.py` from the repo root. Both are standard library only and use a fake `gh`; they never touch GitHub.

## Changes from the working version

- The new-PR publisher and the repair pusher were separate scripts; they are now the `publish` and `repair` subcommands, with the same checks.
- Hardcoded paths, the fork account and the sign-off check are configuration.
- A missing gitleaks now refuses with a clear message instead of crashing.
- Added: the `VERDICT:` refusal, a lock and pid file per round folder, and the `addressed` check.
- Added later: a strict approval check, text digests, untracked-file and dropped-commit refusals, PR body section checks, attempted-before-write ledger records with adoption on rerun, a secret-free suite environment, and tests with a gate-removal check.
- `repair` defaults to fast-forward pushes. The working version used `--force-with-lease` on amended commits; the later rule for repairs is "fast-forward, never force push". Decide which you want before using `ALLOW_FORCE_WITH_LEASE`.
- 2026-11-04: the local full suite is no longer a gate (optional with `LOCAL_SUITE=shared`); added the CI gate on the pushed head with a report outbox, the in-review guard for repairs, and the secret-fixture check with the roadmap repo's own rules.
- A dependency check that made a body wait for another PR's repair push (`WAIT-FOR-PUSH`) was dropped as rarely used. Hold such a folder with `HOLD.md` instead.
