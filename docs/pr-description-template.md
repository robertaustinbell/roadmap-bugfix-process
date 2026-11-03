# PR description

Every loop PR uses one description shape, written to save the maintainer's time.
The fill-in template is [templates/pr-body.md](../templates/pr-body.md). This page
explains each section.

Three sections are required: **Testing**, **Risk** and **How to revert**. The
publisher refuses a body unless each appears exactly once as a `##` heading
outside comments and code blocks, with text under it, and no `<placeholder>`
from the template is left in the prose. The reviewer reviews the text as well as
the code: the review records a digest of the body, and editing it afterwards
needs a new review.

## Rules for the whole body

- One fix per PR. The title says what was wrong, in user terms.
- Short. Put long logs in the fix folder, not the body. One line for all gates.
- Every number matches a receipt at the current head. When the head moves, every
  SHA and count in the body is updated in the same step.
- Never "full suite not yet run" beside a finished run.
- No `VERDICT:` string anywhere in the body, comments or quoted text (see
  [independent-review.md](independent-review.md#where-the-verdict-lives-and-where-it-must-not)).
- Synthetic examples only. No real health data, no personal data, no local paths,
  no tokens, no account identifiers.
- Nothing about a security vulnerability. Those are reported privately per
  `SECURITY.md`.
- The PR says it was prepared by an automated loop and that a human (Austin) runs
  the loop.

## Summary

Two to four sentences: what the user saw, why it happened, what changed. Link the
user story acceptance criterion it restores (for example `US-12 AC17`).

## Testing

In this order:

1. **Failing test first.** The regression test's name and file, and that it failed
   on the unchanged code at `<base>` with the assertion it failed on.
2. **Passes after the fix** at `<head>`.
3. **Controls.** The neighbouring behaviours kept as passing controls.
4. **Gates.** One line: tsc, incremental review, CRAP, changed-line mutants. Name
   any equivalent mutant with its reason.
5. **Full suite** at `<head>`: passed / skipped / failed. If a known
   load-sensitive file was accepted by a solo rerun, say which file and that it
   passed alone at the same head.
6. **Live check**, if any, with its evidence level from
   [validation-and-sandbox.md](validation-and-sandbox.md#3-live-validation).
7. **Not tested.** Surfaces the evidence does not reach (real browser close,
   Safari, the phone, the deployed service).

## Risk

`low`, `medium` or `high`. Set by **what the change touches**, never by the
author's confidence. Use the highest row that applies.

| Risk | The change touches |
|---|---|
| `high` | Clinical values, ranges, units or advice; health-record merge, sync or erase; schema or stored data shape; privacy, consent or data leaving the device; authentication or authorisation; CI workflows, release or deploy gates; dependency or lockfile changes |
| `medium` | Shared library code with several callers; persistence of non-clinical data; error handling or retry on a network path; anything the user sees as text about their data |
| `low` | One UI component with no data effect; tests only; comments or docs |

Add one line saying why. Higher risk gets deeper confirmation before the PR
opens: a traced-path-only finding is not enough for `high`; it needs a failing
test or a second independent check ([evidence-bar.md](evidence-bar.md)).

If the change needs an owner decision (clinical, schema, merge/FHIR, security
policy, product behaviour), it is not a loop PR. It goes to the maintainer as a
question first.

## How to revert

The exact command and what reverting brings back. Usually:

```sh
git revert <merge-commit>
```

Also say:

- whether a data migration, stored-format change or config change means a revert
  is not enough on its own;
- whether any other PR depends on this one.

## Needs your decision / Further testing needed

Only when there is something. Suspected findings from the incremental review that
were not confirmed, choices the fix did not make, touched quality dimensions that
got worse and the concrete cost.

## Round N (repairs only)

For each repair round, add a `## Round N` section near the top with current
numbers. Keep earlier rounds below as history. Per maintainer comment: what
changed and the test that pins it.
