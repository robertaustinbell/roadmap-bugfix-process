# Evidence bar

What the [Decider](../agents/decider.md) needs before a candidate counts as a
**Confirmed** bug. Nothing gets a fix until it is Confirmed. See also
[process.md](process.md#34-decide) and [human review](human-review-and-escalation.md).

## Principles

- A finder's claim is a hypothesis. So is the Decider's own first read. So is a
  subagent's summary.
- Evidence is pinned: it names the commit it was taken at.
- The question is "does a supported user or system action produce a wrong outcome?",
  not "does this code look wrong?".
- Scores (CRAP, duplication, scanner severity, lines of code) point where to look.
  They never prove a bug.

## The three levels

A candidate is Confirmed when it meets **one** of these.

### Level 1: failing test

A test that, at the pinned commit:

- fails on an **assertion** whose message matches the claim (an import error, a
  suite crash or a timeout is a broken test, not a confirmation);
- has a **passing control**: a sibling case showing the correct outcome on the same
  code path, so the test is not just failing for everything;
- gets its expected value from an independent source: a user story acceptance
  criterion, a guideline, a documented contract or a hand calculation, never from
  what the code currently does;
- uses synthetic data only;
- is saved with its run log under `decider/witness/<id>/`.

A failing test confirms on its own.

### Level 2: reproduction

For behaviour a unit test cannot reach (a build, a workflow, a browser-only path):
a scripted reproduction at the pinned commit with exact commands, environment
(Node version, `TZ`), synthetic inputs, observed output, and a control run showing
the correct output. A reproduction confirms on its own.

### Level 3: traced path

For code that cannot be run safely or cheaply (CI workflow files, configuration,
deployment-only paths): an end-to-end trace that names

- the trigger (who or what starts it, and that it is supported today);
- every step through **real callers**, with `file:line` at the pin;
- every existing guard or mitigation on the way, and why each does not stop it;
- the wrong outcome and who sees it;
- any written maintainer intent that covers the behaviour (story text, code comment,
  `CLAUDE.md`, `docs/loops/`, commit message) and why it does not.

A traced path alone needs **two independent agents that agree**. The second agent
gets the candidate and the code, not the first agent's conclusion, and traces it
itself. If they disagree, or only one traced it, the candidate is **Suspected**.

## Independent evidence

Two checks agree only if they could have disagreed.

- **Same origin counts once.** Two finders that saw the same scanner output, the same issue text or
  each other's notes are one piece of evidence. So are two agents that read the first agent's
  conclusion. A second trace for Level 3 gets the candidate and the code only.
- **Same model is labelled.** A second check on the same model as the first is recorded as
  `same_model: true`. It is a second look, good for catching slips, not independent proof. For a
  high-risk `fix`, a same-model agreement on a traced path is not enough.
- **A claim about the bug is not evidence about the bug.** "Already fixed", "not a bug",
  "duplicate of #N" or "works for me", from a maintainer, a bot or another agent, is recorded as
  `reported` until a command checks it at the current commit (the witness passes, the linked PR
  touches this path). A closed PR is not proof the bug is gone.
- **"Not reproduced" says how hard it looked.** Record whether the search was `bounded` (some
  inputs, one environment) or `exhaustive` (every supported path). Only an exhaustive miss drops a
  candidate. A bounded miss leaves it `suspected` with what was tried.
- **The claim is stored word for word, and the test asserts that claim.** The witness must fail on
  the finder's claim, not on a cleaner nearby claim that was easier to test. Each candidate also
  names the requirement it violates (a story criterion, a contract, a guideline).
- **History before routing `fix`.** Read the history of the lines the fix would change. If a
  similar change was reverted, or a comment marks the code as a deliberate workaround, route
  `question` with that history attached.

## Below the bar: Suspected

A candidate that meets none of the levels is Suspected. Suspected items go to the
[human review list](human-review-and-escalation.md) with:

- the observation that would confirm it;
- what was tried and what it showed.

Suspected items never become PRs, and are never described to Brad as bugs.

## Things that look like evidence but are not

- A test that passes and pins the buggy behaviour (that is a test weakness, recorded
  as such, not a repair regression).
- A test that calls an API in an order the app never uses: that shows a latent
  weakness, not a current user defect. Route `park` unless Brad asked for hardening.
- Configuration present in the repo: it does not prove what runs in production.
- Mocks of the exact function under test.
- A finder's or reviewer's severity label.
- Two finders using the same words. (Two finders independently describing the **same
  mechanism** is supporting evidence that a candidate is real, but it still needs a
  level above.)
- A green CI run (it shows the suite passed, not that the suite can fail).

## Reachability and status labels

The Decider labels each candidate with one status:

| Status | Meaning | Route |
|---|---|---|
| `confirmed` | Meets a level above and is reachable through a supported journey | `fix`, `question` or `security-private` |
| `latent` | Mechanism confirmed, but only reachable through a hand-edited or corrupt file, near-impossible timing, an unsupported call order, or a removed feature | `park` with a revisit trigger |
| `suspected` | Below the bar | `human-review` |
| `decision-needed` | Real, but the correct behaviour is a choice Brad has not made, or a fix would reverse a written decision | `question` |
| `refuted` | Disproved by a caller, a guard, a constraint or written intent | `drop` |
| `known` | Already on the known list with no new evidence | `drop` (link the known item) |
| `not-pr-worthy` | Real but no user or maintainer cost (hygiene, test-only adapters, dev harnesses, style) | `drop` or `park` |

## Re-confirmation before fixing

The pin can be days old by the time a fix starts. The Bug fixer re-runs the witness
on current `upstream/main` before writing any production code. If it no longer
fails, the fixer writes `NOT-REPRODUCED.md` with the measurements and stops. Brad may
have fixed it already.

## Same-pattern sites

Before routing `fix`, the Decider searches for every other place the same bug class
occurs (variant analysis). Each extra site is:

- `confirmed` with its own witness, and then fixed in the same PR; or
- `likely`, and then listed under "Further testing needed" in the PR and sent back to
  the finders; it is folded into the PR only once a test of it fails.

## Severity and risk

- **Severity** is set by the Decider from reachable impact, likelihood, exposure and
  existing safeguards. Finders' severities are inflated; expect most "high" claims to
  come back lower or refuted.
- **Risk** is set by what the change touches, never by who wrote it:

| Risk | Touches |
|---|---|
| high | clinical logic or text, privacy/egress/consent/erase, identity and auth, CI workflows and release, record schema, merge and sync of stored records |
| medium | shared core (non-clinical), server routes, persistence, cross-tab or cross-device state |
| low | display-only code, tooling, docs, test-only changes |

Higher risk gets deeper confirmation. Proposed default: a high-risk `fix` needs a
Level 1 or 2 witness (a traced path alone is not enough) and the independent review
must re-run the witness itself.

## Security findings

A candidate that may be a security weakness follows this page for confirmation but
never takes the `fix` route to a public PR. See
[security findings](human-review-and-escalation.md#security-findings).
