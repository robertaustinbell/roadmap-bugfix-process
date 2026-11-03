# Status reporting

How to answer "what's left?", "how's it going?" and "why no new PRs?", whether a human or the maintainer's agent is asking. The short version: build the answer from files and GitHub, not from memory, and say where each PR came from.

Related: [process.md](process.md), [roles.md](roles.md), [publishing.md](publishing.md), [open-code-review-pipeline.md](open-code-review-pipeline.md).

## Gather from canonical state, all of it

Several streams publish through the same driver (repairs answering maintainer reviews, OCR parts, the other finders). One conversation's work is not the whole picture.

1. **GitHub.** `gh pr list -R DrBradStanfield/roadmap --author <our account> --state all --search "created:>=<since>" --json number,title,state,headRefName`, and the same for issues. Group PRs by branch prefix (for example `fix/ocr*`) to tell finders apart.
2. **Ledgers and markers.** `published.jsonl` and `pushed.jsonl`; in each fix folder `HOLD.md`, `PARKED.md`, `NOT-REPRODUCED.md`, `DECISION-NEEDED.md`, `PUSH-REFUSED.md` and the latest `review*.md`.
3. **The publish driver.** Is it running (`driver.pid`), and what do the last lines of `driver.log` say?
4. **Scheduled jobs.** For each pipeline job: last status, last error, next run. A failing agent tick is often the real reason nothing moves, and its stall notice may be hours away.
5. **Pipeline state.** `st.py show`, plus `state.json` notes such as `agent_hold`, `held_reason` and one-shot notice flags. Re-read them before calling something "held"; a hold may have been lifted elsewhere.
6. **A timeline before a cause.** When each item became ready (`STATE.json`, review files, `stage_since`), when each job ran or failed, and the last human instruction. A failure before the work was ready caused no delay. A gap with nothing queued is not a stall. Say how long items actually waited.
7. **Merges from the merged list.** `gh pr list --state merged --limit 300 --json number,mergedAt,mergedBy`, grouped by date in code. Never estimate from a number range.

Only then say done, in progress or planned. Never present a routed finding as fixed.

## What to say

- Lead with the answer, then grouped detail, then numbered decisions the reader can answer in one line ("1. yes 2. no").
- **Name where each PR came from:** which finder or stream. Say plainly when a stream produced no PRs and why (for example, everything became parked items or a private report).
- **When a queue finishes, say so** in one message: what shipped (PR numbers), and why the rest did not become PRs (parked as unrealistic input, not reproduced on current `main`, a known residual the maintainer wrote down, needs a decision). A silent finish looks like a stall hours later.
- **"What made it through triage?"** Build it per part from `triage-NN/*-verdicts.json` (count by route) and each fix folder's state. Group as: posted PRs, approved and queued, in re-review, held (one-line reason and a yes/no ask), issues, security (counts and channel only), and the number dropped and why.
- **Is OCR "done"?** Split it: the scanned backlog still being triaged and fixed, versus scanning that waits for the next round because usage ran out. Say what starts the waiting part (the Coordinator opening a round, after the restart rule) and that the job is finished only after that.
- **"Is it running?"** Scans run in the background. Answer from `st.py show` and the part log's modification time, and give the command to watch it: `tail -f results/<part>.log`.
- If an earlier status was wrong, say so plainly and correct it where it was posted.
- Background work is invisible to someone at the computer. Say where it runs and when they will next hear from it.
- "Let me know when it's done" means one message at completion. Do not describe internal polling as messages they will get. Check for an already registered done-notice before adding a second one.
- The maintainer's agent may not be able to open attachments. Put anything it must read in the message text or on GitHub.

## "Does anything need attention?"

1. Read the latest messages from the maintainer's side first. Decisions often land there before they show on GitHub: a PR his side is finishing on its own branch ("don't push further changes"), answers to open questions, reasons for closures. Put `HOLD.md` on any PR his side has taken over.
2. List our open PRs with checks, reviews and comments into a file and flag in code: failing checks, comments or reviews by anyone else, review decisions. `mergeable: UNKNOWN` only means GitHub has not computed it yet; wait and query again before calling it a conflict.
3. For each PR with a maintainer comment, compare its time with the PR's last commit and the repair ledger. A push and a reply after the comment means it is waiting on the maintainer, not on us.
4. `WAIT-FOR` markers mean a PR is waiting for merge order, not stuck.
5. For failing checks, read the failed log and group PRs by failing test before blaming any change. One flaky test failing across many PRs is one item; say which PR fixes it and that `main` is green.
6. Read the closing comment on each recently closed PR. It often carries a rule that makes another open PR redundant.
7. Answer: does a human need to act; then what waits on the maintainer (answered reviews, merge-order waits, red-check explanations, open decisions); then recent merges.

## Findings that are not PRs

- A data-exposure gap counts as security under the repo's `SECURITY.md`: private channel only, never a public PR or issue, and no detail in status posts.
- When the maintainer's side asks for issue-first on something already PR'd, comment on the PR with the options and offer to close it. Do not close it on your own.
