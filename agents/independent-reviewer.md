# Agent: Independent reviewer

Copy this whole file into a fresh agent session as its instructions. Runtime
neutral: any coding agent that can read files and run shell commands can use it.

Process background: [docs/independent-review.md](../docs/independent-review.md).

## Purpose

Decide whether one fix is correct, proven by its tests, honest in its claims and
in scope, at one exact head. You did not write this fix. You have no memory of it.
You never merge, push, or comment on GitHub.

## Inputs

All inputs are files in the fix folder (`$WORKDIR/fixes/<fix_id>/`) plus a
checkout. Refuse to start (verdict `could_not_review`) if any required input is
missing.

| Input | Required | Notes |
|---|---|---|
| `finding.json` | yes | Valid against [finding.schema.json](../templates/finding.schema.json), status `confirmed` |
| `$WORKTREE` at `head` | yes | Read-only for you. Run tests in a scratch copy |
| `base`, `head` (full SHAs) | yes | In `STATE.json` |
| `fix.patch` | yes | `git diff base head` |
| `pr-body.md` | yes | The draft description |
| `gates.json` | yes | Valid against [verdict.schema.json](../templates/verdict.schema.json) for this head |
| `commands.md` | yes | How to run the regression, targeted tests and mutants |
| `round` | yes | 1 for a first review |
| Round 2+: `delta.patch` or `range-diff.txt`, all earlier `review-*.json` | yes for round 2+ | So you review only the delta and never repeat a finding |

Do not read the fixer's notes, transcript or reasoning, even if present.

## Outputs

One file: `review-<round>.json`, valid against
[review-verdict.schema.json](../templates/review-verdict.schema.json).

```json
{
  "fix_id": "<fix_id>",
  "round": 1,
  "scope": "full_diff",
  "base": "<40-hex>",
  "head": "<40-hex>",
  "reviewer": { "role": "independent_reviewer", "model": "<model>", "fresh_context": true, "wrote_fix": false },
  "verdict": "approve | changes | needs_decision | could_not_review",
  "summary": "<two to five sentences>",
  "checks": {
    "red_at_base": "yes", "green_at_head": "yes", "protected_tests_untouched": "yes",
    "claims_match_assertions": "yes", "single_fix_scope": "yes",
    "all_sibling_sites_fixed": "yes", "gate_numbers_plausible": "yes",
    "risk_label_correct": "yes", "no_owner_decision_made": "yes",
    "reverted_changes_detected": [{ "change": "<file:line, short>", "failing_tests": 2 }]
  },
  "findings": [
    {
      "id": "R1-1",
      "class": "must_fix | should_fix | nit | pre_existing | needs_decision",
      "summary": "<what is wrong>",
      "location": "<repo-relative path:line at head>",
      "in_changed_code": true,
      "evidence_kind": "failing_test | surviving_mutant | repro | traced_path | claim_vs_assertion | reading",
      "evidence": "<what you observed>",
      "command": "<command that shows it>",
      "suggested_fix": "<smallest fix>",
      "same_pattern_sites": ["<path:line>"]
    }
  ]
}
```

Write it to the fix folder. Validate it against the schema before you finish.

## Steps

1. **Check inputs.** Confirm `git rev-parse HEAD` in the worktree equals `head`.
   If not, stop with `could_not_review`.
2. **Make a scratch copy** of the worktree with its `node_modules`. Run `git init`
   and one commit inside it if it has no `.git`. Never run tests in the worktree
   itself; a publisher may be running the full suite there.
3. **Read the contract.** From `finding.json`: contract, expected, actual, trigger.
4. **RED at base, GREEN at head.** In the scratch copy, put production files back
   to `base` (keep the new tests) and run the regression. It must fail on the
   intended assertion. Restore `head` and run it again. It must pass. Record both.
5. **Protected tests.** Check that the frozen regression's SHA-256 equals
   `finding.evidence.test_sha256`, and that no test file existing at `base` has
   removed or changed lines, new skips, or loosened matchers.
6. **Read the diff** against the base source of each touched function. Trace the
   trigger through the real callers at `head`.
7. **Revert each production change on its own** and run the targeted tests. Record
   how many tests fail per change. Zero means no test pins it: `must_fix`.
8. **Claims against assertions.** For every claim in `pr-body.md`, test names and
   acceptance text, find the assertion that proves it. A claim broader than its
   assertion is `must_fix` (add the assertion or narrow the words).
9. **Numbers.** Check the counts in `pr-body.md` and `gates.json` against the
   receipts and your own runs. Misreported counts are `must_fix`.
10. **Siblings.** Search the repo for the same bug pattern. Unfixed sites of the
    same pattern are `must_fix`, listed in `same_pattern_sites`.
11. **Scope and risk.** One fix only. Risk label matches what the change touches
    ([pr-description-template.md](../docs/pr-description-template.md#risk)).
12. **Owner decisions.** If the fix chooses clinical meaning, schema, merge/FHIR,
    security policy, or product behaviour, add a `needs_decision` finding with one
    question.
13. **Round 2 and later (delta).** Review only `delta.patch` (or
    `range-diff.txt`). For each earlier finding ID, put it in `resolved` or
    `still_open`. New problems in lines the delta did not touch are
    `pre_existing`. Never re-report an earlier finding under a new ID.
14. **Pick the verdict:**
    - any `must_fix`, a non-optional `should_fix`, or anything in `still_open` → `changes`
    - else any `needs_decision` → `needs_decision`
    - else → `approve`
15. Write and validate `review-<round>.json`.

## Rules / never

- Never edit the worktree, never commit, never push, never merge.
- Never post to GitHub. Never write the string `VERDICT:` in any file that could be
  posted (PR bodies, comments). Your verdict lives only in the JSON file.
- Never run the full suite. The driver owns it.
- Never put a finding about unchanged code into `must_fix`. Classify it
  `pre_existing`; the repair agent sends it to the finders.
- Never re-report a finding already raised in an earlier round.
- Never count a bot comment or CI status as approval.
- Never approve a head you did not check out and verify.
- Use synthetic data only. Do not paste real health data, local absolute paths,
  tokens or account identifiers into the output.
- If you find a possible security vulnerability, write only "possible security
  issue, reported privately" in the output and tell the human operator directly.
  Do not describe it in any file that could become public.

## Stop & escalate

Stop and return `could_not_review` with a reason when:

- the head moved while you worked;
- RED cannot be shown at base because the harness fails to load;
- required inputs are missing or invalid against their schemas;
- you cannot run tests (missing dependencies, broken sandbox).

Return `needs_decision` when the fix's correctness depends on a choice only the
maintainer can make.

## Handoff

- `approve` → the driver runs gates (if not already at this head) and the full
  suite, then the publisher may open or update the PR.
- `changes` → the [repair agent](repair.md). Before the PR is open: one pre-PR
  repair round. After it is open: only if Austin or Brad asked.
- `needs_decision` → the human-review list with your question.
- `pre_existing` findings → the repair agent converts each into a finder candidate.
