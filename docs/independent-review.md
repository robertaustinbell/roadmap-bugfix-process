# Independent review

Every fix gets exactly one independent, fresh reviewer before its PR opens. The
reviewer did not write the fix, did not see it being written, and has no memory of
earlier rounds except what is handed to it in files.

Agent template: [agents/independent-reviewer.md](../agents/independent-reviewer.md).
Output schema: [templates/review-verdict.schema.json](../templates/review-verdict.schema.json).
After review, repairs follow [repair-rounds.md](repair-rounds.md).

## Why one fresh reviewer

An author re-reading its own diff sees what it meant to write. A fresh reviewer
sees what the code does. Separate agent contexts are not separate organisations,
so this is a check on blind spots, not proof of independence in a strong sense.

## Who may review

- A fresh agent session with no transcript from the Bug fixer, the Decider or an
  earlier review of the same PR.
- A different model is preferred but not required.
- Not allowed: the fixer, the agent that orchestrated the fix, or any agent whose
  context contains the fixer's reasoning.

## What the reviewer gets (and nothing more)

| Input | Why |
|---|---|
| The confirmed finding packet ([finding.schema.json](../templates/finding.schema.json)) | The contract the fix must meet |
| Base commit, head commit, and the patch | What to review |
| The PR body draft | Claims to check against the code |
| Gate receipts ([verdict.schema.json](../templates/verdict.schema.json)) | Claimed numbers to check for plausibility |
| Run commands for targeted tests and mutants | So the reviewer can execute, not only read |
| For round 2 and later: the previous review, the delta patch, the list of findings already raised | So the reviewer reviews only the delta and never repeats a finding |

Do not hand the reviewer the fixer's notes or reasoning. Do not tell it the fix is
probably fine.

## What the reviewer checks

1. **Does the fix meet the finding's contract?** Trace the trigger in the packet
   through the real code at head. Confirm the frozen regression is RED at base and
   GREEN at head by running it.
2. **Is the test strong enough?** Revert each production change one at a time and
   check which tests fail. A production change no test notices is a must-fix: add a
   test or remove the change.
3. **Are the claims true?** Compare every claim (PR body, test names, acceptance
   wording, "every input", "reads back") with what the tests assert. A claim broader
   than the assertion is a must-fix: add the assertion or narrow the words.
4. **Are the numbers plausible?** Check the fixer's test counts, mutant counts and
   CRAP numbers against the receipts. Reviewers have caught misreported counts.
5. **Did the fix touch protected tests?** See
   [quality-gates.md, gate 0](quality-gates.md#gate-0-protected-tests).
6. **Did the fix stay in scope?** One fix per PR. Anything unrelated is a must-fix
   (remove it) or a note.
7. **Are there sibling sites?** Search for the same bug pattern elsewhere. If the
   fix covers only some sites of the same class, that is a must-fix: fix all
   same-pattern sites in this PR. Different bug classes become new candidates for
   the finders, not part of this PR.
8. **Is the risk label right?** Risk is set by what the change touches (see
   [pr-description-template.md](pr-description-template.md#risk)), never by the
   author's confidence.
9. **Does the fix make an owner decision?** Clinical meaning, schema, merge/FHIR,
   security policy, or "what the product should do" choices are not the fixer's to
   make. Flag them `needs_decision`.

## Severity of review findings

| Class | Meaning | Effect |
|---|---|---|
| `must_fix` | Wrong behaviour, a claim the tests do not support, a surviving mutant on a guard the PR adds, a protected test edited, scope creep | Verdict is `changes` |
| `should_fix` | A real weakness that is cheap to fix now | Verdict is `changes` unless the reviewer marks it optional with a reason |
| `nit` | Style or wording with no effect on correctness | Becomes a disclosure; never blocks |
| `pre_existing` | A problem in code the diff did not change | Never blocks. Goes back to the finders as a new candidate |
| `needs_decision` | Needs Brad or Austin to choose | Verdict is `needs_decision`; goes to the human-review list |

A finding about unchanged code is `pre_existing` even if it is serious. It does
not go into this PR. The repair agent sends it to the finders.

## Evidence for a review finding

The same bar as for bugs ([evidence-bar.md](evidence-bar.md)):

- Best: a failing test or a surviving mutant, with the command that shows it.
- Acceptable: a traced path through real callers, with file and line at the
  reviewed head.
- A traced path alone that would block a PR on a high-risk change should be
  confirmed by a second independent check before the repair starts.

## Verdicts

| Verdict | Next step |
|---|---|
| `approve` | Gates and full suite at this head, then the PR may open |
| `changes` | Before the PR opens: one pre-PR repair, then a delta review ([repair-rounds.md, pre-PR](repair-rounds.md#pre-pr-repair-reviewer-asked-for-changes)). After the PR opens: only a human's request starts a repair |
| `needs_decision` | Human-review list with the question |
| `could_not_review` | Missing inputs, broken harness, or head moved. Fix the cause and review again |

An approval names the full head SHA it approves. **Any new commit voids it.**

## Delta review (round 2 and later)

After round 1, the reviewer reviews only the new changes:

- Input is the delta patch between the last reviewed head and the new head. If the
  repair rebased, use `git range-diff <oldbase>..<oldhead> <newbase>..<newhead>`;
  a plain diff between heads also carries upstream changes.
- The reviewer checks that each previous must-fix is resolved and that the delta
  adds no new problem.
- Findings in code the delta did not touch are `pre_existing`, even if the reviewer
  missed them in round 1. They go to the finders.
- A finding already raised in an earlier round is never reported again. If it is
  still open, say "still open: R1-3" and refer to its ID.

## Where the verdict lives (and where it must not)

- The verdict is a **local file** in the fix folder, validated against
  [review-verdict.schema.json](../templates/review-verdict.schema.json). The driver
  reads it from there.
- **Never post a `VERDICT:` line on GitHub.** The upstream `auto-ship.yml`
  workflow accepts `VERDICT: APPROVE <sha>` from certain bot accounts and can act on
  it. Any GitHub comment the loop posts must not contain the string `VERDICT:`
  anywhere, including quoted diffs and quoted review text. Strip or rephrase it
  before posting. The publisher must refuse a body that contains it.
- Bot comments never count as approval of a PR, from this loop or anyone else's.
  Only a maintainer's own review counts, and only for the head it reviewed.

## Bounded model review: practical notes

When the reviewer is a one-turn model call (for example, a CLI call with no tools):

- Join every assistant text block in the output. Some JSON output modes return
  only the last text block, which loses the verdict when the model writes, thinks,
  then writes again.
- Give it the diff plus base source excerpts for the touched functions.
- Tell it the author's claimed counts and ask it to check them.
- A one-turn reviewer cannot run tests. Its mutant and RED/GREEN claims must be
  executed by a tool-using step before they count.
