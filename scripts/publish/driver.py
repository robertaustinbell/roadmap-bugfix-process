#!/usr/bin/env python3
"""Publish driver: runs the full suite on approved fix folders, one at a time, then opens or updates PRs.
No AI. It never merges anything.

Sanitized from a working implementation; review before running.

Subcommands:
  driver.py run --round-dir R [--fixes-dir F]   loop until R/stop-driver exists (or R/_done-round and nothing left)
  driver.py publish <fix folder> [--go]         open ONE new PR (dry run without --go)
  driver.py repair <round pr folder> [--go]     push ONE approved repair to an existing PR (dry run without --go)
  driver.py addressed <ledger.jsonl>...         restart-rule check: has every PR in these ledgers had a
                                                maintainer action? exit 0 = all addressed, 1 = not yet

What the loop publishes:
- New PRs: each folder under --fixes-dir with STATE.json, whose highest-numbered review-<k>.json has
  verdict "approve" and "head" matching STATE.json "head", with no HOLD.md, PUSH-REFUSED.md
  or NOT-REPRODUCED.md, not already in <fixes-dir>/published.jsonl, and every PR number in WAIT-FOR MERGED.
- Repairs: each <round-dir>/pr<N>/ folder with STATE.json, meta.json and comment.md, the same review
  rule, not already in <round-dir>/pushed.jsonl.

For each ready folder, in order: textual merge pre-check against current upstream main; full suite once,
serially, load-gated; real failures are rerun alone (still failing = refuse; passing alone = rerun the
suite); files in the known-flaky list get up to 3 solo reruns; then the publish/repair dry run, then --go.
A refusal writes PUSH-REFUSED.md in the folder; the loop skips that folder until a human moves it aside.

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
  KNOWN_FLAKY       comma-separated test files that time out under load (default: the four seen so far)
  DRIVER_MAX_LOAD   wait while the 1-minute load average is above this (default: 4 x CPU count)
  SUITE_TIMEOUT_MIN default 45; SUITE_MAX_WORKERS default 4
  GITLEAKS_BIN      default "gitleaks" on PATH; missing gitleaks refuses (fails closed)
  KEEP_AWAKE        command prefix for the suite, e.g. "caffeinate -ims" (default: that if available)
  MAINTAINER_LOGINS comma-separated logins whose actions count for `addressed` (default: any non-bot,
                    non-GH_FORK_OWNER account)
  ALLOW_FORCE_WITH_LEASE  set to 1 to let `repair` replace an amended commit; default is fast-forward only
"""
import datetime
import fcntl
import glob
import json
import os
import re
import shlex
import shutil
import subprocess as sp
import sys
import time

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
_ka = os.environ.get('KEEP_AWAKE')
KEEP_AWAKE = shlex.split(_ka) if _ka is not None else (['caffeinate', '-ims'] if shutil.which('caffeinate') else [])
_path = [p for p in (os.environ.get('NODE_BIN_DIR'), os.environ.get('EXTRA_PATH')) if p]
ENV = dict(os.environ, PATH=':'.join(_path + [os.environ.get('PATH', '')]), TZ='UTC', CI='1')
VITEST = ['node', 'node_modules/vitest/vitest.mjs', 'run']
SELF = os.path.abspath(__file__)


# ---------------------------------------------------------------------------------------------
# shared checks
# ---------------------------------------------------------------------------------------------

def run(args, cwd=None, check=True):
    """Every git/gh call is an argv list, never a shell string."""
    r = sp.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f'FAILED: {args[:4]}\n{r.stdout}\n{r.stderr}')
    return r.stdout.strip()


def latest_review(d):
    revs = sorted(glob.glob(f'{d}/review-*.json'), key=lambda p: int(re.sub(r'\D', '', os.path.basename(p)) or 0))
    return revs[-1] if revs else None


def review_approves(d, head):
    """Latest local review-<k>.json (templates/review-verdict.schema.json): verdict 'approve' on this head."""
    rv = latest_review(d)
    if not rv:
        return False
    try:
        r = json.load(open(rv))
    except (OSError, ValueError):
        return False
    h = str(r.get('head', ''))
    return r.get('verdict') == 'approve' and len(h) >= 7 and head.startswith(h)


def no_verdict_token(text, what):
    assert 'verdict:' not in text.lower(), f'{what} contains "VERDICT:"; never post that token to GitHub'


def gitleaks_ok(wt):
    if not shutil.which(GITLEAKS) and not os.path.exists(GITLEAKS):
        sys.exit('gitleaks not found (set GITLEAKS_BIN); refusing rather than skipping the secret scan')
    cfg = ['--config', '.gitleaks.toml'] if os.path.exists(os.path.join(wt, '.gitleaks.toml')) else []
    r = sp.run([GITLEAKS, 'dir', '.', '--redact', '--no-banner', *cfg, '--exit-code', '1'],
               cwd=wt, capture_output=True, text=True)
    return r.returncode == 0


def suite_ok_at_head(d, wt, head):
    """suite.json at head; failures only in KNOWN files, each with a passing solo rerun log at head."""
    assert open(f'{d}/suite-head.txt').read().strip() == head, 'suite not at head'
    sj = json.load(open(f'{d}/suite.json'))
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
    assert not bad, f'suite failures: {bad}'


def clean_worktree_at(wt, head):
    assert run(['git', 'rev-parse', 'HEAD'], wt) == head, 'worktree HEAD != STATE head'
    assert run(['git', 'status', '--porcelain', '--untracked-files=no'], wt) == '', 'worktree dirty'


def merges_clean(wt, head):
    run(['git', 'fetch', '-q', UP_REMOTE, 'main'], wt)
    mt = sp.run(['git', 'merge-tree', '--write-tree', f'{UP_REMOTE}/main', head], cwd=wt, capture_output=True, text=True)
    assert mt.returncode == 0, f'conflicts with current {UP_REMOTE}/main:\n{mt.stdout[-1500:]}'


def ledger_has(path, key, value):
    if not os.path.exists(path):
        return False
    return any(json.loads(ln).get(key) == value for ln in open(path) if ln.strip())


# ---------------------------------------------------------------------------------------------
# publish: one new PR
# ---------------------------------------------------------------------------------------------

def publish(folder, go):
    F = os.path.abspath(folder)
    ledger = os.path.join(os.path.dirname(F), 'published.jsonl')
    st = json.load(open(f'{F}/STATE.json'))
    wt, branch, head = st['worktree'], st['branch'], st['head']
    if ledger_has(ledger, 'branch', branch):
        sys.exit('already published')
    assert FORK_OWNER, 'set GH_FORK_OWNER'
    clean_worktree_at(wt, head)
    assert review_approves(F, head), 'latest review not APPROVE on head'
    suite_ok_at_head(F, wt, head)
    merges_clean(wt, head)
    assert gitleaks_ok(wt), 'gitleaks (the CI secret scan) flags this tree'
    title = open(f'{F}/pr-title.txt').read().strip()
    body = open(f'{F}/pr-body.md').read()
    assert 0 < len(title) < 200, 'title missing or too long'
    if ATTRIBUTION:
        assert ATTRIBUTION in body, 'PR body lacks the ATTRIBUTION line'
    no_verdict_token(title + '\n' + body, 'PR title/body')
    print(f'{branch} @{head[:8]}: {title}')
    if not go:
        return
    run(['git', 'push', PUSH_REMOTE, f'{head}:refs/heads/{branch}'], wt)
    url = run(['gh', 'pr', 'create', '--repo', UP, '--base', 'main', '--head', f'{FORK_OWNER}:{branch}',
               '--title', title, '--body-file', f'{F}/pr-body.md'])
    v = json.loads(run(['gh', 'pr', 'view', url, '--json',
                        'number,url,author,baseRefName,headRefOid,isDraft,title,body,state']))
    ok = (v['author']['login'] == FORK_OWNER and v['baseRefName'] == 'main' and v['headRefOid'] == head
          and not v['isDraft'] and v['title'] == title and v['body'].strip() == body.strip() and v['state'] == 'OPEN')
    rec = dict(folder=os.path.basename(F), branch=branch, number=v['number'], url=v['url'], head=head,
               verified=ok, at=datetime.datetime.now().isoformat(timespec='seconds'))
    with open(ledger, 'a') as f:
        f.write(json.dumps(rec) + '\n')
    print('PUBLISHED', json.dumps(rec))
    if not ok:
        sys.exit('READBACK MISMATCH')


# ---------------------------------------------------------------------------------------------
# repair: push an approved repair to an existing PR and post the reply
# ---------------------------------------------------------------------------------------------

def repair(folder, go):
    d = os.path.abspath(folder)
    R = os.path.dirname(d)
    n = re.sub(r'\D', '', os.path.basename(d))
    meta = json.load(open(f'{d}/meta.json'))  # {"head_at_start": sha, "addressed_comment_at": iso time}
    st = json.load(open(f'{d}/STATE.json'))
    wt, branch, head = st['worktree'], st['branch'], st['head']
    clean_worktree_at(wt, head)
    assert review_approves(d, head), 'latest review not APPROVE on head'
    suite_ok_at_head(d, wt, head)
    v = json.loads(run(['gh', 'pr', 'view', n, '-R', UP, '--json', 'headRefOid,headRefName,state,comments,body']))
    assert v['state'] == 'OPEN', v['state']
    assert v['headRefName'] == branch, (v['headRefName'], branch)
    assert v['headRefOid'] == meta['head_at_start'], f"PR head moved on GitHub: {v['headRefOid']}"
    newer = [c for c in v['comments'] if c['author']['login'] != FORK_OWNER
             and c['createdAt'] > meta['addressed_comment_at']]
    assert not newer, f'new comment since the repair started: {[c["createdAt"] for c in newer]}'
    ff = sp.run(['git', 'merge-base', '--is-ancestor', meta['head_at_start'], head], cwd=wt).returncode == 0
    force = os.environ.get('ALLOW_FORCE_WITH_LEASE') == '1'
    assert ff or force, 'repair is not a fast-forward of the pushed head (set ALLOW_FORCE_WITH_LEASE=1 to allow)'
    merges_clean(wt, head)
    assert gitleaks_ok(wt), 'gitleaks (the CI secret scan) flags this tree'
    comment = open(f'{d}/comment.md').read()
    body = open(f'{d}/body.md').read() if os.path.exists(f'{d}/body.md') else None
    title = open(f'{d}/title.txt').read().strip() if os.path.exists(f'{d}/title.txt') else None
    if ATTRIBUTION:
        assert ATTRIBUTION in comment, 'comment lacks the ATTRIBUTION line'
    no_verdict_token(comment + (body or '') + (title or ''), 'comment/body/title')
    print(f'PR #{n} {branch}: {meta["head_at_start"][:8]} -> {head[:8]} ({"fast-forward" if ff else "force-with-lease"}); '
          f'comment {len(comment)} chars; body {"update" if body else "unchanged"}; title {title!r}')
    if not go:
        return
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
    rec = dict(pr=int(n), old=meta['head_at_start'], new=head, comment=cr, verified=ok,
               at=datetime.datetime.now().isoformat(timespec='seconds'))
    with open(f'{R}/pushed.jsonl', 'a') as f:
        f.write(json.dumps(rec) + '\n')
    print('PUSHED', json.dumps(rec))
    if not ok:
        sys.exit('READBACK MISMATCH')


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

    def counts(login):
        if not login or login == FORK_OWNER or login.endswith('[bot]') or login in ('github-actions', 'claude'):
            return False  # CI, bots and our own account never count
        return not maint or login in maint

    pending = []
    for n in nums:
        v = json.loads(run(['gh', 'pr', 'view', str(n), '-R', UP, '--json', 'state,reviews,comments']))
        why = []
        if v['state'] in ('MERGED', 'CLOSED'):
            why.append(v['state'].lower())  # check who closed it if our own account might have
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
        st = json.load(open(f'{d}/STATE.json'))
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
        return st if review_approves(d, st['head']) else None

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
                          cwd=wt, env=ENV, stdout=o, stderr=sp.STDOUT, start_new_session=True)
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

    log('driver start')
    while not os.path.exists(f'{R}/stop-driver'):
        did = False
        dirs = sorted(glob.glob(f'{R}/pr*/')) + (sorted(glob.glob(f'{NEWDIR}/*/')) if NEWDIR else [])
        for d in dirs:
            d = d.rstrip('/')
            st = ready(d)
            if not st:
                continue
            key = (d, st['head'])
            tries[key] = tries.get(key, 0) + 1
            if tries[key] > 2:
                refuse(d, 'Full suite failed twice outside the known flaky files; see suite.log / suite.json.\n',
                       'refused after 2 tries')
                continue
            did = True
            wt = st['worktree']
            # cheap pre-check before spending a full suite: textual conflict with current upstream main
            sp.run(['git', 'fetch', '-q', UP_REMOTE, 'main'], cwd=wt)
            mt = sp.run(['git', 'merge-tree', '--write-tree', '--name-only', f'{UP_REMOTE}/main', st['head']],
                        cwd=wt, capture_output=True, text=True)
            if mt.returncode:
                refuse(d, f'CONFLICT with current {UP_REMOTE}/main (pre-suite check); rebase needed.\n' + mt.stdout[-1500:],
                       'pre-check: conflicts with upstream main; skipped suite')
                continue
            if not suite(d, st):
                log(f'{os.path.basename(d)} no suite.json')
                continue
            fl = failures(d, st)
            real = [f for f in fl if f not in KNOWN]
            if real:
                # Rerun the failing files alone: still failing = real, refuse now instead of a second full run.
                solo = {f: sp.run(VITEST + [f], cwd=wt, env=ENV, capture_output=True, text=True) for f in real}
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
                    r = sp.run(VITEST + [f], cwd=wt, env=ENV, capture_output=True, text=True)
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
            break  # one publication per pass; rescan folders from the top
        if not did:
            if os.path.exists(f'{R}/_done-round'):
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
