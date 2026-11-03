# Human review and escalation

Where the [bug-fix loop](process.md) stops and hands over to a person, and how.
See also [roles.md](roles.md), [evidence-bar.md](evidence-bar.md) and
[coordination-with-brads-agent.md](coordination-with-brads-agent.md).

## The human review list

One file, `$STATE_DIR/human-review.md`, owned by the operator. Agents append; only a
human removes or resolves an entry.

### What goes on it

| Category | Added by | Example trigger |
|---|---|---|
| `suspected` | Decider | Candidate below the [evidence bar](evidence-bar.md) |
| `policy-or-behaviour` | Decider, Bug fixer | The fix changes what users see or what the product does on purpose |
| `clinical` | Decider, Bug fixer | Thresholds, guideline values, clinical text, what the bot should answer |
| `schema` / `merge-fhir` | Decider, Bug fixer | Record shape, merge rules, interchange format |
| `security-policy` | Decider | How a security control should behave (distinct from a security bug) |
| `written-decision` | Decider, Bug fixer | The fix would reverse a recorded maintainer decision |
| `test-pins-bug` | Bug fixer | An existing test asserts the buggy behaviour, so the fix needs a test change |
| `repair-cap` | Bug fixer | A PR hit the repair cap |
| `gate-worse` | Bug fixer | A touched FMSM dimension got worse, or CRAP/mutation cannot pass without a refactor |
| `refactor` | Any finder via Decider | Structural restructuring of legacy code |
| `coach-proposal` | Coach | Durable rule or process change |
| `stuck` | Coordinator | An agent failed twice, a gate could not run, or state is inconsistent |

### Entry format

```markdown
## HR-<yyyymmdd>-<n>: <one-line title>
- category: <category>
- round: <round>  pinned: <sha>
- source: <finder id / PR #N / coach>
- what: <plain words: what goes wrong or what is proposed>
- evidence: <witness path, trace, or "none: suspected">
- would confirm it: <for suspected items>
- options: 1) ... 2) ... (mark the loop's recommendation)
- needs: operator | Brad
- status: open | asked-brad | decided:<option> | dropped:<reason>
```

Write in plain words. Do not ask the human to read a long proposal to understand a
small item.

## Escalation triggers

An agent stops and escalates (adds an entry, writes a stop file in its folder, and
moves on to other work) when:

1. the evidence is below the bar;
2. the correct behaviour is a product, clinical, schema, merge/FHIR, privacy-promise
   or security-policy choice;
3. a fix would reverse a written maintainer decision (story text, code comment,
   commit message, `CLAUDE.md`);
4. an existing test pins the buggy behaviour;
5. the gates cannot pass without refactoring legacy code, or a touched quality
   dimension gets worse;
6. the repair cap is reached;
7. a gate could not run (missing tool, broken harness, environment failure) after one
   honest retry;
8. the maintainer or his agent asks the loop to hold;
9. anything suggests real personal or health data has entered loop state or output.
   (Stop everything, tell the operator, do not post.)

Stop files the [Bug fixer](../agents/bug-fixer.md) and publisher respect:
`HOLD.md`, `DECISION-NEEDED.md`, `NOT-REPRODUCED.md`, `HELD-FOR-HUMAN.md`. A folder
with any of them is never published.

## Questions to Brad

When a fix depends on a product decision Brad has not made (skip vs block, how to
read a user's words, what the bot should answer), **ask first; do not open a PR**.
PRs #469, #484 and #510 were closed for this reason: the code was fine, the choice
was his.

How to ask:

- One question per item. Lead with one synthetic case and what happens today.
- Give the options with their concrete effect, and the loop's recommendation.
- Offer to prepare the change once he decides.
- Use the channel Brad prefers. Brad's rule (header of `stale-pr-watch.yml` in his
  repo) is that notifications go through his Claude app, and new issue-filing
  automation needs his exception. So the loop does **not** file GitHub issues unless
  Brad has granted this loop that exception. Without it, the question goes on the
  human review list (`needs: Brad`) and the operator, or Brad's agent, carries it to
  him.
- Clinical-rule mismatches (code vs code, or code vs guideline) are questions, never
  PRs, even when a witness fails.

When Brad answers, record the answer in the entry, add it to the Decider's outcome
data, and (if he chose a change) route a `fix` in the next round.

## Security findings

Security weaknesses are reported **privately**, never as a public PR, issue,
comment, or PR-body mention. See also [security-findings.md](security-findings.md). A public write-up is a working recipe for an attacker.

1. Read the repo's `SECURITY.md` at current `main` for the channel Brad wants.
   Today that is GitHub private vulnerability reporting, or a direct private channel
   to Brad (or his agent) that he has named.
2. Use **one channel per item**, never both.
3. Confirm the finding with the [evidence bar](evidence-bar.md) and an independent
   check before sending. Grade severity honestly: a gap that only weakens one of
   several alarms, or that needs the maintainer's own credentials, is Low at most.
4. Describe the class, the location (file and function at a pinned commit), the
   reach, and the suggested fix. Do not include a working attack string or
   step-by-step exploit.
5. Keep the weakness out of every other PR body, commit message and comment. A fix
   folder may be prepared locally, but it carries `HOLD.md` so nothing publishes it.
6. Whether reports go out automatically or wait for the operator's approval is the
   operator's setting. Record which setting was in force with each report.
7. After filing, check the report is not publicly visible (for example, the advisory
   URL returns 404 when logged out). Record only the report ID and status in loop
   state, not the content.

## Repair escalation

- Only Austin's or Brad's review feedback starts a repair.
- Cap: 3 rounds (operator may set 2). On reaching it, add a `repair-cap` entry with
  the PR number, what each round changed, and what is still unresolved, and stop
  pushing.
- Pre-existing problems found during review go back to the finders, not into the PR.

## What a human does with the list

- **Operator:** triage weekly or when the Coordinator flags new entries. Decide,
  forward to Brad, or drop with a reason.
- **Brad:** answers `needs: Brad` items when they reach him. Silence is not an
  answer; the item stays open.
- Dropped items with Brad's reason go to `declined.md` so finders do not raise them
  again.
