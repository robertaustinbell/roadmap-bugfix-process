# Open questions

Places where sources disagreed or a default had to be invented. Each has a current working
answer (used in the docs) and needs a human decision to confirm or change. When one is settled,
move it into the relevant doc and delete it here. Numbers stay fixed, so a gap means a settled
question; settled answers are listed in [decisions.md](decisions.md).

| # | Question | Working answer in these docs | Decide |
|---|---|---|---|
| 3 | How to ask Brad a product question when issue-filing automation needs his exception | No automated issues without his exception; the question goes on the human review list and a human relays it. | Brad |
| 6 | May a self-edit to a test that pins the bug ever happen? | No. Any existing test that pins the bug is a human-review stop. | Austin |
| 7 | May the orchestrator close a test-only or wording-only repair delta without a fresh reviewer? | Yes, narrowly; everything else gets a fresh reviewer. | Austin |
| 8 | Strict tsc when the root config already has about 700 errors on main | "No new errors, none on changed lines." | Brad |
| 10 | Risk table in the PR template | Proposal; confirm before relying on it. | Austin + Brad |
| 11 | Repair pushes: fast-forward only, or `--force-with-lease` on amended commits | Fast-forward only by default; `ALLOW_FORCE_WITH_LEASE=1` restores the old behavior. | Austin |
| 13 | Duplication ("dryer") gate | Not a per-PR gate yet. | Austin |
| 14 | Invented defaults: high-risk fixes need a failing test (not a traced path); 30-minute Coach cool-down; branch prefix `fix/<tob\|fmsm\|tda\|ocr>-<slug>-<date>` | Proposals in use. | Austin |
| 15 | `addressed` check cannot tell who closed a PR, so a PR the author closed counts | Known limitation; check by hand if a self-closed PR exists. | Anyone |
| 16 | Should Open Code Review keep scanning ahead while the previous round's PRs wait, holding only new PRs? | No. It scans only inside a round the Coordinator opens. | Austin |
