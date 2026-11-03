# Publish driver

Sanitized from a working implementation; review before running. `driver.py` needs Python 3, `git`, an authenticated `gh`, `node` with the repo's dependencies installed in each fix worktree, and `gitleaks`. It passes `python3 -m py_compile`.

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
| `NODE_BIN_DIR` | empty | put first on PATH, so the suite runs on CI's Node version |
| `EXTRA_PATH` | empty | more PATH entries (for example an OpenSSL 3 bin folder; some tests need OpenSSL 3 and macOS ships LibreSSL) |
| `KNOWN_FLAKY` | four timing-sensitive test files | comma-separated; failures here need passing solo reruns, not a refusal |
| `DRIVER_MAX_LOAD` | 4 x CPU count | wait while the 1-minute load average is above this |
| `SUITE_TIMEOUT_MIN` / `SUITE_MAX_WORKERS` | 45 / 4 | suite limits |
| `GITLEAKS_BIN` | `gitleaks` | secret scan; missing means refuse |
| `KEEP_AWAKE` | `caffeinate -ims` if present | prefix for the suite |
| `MAINTAINER_LOGINS` | empty (any non-bot, non-owner account) | whose actions count for `addressed` |
| `ALLOW_FORCE_WITH_LEASE` | unset | `1` lets `repair` replace an amended commit; default is fast-forward only |

## Folder contract

New PR folder: `STATE.json`, `review-<k>.json` (verdict `approve`, `head` = the SHA; see `templates/review-verdict.schema.json`), `pr-title.txt`, `pr-body.md`; optional `WAIT-FOR`, `HOLD.md`, `NOT-REPRODUCED.md`. The driver adds `suite.json`, `suite-head.txt`, `suite.log`, `rerun-*.log`, `push-dry.log`, `push-go.log`, and `PUSH-REFUSED.md` on refusal. Ledger: `published.jsonl` in the fixes folder.

Repair folder `pr<N>/`: the same plus `meta.json` (`head_at_start`, `addressed_comment_at`), `comment.md`, optional `body.md` and `title.txt`. Ledger: `pushed.jsonl` in the round folder.

## Changes from the working version

- The new-PR publisher and the repair pusher were separate scripts; they are now the `publish` and `repair` subcommands, with the same checks.
- Hardcoded paths, the fork account and the sign-off check are configuration.
- A missing gitleaks now refuses with a clear message instead of crashing.
- Added: the `VERDICT:` refusal, a lock and pid file per round folder, and the `addressed` check.
- `repair` defaults to fast-forward pushes. The working version used `--force-with-lease` on amended commits; the later rule for repairs is "fast-forward, never force push". Decide which you want before using `ALLOW_FORCE_WITH_LEASE`.
- A dependency check that made a body wait for another PR's repair push (`WAIT-FOR-PUSH`) was dropped as rarely used. Hold such a folder with `HOLD.md` instead.
