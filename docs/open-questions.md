# Open questions

Places where sources disagreed or a default had to be invented. Each has a current working
answer (used in the docs) and needs a human decision to confirm or change. When one is settled,
move it into the relevant doc and delete it here.

| # | Question | Working answer in these docs | Decide |
|---|---|---|---|
| 1 | Does a maintainer **review** (not merge/close/comment) count as "addressed"? | Yes, any maintainer action counts. CI and bots never do. | Austin |
| 2 | Do reviews by Brad's own agent start a repair? | Its merges and closes always count. Its reviews start a repair only when Brad asked for them. | Austin + Brad |
| 3 | How to ask Brad a product question when issue-filing automation needs his exception | No automated issues without his exception; the question goes on the human review list and a human relays it. | Brad |
| 4 | CRAP on changed functions: "10 or less" (strict tier) or "no worse than base" | Tiered: strict tier must be 10 or less; ratchet tier no worse than base. | Austin |
| 5 | Repair cap: 2 or 3 rounds; and is a pre-PR reviewer "changes" a repair round? | One pre-PR repair, then up to 3 maintainer-requested repairs after the PR opens; operator may set 2. | Austin |
| 6 | May a self-edit to a test that pins the bug ever happen? | No. Any existing test that pins the bug is a human-review stop. | Austin |
| 7 | May the orchestrator close a test-only or wording-only repair delta without a fresh reviewer? | Yes, narrowly; everything else gets a fresh reviewer. | Austin |
| 8 | Strict tsc when the root config already has about 700 errors on main | "No new errors, none on changed lines." | Brad |
| 9 | Whole-file mutation score ratchet in addition to changed-line mutants | Both apply. | Austin |
| 10 | Risk table in the PR template | Proposal; confirm before relying on it. | Austin + Brad |
| 11 | Repair pushes: fast-forward only, or `--force-with-lease` on amended commits | Fast-forward only by default; `ALLOW_FORCE_WITH_LEASE=1` restores the old behavior. | Austin |
| 12 | Who approves sending a private security report | Operator setting. Default: the operator approves each one. | Austin |
| 13 | Duplication ("dryer") gate | Not a per-PR gate yet. | Austin |
| 14 | Invented defaults: high-risk fixes need a failing test (not a traced path); 30-minute Coach cool-down; branch prefix `fix/<tob\|fmsm\|tda\|ocr>-<slug>-<date>` | Proposals in use. | Austin |
| 15 | `addressed` check cannot tell who closed a PR, so a PR the author closed counts | Known limitation; check by hand if a self-closed PR exists. | Anyone |
| 16 | Should Open Code Review keep scanning ahead while the previous round's PRs wait, holding only new PRs? | No. It scans only inside a round the Coordinator opens. | Austin |
