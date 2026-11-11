# Bug-fix loop for DrBradStanfield/roadmap: process, v0.8

> **Design draft, not running.** The kit in this repository runs v0.3.1
> ([process spec](../../process.md)). This file is the public copy of the v0.8 design of
> 2026-11-10. A few sentences were made generic before publishing (section 11, Appendix
> A3, and the review packet), under the loop's own private-route rule (step 4b), and chat
> channels are named generically, as elsewhere in this kit.

**Status:** design only for the roadmap. Nothing here runs on the roadmap yet. It is held
until the maintainer's own refactor ("untangle") is finished, and each rollout phase needs
the owner's approval. Sections 1 to 11 describe what rollout phases 0 to 2 would build.
Everything else is in **Appendix A, not built**, and stays there until a phase earns it.

**Owner:** Austin (an outside contributor who runs the loop).
**Maintainer:** Brad (owns the repo, merges everything, has his own coding agent).

**What v0.8 changes from v0.7.** It applies an outside review (Claude Fable 5.2,
2026-11-10, quotes checked against v0.7) and the owner's decisions on it:

- Unbuilt parts move to Appendix A. Parent is parked. Signal stays off until it has a
  redaction step. Fresh eyes becomes a trigger, not an oracle.
- Safety: Publish becomes a host script. No agent holds push access. Every VM gets a
  network allowlist. Security findings are classified by script before Route. Clinical
  changes carry a before-and-after table.
- Proof: every witness records who wrote its expectation. The independent check, the
  control and the path check are now defined. Timing bugs get their own proof rule.
  High-harm parks become questions. The rubric is shorter.
- Review: the reviewer and adversary are one role. The reviewer runs on a different model
  family from the fixer and uses a scripted environment matrix. Repair stops after two
  rounds. Blast radius becomes a script.
- Throttle counts only loop PRs, and closes without a merge lower the cap.
- Learn now measures recall (with planted bugs) and the time from event to Published.
- Before phase 1, v0.3.1 and v0.8 are compared on an old snapshot. This waits for the
  refactor.
- Five errors in v0.7 are corrected (section 12).

---

## 0. Brief

**What the system is.** An agent pipeline, run by an outside contributor, that finds bugs
in a public open-source health app (Shopify app, web widget, iOS app; TypeScript and
Swift; health data lives in the user's own cloud file). It proves each bug with a failing
test, fixes it in a small pull request (PR), and hands the PR to the maintainer, who
decides whether to merge.

**Why it exists.** The maintainer's own agent writes and reviews most of the code. This
loop is a second set of eyes. It is only independent if its prompts, tools and models
differ from his. Which models his agent uses is not yet known (section 11), so the claim of
independence is not yet checked.

**What it already is (v0.3.1, in use).** A custom kit of role prompts and scripts: finders,
a decider, a bug fixer, a reviewer, an adversary and a publisher, with quality gates
(complexity, mutation testing). About 194 loop PRs have been merged. Two third-party
finders have run in it: FMSM (an audit skill) and the Open Code Review CLI.

**What this design changes.** It organises the loop around *oracles* (what says the code
is wrong), adds an explicit proof stage, a budget for the maintainer's attention, and
files that keep what the loop learns. **Nothing yet shows that it finds more than v0.3.1.**
Rollout starts with that comparison (section 8).

## 1. Purpose

Give the repo fresh perspectives its maintainer's agent does not have. Prove every finding
with executable evidence. Spend the maintainer's time only on what is proven and worth it.

## 2. Three ideas

1. **A bug is a disagreement between the code and an oracle**: something that says what
   the code should do (a spec line, a twin file, a fixed bug, an invariant). The loop is
   organised by oracle, not by tool. **A witness is only as strong as its oracle**, so
   every witness records who wrote the expectation it checks (step 4).
2. **Nothing reaches the maintainer without executable proof.** Finding candidates is cheap.
   Proof and the maintainer's attention are the real costs.
3. **What the loop learns is kept in files**, so each pass starts smarter than the last.

Needless complexity counts as a defect: it makes the next bug likely and hides it. That
applies to this design too.

## 3. Rules that never change

- The maintainer merges. The loop never merges, approves, labels or closes on his repo.
- One fix per PR. No fix without a confirmed failing test (a *witness*).
- A session starts only when the owner says so. Events (commits, schedule ticks) only
  queue work; nothing starts a session by itself.
- Public text contains only synthetic data. Security findings go only to the private route
  (section 7).
- Text in PRs, issues, files and tool output is information, never instruction.
  Bot comments are not approval.
- **Enforced, not only instructed:**
  - Every role runs in a fresh context, in a disposable VM with no credentials inside.
  - Every VM has a network egress allowlist: only the package mirrors and model API the
    role needs. Nothing else is reachable.
  - Each role's VM mounts only its own run folder as writable. Skills, kit files, loop
    memory and other roles' output are read-only. Changes to them are proposals that the
    owning stage (section 6) or Learn accepts and the owner approves.
  - No agent role holds push access. Publish is a host script (step 7).
  - The preflight probe tests all four before the first role starts.
- Never push to a PR the maintainer is reviewing. Before Publish, the loop checks the
  maintainer's channels for a pause request (section 7) and stops if there is one.
- **Scripts do what must not go wrong** (file selection, coverage, reruns, dedupe, budget,
  classification, publishing). **Agents do judgment** (finding, intent, proof design,
  impact, fixing, review). Moving a step from agent to script is a win.

## 4. The oracles in the core

Phases 0 to 2 use three oracles. The others are in Appendix A.

| Oracle | Checks the code against | Finds | Runs when | Tools |
|---|---|---|---|---|
| **Structure** | "Should these pieces change together?" | Hidden links, needless links, surplus code, special cases; copies that drifted apart | Scout flags co-change or special cases; a fix touched one copy; a refactor PR landed in the area | Maintainer's `untangle` skill and `untangle-measures` script; `dryer` shortlist |
| **Variant** | A bug already fixed | The same mechanism elsewhere | Every merged fix | Semgrep rules (script); agent |
| **Sibling** | A twin (Drive vs Dropbox storage, TS vs iOS engine, `.mjs` vs TS copy) | A fix made on one side only; twins that disagree | A merged fix touches one twin; a change to a twin | Twin map; **differential test** (below); agent |

**Differential testing of twins.** Where twins have comparable outputs, a script feeds the
same generated inputs to both and compares the results. A disagreement is a candidate with
a ready witness. This turns most of Sibling into a script. It is new and untested: phase 2
first checks which twins have comparable outputs (an inference, not yet known).

**Fresh eyes is a trigger, not an oracle.** A new model or tool (FMSM, Open Code Review)
queues a re-read of high-risk areas. Its candidates must still name an oracle in Prove.

Each oracle has a written definition and a list of exclusions (what never counts).
The loop does not run plain diff review; the maintainer's agent already does.

**What runs today.** In the loop now: the custom kit, FMSM, Open Code Review, `crapper` and
`mutator` (as fixer gates). Installed, not yet used in the loop: Grim Prompter, `dryer`.
Not installed: the Trail of Bits skills, the tech-debt skill. Each new tool is pinned to a
version and run on a test set before adoption.

## 5. The flow

### Step 0. Preflight (script)

Before any role starts, whatever the run:

1. **Isolation probe.** Proves no credentials in any VM, the egress allowlist, read-only
   mounts outside the role's run folder, and no push access.
2. **Harness self-test in every workspace.** Each role's copy runs the repo's quick check
   (unit tests, plus one browser smoke where there is one) and must pass, with dependencies
   resolving from inside that copy. (Dry run: a broken dependency link in all six finder
   copies went unnoticed; each finder worked around it.)
3. **One port and one build marker per role.** Every browser or load check first fetches
   a marker proving it measures its own build. (Dry run: one finder measured another
   agent's server.)
4. **Pinned browsers installed** at the exact builds the pinned Playwright wants.
   Playwright's WebKit with phone emulation is not Safari on an iPhone, and is labelled as
   emulation. (Dry run: WebKit was missing, so finders did not test it.)
5. **Evidence root.** All evidence lives under the run folder. Scratch outside it is
   pruned and cannot be sealed.
6. **Instrument fit.** Each instrument states what it covers on this repo. What it does not
   cover is recorded as Not assessed. (Dry run: `crapper` scored only Python; `mutator`
   needed a clone per mutant.)

### Step 1. Intake (script)

Commits, merged fixes, schedule ticks and new models or tools become events in a queue.
Each event names the oracles it triggers and the files it touches. Intake never waits on
the maintainer.

Intake reads the maintainer's refactor ledger (`docs/untangle/*.csv`) read-only. Items on
it are already known, so the loop never re-raises them; a finding in a ledger area cites
the ledger id.

### Step 2. Scout (script, then agent)

Builds and keeps a living **area map**.

- **Risk score (script):** churn x size x past confirmed bugs, plus `knip`, `madge`, `tsc`,
  `crapper`, `dryer` (as a shortlist only) and the maintainer's `untangle-measures`, so the
  loop and the maintainer use the same numbers. Special cases (an `if` for one value, a
  swallowed error, a retry or sleep, a skipped test) raise the score.
- **Reach and harm (agent, from a threat model):** what a user can reach and what it can
  hurt (clinical advice, health data, privacy, sync, AI chat and tools). Built with Grim
  Prompter. Updated per change against its saved baseline.
- **Twin map:** seeded from git co-change and copied logic, checked by an agent. Records
  which twins have comparable outputs for differential testing.
- **Coverage:** per area and per oracle, each High / Medium / Low / **Not assessed**, with
  the files read and whether the read is fresh or carried over. An area that was not
  assessed is never reported as clean.

Finders run only on areas that are reachable and matter. After a big refactor, the whole
map is rebuilt before any finder runs.

### Step 3. Look (one isolated finder per oracle)

Each finder gets its area, the matching area rules, twin bundles and the known lists.

1. **Orient first.** A short note on the area: purpose, entry points, data flow,
   applicable acceptance criteria (ACs), recent churn. Cached; redone when the area
   changes. A note that contradicts the map is reported as a map error.
2. **Candidates.** Each names its oracle, the exact rule broken, file:line, and the model
   and tool used.
3. **Looks wrong but is fine.** Things considered and rejected, with reasons. These are
   proposals for the known-fine list (section 6), not entries.
4. **Surprises.** Problems the oracle does not cover. These become new rules or oracles.

### Step 4. Prove (Decider, then an independent check)

0. **Evidence rubric.** Score 0-2 on each of: a real trigger, an impact (user-visible
   harm, or a structural cost for Structure findings), a reproduction idea. Under 4 of 6
   stops as `thin-evidence`. The rubric scores the claim, never the code.
1. **Attack the premise.** Is the expected behaviour really what the code should do?
2. **Record who wrote the expectation.** Each witness names the source of the behaviour
   it expects:
   - **Maintainer-written:** an AC, the algorithm doc, a fixed twin, his own test or
     comment. May go to a Fix PR.
   - **Loop-inferred:** an invariant, a durability rule or a contract the loop wrote.
     Goes to the Question route first. After the maintainer answers, it becomes
     maintainer-written and re-enters Prove.
   - **Clinical behaviour** is never loop-inferred. Any expectation about advice output
     needs a maintainer-written source or his answer.
3. **Lenient static screen.** Drop only what has no path from a real user or caller.
4. **Location check.** The cited code is really there.
5. **Witness and control.** A test that fails on fresh `main` for the claimed reason.
   The **control** is the same test with an input that should not trigger the bug, and it
   must pass.
6. **Path check.** A minimal change at the claimed line turns the witness green. If it
   does not, the bug is somewhere else.
7. **Impact.** The harm a user would see, on the real path. Severity comes from this.
8. **Group by root cause.** Seal the evidence package (pinned revisions, witness, control,
   logs, expectation source) with hashes.
9. **Independent check (script).** Reruns the sealed witness and control in a clean VM on
   the pinned revision. Both must behave as recorded.
10. **Give up.** No progress in 30 minutes: park as `not-reproduced` with a reason. An item
   with high harm (data loss, sync, privacy, clinical) is not dropped: it becomes one row in
   the question table, with what was tried.

**Timing bugs** (races, ordering, timeouts) need a deterministic reproduction, using fake
timers or controlled delays. If none is possible, report a failure rate over at least 50
runs against a control that fails 0 times. "Fails three times out of three" alone parks real
races.

**Structure findings** are proved one of two ways:
- **Drift:** the copies already behave differently. Normal witness, then a Fix PR.
- **Structural:** nothing behaves differently yet. Proof is (a) the copies, links or special
  cases with file:line and co-change counts; (b) a durability test or lint that fails on
  fresh `main` and passes after the fix; (c) `untangle-measures` before and after; (d) the
  full suite unchanged. The guard is loop-inferred, so it goes to Question first.

### Step 4b. Classify (script)

Before Route, a script marks a finding **private** if any of these hold:
- it touches sign-in, sessions, tokens or keys;
- it shows one user's data reaching another user, a log, an analytics service or a third
  party;
- its oracle or lens is Sneaky or Data flow (Appendix A);
- the Decider or any role flagged it as security.

Private findings go only to the private route. A failing test for a private finding is
never public, because it would disclose the problem. The default when unsure is private.

### Step 5. Route

| Route | When |
|---|---|
| **Fix PR** | A maintainer-written expectation is broken |
| **Untangle PR** | A proved structural defect the maintainer asked to have guarded. Follows his untangle terms: small, one fix, cites an AC, bugs first, no bulk comment deletion, tests removed only from a list he approved, his yes on clinical items |
| **Question** | Intent unclear, a loop-inferred expectation, a clinical call, or a parked high-harm item. One table a week. **An answer is a spec change:** it is written into the spec file the maintainer owns (or the loop's area rules), and the finding re-enters Prove |
| **Private** | Classified private in step 4b |
| **Park** | With a reason code |
| **Prevent** | A bug class seen three times. First a loop-side Semgrep rule; then one guard proposed to the maintainer, preferring the one structural fix behind several bugs |

**Durability work goes as one question first.** The refactor ledger has rows marked done
with nothing guarding them (29 on 2026-11-10). They are offered as one question row ("which
of these do you want guarded?"), preferring one lint rule over many tests. Only rows he
picks become Untangle PRs.

**Clinical changes are flagged.** Any diff that changes the advice engine's output says so
in the first line of the PR and carries a before-and-after table on a fixed input set.

Before anything leaves: re-check on the newest `main`, against the maintainer's open
branches and PRs, and against section locks in his agent channel. The loop never takes a
lock; a locked section waits.

### Step 6. Throttle (script, before Fix)

- Open loop PRs never exceed the number of loop PRs the maintainer merged in the last 14
  days (minimum 1, starting cap 6). Each loop PR he closed without merging in that window
  lowers the cap by one.
- At most one question table a week, top 10 rows.
- Rank by severity x confidence x the maintainer's cost to review.
- Areas under active refactor are held.

### Step 7. Fix and publish

1. **Bug fixer:** test fails first (RED), then passes (GREEN). Gates: every changed
   function CRAP 10 or less; every changed-line mutant killed or named equivalent, within
   a time cap (mutants not run in time are recorded as Not assessed); no new
   near-duplicate (`dryer` 0.8 on changed files). Rules: fix the root cause, subtract
   before adding, test behaviour not implementation, make writes idempotent.
2. **Blast radius (script).** Computes every consumer of each shared thing the fix changes,
   and checks that a passing test executes each one.
   - **Shared** means a changed declaration referenced outside its own file, or a changed
     string key (CSS variable, config key, stored field name, `UserDefaults` key) found in
     two or more files.
   - TypeScript: compiler find-references on each changed exported symbol (`ts-morph`),
     extended through the import graph (`madge`).
   - Swift: the compiler's index store (the symbol database Xcode and SourceKit-LSP build).
   - String keys: a literal text search across all file types. Type checkers miss these,
     and the dry-run failure was one.
   - Map consumers to tests with the runner's related-tests mode and line coverage
     (`xccov` for Swift). A consumer no passing test executes is Not assessed and blocks
     Ready until tested or accepted by the owner.
   - A changed symbol in the twin map queues a Sibling event.
   - A changed stored field adds two consumers: files written by older versions, and the
     other platform.
   (Dry run: a fix raised the header height variable, which also sized the phone menu;
   every gate passed and the menu broke at 200% text.)
3. **Post-patch validation:** the original bug, variants of its root cause, and behaviour
   that must not change. Prove "no change" claims with a measured before/after against the
   base build, never by reading the diff. **Every user-interface fix** runs a fixed matrix
   (browsers, widths, text sizes, before and after) by script.
4. **Reviewer (one role, two parts), on a different model family from the fixer.**
   - *Review:* verify the receipt's claims; they are claims, not facts.
   - *Attack:* try to break the fix with unusual inputs and conditions, including at
     least one fixture that breaks the pattern of the existing ones. (Dry run: the same
     agent found the phone-menu regression in its review and the Cal.com wording bug in its
     attack.)
   - **Request-changes starts a repair round:** the finding becomes a RED test first, then
     the fix, then review again. **At most two rounds**, then the item parks with the
     reviewer's notes.
   - Anything found beyond the fix is a new candidate and goes back to Prove.
5. **Durability tests need fixture diversity.** At least one fixture breaks the dominant
   pattern of the others. (Dry run: every "dead link" fixture began with "404:", so the
   suite could not see that "could not be found" was missed.)
6. **Publisher (host script).** Accepts only sealed packages whose hashes match. Runs a
   secret scan on the diff, the PR text and the evidence package with the repo's pinned
   `gitleaks` and `.gitleaks.toml`. Checks for a pause request and the in-review guard.
   Then pushes. It is the only thing with push access, and it runs no model.

### Step 8. Learn (Coach)

- Every item ends as merged, closed, undone later, open or parked.
- Per oracle: precision, **recall** (below), the maintainer's review time, cost per stage.
  Per stage: how often review found a problem the fixer's gates missed.
- **Time from event to Published.** The maintainer's agent moves `main` fast and review
  roughly doubles fixing time, so stale witnesses are a real risk.
- **Recall by planted bugs.** Plant known bugs in a snapshot (never shown to finders) and
  count what each oracle finds. Precision alone cannot show what the loop misses.
- Each confirmed fix gets one bug-class label from a fixed list. Rules and Prevent count
  from labels, never from PR titles. Learn also tracks which classes the maintainer's agent
  keeps introducing, and feeds them to Prevent.
- An oracle switches off after two cycles below its bar **and** at least five results.
  It stays off until the owner turns it back on.
- When the model changes, rerun the test set with one scaffolding layer removed at a time,
  and drop layers that no longer help.
- Scores stay internal. The maintainer only ever sees evidence. A plan is never a passed
  test, and missing documentation alone is never a defect.
- Once a quarter, threat-model the loop itself: roles, tokens, VMs, tool permissions.
- **Every instrument proves itself:** each checking tool has a self-test with a known
  answer and a negative control, run before it is trusted. A tool that cannot fail is not
  checking anything.
- Only Learn proposes changes to skills, the kit or memory; the owner approves.

**Rules for testing the loop itself.** Whenever the loop compares configurations (a new
tool, an oracle on or off, a new model, v0.3.1 against v0.8), the test set obeys five rules:
1. **Fair evaluators:** the same scoring for every configuration, blind to which one
   produced the output.
2. **Only the thing under test varies:** same items, same prompts, same output format.
3. **Never leak the answer:** the known bug is for scoring only, never shown to the finder.
4. **Representative environment:** the finder gets what a real pass would get.
5. **Context-free runs:** each item gets a fresh agent with no memory of the others.
Rule 3 is enforced by VM isolation with only the old snapshot inside, not by instruction.

## 5b. Running parts of the process

Every stage reads its input from files and writes its output to files, so a run can start
at any stage that has its input and stop after any stage.

| Run | Stages | Ends with | Touches the repo? |
|---|---|---|---|
| **Map** | Preflight, Intake, Scout | Area map, twin map, threat model, coverage gaps | No |
| **Hunt** | Look, Prove, Classify (needs a map) | Sealed, proved items, plus parked and known-fine proposals | No |
| **Fix** | Throttle, Fix, validate, review (needs proved items) | Ready local branches with receipts | No |
| **Publish** | Final re-check, publish (needs Ready branches) | PRs and the question table | **Yes**, only on the owner's go |
| **Learn** | Coach | Per-oracle report; switch-off proposals | No |

**Publish states are named.** Every report says which state each fix is in:

| State | On the roadmap | On a repo the owner controls |
|---|---|---|
| Ready | A local branch with receipt and review | Same |
| Merged locally | n/a (the loop never merges) | On the owner's local `main` |
| Published | A PR is open on the maintainer's repo | Pushed to the remote |
| Live | The maintainer merged and deployed | Deployed and verified live |

The loop moves a fix one state only on the owner's go for that state. On the roadmap the
loop makes only one move, Ready to Published.

**Options on any run:** oracles, area, stop after a stage, budget (wall time and model
spend; the run stops cleanly when either runs out), target repo.

**Rules every run keeps:**
- Preflight runs first.
- A run that starts mid-process checks its input: packages verified by hash; if `main`
  moved since sealing, the witness reruns on the new `main` before any fix. A stale map is
  rebuilt, not trusted.
- Only Publish touches the repo, and only on the owner's go.
- Each run writes a short manifest (options, start and end state, what is left).
- Learn counts every run, including partial ones.

## 6. Loop memory

Each file has one owning stage. Roles propose; the owner of the file accepts.

| File | Holds | Accepted by | Read by |
|---|---|---|---|
| Area map | Risk score, reach, harm, coverage per area and oracle | Scout, Learn | Scout, Look, Throttle |
| Orientation notes | Per area: purpose, entry points, data flow, ACs, churn | Look (own area) | Look, Prove |
| Threat model + data inventory | Assets, boundaries, controls, where personal data goes | Scout | Scout, Classify |
| Twin map | Files that must agree; which have comparable outputs | Scout | Look, Blast radius |
| Area rules + Semgrep | Checks from confirmed bug classes | Prevent, Learn | Look, Variant |
| Known bugs | Everything raised or fixed, anchored by symbol and test name | Prove | Look, Prove |
| Known-fine | Looked wrong, is fine, with reasons | **Decider** | Look |
| Bug classes | One label per confirmed fix | Learn | Prevent, rules |
| Coverage stamps | Model, tool, files read, fresh or carried | Look | Scout |

**Known-fine entries expire.** Each is bound to a hash of the code it covers and lapses
when that code changes. One finder cannot hide a bug from later passes.

## 7. Who decides, and channels

| Owner (Austin) | The loop | Maintainer (Brad) |
|---|---|---|
| When sessions run, which oracles are on, kit releases, private routing | Budget within the rules, ranking, parking | Merges, answers the question table, clinical calls, pausing the loop |

**Channels with the maintainer** already exist: GitHub first; the agent chat channel when GitHub rate
limits. The question table, PRs and pause requests travel there. Private findings use the
private form of the same channels (a GitHub private vulnerability report, or a direct
chat message if GitHub rate limits), never a public issue, PR or channel.

## 8. Rollout

Each phase needs the owner's approval. None starts until the maintainer's refactor is done.

**Gate before phase 1: does v0.8 beat v0.3.1?** Run both on one old roadmap snapshot and
score them against fixes the maintainer later merged, under the rules for testing the loop
(section 5, step 8). If v0.8 does not find more, or the same for less of his time, phase 1
does not start. Waits for the refactor and the owner's go.

0. **Safety:** VMs, egress allowlist, read-only mounts, host-script publisher, isolation
   probe, harness preflight; kit release approved.
1. **Reshape, nothing new.** Queue, oracle labels on today's finders, throttle, question
   table, reason codes, Classify, loop memory files, per-oracle report. This is the real dry
   run on someone else's repo. **Pass criteria, all required:**
   - preflight passes in every workspace with no manual repair;
   - every published item has a sealed package that the independent check reproduces;
   - no private finding appears in public text;
   - the maintainer closes no loop PR as noise or duplicate;
   - throttle, re-check and pause request each fire correctly at least once (forced if
     needed);
   - time from event to Published is recorded for every item.
2. **Structure, then Variant + Sibling.** Durability as one question row first; then
   structural findings in finished areas. Variant and Sibling after each merged fix, with
   Semgrep rules and differential tests where twins allow.

Later phases come from Appendix A, one at a time, each with its own pass criteria.

## 9. Costs and limits the design accepts

- Proof is expensive. The loop will find fewer things and send fewer still: precision over
  recall, now measured (step 8).
- VMs add setup time to every role. iOS builds need macOS hosts.
- Several numbers (cap 6, 14-day window, rubric cut, 30-minute limit, 50 timing runs,
  three-repeat Prevent trigger, two repair rounds) are starting guesses for Learn to tune.
- Review and repair roughly double fixing time. On the dry run the round found one
  regression and one real bug in four fixes.
- **TruffleHog is not adopted.** The repo's CI already runs gitleaks; TruffleHog's extra is
  verifying found secrets, which means using a credential, which the loop must never do.
- Third-party skills steer agents with repo access; each is pinned and vetted first.

## 10. Failure modes it guards against

| Failure | Guard |
|---|---|
| Plausible but false findings | Rubric, premise check, expectation source, witness + control, path check, independent check |
| The loop's own expectation is wrong | Loop-inferred expectations go to Question first |
| Flaky or racy runs | Deterministic timing reproduction or measured rate against a zero control |
| Wrong line or file cited | Location check; sealed evidence |
| Flooding the maintainer | Throttle on merged loop PRs; durability as one question; one table a week |
| Duplicating his work | Ledger, open PRs, branches and locks checked before anything leaves |
| Re-raising rejected ideas | Known bugs; known-fine bound to code hashes |
| One finder suppressing a real bug | Known-fine accepted by the Decider, expires on code change |
| Prompt injection from repo text | No credentials, egress allowlist, read-only mounts, no agent push |
| Leaking a vulnerability in public | Classify by script, default private |
| Leaking a secret in loop output | Publisher secret scan with the repo's own gitleaks config |
| A clinical change slipping through | Flag in first line, before-and-after table, maintainer-written expectation |
| A fix breaking another consumer | Blast-radius script with test mapping |
| Tests sharing the code's blind spot | Fixture diversity; attack part of review |
| Endless repair | Two rounds, then park |
| Tool or model drift | Pinned tools; coverage stamps; ablation on model change |
| Silent coverage gaps | Not assessed is recorded, never read as clean |
| A broken harness every role works around | Preflight self-test in every workspace |
| Measuring someone else's server | One port and build marker per role |
| Evidence lost to scratch cleanup | Evidence root under the run folder |
| Stale witnesses on a fast `main` | Rerun on new `main` before fix; time to Published tracked |
| Owner and loop meaning different things by "merge" | Named publish states |

## 11. Open questions

- **Which models does the maintainer's agent use?** If the loop uses the same family, its
  main advantage is weak. Find out, and prefer a different family for finders and the
  reviewer.
- Known-bug entries cite file:line; after the refactor many have moved. Re-anchor them by
  symbol and test name before the first pass.
- One possible bug from the backtest is unconfirmed. It is held on the private route
  (step 4b) and parked until after the refactor.
- On the roadmap, the loop's host holds push access to a fork. Phase 0 must show that no VM
  can reach it.

## 12. Evidence behind the design

From a local backtest (2026-11-09) on the loop's own merged fixes, the record of one
earlier structural audit, and one dry run. Small samples; read as direction, not proof.

- **Origin of loop-fixed bugs.** Of 74 fixes checked: **2** were regressions from a
  specific commit; 31 were present in the earliest version that loads; 3 still failed at the
  oldest commit checked; 29 could not be determined (old code would not load or test); 9
  had no usable witness (no test file, the witness did not flip, or the start did not
  fail). The sample is bugs found by a loop with no Parent oracle, so few regressions is
  partly selection. It suggests most of these bugs were old, not that spec checking beats
  regression checking.
- **Catching tests (Meta JiTTests method).** On 5 commits (2 known bug-introducing, 3
  controls), one model: intent-aware generation had 17 stable catches, 8 later confirmed by
  the maintainer changing that behaviour (47%). Treat-every-change-as-a-bug had 37 catches,
  5 confirmed (14%). No flaky catches in 54 after three reruns each. Blinding was by
  instruction only.
- **The maintainer's own review** fixed two control-commit issues within minutes. The loop's
  value is in what is left: variants, one-sided fixes, structure.
- **Structural audit (2026-11-06,** the untangle method): 9 bugs found along the way; 7 now
  fixed and merged, each with a test that catches its return. Its 98 structural items became
  the maintainer's own refactor ledger.
- **Open Code Review scan** (earlier, local notes): about 47% of comments were not bugs;
  about 1 in 30 became a PR.
- **Grim Prompter** (one run): 0 confirmed defects. Used for mapping, not finding.

### 12b. Dry run on the owner's website (2026-11-10)

A static site (HTML, CSS, JS, a Python build; about 230 tests) that five tools had audited
two days earlier. Every stage ran in scratch clones; results were then merged, pushed and
deployed on the owner's go. Roles were separated by instruction, not VMs. The owner was
also the maintainer, so throttle, the question route's delay, duplicate-work checks,
section locks, staleness and Swift were not exercised.

| Stage | Result |
|---|---|
| Look | 6 finders, 24 candidates plus UX notes; Parent found 0 after 21 builds |
| Group | 17 routed items (v0.7 said 16; that was a miscount); two root causes found by 2 and 3 finders |
| Prove | The Decider re-ran the key proofs; none was false. Same model family, so not a precision measurement |
| Route | 4 PRs (2 Fix, 1 Untangle, 1 Durability), 5 questions, 8 parked |
| Fix | 4 fixes, each RED then GREEN, all gates passed |
| Review | One agent per fix did review and attack. 1 request-changes (a regression the gates missed, found in review); 3 approve-with-notes; one real production bug the new tests could not see (found in attack) |
| Repair | 1 round, RED test of the finding first |
| Questions | 4 answered by the owner in one message; produced 2 more fixes and a written rule |
| Outcome | 9 commits merged, pushed, deployed, verified byte-identical live |
| Cost | About 20 agent runs and 2 hours, including deploy |

Likely to hold elsewhere: the harness lessons (step 0), write scope, the repair round,
blast radius as a script, named publish states. Probably specific to this run: how fast
and useful the questions were (the owner answered his own), "none was false", agreement
between finders on one model family (two cases), and the cost.

### 12c. Corrections from the outside review

v0.7 said "three named publish states" above a table of four; said 16 items where the
routes add to 17; left 9 backtest cases unexplained; drew a conclusion from the backtest
it did not support; and described review and attack as two roles when one agent did both.
All are corrected above.

## 13. Sources and what each contributed

| Source | Contribution |
|---|---|
| Local backtest | Most loop-fixed bugs were old; intent-aware tests only |
| Meta, Catching JiTTests (2026) | Parent oracle (parked); rule-based plus model filtering |
| OpenAI, "A thousand fewer paths to root" (2026) | Scout and reachability; cheap screen; time-boxed proof; mechanism check; separate impact step; root-cause grouping; check maintainer activity |
| Alibaba Open Code Review | Scripts for what must not fail; twin bundles; area rules; location check; precision first |
| ksimback tech-debt-skill | Orient before judging; "looks bad but is fine"; surprises; living map |
| FMSM | Not assessed is not clean; Test strength; evidence rubric |
| Trail of Bits (skills, coop, devcontainer, Semgrep) | VM isolation; bugs become Semgrep rules; post-patch validation; sealed evidence |
| Grim Prompter | Threat model as the harm map; data inventory; threat-model the loop |
| caldoai untangle-codebase | Structure oracle; special cases as signals; one fix behind several problems |
| Uncle Bob's ub-mode | Attack the premise; fixer rules; `crapper`, `dryer`, `mutator` |
| Owner's break-it prompt | Break-it oracle (Appendix A) |
| fast-check | Property oracle engine (Appendix A) |
| k6 and the local load rig | Load oracle (Appendix A) |
| TruffleHog | Not adopted; see section 9 |
| Meta Astryx (its internal test tooling) | Accessibility pattern contracts; instruments prove themselves; five rules for testing the loop |
| Dry run on the owner's website | Preflight; write scope; blast radius; fixture diversity; answers as spec changes; repair round; named publish states |
| Claude Fable 5.2 review (2026-11-10) | Comparison gate; expectation source; enforced isolation and host publisher; Classify; defined proof parts; timing rule; blast radius script; differential, stateful and old-file testing; recall by planted bugs; trims |

---

## Appendix A. Not built

Nothing here is part of phases 0 to 2. Each item enters rollout only with the owner's go and
its own pass criteria. Kept so the reasoning is not lost.

### A1. More oracles

| Oracle | Checks the code against | Finds | Notes |
|---|---|---|---|
| **Spec** | ACs, algorithm doc | Code wrong from the start | First candidate for phase 3, in one area with strong ACs. Many old bugs have no AC, so expect gaps |
| **Break-it** | The running app, used by six lenses (A2) | Crashes, false "saved", races, traps, other users' data | Web widget first. First check: can it run locally without a Shopify login or tunnel? Playwright cannot drive the iOS app |
| **Property** | Invariants (unit conversions round-trip) | Edge cases nobody wrote down | Loop-side `fast-check` only; the shrunk failure ships as a plain example test. Invariants are loop-inferred, and clinical ones (for example "a worse lab value never removes advice") need the maintainer's answer first |
| **Test strength** | Mutants the tests should kill | Fake-green tests | `mutator` stays a fixer gate in the core |
| **Data flow** | A data inventory: which personal data may go where | Health data reaching logs, analytics or third parties; deletes that miss a copy | Always classified private |
| **Load** | Thresholds: p95 under 1 s, errors under 1%, memory flat | Leaks, slow paths, crashes under concurrency | Isolated rig only, never production. Its one run found a real memory leak |
| **Signal** | Error reports, user reports, the maintainer's agent's notes | What tests cannot reach | **Off until a redaction step exists.** Sources may hold real health data and attacker-written text; where they come from is not yet defined |
| **Parent** | The previous commit, read through intent | Regressions | **Parked** (owner, 2026-11-10). 2 regressions in 74 backtest fixes, 0 in the dry run. Returns only if a regression the maintainer's agent missed turns up |

### A2. Break-it lenses

One isolated browser agent per lens, against a local build only, with synthetic accounts
and data. Chaos and timing (double clicks, back mid-save, many tabs); Weird input (emoji,
5,000 characters, wrong units); Slow network and small device (throttled, offline, phone
size in Chromium and WebKit emulation); Sneaky (other users' IDs, edited requests, expired
sessions; own two test accounts only; always private); Keyboard and assistive tech (focus
order, labels, `axe`, pattern contracts); Newcomer (no instructions, an older user). What
counts as broken: a crash or console error, lost data, saved data that does not match what
is shown, a false success, an `axe` violation or keyboard trap, another user's data.
**Confusion alone is not a bug:** Newcomer notes go to Question as UX notes.

**Accessibility pattern contracts.** Each widget pattern (dialog, switch, tabs, menu,
combobox) gets one written contract from the WAI-ARIA patterns, and the test asks the
browser what it exposes. Prefer real browser settings (text size through the DevTools
protocol, reduced motion, forced colours) over injected CSS.

### A3. New testing methods (from the outside review)

- **Stateful sync testing.** Generate sequences of connect, edit and disconnect across
  two devices against a fake cloud, and check the end state.
- **Old stored files.** Keep a set of files written by earlier versions of each platform,
  and test that every version still reads them in both engines.
- **Differential testing beyond twins.** Once twin differential tests work (core, phase 2),
  extend them to pairs that are not twins but should agree: for example, the same value
  computed by the widget and by the server.
