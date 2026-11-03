# Code standard

The standard every loop fix must meet, and the rules the finders and Decider use to
judge code. The [Bug fixer](../agents/bug-fixer.md) applies it; the
[Coach](../agents/coach.md) reports on how well fixes meet it.

Status: a working draft, derived from bug classes in the roadmap repo's own public
history and from checkable requirements in outside frameworks. It is offered to the
maintainer; it is not his adopted policy. Where it conflicts with the live
`CLAUDE.md`, `docs/loops/` or `.github/workflows/` in the roadmap repo, **the repo
wins**. Read those files at the current `upstream/main` before each fix; they change
often.

Related: [process.md](process.md), [evidence-bar.md](evidence-bar.md),
[human-review-and-escalation.md](human-review-and-escalation.md).

## 1. Requirements

1. **Privacy and security come first.** This is a doctor's system that handles
   people's health data. When rules compete:
   privacy and security > clinical correctness > data integrity > features > style.
2. **Code nobody reads must be trustworthy.** If it passes the gates, it can be
   trusted. Passing is strong evidence, not proof: a wrong spec and harm nobody
   predicted can still get through.
3. **Humans own the spec.** Brad owns clinical values, privacy promises and user
   stories. Agents implement and verify. Agents never change what a rule, threshold
   or acceptance criterion means.

## 2. How rules work

Every rule is a card: rule ID, kind, check, and when to retire it.

Kinds:

- **Prevent:** the bug cannot be written (a type, a single function, a lint ban).
- **Detect:** a test or scan catches it.
- **Contain:** if it gets through, the damage is limited.

Rules about rules:

1. **No check, no rule.** A rule nothing enforces is deleted.
2. **Strongest check wins:** type, then single function plus lint ban, then test,
   then CI script, then review checklist, then prose.
3. **Every check proves it can fail** with a seeded input it must reject. A check
   that passes on zero inputs is broken.
4. **Strict and ratchet tiers.** Strict-tier code that a change touches must meet the
   thresholds. Ratchet-tier code may not get worse. Old code is grandfathered, but
   grandfathering is not a waiver for a changed strict-tier function.
5. **One door.** Anything security- or privacy-relevant (identity, erase, consent,
   egress, logging, text cutting, unit conversion) happens in one function, and lint
   bans the bypass. The most common bug shape in the history is one path that
   skipped the shared helper.
6. **Thresholds are human-owned.** Changing a threshold, a tier or the gated-path list
   needs human approval. A baseline run calibrates enforcement; it does not grant
   permission to accept a weaker threshold.
7. Frameworks are cited as "adapted from", never as a conformance claim. Which laws
   apply is a legal question for Brad.

## 3. Rules

`[core]` marks the first wave. IDs are stable so findings and PRs can cite them.

### PRIV: health data goes only where it is allowed

| ID | Kind | Rule | Check |
|---|---|---|---|
| PRIV-1 [core] | Prevent, Detect | Data leaves only through an allowlist of typed fields. Raw `console.*` only inside one logger. | Canary test pushes a fake health value through every exit (error tracking, logs, analytics, error responses) and asserts it never appears. |
| PRIV-2 [core] | Contain | One egress registry per surface; server fetches go through one guarded client (host, size, port, timeout). CSP is generated from the same list. | Test fails if `fetch(` appears outside the client. |
| PRIV-3 [core] | Detect | Every privacy promise (docs, in-app wording, `CLAUDE.md`) maps to the test that enforces it. Wording no broader than the test. | CI fails on a promise with no test or a named test that does not exist. |
| PRIV-4 [core] | Prevent, Detect | Erase and consent are one door each, tested end to end across devices/tabs, sync, reload, migrate and merge in both orders. Success reported only after the erase is written. | End-to-end erase and consent tests. |
| PRIV-5 | Detect | Retention is declared per stored server field. | CI fails if a migration adds a text column with no retention class. |
| PRIV-6 [core] | Detect, Contain | Health data never reaches public places (commits, analytics, session recordings, public repos). | Commit scan for record-shaped data; recorder masking test per health surface. |
| PRIV-7 [core] | Prevent, Detect | A data inventory as code lists every stored or sent field and every outside service. | CI fails on a column, schema field, telemetry field or egress host missing from it. |
| PRIV-8 | Detect | Export, correction and erase are tested journeys. | End-to-end tests on synthetic data. |
| PRIV-9 | Detect, Contain | Append-only audit events (no health values) for logins, admin access, erase, export, consent. | Tests assert each event is written and holds no health value. |
| PRIV-10 | Prevent, Detect | Consent is recorded, separate per purpose, versioned, and withdrawable in one step. | Consent record tests. |

### SEC: only the right person can do the right thing

| ID | Kind | Rule | Check |
|---|---|---|---|
| SEC-1 [core] | Prevent | Identity comes only from a verified signature or session, never from query params, bodies, client-settable headers, editable metadata or model output. | Type-level: identity only from the verifier's return value; tests for repeated params. |
| SEC-2 [core] | Detect, Contain | Every route declares its gate or sits on a public list with a reason; every server table denies by default. | Route-inventory test with a minimum route count; catalog check on an ephemeral database. |
| SEC-3 [core] | Prevent | Fail closed: errors in auth, caps, locks, rate limits or safety gates mean deny, returned as a typed result. | Lint for `catch` blocks that return allow/true/0/empty in those modules. |
| SEC-4 | Prevent | Untrusted content never runs or escapes: uploads served as downloads, one encoder for paths/URLs/headers, size caps, parameterised filters, no untrusted text in CI shells. | Tests per entry point. |
| SEC-5 | Detect | Auth flows are tested out of order (skip, repeat, reorder). | Flow tests. |
| SEC-6 | Prevent | No unapproved dependencies; installs with `--ignore-scripts`; no `eval`. | CI fails when the lockfile gains a package not on the approved list. |
| SEC-7 | Prevent | Results bind to one commit; workflows, tests, thresholds, baselines and this standard are protected paths a code change cannot edit in the same change. | CI path check. |
| SEC-8 | Detect | OWASP ASVS (pinned version) and MASVS mapping file. | CI fails on a missing or dangling ID. |
| SEC-9 | Prevent, Detect | Supply chain: actions pinned by SHA, tools checksum-verified, images pinned by digest, least-privilege workflow permissions. | Static workflow scan. |
| SEC-10 | Detect | Security headers on every response. | Per-route header test. |
| SEC-11 | Detect | OAuth server hardening (exact redirects, PKCE, single-use short-lived codes, token checks). | Violation tests. |

### TRUTH: the app never claims more than it knows

| ID | Kind | Rule | Check |
|---|---|---|---|
| TRUTH-1 [core] | Prevent | Missing, refused, unknown and zero are different typed values. Unknown never becomes 0, false, "" or a default. Censored results keep their comparator. Safety gates treat unknown as the risky case. | Types plus boundary tests. |
| TRUTH-2 | Detect | Errors, refusals, cut-off model output and non-JSON 5xx responses are never shown, stored or replayed as content. | Forced-failure test per route. |
| TRUTH-3 [core] | Prevent | A save returns `saved` (with proof), `failed` or `unknown`; UI wording comes from that type. | Success type cannot be built without proof. |
| TRUTH-4 | Detect | Nothing silently dropped or undercounted: paged reads handle row caps; counters record failures; switches over unions are exhaustive. | Tests and exhaustiveness checks. |
| TRUTH-5 | Prevent | Safety content is tagged and size caps never drop it. | Fill-to-cap test. |
| TRUTH-6 | Detect | No ignored results: every database `error` checked before `data`; no floating promises. | Lint and tests. |

### EDGE: outside data is checked where it enters

| ID | Kind | Rule | Check |
|---|---|---|---|
| EDGE-1 [core] | Prevent | Requests, provider responses, stored data read back and model output are parsed by a closed schema before use. One strict number parser (locale-aware, refuses ambiguity) with plausibility ranges. Unknown units refused, never guessed. | Schema and parser tests. |
| EDGE-2 | Prevent | One function each for unit conversion, text cutting (surrogate-safe) and path/URL/header encoding; lint bans alternatives. | Lint ban plus locale label tests. |

### ONE: one decision lives in one place

| ID | Kind | Rule | Check |
|---|---|---|---|
| ONE-1 [core] | Prevent | Clinical thresholds and the decisions built on them live once, in the shared clinical core. Other surfaces render; they do not recompute. Round only for display. | Duplication gate plus tests on each surface. |
| ONE-2 | Detect | Each threshold is tested below, at and above, with values from the cited guideline. Brad confirms the cited value. | Boundary table tests. |
| ONE-3 | Detect | One request schema shared by client and route; contract test posts the client's real body to the real route. | Contract tests; stale check on generated copies. |
| ONE-4 [core] | Detect | A machine-checked clinical hazard log; severity 3+ needs a test; Brad owns the file. | CI fails on a missing or skipped named test or an untagged hazard. |

### TIME, ONCE

| ID | Kind | Rule | Check |
|---|---|---|---|
| TIME-1 | Prevent | Clinical code never reads the clock; tests run in UTC and one other zone. | Lint ban on `Date.now()` / bare `new Date()` in the clinical core. |
| TIME-2 | Prevent | Dates parsed once and checked; impossible dates refused; the user's day uses the user's zone. | Parser tests. |
| ONCE-1 [core] | Prevent, Detect | Writers cannot overwrite what they have not seen (conditional writes); merge gives the same result in any order and when repeated. | Property tests. |
| ONCE-2 | Prevent | Running twice equals running once (deterministic IDs, unique constraints, durable replay protection). | Retry tests. |
| ONCE-3 | Detect | Count after commit. | Tests. |

### TEST: tests that can fail

| ID | Kind | Rule | Check |
|---|---|---|---|
| TEST-1 [core] | Detect | A bug-fix test is seen failing on the unfixed code, on an assertion. Every gate has a canary it must reject. | RED log in the PR; mutation gate. |
| TEST-2 [core] | Detect | No self-graded tests: expected values come from the spec, guideline or hand calculation. Each rejection test has an acceptance sibling. | Review checklist; mutation gate. |
| TEST-3 | Detect | The suite cannot shrink silently: skips counted; deleting a test, story or AC needs a stated reason. | CI skip count; review. |

### GATE: deterministic quality gates

Same code in, same verdict out, no model judgment.

**Strict tier (gated paths):** the shared clinical core, and server modules for auth,
identity, erase, consent, egress, telemetry and logging. Everything else is ratchet
tier. The exact path list is a human-owned file.

| ID | Kind | Rule |
|---|---|---|
| GATE-1 [core] | Prevent | The compiler is never silenced. `tsc` strict on every project, tests included. In strict paths, no new `@ts-ignore`, `@ts-expect-error`, `any` or non-null `!` without a waiver naming the line and reason. |
| GATE-2 [core] | Detect | CRAP 10 or less for every new or changed function, in both tiers. A function already over 10 at base may stay no worse than base and is flagged for a later cleanup PR; it is never split inside a bug fix. Fix by testing first, splitting second. |
| GATE-3 [core] | Detect | No surviving or uncovered mutants on changed lines in strict paths, except equivalent mutants named with a reason. Ratchet tier: a file's mutation score may not drop. Zero killed means the harness is broken. |
| GATE-4 | Detect | No new duplication at similarity 0.8 or above in strict paths. (Not yet part of the per-PR gates; see section 4.) |
| GATE-5 | Prevent | Gate tools pinned by version or commit, run on a clean copy, and write a receipt (tool pin, commit, inputs, result). |

### SHIP

| ID | Kind | Rule |
|---|---|---|
| SHIP-1 | Prevent | Gates have three outcomes: pass, fail, could-not-run. Could-not-run is fail. A missing tool is never reported as a pass. |
| SHIP-2 | Detect | Gates cover everything that ships: every built file typechecked; browser-target floor respected; environments never share build output. |

### Parked ideas

| Idea | Why parked |
|---|---|
| Repo-wide 100% line coverage target | Coverage shows code ran, not that a test would fail if it were wrong; agents meet the number with assertion-light tests. At 100% coverage CRAP equals complexity. GATE-3 is the stronger check. |
| Function-length caps | GATE-2 covers the risk more precisely. |
| Generic scanners as blocking gates | No confirmed app bugs in trial runs. Revisit if one catches seeded bugs the gates miss. |

## 4. Per-PR gates

Every loop PR passes all of these at its **final head** before it is published. If
the head moves, the gates run again. The step-by-step procedure and receipt format
are in [quality-gates.md](quality-gates.md); the PR body template is in
[pr-description-template.md](pr-description-template.md).

1. **Strict `tsc`** on the three projects the repo's CI checks (at the time of
   writing: `widget-src/tsconfig.json`, `packages/health-core/tsconfig.json` and the
   server config). The root `tsconfig.json` is not a gate: compare it base vs head and
   require no new error on a changed line.
2. **CRAP** (`crapper`, pinned) on scratch copies of base and head, with the same
   test scope on both (every test file importing a changed production file, plus the
   PR's new tests). State the scope next to every number. Thresholds per GATE-2.
   Do not refactor legacy hot spots inside a fix PR; if the fix cannot meet the
   gate without one, stop and put it on the human review list.
3. **Mutation ratchet** (`mutator`, pinned; and Brad's own Stryker config where it
   covers the file) on each changed production file, using every importing test file.
   Count mutants on lines the diff adds or changes. Each must be killed, or named in
   the PR body as equivalent with a reason. Where the tool has no operator for a
   construct, hand-mutate each changed clause on its own. Extend Brad's existing
   Stryker setup; do not add a second mutation tool upstream.
4. **FMSM incremental review** (`fuck-my-shit-mountain`, `incremental` mode) on
   `<base>...<head>`, read-only, by an agent that did not write the fix. No PR ships
   with a confirmed Medium-or-worse problem the diff introduces or worsens. Record
   per-dimension direction (better / same / worse) for each touched dimension. A
   touched dimension that gets worse holds the PR for human review.
5. **Full test suite** at the exact head, with `TZ=UTC` and CI's Node version,
   compared with an untouched baseline at the same base (compare failing sets, not
   against zero). Run suites one at a time. A lone failure in an untouched file is
   rerun alone on both head and base before it is called load or flake; report it
   honestly, never as green.
6. **Secret scan** with the version CI pins, on the head, before push. Fix a false
   hit by renaming the identifier, never by allowlisting.
7. **Independent review** approves the current head (see
   [bug-fixer.md](../agents/bug-fixer.md#independent-review)).

Duplication (`dryer`) is not part of the per-PR gates yet.

## 5. Repo conventions the fix must follow

Read these live in the roadmap repo; summarised here so a fixer knows to look.

- **Lane A (bug fix):** name the violated user-story acceptance criterion (add one
  with the next free number or a letter suffix if missing), failing test citing the
  story ID, smallest production change, regenerate the stories HTML, `test:all`.
- **Lane B (feature, schema, merge, clinical text):** needs Brad's agreement before
  code. The loop routes these to `question` or `human-review`, never `fix`.
- **Clinical sources stay in sync** (algorithm doc, evidence file, roadmap text) or
  the PR says why not.
- **Deletion-first:** state net production lines of code and what was deleted, in the
  commit message and the PR body.
- **No new dependency** without a one-line justification. No abstraction layers or
  drive-by refactors in a fix.
- **Synthetic data only** in every test and fixture.
- Name test files after the behaviour or area, not internal finding IDs.

## 6. Pull request body

Every loop PR body has these sections, in this order:

1. **What goes wrong** (one synthetic case: expected vs actual, who sees it).
2. **Violated acceptance criterion** (story ID and AC).
3. **The change** (what and why; net production LOC; what was deleted).
4. **How to reproduce** (one command that fails on unfixed `main` and passes after).
5. **Testing**: the failing test or reproduction first, then the gates passed (tsc,
   CRAP before→after, changed-line mutants killed/total, FMSM incremental result,
   full suite passed/skipped/failed vs baseline at the same base). Anything not run
   says "did not run" and why.
6. **Risk**: low / medium / high, set by what the change touches (see
   [evidence-bar.md](evidence-bar.md#severity-and-risk)), with one line of reason.
7. **How to revert**: the exact revert (for example `git revert <sha>`) and anything
   it does not undo (data written in the meantime, a migration).
8. **Behaviour change** (if any, including removed accidental behaviour).
9. **Needs your decision** (numbered, options, "as submitted" marked), when any.
10. **Further testing needed** (live provider, built bundle, iPhone), when any.
11. A closing line saying the PR was prepared by an automated loop at the operator's
    request, and the base SHA.

The body must never contain the token `VERDICT:` and never describe a security
weakness. Every number in it comes from a run log at the published head.
