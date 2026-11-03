# Open Code Review pipeline

Open Code Review (Alibaba's `ocr` CLI, Homebrew formula `open-code-review`) is one of the four finders in the bug-fix loop. This page explains how it scans the repo, how its comments are triaged, and how confirmed findings become PRs, issues or private reports.

Read [process.md](process.md) first for the whole loop and [roles.md](roles.md) for who does what. Where this page and the loop rules disagree, the loop rules win.

## In one paragraph

The repo is split into about 14 parts of 33 to 67 files each. When the Coordinator starts a round, it opens OCR scanning together with the other finders (`st.py round open`). A no-AI mechanics job then scans new parts one after another until the model subscription's usage limit hits. At that point it closes scanning for the round and leaves the stopped part queued; that part resumes from its saved OCR session next round. An agent job triages every comment against the real code, routes each one, prepares fixes, gets each fix reviewed by an agent that did not write it, and hands approved fixes to the [publish driver](publishing.md). The next round starts only after every PR from the previous round has been addressed by the maintainer.

## Why every comment is a hypothesis

OCR overclaims. Across the parts triaged so far, about 47% of comments were not bugs, and roughly 1 comment in 30 became a PR. Most real findings were latent or not worth the maintainer's time. Its own "high" severity label was often wrong (in one part, none of the scanner's "high" labels held up). So nothing OCR says is acted on until triage has read the cited code on current `main` and decided.

The [Decider](../agents/decider.md) confirmation bar applies: a failing test or reproduction at a pinned commit, or a path traced through real callers with evidence. A finding confirmed only by a traced path needs a second independent agent to agree.

## Folder layout

Everything lives outside the repo, in a working folder you choose (`OCR_BASE_DIR`):

```
OCR_BASE_DIR/
  parts/NN-name.txt          one repo path per line; one file per part
  results/NN-name.json       ocr results (comments list)
  results/NN-name.log        scan progress log
  results/NN-name.session    saved ocr session id (resume point)
  results/NN-name.done       written when the part scanned cleanly
  triage-NN/                 per-part triage work (see below)
  pipeline/                  state.json, mech.log, agent.log, NN-REPORT.md, locks
FIXES_DIR/
  ocrNN-<slug>/              one fix folder per confirmed bug
  ocrNN-issues/              issue drafts, REVIEW.md, posted.jsonl
  ocrNN-security/            private report drafts and NOTIFIED records (never published)
  published.jsonl            ledger of opened PRs (written by the publish driver)
```

Scans run in a separate detached git worktree of the repo (`ROADMAP_WORKTREE`), never in anyone's working checkout. Triage reads code with `git show upstream/main:<path>` or a fresh worktree, because a scan base can be 100+ commits behind `main`.

## State and stages

`pipeline/state.json` holds one entry per part. Edit it only with [`scripts/ocr/st.py`](../scripts/ocr/st.py), which takes the same lock as the mechanics tick.

| Stage | Meaning | Who moves it on |
|---|---|---|
| `queued` | waiting to scan (or stopped by the usage limit, will resume) | mechanics, only while `round_open` |
| `scanning` | a scan process is running | mechanics |
| `scan-failed` | scan ended without finishing 3 times, and not because of usage | a human |
| `scanned` | results ready, not yet triaged | agent |
| `reviewing` | triage done; fixes, reviews, issues and reports in progress | agent |
| `held` | a human asked to stop before this part | a human (`st.py stage <part> queued`) |
| `done` | report written | nobody |

Top-level flags:

- `round_open`: set by `st.py round open` (Coordinator), cleared by the mechanics tick when usage runs out, or by `st.py round close`.
- `agent_hold`: scans continue, the agent waits. Use this for "scan ahead, but do not triage yet".
- `paused`: stops the mechanics tick completely, including the publish driver keepalive. Use it only to stop everything.

The agent always works on the first part that is not `done`. Scans pick the first part in `queued`/`scanning`/`scan-failed` in part order, so scanning runs ahead of triage.

## Scanning (mechanics job, no AI)

Each tick of [`scripts/ocr/mech.py`](../scripts/ocr/mech.py), every 15 minutes:

1. Keeps the publish driver running.
2. Sends any notices the agent queued (`st.py notify`).
3. If the active part has been in `scanned` for over 6 hours or `reviewing` for over 18 hours, sends a stall notice (repeated once a day while true).
4. If `round_open` is true, launches or checks the current scan:
   - A fresh part fetches upstream and checks out `upstream/main` detached in the scan worktree, and records that commit as the part's `base`.
   - A part with a saved session resumes it. OCR reuses finished files by content fingerprint, not by model.
   - When a part finishes, the tick launches the next queued part in the same tick, so no time is lost.
   - On the first usage-limit error in the log, the scan is stopped at once (OCR otherwise keeps dispatching and fails every remaining file). The tick sets `round_open` to false, puts the part back to `queued` and sends one notice.
   - Any other early end is retried up to 3 times, then the part goes to `scan-failed` with a notice.

There is no hourly retry, and no job opens a round by itself. Only the Coordinator does that.

### Things that bite

- `ocr scan` does not stop on SIGINT. Stop the whole process group with TERM (the script does this).
- Part lists go stale as `main` changes. The scanner skips listed files that no longer exist and marks a part done if none remain. New files that belong to no part are only found by diffing `ocr scan --preview` against the part lists; do that every few rounds.
- A session with zero finished files cannot be resumed. The script deletes it so the part starts fresh.
- Use `--timeout 0` for whole-part scans. The default run budget silently truncates them.
- Do not wrap scans in the GNU `timeout` command: stock macOS does not ship it, and the
  scan fails before it starts. Bound run time inside the script instead.
- Any model backend works (a subscription sign-in, an API key, or a local bridge). When
  the usage limit is hit, every file in the batch fails with the provider's limit error; treat
  that as "usage ran out", end the finder's turn for the round, and keep the session for a
  later resume.
- Keep OCR's plan, dedup and summary passes on; they are where its depth comes from.

### Model and usage

The working setup signs OCR in with a subscription plan (`ocr auth login`). On the plan first measured, third-party tool use drew on a separate usage pool shared across models; check how yours counts it. On that plan, with a mid-tier model, one part of 40 to 70 files takes roughly 3 to 3.5 million tokens and about 6 minutes, and a weekly pool covered about 4 parts at high reasoning. A top-tier model emptied the pool after about 17 files. Size the first part before assuming a model fits.

OCR can also run on other providers through `custom_providers` in its config (OpenAI-compatible or Anthropic protocol; it needs native tool calling on every turn). Environment variables do not override a config file that already names a provider. To try another provider without touching the live config, give OCR its own `HOME`.

Judge a scan model by triage outcome, never by comment count: per part, the share confirmed or likely, and the share routed to fix, issue or security. A small model that leaves more comments mostly moves the work into triage.

## Triage (agent job)

The agent job follows [agents/ocr-pipeline-agent.md](../agents/ocr-pipeline-agent.md). For a `scanned` part:

1. Give every comment an `id` (1-based) and split them into at most 4 groups of related files, about 60 comments each (up to about 90 for a very large part). Write `triage-NN/<group>-comments.json` with `id, path, start_line, end_line, category, severity, content, existing_code`.
2. One triage worker per group, at most 4 at once. Each worker, for every comment:
   - checks the cited file still exists on current `main` (the maintainer deletes whole surfaces; comments on them are `covered` as outdated);
   - reads the cited code on current `main` and decides `confirmed`, `likely`, `not-a-bug` or `unclear`, with a real severity and a one-line reason;
   - for confirmed and likely items, searches open and closed PRs and issues, earlier fix folders and ledgers, the maintainer's parked list, and earlier private reports, and records any `overlap`;
   - assigns one route (table below);
   - writes `triage-NN/<group>-verdicts.json` every few ids, so a dropped connection loses little. Notes go in `triage-NN/<group>-NOTES.md`.
3. After the workers return, the agent sets the part to `reviewing`. A group whose verdicts file covers fewer ids than its comments file gets its worker sent again, resuming from its notes.

### Routes

| Route | When | What happens |
|---|---|---|
| `fix` | a real user path is affected and a failing test is possible | [Bug fixer](../agents/bug-fixer.md) prepares one PR per finding |
| `issue` | a clinical rule or wording, or a product decision only the maintainer can make | issue draft with options, reviewed, then posted |
| `security-private` | any auth, signature, data-exposure, secret or injection weakness | private report only; never a public PR or issue |
| `covered` | an existing PR, issue, earlier fix or deleted file already deals with it | recorded, nothing else |
| `park` | latent: needs hand-edited data, an attacker with no impact, test helpers only, dev only, cosmetic | recorded with a revisit trigger |
| `not-pr-worthy` | not a bug, or not worth the maintainer's review time | recorded |

When a fix depends on a product or clinical choice the maintainer has not made yet, route it as a question (`issue`), not a PR. Most closed loop PRs so far were the maintainer ruling on such a choice, not false bugs.

### Partial snapshots

If usage ran out in the middle of a part and you want its comments worked now, copy `results/NN-name.json` to `results/NNa-name-partial.json`, add a `NNa-name-partial` part before it with stage `scanned`, and let the agent triage it. When the full part later reaches `scanned`, drop every comment whose (path, start_line, first 80 characters of content) already appears in the snapshot, and say how many were dropped.

## Fixes, review and publishing

Fixes follow the same rules as every other finder:

- Re-confirm with a failing test on fresh `upstream/main` before fixing. Not reproduced means `NOT-REPRODUCED.md`, not a PR.
- One finding per PR, smallest change, story-cited, branch prefix `fix/ocr*` so outcomes can be measured per finder.
- Pass the [quality gates](quality-gates.md): type checks, related tests, mutants on changed lines killed or explained, code standard.
- The fix folder holds `STATE.json` (`worktree`, `branch`, `head`), `pr-title.txt`, `pr-body.md`, logs and `fix.patch`. `STATE.json` and `READY-FOR-REVIEW` are written last.
- An agent that did not write the fix reviews it ([independent-review.md](independent-review.md)) and writes the next `review-<k>.json` ([schema](../templates/review-verdict.schema.json)): `verdict`, the full `head`, the checks, and a `text_sha256` digest of the title and body it reviewed. These are local files only.
- `CHANGES` goes to a repair worker; after round 1, only the new diff is re-reviewed. Wording-only changes to the PR body can be applied directly with a new APPROVE on the same head. After 3 rounds without approval the folder gets `HOLD.md` and a human is told.
- The [publish driver](publishing.md) runs the full suite and opens the PR once the latest review approves the current head. The pipeline never pushes, comments or merges by itself.

The PR body says the finding came from an Open Code Review scan and was confirmed by a failing test. It has Testing, Risk and How to revert sections.

## Issues

Issue drafts (`ocrNN-issues/<id>-<slug>.md`, first line `# <title>`) get one independent reviewer, who re-runs the witness, checks the primary source for clinical items, re-checks duplicates, and writes `REVIEW.md` with POST, FIX-WORDING or DROP per draft. The agent then posts each POST draft with `gh issue create --title ... --body-file ...` as an argument list, reads back the title and body, and appends `{id, url, title}` to `posted.jsonl`. It searches for a duplicate once more just before posting.

Never write local finding ids as `#N` in a draft: GitHub links them to unrelated real issues.

## Security findings

Never public: no PR, no issue, no public comment, no detail in PR bodies. One reviewer verifies each item (synthetic witness, real reachability, severity, duplicate check against earlier private reports). Confirmed, non-duplicate items go to the maintainer privately, through one channel per item: GitHub's private vulnerability reporting, or the private channel the maintainer has agreed for his own agent. Record where each went in `ocrNN-security/NOTIFIED`. Items that turn out to be a documented trade-off go to the maintainer as a question.

A data-exposure gap (a health value that could reach a log or error report) counts as security. A filter gap with no code path into the sink is defence in depth, not a leak. The general rules are in [security-findings.md](security-findings.md).

## Part reports

When a part is finished, the agent writes `pipeline/NN-REPORT.md` and sets the part `done`. The report has these sections:

- **Scan:** model class, scan base commit, comment count, how many were dropped as already in a partial snapshot.
- **Verdicts:** confirmed / likely / not a bug / unclear, and counts per route.
- **PRs:** each fix folder with head, review round, and PR number once published.
- **Issues:** posted (with numbers) and held (with the reason).
- **Security:** counts and channel only. No content in any public copy.
- **Held / parked:** folders with HOLD, NOT-REPRODUCED or DECISION-NEEDED, and where parked items are recorded.

A part with zero fixes is a normal result. Sample a few parked reasons before reporting a fast triage.

## Holding and tuning

- **Finish the current part, then stop:** `st.py stage <next part> held` plus `st.py set <next part> held_reason '"..."'`. The active part still reviews and publishes. Do not use `paused` for this; it also stops the publish driver keepalive. Resume with `st.py stage <part> queued`.
- **Scan ahead, but do not triage yet:** `st.py top agent_hold true`. Do not leave parts in `held` for this, because the scan picker skips held parts and later parts would scan out of order.
- **Start the agent stage now** instead of waiting for its next tick: run the agent job once by hand (see [scheduling.md](scheduling.md)).
- Change the process by editing the agent instructions, not by running steps by hand alongside the jobs.

Scripts: [scripts/ocr/README.md](../scripts/ocr/README.md). Status questions: [status-reporting.md](status-reporting.md).
