# Validation and sandbox

Where and how fixes are run so that results are honest, repeatable and safe.
Three layers:

1. [Offline synthetic sandbox](#1-offline-synthetic-sandbox): target code runs in
   a locked-down container with no network and no credentials.
2. [Full suite](#full-suite): the whole test suite at the exact head, run serially.
3. [Live validation](#3-live-validation): browser, two-tab, real cloud storage or
   a phone simulator, for what offline tests cannot settle.

Every result records its base, head, environment and evidence level. Missing or
stale evidence is `could_not_run`, never a pass.

Placeholders: `$WORKDIR` is your local working folder for the loop, `$WORKTREE`
is one fix's checkout, `$SCRATCH` is a disposable copy, `$SOCKET` is the
container daemon you were authorised to use.

## Synthetic-only rule

All test inputs, fixtures, screenshots and logs are synthetic. Never use real
patient or health data, the maintainer's production site or server, real user
accounts, or anyone's browser profile. Keep the client IDs, overrides and harness
code used for live checks out of every commit and PR body: grep the PR diff and
body for them before every push.

## 1. Offline synthetic sandbox

Use when repository code must not run on the host or reach any external service.
Setup, execution and publishing are separate permissions.

### Runtime boundary

- Use a dedicated runtime. Mount only the task's disposable source folder, never
  the home directory.
- Acquire a pinned public runtime image and locked dependencies from the manifest
  only. Disable dependency lifecycle scripts (`npm ci --ignore-scripts`). Permission
  to download dependencies is not permission for target code to use the network.
- Run target code only in containers with:
  - `--network=none`
  - a non-root user
  - `--cap-drop=ALL --security-opt=no-new-privileges`
  - read-only root, source, dependencies and Git metadata
  - a bounded writable scratch area
  - limits on CPU, memory, PIDs, file size and wall-clock time
- Inspect the actual container settings before releasing its execution gate.
- Name the daemon explicitly (`docker --host "$SOCKET"` or `--context`) for create,
  inspect, start and cleanup. The shell's default daemon is not necessarily the
  authorised one.

### Preflight

Before any broad suite or fan-out to workers:

1. In the container, check `node -v` matches CI.
2. Compare the source lockfile hash with the lockfile the dependency volume was
   built from. A volume built from an older lockfile certifies only that lockfile.
3. Run one representative existing test and see it pass.
4. Exercise any shell or native-tool fixture the fix adds, in the real container.
   A passing JavaScript slice does not prove native tools are present.
5. Run the complete gate harness on one candidate end to end, including steps
   after the build.

### Evidence boundaries

- Freeze the source before checks. Afterwards compare commit, changed paths and
  file hashes. Source that changed during a run makes the run stale, even if it
  exited 0.
- Keep harness failures separate from product failures. Run unchanged upstream
  under identical settings before classifying a failure.
- Save structured test reports on failed runs as well as passing ones, before
  removing the container. A missing report is a harness failure, not an empty pass.
- Files a generator writes inside a read-only container must be exported and
  compared with a fresh generation before they replace the host copy.
- Tests that shell out to `git` need a self-contained Git snapshot whose HEAD
  equals the copied source base.
- When several workers share one small runtime, put a shared lock around
  container execution. Keep reading and editing parallel; serialise only the heavy
  checks.

### Real databases instead of mocks

When a claim depends on database policy (foreign keys, row-level security) or on
the real query parser, mocks prove nothing. Run a throwaway database (and API
layer, if needed) in a container with no network and no published ports, tmpfs
storage, synthetic roles and a synthetic secret. Rules:

- Run authorisation cases as the restricted role, never as the owner. An owner
  bypasses the policy and the test becomes meaningless.
- Apply the candidate policy over the existing one, not only to a fresh schema.
  Permissive policies combine with OR.
- Assert the expected SQL error code. An arbitrary error is not a denial.
- Run the harness under `env -i` and assert the target URL is `http://127.0.0.1:...`
  before importing any app module. The host shell may export real service URLs and
  keys.
- Remove containers in a `finally` path.

## Full suite

The full suite runs at the exact head that was reviewed and gated.

1. **Serial, one at a time.** One suite saturates a laptop. Parallel suites push
   load high enough to time out timing-sensitive tests. Parallelise everything
   else (fixing, reviewing, rebasing); serialise suites.
2. **Match CI.** `TZ=UTC`, CI's Node major, the locked dependencies, every
   workspace's `node_modules` installed per worktree (no symlinks between
   worktrees).
3. **Own the process.** Start vitest directly in its own process group with a
   JSON reporter and a timeout, for example:

   ```sh
   TZ=UTC node node_modules/vitest/vitest.mjs run \
     --maxWorkers=4 --reporter=json --outputFile="$OUT/full-suite.json"
   ```

   On timeout, kill the whole group. A hung suite at 0% CPU stalls every PR behind
   it.
4. **Do not edit a worktree while its suite runs.** That run is void even if it
   passes. When a repair lands mid-run, stop and restart.
5. **Rename superseded results** (`full-suite-superseded.json`) so stale evidence
   cannot be read as current. Record which head each surviving result belongs to.
6. **Update the PR body in the same step** as the result lands: head, passed,
   skipped, failed, counted from the JSON assertion results.

### When the suite fails

```
failure in a file the diff touches        → real; repair
failure reproduces when the file runs alone → real; repair
fails alone? no, and file is byte-identical to main, and
  different unrelated files fail on each run under high load → host load; requeue
same untouched file fails on two different heads → main flake; add to known list, tell Austin
```

- Solo-rerun only the failing files first (seconds). Never start a blind second
  full run on a real failure.
- Known load-sensitive files (timing assertions, long budgets) are accepted only by
  a solo rerun at the same head whose summary shows every test passed. A partial
  line like `7 passed (23)` is a failed rerun.
- Before blaming the loop's own workers for load, check what else is running.
  Do not stop the user's own processes.

### Before pushing

- Fetch, then check the head still merges cleanly with
  `git merge-tree --write-tree upstream/main "$HEAD"`.
- `merge-tree` finds only text conflicts. Also run test files main added or
  changed since the head's base, at the head:
  `git diff --name-only "$BASE" upstream/main -- '*.test.*'`.
- Run the secret scan CI runs, at the version CI pins, on every head before push.
  Fix a false positive by renaming the identifier, never by adding an allowlist
  entry.

### After upstream moves

A clean merge is not a correct result. For each open loop PR, test the merge onto
the new main (full suite and type-checks). Push a corrective commit only when
behaviour breaks, with the test that shows it, and add an "Update" note to the PR
body.

## 3. Live validation

For checks offline tests cannot settle. Run each check on upstream main **and** on
the fix branch. The comparison is the evidence.

Record each result in `LIVE-EVIDENCE.md` with exactly one level:

| Level | Meaning |
|---|---|
| `live_discriminating` | Main and the fix behave differently in the way the finding predicts |
| `live_not_discriminating` | The flow never reached the guarded path; unit tests remain the proof |
| `simulator_regression_level` | The fix adds no failures on the simulator |
| `not_run` | With the reason |

### General

- Serve locally built bundles on `127.0.0.1`, one port per tree. Never use the root
  dev command if it starts a hosted preview that affects production.
- Guest mode, synthetic values, fresh storage, a fresh browser context per lane.
- Install a route guard before navigation that allows only the local app origin
  and needed `data:`/`blob:` URLs. Abort telemetry, cloud, model and other external
  requests.
- Use real typing (`fill`, `press`) so the UI framework sees the change.
- HTTP 200 is not readiness. Require a rendered page.

### Two-tab checks

- The order tabs load decides what you test. To land an event while the other tab
  is still loading, load the sending tab first and hold the other tab's first read.
- Confirm timing from storage-event timestamps, not from intent.
- Name which writer produced an observed write. A write from a different writer
  than the one the fix guards is not evidence for the fix.

### Real cloud storage

- Use a dedicated throwaway project under the tester's own account, with the
  narrowest scope that works (for example a scope that sees only files the client
  created). Leave existing projects alone.
- The client ID stays in an uncommitted local override. Never copy a client secret.
- Sign-in is the human's action. The agent opens the window and waits.
- Never log a token. Log only a status line (token present, scope).
- Force races with an in-page hook, then compare fix and main.
- Cleanup is part of the check: delete created items and confirm the client sees
  zero, revoke the token and confirm it is refused, clear local storage, stop
  servers, scan logs for token strings, and ask the human to shut down the test
  project.

### Phone simulator

- A simulator runtime is a multi-GB download and needs the human's approval.
- If a binary package cannot be fetched, strip it in local build copies only, never
  in a worktree or PR, and disclose it.
- Undo a hand mutant with a reverse edit or only after committing the fix:
  `git checkout -- <file>` also drops an uncommitted fix.
- Compare **sets** of failing tests between main and the fix, not pass counts.
  Some failures (unsigned keychain access) are environmental and shared.

## Limits to state

Say in the PR body which of these apply:

- Simulated DOM events are not a real unload or navigation.
- Mocked HTTP checks the request, not the provider's acceptance.
- Browser phone emulation is not Safari or WebKit.
- A throwaway database checks the extracted schema, not the deployed instance.
- A synthetic restore is not production recoverability.
