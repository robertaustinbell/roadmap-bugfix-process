# Regression review

How to turn a confirmed finding into a regression test that proves the bug, and
then into a fix the test proves. This is the method the Decider uses to confirm a
bug and the Bug fixer uses to write RED before GREEN.

Related: [evidence-bar.md](evidence-bar.md) (what counts as confirmed),
[quality-gates.md](quality-gates.md) (what the fix must pass),
[validation-and-sandbox.md](validation-and-sandbox.md) (where to run it).

All inputs are synthetic. No real patient or health data in tests, fixtures,
logs or PR text.

## Contents

1. [Pin the behaviour that is violated](#1-pin-the-behaviour-that-is-violated)
2. [Build fixtures from an independent contract](#2-build-fixtures-from-an-independent-contract)
3. [Write RED that fails for the right reason](#3-write-red-that-fails-for-the-right-reason)
4. [Pair every witness with a control](#4-pair-every-witness-with-a-control)
5. [Drive the real path end to end](#5-drive-the-real-path-end-to-end)
6. [Schedule races on purpose](#6-schedule-races-on-purpose)
7. [Quantities, units and dates](#7-quantities-units-and-dates)
8. [Failure, retry and uncertainty](#8-failure-retry-and-uncertainty)
9. [Privacy and telemetry](#9-privacy-and-telemetry)
10. [Trust-boundary guards](#10-trust-boundary-guards)
11. [Verify and package](#11-verify-and-package)
12. [Say what the test does not prove](#12-say-what-the-test-does-not-prove)

## 1. Pin the behaviour that is violated

- Pin the commit you inspected. Every claim names it.
- Name the user story acceptance criterion (or code comment, or documented
  contract) that the code violates. No contract, no bug: it becomes a question for
  the maintainer.
- Read known exceptions and deferred decisions first. An explicit deferred policy
  is not a missing implementation.
- Separate "this code path is wrong" from "this happens to real users often". A
  mocked provider proves the tested contract, not deployed behaviour.

## 2. Build fixtures from an independent contract

- Build provider fixtures from the provider's documented wire shape, not from the
  fields the application reads. A mock copied from the bug makes old tests pass.
- Read the current exported enums and full response shape before writing a
  fixture. A guessed status or unit spelling creates a harness failure that looks
  like the bug.
- Give each outcome category a distinct non-zero count, so swapped or duplicated
  fields cannot pass through equal totals.
- Expected values come from the contract, never from running the buggy code and
  copying its output.

## 3. Write RED that fails for the right reason

- Run the new test against unchanged production code. It must fail on the
  intended assertion, not on a load error, a missing import or a fixture typo.
- If the test fails to load, repair the harness before treating anything as
  evidence about the application.
- A test that passes while observing the bug ("asserts the wrong value is
  returned") is a witness, not a regression. The regression asserts the correct
  behaviour and fails today.
- Tests that also pass at base are controls. Put `control:` in their titles so the
  base failure count is honest.
- Keep production edits out of the RED run: stash only production paths
  (`git stash push -- <production paths>`) so new tests stay in place.

## 4. Pair every witness with a control

Every confirmed claim has a failing witness and a passing control.

- The control shows the harness can pass: same setup, the valid case.
- Keep neighbouring behaviours as controls so a fix cannot trade one bug for
  another (for example: results still land under the right index; definite
  failures stay retryable; unrelated records are untouched).
- Pair every negative assertion (`not.toContain`, "no write happened") with a
  positive one that the thing it inspects exists.

## 5. Drive the real path end to end

- Trace a synthetic input through the real dispatcher, the write, and a fresh read
  by the real consumer. A success response can still leave the value unchanged or
  stored where the consumer never reads it.
- Prefer real UI gestures, the real store and real persistence, with only the
  outer boundary (network provider, model, telemetry transport) replaced.
- Route tests that mock the function under test do not test it. Test the shared
  builder or writer itself.
- When many callers share one function, fix and test at that function. Then list
  callers that bypass it, and say whether they are covered.

## 6. Schedule races on purpose

- Use barriers or deferred promises to force one specific interleaving. Do not
  hope that simultaneous promises expose a race.
- For two-tab or two-device cases, open both sessions before the failure, then
  release events in the order the finding describes.
- For "last slot" quota races, hold two independent calls behind a barrier and
  count accepted provider operations, not returned messages.
- Confirm timing from recorded timestamps, not from intent.

## 7. Quantities, units and dates

- Compare quantities, not spellings. Test the same number in different units and
  equal quantities written differently.
- Use the existing conversion path as the control. Never add a second factor
  table, and never change a clinical factor to make a test pass. Clinical values
  are the maintainer's decision.
- Test the raw text before sanitising, not only the parsed number: negative signs,
  exponents, inequality symbols, pasted multi-cell text, decimal commas.
- Freeze the clock. Run date tests in the CI timezone (`TZ=UTC`) and in a local
  timezone when dates matter. Check that unknown date precision is not silently
  turned into a confirmed day.

### Health-data probes

Bug shapes that recur in health records. Finders check scanned code for each one;
the Decider writes a synthetic witness for each it confirms.

| Probe | What goes wrong |
|---|---|
| `x \|\| default` on a value that can be `0` or `""` | A real zero (0 mmHg change, 0 drinks, an empty note) is replaced by the default. Use `??` or an explicit check |
| Dedupe keys | Two genuine readings taken in the same minute merge into one because the key is (metric, minute) |
| Date filters on strings | `"2026-11-03T23:30-05:00" < "2026-11-04"` compares text, not instants; readings near midnight move day across timezones |
| Fraction vs percent | SpO2 `0.98` from one source and `98` from another, graded on one scale |
| Paired values | Systolic and diastolic stored or synced separately, so one half updates and the pair no longer matches a reading |
| Overlapping sources | The same reading imported from the phone and a device is counted twice in averages and trends |
| Empty from a permission-gated read | A read that returns no rows because permission was not granted is shown as "no data" instead of "not allowed" |
| Label vs value at the boundary | The badge, colour or text says "normal" while the value sits on or past the threshold. Test exactly at each threshold and one step either side |
| Same unit, different quantity | Two values in mg/dL measured by different methods (calculated vs direct LDL) are charted or compared as one series |

## 8. Failure, retry and uncertainty

- Separate "definitely not written" from "may have been written". A lost success
  response after the provider stored the bytes is a possible write. Unconditional
  refunds or retries can duplicate accepted work.
- Keep possible-write history across the whole operation, not just the last
  attempt. Assert the machine-readable flag, not only the message.
- Keep the original error class through wrappers. Wrapping an auth refusal as a
  generic error can disable reconnect even when the message improves.
- Exercise both a stall before headers and a stall during the body. A settled
  `fetch` promise is not a complete download.
- Read each dependency's failure contract before stubbing it. A rejected promise
  and a fulfilled `false` are different failures.
- `array.forEach(async ...)` does not wait. Code after it runs before any of the
  awaits finish, and their errors are lost. Test that the caller sees every result
  and every failure.

## 9. Privacy and telemetry

- Inspect the final event that would leave the process, not the call site. Build
  it with the real tags and run the real scrub hook. Never send a witness to a
  live telemetry service.
- Use invented names and references as the sensitive text, then assert they are
  gone from the final event.
- Check breadcrumbs, extra fields and contexts as well as the message.
- Do not call a gap a leak until a current call site sends that data.

## 10. Trust-boundary guards

- Call the exported guard with synthetic inputs. A wrong answer from a pure
  function is a guard gap. It is not proof of live exploitation.
- Pin intended rejections and allowed public controls in the same test.
- Any finding that could be a security vulnerability is reported privately per
  the repository's `SECURITY.md`. It does not become a public issue, PR text or
  test name until the maintainer says so.

## 11. Verify and package

- Install the lockfile in an isolated checkout and match CI's Node version.
- Type-check test files as well as production code.
- Count results from the JSON reporter's assertion results, not from stdout.
  Reconcile the tests you asked to run with the tests that actually ran.
- Compare full-suite inventories as sets of file and test name, not totals.
  Additions can hide removals.
- After any review repair or source edit, rerun the changed evidence and replace
  stale numbers. Keep the earlier receipt as history; do not relabel it.
- Export the patch and check it reconstructs the tested tree: apply its exact
  bytes to a fresh checkout at the pinned base and compare file hashes. A clean
  `git apply --check` does not prove the bytes match.
- Check claimed conflicts with sibling PRs using
  `git merge-tree --write-tree --name-only <head-a> <head-b>`. Shared filenames
  alone do not prove a conflict.

## 12. Say what the test does not prove

Every PR states its limits in plain words. Examples:

- "Simulated unload events; not a real browser tab close."
- "Mocked HTTP; checks the request we build, not the provider's acceptance."
- "Chrome phone emulation; not Safari."
- "Extracted policy SQL on a throwaway database; not the deployed instance."
- "Local fixtures; not deployed cross-user access."

A survivor or an untested surface marks a weak test or an open question. It is
not a bug until it meets the [evidence bar](evidence-bar.md).
