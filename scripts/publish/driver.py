#!/usr/bin/env python3
"""Publish driver: checks approved fix folders, one at a time, opens or updates PRs, then waits for CI.
No AI. It never merges anything.

Sanitized from a working implementation; review before running.

Subcommands:
  driver.py run --round-dir R [--fixes-dir F]   loop until R/stop-driver exists (or R/_done-round and nothing left)
  driver.py publish <fix folder> [--go]         open ONE new PR (dry run without --go)
  driver.py repair <round pr folder> [--go]     push ONE approved repair to an existing PR (dry run without --go)
  driver.py ci <folder> [--wait-min N]          wait for CI on the head the driver pushed for this folder:
                                                CI-GREEN (exit 0), CI-RED.md (exit 4) or CI-PENDING (exit 3)
  driver.py addressed <ledger.jsonl>...         restart-rule check: has every PR in these ledgers had a
                                                maintainer action? exit 0 = all addressed, 1 = not yet

What the loop publishes:
- New PRs: each folder under --fixes-dir with STATE.json, whose highest-numbered review-<k>.json
  approves STATE.json "head" (see "Approval" below), with no HOLD.md, PUSH-REFUSED.md or
  NOT-REPRODUCED.md, not already final in <fixes-dir>/published.jsonl, and every PR number in WAIT-FOR MERGED.
- Repairs: each <round-dir>/pr<N>/ folder with STATE.json, meta.json and comment.md, the same review
  rule, not already final in <round-dir>/pushed.jsonl.

Approval (templates/review-verdict.schema.json): the file parses strictly (duplicate keys refused),
has no unknown fields, verdict "approve", "head" equal to the full 40-character head, the five
required checks all "yes", no blocking finding, nothing still open, and a text_sha256 entry matching
every file the driver will post. Editing a title, body or comment after review voids the approval.

Ledgers record each external effect as "attempted" before the first GitHub write, then
"observed_succeeded" or "observed_failed" after read-back. A rerun that finds an unfinished attempt
looks for the PR on GitHub and adopts it instead of opening a second one. Only observed_succeeded
counts as published.

For each ready folder, in order: textual merge pre-check against current upstream main; the publish/repair
dry run, then --go; then the CI gate on the pushed head. The local full suite is not a gate: the maintainer's
CI runs the whole suite on every push. LOCAL_SUITE=shared still runs it, serially and load-gated, when the
change touches SHARED_SUITE_PATHS (real failures are rerun alone; known-flaky files get up to 3 solo reruns).
A refusal writes PUSH-REFUSED.md in the folder; the loop skips that folder until a human moves it aside.

Checks before any push (publish and repair): the review approves this head and text; clean worktree; merges
clean; the fix commits are there; gitleaks; the secret-fixture check (the roadmap repo's own credential
shapes, tools/secret-rules.mjs at upstream main, on the added lines); for a repair, the in-review guard (no
push to a PR whose head an open claude/batch-* or claude/group-* PR body names: it is in the maintainer's
review).

CI gate (after the push): poll the check runs of the exact pushed head until all are complete or
CI_WAIT_MIN passes. All success, skipped or neutral: CI-GREEN in the folder, a line in ci.jsonl and
"PR #N ready, head <sha>" appended to report-outbox.txt in STATE_DIR for the Coordinator to post. Any other
result: CI-RED.md with the failing jobs and a short log excerpt; the folder goes back to repair. Still
running: CI-PENDING, polled again on every loop pass. A red head is never reported.

Review files are LOCAL JSON files. Never post a `VERDICT:` line to GitHub: the
maintainer's auto-ship workflow treats a bot comment carrying a `VERDICT: APPROVE` line as an approval.
This script refuses to post any PR body or comment that contains "VERDICT:". Our own bot comments
never count as approval, for us or for anyone.

Configuration (env vars):
  UPSTREAM_REPO     default DrBradStanfield/roadmap
  GH_FORK_OWNER     required for publish: the GitHub account whose fork holds the branches
  UPSTREAM_REMOTE   default "upstream"; PUSH_REMOTE default "origin" (the fork)
  ATTRIBUTION       optional: text every PR body / repair comment must contain (e.g. the agent's sign-off)
  NODE_BIN_DIR      optional: directory put first on PATH for the suite (the repo's CI Node version)
  EXTRA_PATH        optional: more directories for PATH (e.g. an OpenSSL 3 bin dir; the repo's
                    app-attest tests need OpenSSL 3, and macOS ships LibreSSL)
  LOCAL_SUITE       off (default): no local full suite; shared: run it only when the change touches
                    SHARED_SUITE_PATHS (comma-separated globs; default: health-core merge, sync and
                    record-session files, widget-src storage files)
  CI_WAIT_MIN       how long the CI gate waits for the pushed head's checks (default 20)
  CI_POLL_SEC       seconds between CI polls (default 60)
  WORKDIR           the roadmap clone; the secret-fixture check reads tools/secret-rules.mjs from its
                    upstream main. Missing rules refuse (fails closed)
  STATE_DIR         report-outbox.txt goes here (default: next to the ledger)
  KNOWN_FLAKY       comma-separated test files that time out under load (default: the four seen so far)
  DRIVER_MAX_LOAD   wait while the 1-minute load average is above this (default: 4 x CPU count)
  SUITE_TIMEOUT_MIN default 45; SUITE_MAX_WORKERS default 4 (only with LOCAL_SUITE=shared)
  GITLEAKS_BIN      default "gitleaks" on PATH; missing gitleaks refuses (fails closed)
  KEEP_AWAKE        command prefix for the suite, e.g. "caffeinate -ims" (default: that if available)
  MAINTAINER_LOGINS required for `addressed`: comma-separated logins whose review, comment or
                    close counts. There is no default: an unset list would let any passer-by's
                    comment open the next round
  ALLOW_FORCE_WITH_LEASE  set to 1 to let `repair` replace an amended commit; default is fast-forward only
"""
import datetime
import fcntl
import fnmatch
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess as sp
import sys
import time
import unicodedata


def _loop_settings():
    """Fill unset settings from the kit's loop.env (scripts/loopenv.py), so cron jobs and
    subagents get the same values without exporting them."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'loopenv.py')
    if os.path.exists(p):
        import importlib.util
        spec = importlib.util.spec_from_file_location('loopenv', p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.load()
    elif os.environ.get('LOOP_CONFIG'):
        sys.exit('LOOP_CONFIG is set but scripts/loopenv.py is not next to this script')


_loop_settings()

UP = os.environ.get('UPSTREAM_REPO', 'DrBradStanfield/roadmap')
FORK_OWNER = os.environ.get('GH_FORK_OWNER', '')
UP_REMOTE = os.environ.get('UPSTREAM_REMOTE', 'upstream')
PUSH_REMOTE = os.environ.get('PUSH_REMOTE', 'origin')
ATTRIBUTION = os.environ.get('ATTRIBUTION', '')
KNOWN = set(filter(None, os.environ.get('KNOWN_FLAKY', ','.join([
    'app/lib/matched-content.test.ts', 'tools/test-chatbot-matching.test.ts',
    'ios/engine/blood-pressure.test.ts', 'app/lib/app-routes.server.test.ts'])).split(',')))
MAX_LOAD = float(os.environ.get('DRIVER_MAX_LOAD', 4 * (os.cpu_count() or 2)))
SUITE_TIMEOUT = int(os.environ.get('SUITE_TIMEOUT_MIN', '45')) * 60
MAX_WORKERS = os.environ.get('SUITE_MAX_WORKERS', '4')
GITLEAKS = os.environ.get('GITLEAKS_BIN', 'gitleaks')
SHARED_SUITE_DEFAULT = ('packages/health-core/*merge*,packages/health-core/*sync*,'
                        'packages/health-core/*record-session*,widget-src/*storage*')
CI_WAIT_MIN = float(os.environ.get('CI_WAIT_MIN') or 20)
CI_POLL_SEC = float(os.environ.get('CI_POLL_SEC') or 60)
CI_OK = ('success', 'skipped', 'neutral')
IN_REVIEW_PREFIXES = ('claude/batch-', 'claude/group-')
_ka = os.environ.get('KEEP_AWAKE')
KEEP_AWAKE = shlex.split(_ka) if _ka is not None else (['caffeinate', '-ims'] if shutil.which('caffeinate') else [])
SECRET_NAME = re.compile(r'TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL|^GH_|^GITHUB_|^AWS_', re.I)
# The only variables the suite inherits. Everything else (tokens, SSH_AUTH_SOCK, HOME, cloud
# credentials, agent settings) is left behind, so nothing has to be named to be removed.
SUITE_KEEP = ('PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TERM')


def suite_env(base, home):
    """Environment for the target repo's test suite. The suite runs code from the repo under review
    as our user, so it gets only SUITE_KEEP plus a throwaway HOME: no push token, no SSH agent, and
    no path to ~/.config/gh, ~/.ssh or ~/.npmrc. What this does not stop: code that opens files by
    absolute path, the macOS keychain, or the network. The container in
    docs/validation-and-sandbox.md stops those; this driver does not use it yet."""
    _path = [p for p in (base.get('NODE_BIN_DIR'), base.get('EXTRA_PATH')) if p]
    env = {k: base[k] for k in SUITE_KEEP if k in base}
    env.update(PATH=':'.join(_path + [base.get('PATH', '')]), TZ='UTC', CI='1',
               HOME=home, TMPDIR=os.path.join(home, 'tmp'), XDG_CONFIG_HOME=os.path.join(home, '.config'),
               XDG_CACHE_HOME=os.path.join(home, '.cache'))
    os.makedirs(env['TMPDIR'], exist_ok=True)
    return env


_ENV = {}


def suite_environment():
    """One throwaway HOME per driver process, created on first use."""
    if not _ENV:
        import tempfile
        _ENV.update(suite_env(os.environ, tempfile.mkdtemp(prefix='suite-home-')))
    return _ENV
VITEST = ['node', 'node_modules/vitest/vitest.mjs', 'run']
SELF = os.path.abspath(__file__)
TEMPLATES = os.path.join(os.path.dirname(SELF), '..', '..', 'templates')
SECRET_CHECK = os.path.join(os.path.dirname(SELF), 'secret_check.mjs')

SHA40 = re.compile(r'[0-9a-f]{40}')
VERDICTS = ('approve', 'changes', 'needs_decision', 'could_not_review')
CHECK_STATES = ('yes', 'no', 'not_checked', 'not_applicable')
APPROVE_NEEDS_YES = ('red_at_base', 'green_at_head', 'protected_tests_untouched', 'claims_match_assertions',
                     'single_fix_scope')
FRESH_ROLES = ('independent_reviewer', 'delta_reviewer')
POST_FILES_NEW = ('pr-title.txt', 'pr-body.md')
POST_FILES_REPAIR = ('comment.md', 'body.md', 'title.txt')
REQUIRED_SECTIONS = ('Testing', 'Risk', 'How to revert')
FINAL = ('observed_succeeded', 'observed_failed')


# ---------------------------------------------------------------------------------------------
# shared checks
# ---------------------------------------------------------------------------------------------

def need(ok, msg):
    """A gate. Not `assert`: python -O strips asserts, and a gate must never vanish."""
    if not ok:
        sys.exit(f'REFUSED: {msg}')


def run(args, cwd=None, check=True):
    """Every git/gh call is an argv list, never a shell string."""
    r = sp.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f'FAILED: {args[:4]}\n{r.stdout}\n{r.stderr}')
    return r.stdout.strip()


def _no_dupes(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f'duplicate key {k!r}')
        d[k] = v
    return d


def _no_constant(c):
    raise ValueError(f'non-finite number {c}')


def strict_load(path):
    """JSON that gates an action: duplicate keys (at any depth) and NaN/Infinity are errors, not last-wins."""
    with open(path, encoding='utf-8') as f:
        return json.load(f, object_pairs_hook=_no_dupes, parse_constant=_no_constant)


def sha256_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def latest_review(d):
    revs = sorted(glob.glob(f'{d}/review-*.json'), key=lambda p: int(re.sub(r'\D', '', os.path.basename(p)) or 0))
    return revs[-1] if revs else None


def _unknown(obj, allowed, where):
    extra = sorted(set(obj) - set(allowed))
    return [f'unknown fields in {where}: {extra}'] if extra else []


def verdict_problems(r, head):
    """Every reason this verdict does not approve `head`. An empty list means it approves."""
    s = strict_load(os.path.join(TEMPLATES, 'review-verdict.schema.json'))
    if not isinstance(r, dict):
        return ['verdict file is not a JSON object']
    p = _unknown(r, s['properties'], 'verdict')
    missing = sorted(set(s['required']) - set(r))
    if missing:
        p.append(f'missing fields: {missing}')
    if r.get('verdict') != 'approve':
        p.append(f"verdict is {r.get('verdict')!r}, not 'approve'")
    h = r.get('head')
    if not (isinstance(h, str) and SHA40.fullmatch(h)):
        p.append('head is not a full 40-character SHA')
    elif h != head:
        p.append(f'review is for {h[:12]}, folder head is {head[:12]}')
    if not (isinstance(r.get('base'), str) and SHA40.fullmatch(r['base'])):
        p.append('base is not a full 40-character SHA')
    rv = r.get('reviewer')
    if not isinstance(rv, dict):
        p.append('reviewer is missing')
    else:
        p += _unknown(rv, s['properties']['reviewer']['properties'], 'reviewer')
        if rv.get('wrote_fix') is not False:
            p.append('reviewer.wrote_fix is not false')
        if rv.get('role') not in s['properties']['reviewer']['properties']['role']['enum']:
            p.append(f"reviewer.role {rv.get('role')!r} is not a known role")
        elif rv.get('role') in FRESH_ROLES and rv.get('fresh_context') is not True:
            p.append('an independent or delta reviewer must have fresh_context true')
    c = r.get('checks')
    if not isinstance(c, dict):
        p.append('checks is missing')
    else:
        p += _unknown(c, s['properties']['checks']['properties'], 'checks')
        for k in APPROVE_NEEDS_YES:
            if c.get(k) != 'yes':
                p.append(f'checks.{k} is {c.get(k)!r}; approve needs "yes"')
    f = r.get('findings')
    if not isinstance(f, list):
        p.append('findings is not a list')
    else:
        for x in f:
            cls = x.get('class') if isinstance(x, dict) else None
            if cls not in ('nit', 'pre_existing') and not (cls == 'should_fix' and x.get('optional') is True):
                p.append(f"finding {x.get('id') if isinstance(x, dict) else x!r} ({cls}) blocks approve")
    if r.get('still_open'):
        p.append(f"still_open is not empty: {r['still_open']}")
    return p


def review_problems(d, head, files=()):
    """Latest local review-<k>.json must approve this head and the exact bytes of every file to be posted."""
    rv = latest_review(d)
    if not rv:
        return ['no review-<k>.json']
    try:
        r = strict_load(rv)
    except (OSError, ValueError) as e:
        return [f'{os.path.basename(rv)} does not parse strictly: {e}']
    p = verdict_problems(r, head)
    dig = r.get('text_sha256') if isinstance(r, dict) else None
    for name in files:
        fp = os.path.join(d, name)
        if os.path.exists(fp) and not (isinstance(dig, dict) and dig.get(name) == sha256_file(fp)):
            p.append(f'{name} changed after review (or text_sha256 has no matching entry)')
    return p


def review_approves(d, head, files=()):
    return not review_problems(d, head, files)


ZERO_WIDTH = dict.fromkeys(map(ord, '\u200b\u200c\u200d\u2060\ufeff\u00ad'), None)
VERDICT_RE = re.compile(r'verdict\s*:', re.I)


def no_verdict_token(text, what):
    """Normalize first (full-width letters and colons, zero-width joins), then look for the token."""
    t = unicodedata.normalize('NFKC', text).translate(ZERO_WIDTH)
    need(not VERDICT_RE.search(t), f'{what} contains "VERDICT:" (or a disguised form); never post that token to GitHub')


ARTIFACT_RE = re.compile(
    r'\[(?:output )?truncated|<truncated>|\b(?:bytes|lines|chars|characters|tokens) omitted\b'
    r'|^(?:<{7}|>{7})(?:\s|$)|^={7}\s*$', re.I | re.M)


def artifact_problems(text, what):
    """Transport artifacts (tool truncation markers) and merge conflict markers that parse fine but are corrupt."""
    hits = sorted({m.group(0).strip() for m in ARTIFACT_RE.finditer(text)})
    return [f'{what} contains a truncation or conflict marker: {hits}'] if hits else []


HTML_TAGS = {'a', 'b', 'br', 'code', 'details', 'div', 'em', 'hr', 'i', 'img', 'kbd', 'li', 'ol', 'p', 'pre',
             'span', 'strong', 'sub', 'summary', 'sup', 'table', 'td', 'th', 'tr', 'ul'}


def active_markdown(md):
    """Markdown with HTML comments and fenced code removed. An unclosed fence drops the rest (fails closed)."""
    md = re.sub(r'<!--.*?(?:-->|\Z)', '', md, flags=re.S)
    out, fence = [], None
    for ln in md.split('\n'):
        m = re.match(r' {0,3}(`{3,}|~{3,})', ln)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and ln.strip() == m.group(1):
                fence = None
            continue
        if m:
            fence = m.group(1)
            continue
        out.append(ln)
    return '\n'.join(out)


def body_problems(body):
    """The PR body needs exactly one filled-in Testing, Risk and How to revert section, and no template text."""
    a = active_markdown(body)
    secs, cur = [], None
    for ln in a.split('\n'):
        m = re.match(r'##\s+(.+?)\s*#*\s*$', ln)
        if m and not ln.startswith('###'):
            cur = [m.group(1), '']
            secs.append(cur)
        elif cur is not None:
            cur[1] += ln + '\n'
    p = []
    for name in REQUIRED_SECTIONS:
        hits = [b for h, b in secs if h.lower() == name.lower()]
        if len(hits) != 1:
            p.append(f'needs exactly one "## {name}" section outside comments and code, found {len(hits)}')
        elif not re.search(r'\w', hits[0]):
            p.append(f'"## {name}" has no text')
    prose = re.sub(r'`[^`\n]*`', '', a)
    holes = [m for m in re.findall(r'</?([A-Za-z][^<>\n]*)>', prose) if m.split()[0].lower().rstrip('/') not in HTML_TAGS]
    holes += re.findall(r'`(<[^`\n]*>)`', a)
    if holes:
        p.append(f'unfilled template placeholders: {sorted(set(holes))[:5]}')
    return p


def gitleaks_ok(wt):
    if not shutil.which(GITLEAKS) and not os.path.exists(GITLEAKS):
        sys.exit('gitleaks not found (set GITLEAKS_BIN); refusing rather than skipping the secret scan')
    cfg = ['--config', '.gitleaks.toml'] if os.path.exists(os.path.join(wt, '.gitleaks.toml')) else []
    r = sp.run([GITLEAKS, 'dir', '.', '--redact', '--no-banner', *cfg, '--exit-code', '1'],
               cwd=wt, capture_output=True, text=True)
    return r.returncode == 0


def suite_ok_at_head(d, wt, head):
    """suite.json at head; failures only in KNOWN files, each with a passing solo rerun log at head."""
    need(os.path.exists(f'{d}/suite-head.txt') and open(f'{d}/suite-head.txt').read().strip() == head,
         'LOCAL_SUITE=shared and the change touches shared code, but the suite has not passed at head')
    sj = strict_load(f'{d}/suite.json')
    need(isinstance(sj.get('testResults'), list) and sj['testResults'], 'suite.json has no test results')
    bad = []
    for f in sj['testResults']:
        if f['status'] == 'passed':
            continue
        rel = f['name'].split(wt.rstrip('/') + '/')[-1]
        lg = f'{d}/rerun-{os.path.basename(rel)}.log'
        ok = (rel in KNOWN and os.path.exists(lg) and open(lg).readline().strip() == head
              and re.search(r'Tests\s+(\d+) passed \(\1\)', open(lg).read()))
        if not ok:
            bad.append(rel)
    need(not bad, f'suite failures: {bad}')


def clean_worktree_at(wt, head):
    """HEAD is the reviewed head and nothing else is in the tree. Untracked files count: a suite that
    passes only because of a local file that was never committed did not test the pushed commit."""
    need(run(['git', 'rev-parse', 'HEAD'], wt) == head, 'worktree HEAD != STATE head')
    st = run(['git', 'status', '--porcelain', '--untracked-files=all'], wt)
    need(st == '', f'worktree has uncommitted or untracked files:\n{st[:1500]}')


def merges_clean(wt, head):
    run(['git', 'fetch', '-q', UP_REMOTE, 'main'], wt)
    mt = sp.run(['git', 'merge-tree', '--write-tree', f'{UP_REMOTE}/main', head], cwd=wt, capture_output=True, text=True)
    need(mt.returncode == 0, f'conflicts with current {UP_REMOTE}/main:\n{mt.stdout[-1500:]}')


def fix_commits_present(wt, head):
    """A rebase can silently drop the fix commits; pushing that empty branch closes the PR.
    Also refuses conflict and truncation markers in the lines the fix adds. Call after merges_clean."""
    base = run(['git', 'merge-base', f'{UP_REMOTE}/main', head], wt)
    ahead = int(run(['git', 'rev-list', '--count', f'{base}..{head}'], wt))
    diff = run(['git', 'diff', '--no-ext-diff', '--no-textconv', '--unified=0', base, head], wt)
    need(ahead > 0 and diff, f'no fix commits above {UP_REMOTE}/main (a rebase may have dropped them); '
         'restore the previous tip from the reflog instead of pushing')
    added = '\n'.join(ln[1:] for ln in diff.split('\n') if ln.startswith('+') and not ln.startswith('+++'))
    p = artifact_problems(added, 'the diff')
    need(not p, '; '.join(p))


def suite_mode():
    m = (os.environ.get('LOCAL_SUITE') or 'off').strip().lower()
    need(m in ('off', 'shared'), f'LOCAL_SUITE is {m!r}; use off or shared')
    return m


def changed_files(wt, head):
    base = run(['git', 'merge-base', f'{UP_REMOTE}/main', head], wt)
    return [f for f in run(['git', 'diff', '--name-only', base, head], wt).split('\n') if f]


def suite_wanted(wt, head):
    """The local full suite is not a publish gate: the maintainer's CI runs the whole suite on every
    push. With LOCAL_SUITE=shared it still runs when the change touches shared record, sync or storage
    code (SHARED_SUITE_PATHS)."""
    if suite_mode() == 'off':
        return False
    globs = [g.strip() for g in (os.environ.get('SHARED_SUITE_PATHS') or SHARED_SUITE_DEFAULT).split(',') if g.strip()]
    return any(fnmatch.fnmatchcase(f, g) for f in changed_files(wt, head) for g in globs)


def secret_rules(tmp):
    """The roadmap repo's own credential shapes: tools/secret-rules.mjs as it is on upstream main, read
    through WORKDIR's git (the same rules tools/merge-batch.mjs pre-flight uses). Taken from main, not
    from the PR or the clone's checked-out branch, so a change cannot loosen the rules that check it.
    Missing rules refuse."""
    wd = os.environ.get('WORKDIR', '')
    need(wd and os.path.isdir(wd), 'WORKDIR is not set or not a folder; the secret-fixture check needs the roadmap clone')
    sp.run(['git', 'fetch', '-q', UP_REMOTE, 'main'], cwd=wd, capture_output=True)
    r = sp.run(['git', 'show', f'{UP_REMOTE}/main:tools/secret-rules.mjs'], cwd=wd, capture_output=True, text=True)
    need(r.returncode == 0 and 'PATTERNS' in r.stdout,
         f'tools/secret-rules.mjs is missing on {UP_REMOTE}/main in WORKDIR; refusing rather than skipping '
         'the secret-fixture check')
    path = os.path.join(tmp, 'secret-rules.mjs')
    with open(path, 'w') as f:
        f.write(r.stdout)
    return path


def secret_fixture_hits(wt, head):
    """'file:line rule' for every added line (vs upstream main) shaped like a credential; never the value."""
    import tempfile
    diff = run(['git', 'diff', '-U0', '--no-color', '--no-ext-diff', f'{UP_REMOTE}/main...{head}'], wt)
    with tempfile.TemporaryDirectory(prefix='secret-check-') as tmp:
        rules = secret_rules(tmp)
        try:
            r = sp.run(['node', SECRET_CHECK, rules], input=diff, cwd=tmp, env=suite_environment(),
                       capture_output=True, text=True, timeout=300)
        except (OSError, sp.TimeoutExpired) as e:
            need(False, f'the secret-fixture check could not run ({e}); refusing rather than skipping')
    if r.returncode == 0:
        return []
    need(r.returncode == 5, f'the secret-fixture check could not run (exit {r.returncode}): {r.stderr.strip()[-300:]}')
    return [ln.strip() for ln in r.stdout.split('\n') if re.fullmatch(r'\S+:\d+ [\w-]+', ln.strip())] or ['(unparsed hit)']


def secret_fixtures_clean(wt, head):
    hits = secret_fixture_hits(wt, head)
    need(not hits, 'secret-shaped text in the added lines; use plain strings like test-token-good '
         '(file:line rule, never the value):\n' + '\n'.join(hits))


def in_review_by(head, prs):
    """Numbers of open claude/batch-* or claude/group-* PRs whose body names `head` (the full SHA, or a
    7+ character prefix of it as its own word). Such a head is pinned in the maintainer's review."""
    hits = []
    for p in prs:
        if not str(p.get('headRefName') or '').startswith(IN_REVIEW_PREFIXES):
            continue
        words = re.findall(r'(?<![0-9a-f])[0-9a-f]{7,40}(?![0-9a-f])', str(p.get('body') or '').lower())
        if any(head.lower().startswith(w) for w in words):
            hits.append(p.get('number'))
    return hits


def not_in_review(n, head):
    """The in-review push guard: never push to a PR whose current head is in the maintainer's batch review."""
    out = run(['gh', 'pr', 'list', '--repo', UP, '--state', 'open', '--limit', '500', '--json', 'number,headRefName,body'])
    hits = in_review_by(head, json.loads(out or '[]'))
    need(not hits, f"PR #{n} is in Brad's review: its head {head[:12]} is named in open batch PR(s) "
         f"{', '.join(f'#{h}' for h in hits)}. Never push while it is in review; wait for the batch result")


def ledger_records(path, key, value):
    """Records in a JSON-lines ledger. A damaged line stops the driver with its file and line
    number: skipping it could forget a publish that happened and publish it twice."""
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for n, ln in enumerate(f, 1):
            if not ln.strip():
                continue
            try:
                r = json.loads(ln)
            except ValueError:
                need(False, f'{path}:{n}: damaged ledger line. Check GitHub for what that line recorded, '
                          'then repair or remove the line by hand; the driver will not guess')
            if not isinstance(r, dict):
                need(False, f'{path}:{n}: ledger line is not a JSON object')
            if r.get(key) == value:
                out.append(r)
    return out


def utc_time(stamp, what):
    """Parse an ISO 8601 time that names its zone (GitHub uses ...Z). A time without a zone
    is refused: comparing it with GitHub's times would silently give the wrong answer."""
    import datetime
    s = str(stamp or '').strip()
    try:
        t = datetime.datetime.fromisoformat(s[:-1] + '+00:00' if s.endswith('Z') else s)
    except ValueError:
        need(False, f'{what}: not an ISO 8601 time: {s!r}')
        raise
    if t.tzinfo is None:
        need(False, f'{what}: time has no zone: {s!r} (write UTC with Z, as GitHub does)')
    return t


def ledger_status(path, key, value):
    """Last effect state for this key. Records written before states existed count by their verified flag."""
    recs = ledger_records(path, key, value)
    if not recs:
        return None
    r = recs[-1]
    return r.get('status') or ('observed_succeeded' if r.get('verified') else 'observed_failed')


def ledger_has(path, key, value):
    """True once the effect reached a final observed state. An 'attempted' record is not final."""
    return ledger_status(path, key, value) in FINAL


def ledger_append(path, rec):
    rec = dict(rec, at=datetime.datetime.now().isoformat(timespec='seconds'))
    with open(path, 'a') as f:
        f.write(json.dumps(rec) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return rec


def text_checks(texts, attributed):
    """Every title, body and comment the driver is about to post. `attributed` names the texts that
    must carry the ATTRIBUTION line."""
    for what, t in texts.items():
        if t is None:
            continue
        if ATTRIBUTION and what in attributed:
            need(ATTRIBUTION in t, f'{what} lacks the ATTRIBUTION line')
        no_verdict_token(t, what)
        p = artifact_problems(t, what)
        need(not p, '; '.join(p))


def existing_pr(branch):
    """Read-only: a PR from our fork's branch that already exists on GitHub (open, closed or merged)."""
    out = run(['gh', 'pr', 'list', '--repo', UP, '--head', branch, '--state', 'all', '--json',
               'number,url,headRefOid,state,headRepositoryOwner'])
    hits = [p for p in json.loads(out or '[]') if (p.get('headRepositoryOwner') or {}).get('login') == FORK_OWNER]
    need(len(hits) <= 1, f'{len(hits)} PRs already exist for {branch}; reconcile by hand')
    return hits[0] if hits else None


# ---------------------------------------------------------------------------------------------
# publish: one new PR
# ---------------------------------------------------------------------------------------------

def publish(folder, go):
    F = os.path.abspath(folder)
    ledger = os.path.join(os.path.dirname(F), 'published.jsonl')
    st = strict_load(f'{F}/STATE.json')
    wt, branch, head = st['worktree'], st['branch'], st['head']
    need(not ledger_has(ledger, 'branch', branch), 'already published (final record in published.jsonl)')
    need(FORK_OWNER, 'set GH_FORK_OWNER')
    clean_worktree_at(wt, head)
    p = review_problems(F, head, POST_FILES_NEW)
    need(not p, 'latest review does not approve this head and text: ' + '; '.join(p))
    merges_clean(wt, head)
    fix_commits_present(wt, head)
    if suite_wanted(wt, head):
        suite_ok_at_head(F, wt, head)
    need(gitleaks_ok(wt), 'gitleaks (the CI secret scan) flags this tree')
    secret_fixtures_clean(wt, head)
    title = open(f'{F}/pr-title.txt').read().strip()
    body = open(f'{F}/pr-body.md').read()
    need(0 < len(title) < 200, 'title missing or too long')
    p = body_problems(body)
    need(not p, 'PR body: ' + '; '.join(p))
    text_checks({'title': title, 'body': body}, attributed=('body',))
    prior = existing_pr(branch)  # an earlier run may have opened it and died before the ledger write
    if prior:
        need(prior['state'] == 'OPEN' and prior['headRefOid'] == head,
             f"PR #{prior['number']} already exists for {branch} ({prior['state']}, head "
             f"{prior['headRefOid'][:8]}); reconcile by hand")
    print(f'{branch} @{head[:8]}: {title}' + (f" (adopts existing PR #{prior['number']})" if prior else ''))
    if not go:
        return
    rec = dict(folder=os.path.basename(F), branch=branch, head=head, effect='open_pr')
    ledger_append(ledger, dict(rec, status='attempted'))
    if prior:
        url = prior['url']
    else:
        run(['git', 'push', PUSH_REMOTE, f'{head}:refs/heads/{branch}'], wt)
        url = run(['gh', 'pr', 'create', '--repo', UP, '--base', 'main', '--head', f'{FORK_OWNER}:{branch}',
                   '--title', title, '--body-file', f'{F}/pr-body.md'])
    v = json.loads(run(['gh', 'pr', 'view', url, '--json',
                        'number,url,author,baseRefName,headRefOid,isDraft,title,body,state']))
    ok = (v['author']['login'] == FORK_OWNER and v['baseRefName'] == 'main' and v['headRefOid'] == head
          and not v['isDraft'] and v['title'] == title and v['body'].strip() == body.strip() and v['state'] == 'OPEN')
    rec = ledger_append(ledger, dict(rec, number=v['number'], url=v['url'], verified=ok, adopted=bool(prior),
                                     status='observed_succeeded' if ok else 'observed_failed'))
    print('PUBLISHED', json.dumps(rec))
    need(ok, 'READBACK MISMATCH')


# ---------------------------------------------------------------------------------------------
# repair: push an approved repair to an existing PR and post the reply
# ---------------------------------------------------------------------------------------------

def repair(folder, go):
    d = os.path.abspath(folder)
    R = os.path.dirname(d)
    n = re.sub(r'\D', '', os.path.basename(d))
    led = f'{R}/pushed.jsonl'
    meta = strict_load(f'{d}/meta.json')  # {"head_at_start": sha, "addressed_comment_at": iso time}
    st = strict_load(f'{d}/STATE.json')
    wt, branch, head = st['worktree'], st['branch'], st['head']
    last = ledger_records(led, 'pr', int(n))
    need(not (last and last[-1].get('status') == 'attempted'),
         f'an earlier repair push to PR #{n} never reached an observed state. Check the PR on GitHub '
         '(head, last comment, body) and record the outcome in pushed.jsonl by hand before retrying')
    clean_worktree_at(wt, head)
    p = review_problems(d, head, POST_FILES_REPAIR)
    need(not p, 'latest review does not approve this head and text: ' + '; '.join(p))
    v = json.loads(run(['gh', 'pr', 'view', n, '-R', UP, '--json', 'headRefOid,headRefName,state,comments,body']))
    need(v['state'] == 'OPEN', f"PR #{n} is {v['state']}")
    need(v['headRefName'] == branch, f"PR branch {v['headRefName']} != {branch}")
    need(v['headRefOid'] == meta['head_at_start'], f"PR head moved on GitHub: {v['headRefOid']}")
    not_in_review(n, v['headRefOid'])
    since = utc_time(meta['addressed_comment_at'], f'{d}/meta.json addressed_comment_at')
    newer = [c for c in v['comments'] if c['author']['login'] != FORK_OWNER
             and utc_time(c['createdAt'], 'GitHub comment createdAt') > since]
    need(not newer, f'new comment since the repair started: {[c["createdAt"] for c in newer]}')
    ff = sp.run(['git', 'merge-base', '--is-ancestor', meta['head_at_start'], head], cwd=wt).returncode == 0
    force = os.environ.get('ALLOW_FORCE_WITH_LEASE') == '1'
    need(ff or force, 'repair is not a fast-forward of the pushed head (set ALLOW_FORCE_WITH_LEASE=1 to allow)')
    merges_clean(wt, head)
    fix_commits_present(wt, head)
    if suite_wanted(wt, head):
        suite_ok_at_head(d, wt, head)
    need(gitleaks_ok(wt), 'gitleaks (the CI secret scan) flags this tree')
    secret_fixtures_clean(wt, head)
    comment = open(f'{d}/comment.md').read()
    body = open(f'{d}/body.md').read() if os.path.exists(f'{d}/body.md') else None
    title = open(f'{d}/title.txt').read().strip() if os.path.exists(f'{d}/title.txt') else None
    if body is not None:
        p = body_problems(body)
        need(not p, 'PR body: ' + '; '.join(p))
    text_checks({'comment': comment, 'body': body, 'title': title}, attributed=('comment',))
    print(f'PR #{n} {branch}: {meta["head_at_start"][:8]} -> {head[:8]} ({"fast-forward" if ff else "force-with-lease"}); '
          f'comment {len(comment)} chars; body {"update" if body else "unchanged"}; title {title!r}')
    if not go:
        return
    rec = dict(pr=int(n), old=meta['head_at_start'], new=head, effect='repair')
    ledger_append(led, dict(rec, status='attempted'))
    push = ['git', 'push']
    if not ff:
        push.append(f'--force-with-lease={branch}:{meta["head_at_start"]}')
    run(push + [PUSH_REMOTE, f'{head}:refs/heads/{branch}'], wt)
    cr = run(['gh', 'pr', 'comment', n, '-R', UP, '--body-file', f'{d}/comment.md'])
    if body:
        run(['gh', 'pr', 'edit', n, '-R', UP, '--body-file', f'{d}/body.md'])
    if title:
        run(['gh', 'pr', 'edit', n, '-R', UP, '--title', title])
    v = json.loads(run(['gh', 'pr', 'view', n, '-R', UP, '--json', 'headRefOid,comments,body,title']))
    ok = (v['headRefOid'] == head and v['comments'][-1]['body'].strip() == comment.strip()
          and (body is None or v['body'].strip() == body.strip()) and (title is None or v['title'] == title))
    rec = ledger_append(led, dict(rec, comment=cr, verified=ok, status='observed_succeeded' if ok else 'observed_failed'))
    print('PUSHED', json.dumps(rec))
    need(ok, 'READBACK MISMATCH')


# ---------------------------------------------------------------------------------------------
# ci: the CI gate on the head the driver pushed (replaces the local full suite)
# ---------------------------------------------------------------------------------------------

def classify_checks(runs):
    """('green' | 'red' | 'pending', the runs that are not green). No runs yet, or any run not yet
    completed, is pending. Once all are complete: green only when every conclusion is success, skipped
    or neutral; anything else (failure, cancelled, timed_out, action_required, stale, unknown) is red."""
    if not runs or any(r.get('status') != 'completed' for r in runs):
        return 'pending', []
    bad = [r for r in runs if r.get('conclusion') not in CI_OK]
    return ('red', bad) if bad else ('green', [])


def check_runs(head):
    """Latest check runs for the exact head, or None when GitHub could not be read (counts as pending)."""
    runs, page = [], 1
    while True:
        r = sp.run(['gh', 'api', f'repos/{UP}/commits/{head}/check-runs?filter=latest&per_page=100&page={page}'],
                   capture_output=True, text=True)
        if r.returncode:
            return None
        try:
            out = json.loads(r.stdout)
        except ValueError:
            return None
        got = out.get('check_runs') or []
        runs += got
        if not got or len(runs) >= int(out.get('total_count') or 0):
            return runs
        page += 1


TOKEN_SHAPE = re.compile(r'(?:gh[pousr]_|github_pat_|sk-|xox[abposr]-|glpat-|AKIA|AIza)[A-Za-z0-9_\-]{6,}')


def log_excerpt(run_, lines=25):
    """The end of a failed GitHub Actions job's log, with anything token-shaped masked. GitHub masks
    secrets in logs already; this is a second guard. Other check apps get no excerpt, only the link."""
    if ((run_.get('app') or {}).get('slug')) != 'github-actions' or not run_.get('id'):
        return ''
    r = sp.run(['gh', 'run', 'view', '--job', str(run_['id']), '--log-failed', '-R', UP], capture_output=True, text=True)
    if r.returncode:
        return '(log not available)'
    return TOKEN_SHAPE.sub('[masked]', '\n'.join(r.stdout.rstrip().split('\n')[-lines:]))


def ci_target(F):
    """(PR number, pushed head, ledger folder) for a folder the driver published or pushed at its STATE head."""
    st = strict_load(f'{F}/STATE.json')
    head, led_dir = st['head'], os.path.dirname(F)
    if os.path.exists(f'{F}/meta.json'):
        n = int(re.sub(r'\D', '', os.path.basename(F)) or 0)
        recs = ledger_records(f'{led_dir}/pushed.jsonl', 'pr', n)
        ok = bool(recs) and recs[-1].get('status') == 'observed_succeeded' and recs[-1].get('new') == head
    else:
        recs = ledger_records(f'{led_dir}/published.jsonl', 'branch', st['branch'])
        ok = bool(recs) and recs[-1].get('status') == 'observed_succeeded' and recs[-1].get('head') == head
        n = recs[-1].get('number') if recs else None
    need(ok and n, f'{os.path.basename(F)}: the driver has not pushed this head ({head[:12]}); nothing to wait for')
    return int(n), head, led_dir


def ci_result(F, head):
    for name, state in (('CI-GREEN', 'green'), ('CI-RED.md', 'red')):
        p = f'{F}/{name}'
        if os.path.exists(p) and open(p).readline().split()[-1:] == [head]:
            return state
    return None


CI_LINE = re.compile(r'(CI\**\s+at\s+`([0-9a-f]{7,40})`:\s*)pending\b[^\n]*')


def fill_ci_line(F, n, head, led):
    """Fill the PR body's 'CI at `<head>`: pending' line, the only body text the driver writes itself.
    No marker line, nothing is edited."""
    v = json.loads(run(['gh', 'pr', 'view', str(n), '-R', UP, '--json', 'body,headRefOid']))
    body = v.get('body') or ''
    link = f'https://github.com/{UP}/pull/{n}/checks'
    new = CI_LINE.sub(lambda m: m.group(1) + f'all checks passed ([checks]({link}))'
                      if head.startswith(m.group(2)) else m.group(0), body)
    if new == body or v.get('headRefOid') != head:
        return
    text_checks({'body': new}, attributed=())
    with open(f'{F}/ci-body.md', 'w') as f:
        f.write(new)
    rec = dict(pr=n, head=head, effect='ci_body')
    ledger_append(led, dict(rec, status='attempted'))
    run(['gh', 'pr', 'edit', str(n), '-R', UP, '--body-file', f'{F}/ci-body.md'])
    got = json.loads(run(['gh', 'pr', 'view', str(n), '-R', UP, '--json', 'body']))['body']
    ok = got.strip() == new.strip()
    ledger_append(led, dict(rec, status='observed_succeeded' if ok else 'observed_failed'))


def ci(folder, wait_min=None, poll=None):
    """The CI gate. 0 = CI-GREEN, 4 = CI-RED.md, 3 = CI-PENDING (polled again next loop pass)."""
    F = os.path.abspath(folder)
    n, head, led_dir = ci_target(F)
    done = ci_result(F, head)
    if done:
        print(f'PR #{n} @{head[:8]}: CI already {done}')
        return 0 if done == 'green' else 4
    led = f'{led_dir}/ci.jsonl'
    wait = CI_WAIT_MIN if wait_min is None else wait_min
    with open(f'{F}/CI-PENDING', 'w') as f:  # written first, so a crash mid-wait is polled again
        f.write(f'{head}\n')
    deadline = time.time() + wait * 60
    while True:
        runs = check_runs(head)
        state, bad = classify_checks(runs or [])
        if state != 'pending' or time.time() >= deadline:
            break
        time.sleep(poll if poll is not None else CI_POLL_SEC)
    now = datetime.datetime.now().isoformat(timespec='seconds')
    if state == 'pending':
        with open(f'{F}/CI-PENDING', 'w') as f:
            f.write(f'{head}\nchecked {now}: {len(runs or [])} check run(s), not all complete\n')
        print(f'PR #{n} @{head[:8]}: CI-PENDING')
        return 3
    os.remove(f'{F}/CI-PENDING')
    if state == 'red':
        parts = [f'CI is red at {head}\n', f'PR #{n}. The folder goes back to a repair fixer; push again only after '
                 'the repair is reviewed. This head is never reported as ready.\n']
        for r in bad:
            parts.append(f"\n## {r.get('name')}: {r.get('conclusion')}\n\n{r.get('html_url') or ''}\n")
            ex = log_excerpt(r)
            if ex:
                parts.append('\n```\n' + ex.replace('```', '` ` `') + '\n```\n')
        with open(f'{F}/CI-RED.md', 'w') as f:
            f.write(''.join(parts))
        ledger_append(led, dict(pr=n, head=head, effect='ci', status='red', failed=[r.get('name') for r in bad]))
        print(f'PR #{n} @{head[:8]}: CI-RED ({", ".join(str(r.get("name")) for r in bad)})')
        return 4
    with open(f'{F}/CI-GREEN', 'w') as f:
        f.write(f'{head}\n{len(runs)} check run(s) success, skipped or neutral at {now}\n')
    ledger_append(led, dict(pr=n, head=head, effect='ci', status='green', checks=len(runs)))
    outbox = os.path.join(os.environ.get('STATE_DIR') or led_dir, 'report-outbox.txt')
    with open(outbox, 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(f'PR #{n} ready, head {head}\n')
    fill_ci_line(F, n, head, led)
    print(f'PR #{n} @{head[:8]}: CI-GREEN; reported to {os.path.basename(outbox)}')
    return 0


# ---------------------------------------------------------------------------------------------
# addressed: the restart rule (next round only when every previous-round PR had a maintainer action)
# ---------------------------------------------------------------------------------------------

def addressed(ledgers):
    nums = []
    for path in ledgers:
        for ln in open(path):
            if ln.strip():
                r = json.loads(ln)
                n = r.get('number') or r.get('pr')
                if n and n not in nums:
                    nums.append(n)
    maint = set(filter(None, os.environ.get('MAINTAINER_LOGINS', '').split(',')))
    need(maint, 'MAINTAINER_LOGINS is not set: without it any passer-by would count as the maintainer')

    def counts(login):
        if not login or login == FORK_OWNER or login.endswith('[bot]') or login in ('github-actions', 'claude'):
            return False  # CI, bots and our own account never count
        return login in maint

    def closer(n):
        out = run(['gh', 'api', f'repos/{UP}/issues/{n}/events', '--paginate', '-q',
                   '.[] | select(.event == "closed") | .actor.login'])
        return (out.split() or [''])[-1]

    pending = []
    for n in nums:
        v = json.loads(run(['gh', 'pr', 'view', str(n), '-R', UP, '--json', 'state,reviews,comments']))
        why = []
        if v['state'] == 'MERGED':
            why.append('merged')  # only an account with write access can merge; ours has none
        elif v['state'] == 'CLOSED':
            who = closer(n)
            if counts(who):
                why.append(f'closed by {who}')
            else:
                print(f'#{n}: closed by {who or "unknown"}, which does not count')
        why += [f"review by {r['author']['login']}" for r in v['reviews'] if counts(r['author']['login'])]
        why += [f"comment by {c['author']['login']}" for c in v['comments'] if counts(c['author']['login'])]
        print(f"#{n}: {'addressed (' + why[0] + ')' if why else 'NOT addressed'}")
        if not why:
            pending.append(n)
    print(f'{len(nums) - len(pending)}/{len(nums)} addressed')
    return 1 if pending else 0


# ---------------------------------------------------------------------------------------------
# run: the loop
# ---------------------------------------------------------------------------------------------

def loop(R, NEWDIR):
    tries = {}

    def log(m):
        with open(f'{R}/driver.log', 'a') as f:
            f.write(time.strftime('%F %T ') + m + '\n')

    def is_new(d):
        return bool(NEWDIR) and d.startswith(NEWDIR)

    def ready(d):
        if not os.path.exists(f'{d}/STATE.json'):
            return None
        if any(os.path.exists(f'{d}/{x}') for x in ('HOLD.md', 'PUSH-REFUSED.md', 'NOT-REPRODUCED.md')):
            return None
        try:
            st = strict_load(f'{d}/STATE.json')
        except ValueError as e:
            refuse(d, f'STATE.json does not parse strictly: {e}\n', 'bad STATE.json')
            return None
        if is_new(d):
            if ledger_has(f'{NEWDIR}/published.jsonl', 'branch', st['branch']):
                return None
        else:
            if not (os.path.exists(f'{d}/meta.json') and os.path.exists(f'{d}/comment.md')):
                return None
            if ledger_has(f'{R}/pushed.jsonl', 'pr', int(re.sub(r'\D', '', os.path.basename(d)) or 0)):
                return None
        if os.path.exists(f'{d}/WAIT-FOR'):  # WAIT-FOR means MERGED, not open; any non-number blocks
            for n in open(f'{d}/WAIT-FOR').read().split():
                s = sp.run(['gh', 'pr', 'view', n, '-R', UP, '--json', 'state', '--jq', '.state'],
                           capture_output=True, text=True).stdout.strip()
                if s != 'MERGED':
                    return None
        return st if review_approves(d, st['head'], POST_FILES_NEW if is_new(d) else POST_FILES_REPAIR) else None

    def suite(d, st):
        wt, head = st['worktree'], st['head']
        if (os.path.exists(f'{d}/suite-head.txt') and open(f'{d}/suite-head.txt').read().strip() == head
                and os.path.exists(f'{d}/suite.json')):
            return True
        while os.getloadavg()[0] > MAX_LOAD:
            time.sleep(60)
        log(f'suite {os.path.basename(d)} @{head[:8]}')
        with open(f'{d}/suite.log', 'w') as o:
            if os.path.exists(f'{d}/suite.json'):
                os.rename(f'{d}/suite.json', f'{d}/suite-prev.json')
            pr = sp.Popen(KEEP_AWAKE + VITEST + ['--reporter=json', f'--outputFile={d}/suite.json', f'--maxWorkers={MAX_WORKERS}'],
                          cwd=wt, env=suite_environment(), stdout=o, stderr=sp.STDOUT, start_new_session=True)
            try:
                pr.wait(timeout=SUITE_TIMEOUT)
            except sp.TimeoutExpired:
                os.killpg(pr.pid, 9)
                pr.wait()
                log(f'{os.path.basename(d)} suite hung past {SUITE_TIMEOUT // 60} min; stopped')
                return False
        if not os.path.exists(f'{d}/suite.json'):
            return False
        with open(f'{d}/suite-head.txt', 'w') as f:
            f.write(head + '\n')
        return True

    def failures(d, st):
        sj = json.load(open(f'{d}/suite.json'))
        return [f['name'].split(st['worktree'].rstrip('/') + '/')[-1] for f in sj['testResults'] if f['status'] != 'passed']

    def refuse(d, text, msg):
        with open(f'{d}/PUSH-REFUSED.md', 'w') as f:
            f.write(text)
        log(f'{os.path.basename(d)} {msg}')

    def wants_suite(d, st):
        """LOCAL_SUITE=shared and the change touches shared code. A git error here refuses the folder."""
        try:
            return suite_wanted(st['worktree'], st['head'])
        except SystemExit as e:
            refuse(d, f'{e}\n', 'could not tell whether the local suite is needed')
            return None

    def ci_wait(d, wait_min=None):
        cmd = [sys.executable, '-I', SELF, 'ci', d] + (['--wait-min', str(wait_min)] if wait_min is not None else [])
        r = sp.run(cmd, capture_output=True, text=True, env=os.environ)
        with open(f'{d}/ci.log', 'a') as o:
            o.write(time.strftime('%F %T ') + r.stdout + r.stderr)
        log(f'{os.path.basename(d)} ci rc={r.returncode} {(r.stdout + r.stderr).strip()[-200:]}')
        return r.returncode

    def all_dirs():
        return [d.rstrip('/') for d in sorted(glob.glob(f'{R}/pr*/')) + (sorted(glob.glob(f'{NEWDIR}/*/')) if NEWDIR else [])]

    log('driver start')
    while not os.path.exists(f'{R}/stop-driver'):
        did = False
        dirs = all_dirs()
        for d in [x for x in dirs if os.path.exists(f'{x}/CI-PENDING')]:
            ci_wait(d, 0)  # CI still running at the last look: one poll each pass
        for d in dirs:
            st = ready(d)
            if not st:
                continue
            key = (d, st['head'])
            tries[key] = tries.get(key, 0) + 1
            if tries[key] > 2:
                refuse(d, 'Local suite (LOCAL_SUITE=shared) failed twice outside the known flaky files; '
                       'see suite.log / suite.json.\n', 'refused after 2 tries')
                continue
            did = True
            wt = st['worktree']
            # cheap pre-check: textual conflict with current upstream main
            sp.run(['git', 'fetch', '-q', UP_REMOTE, 'main'], cwd=wt)
            mt = sp.run(['git', 'merge-tree', '--write-tree', '--name-only', f'{UP_REMOTE}/main', st['head']],
                        cwd=wt, capture_output=True, text=True)
            if mt.returncode:
                refuse(d, f'CONFLICT with current {UP_REMOTE}/main (pre-check); rebase needed.\n' + mt.stdout[-1500:],
                       'pre-check: conflicts with upstream main')
                continue
            need_suite = wants_suite(d, st)
            if need_suite is None:
                continue
            if need_suite:
                if not suite(d, st):
                    log(f'{os.path.basename(d)} no suite.json')
                    continue
                fl = failures(d, st)
                real = [f for f in fl if f not in KNOWN]
                if real:
                    # Rerun the failing files alone: still failing = real, refuse now instead of a second full run.
                    solo = {f: sp.run(VITEST + [f], cwd=wt, env=suite_environment(), capture_output=True, text=True) for f in real}
                    hard = [f for f, r in solo.items() if r.returncode]
                    if hard:
                        refuse(d, 'Real failures (fail again when run alone): ' + ', '.join(hard) + '\n\n'
                               + '\n'.join(solo[f].stdout[-1500:] for f in hard), f'real failures {hard} (confirmed solo); refused')
                        continue
                    log(f'{os.path.basename(d)} failures {real} pass solo; running the suite again')
                    os.remove(f'{d}/suite-head.txt')
                    continue
                for f in fl:
                    lg = f'{d}/rerun-{os.path.basename(f)}.log'
                    for attempt in range(3):  # known flaky files: up to 3 solo tries; publish still needs a passing log
                        r = sp.run(VITEST + [f], cwd=wt, env=suite_environment(), capture_output=True, text=True)
                        with open(lg, 'w') as o:
                            o.write(st['head'] + '\n' + r.stdout + r.stderr)
                        log(f'{os.path.basename(d)} rerun {f} try {attempt + 1}: rc={r.returncode}')
                        if r.returncode == 0:
                            break
            cmd = [sys.executable, '-I', SELF, 'publish' if is_new(d) else 'repair', d]
            r = sp.run(cmd, capture_output=True, text=True, env=os.environ)
            with open(f'{d}/push-dry.log', 'w') as o:
                o.write(r.stdout + r.stderr)
            if r.returncode:
                refuse(d, r.stdout + r.stderr, f'dry run refused: {(r.stdout + r.stderr)[-300:]}')
                continue
            r = sp.run(cmd + ['--go'], capture_output=True, text=True, env=os.environ)
            with open(f'{d}/push-go.log', 'w') as o:
                o.write(r.stdout + r.stderr)
            log(f'{os.path.basename(d)} push rc={r.returncode} {(r.stdout + r.stderr)[-250:]}')
            if r.returncode:
                with open(f'{d}/PUSH-REFUSED.md', 'w') as o:
                    o.write(r.stdout + r.stderr)
            else:
                ci_wait(d)  # the CI gate on the head just pushed
            break  # one publication per pass; rescan folders from the top
        if not did:
            if os.path.exists(f'{R}/_done-round') and not any(os.path.exists(f'{x}/CI-PENDING') for x in all_dirs()):
                log('done; exit')
                break
            time.sleep(120)
    log('driver end')


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == 'publish' and len(a) >= 2:
        return publish(a[1], '--go' in a)
    if a[0] == 'repair' and len(a) >= 2:
        return repair(a[1], '--go' in a)
    if a[0] == 'ci' and len(a) >= 2:
        w = float(a[a.index('--wait-min') + 1]) if '--wait-min' in a else None
        sys.exit(ci(a[1], w))
    if a[0] == 'addressed' and len(a) >= 2:
        sys.exit(addressed(a[1:]))
    if a[0] == 'run' and '--round-dir' in a:
        R = os.path.abspath(a[a.index('--round-dir') + 1])
        NEWDIR = os.path.abspath(a[a.index('--fixes-dir') + 1]) if '--fixes-dir' in a else ''
        os.makedirs(R, exist_ok=True)
        lk = open(f'{R}/.driver.lock', 'w')
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)  # one driver per round folder
        except OSError:
            sys.exit('another driver already serves this round folder')
        with open(f'{R}/driver.pid', 'w') as f:
            f.write(str(os.getpid()))
        loop(R, NEWDIR)
        return
    sys.exit(__doc__)


if __name__ == '__main__':
    main()
