#!/usr/bin/env python3
"""Start checks, open-PR reconciling and the role launcher for the bug-fix loop.

    loop.py preflight [--finders a,b] [--offline]
        Everything a real run needs, checked before it starts, reported as one list. Exit 1 if
        anything is missing. --offline skips the GitHub checks (for a local self-test).
    loop.py reconcile
        Open PRs from GH_FORK_OWNER against UPSTREAM_REPO that no round and no owner has
        claimed. Any found: exit 1 ("reconcile first"). A new state folder cannot hide them.
    loop.py record-pr ROUND N [N...]
        The Coordinator records each PR it opened (step 11).
    loop.py adopt --by OWNER --label TEXT N [N...]
        The owner claims open PRs this state folder did not open (an older run, a hand PR).
        They then count for follow-up and for the start gate like the loop's own.
    loop.py run-role ROLE --round R --prompt-file F [--id ID]
        Start one role as its own process, from ROLE_CMD plus the prompt, with an environment
        built from a short allow-list. See "What run-role enforces" below.

What run-role enforces, and what it does not:
- The role's environment holds only ROLE_KEEP, the loop's settings and the names in ROLE_PASS
  (for the agent CLI's own model login). No GitHub token, no SSH agent socket.
- gh sees an empty config folder, so it is signed out. git has every credential helper turned
  off and every github.com push URL rewritten to an address that fails, so `git push` cannot work.
- Finders write to a fresh private folder outside STATE_DIR with their own copy of known.json;
  their output moves into rounds/<round>/findings/<id>/ only when they exit. A finder cannot
  read another finder's output by its known path while both run.
- It cannot stop a role that runs as your user from opening files by absolute path (for
  example ~/.config/gh) or asking the macOS keychain directly. Only a separate user account or
  a container stops that. The roles.md table says the same.
- Each start is recorded in rounds/<round>/dispatch.json: the variable NAMES the role got
  (never values) and what was disabled.
"""
import argparse
import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess as sp
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROLES = ('finder', 'decider', 'bug-fixer', 'repair', 'independent-reviewer', 'coach', 'drop-recheck')
ROLE_KEEP = ('PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TERM', 'TMPDIR')
NEVER_PASS = re.compile(r'^(GH_|GITHUB_|SSH_|GIT_)|TOKEN$', re.I)
FINDER_TOOLS = {  # finder: (setting, must be a folder or a file)
    'fmsm': ('FMSM_SKILL_DIR', 'dir'),
    'trail-of-bits': ('TOB_SKILLS_DIR', 'dir'),
    'tech-debt-audit': ('TECH_DEBT_SKILL', 'file'),
    'open-code-review': ('OCR_BIN', 'cmd'),
}


def _loop_settings():
    """Fill unset settings from the kit's loop.env (scripts/loopenv.py)."""
    sys.path.insert(0, HERE)
    import loopenv
    loopenv.load()
    return loopenv


LE = _loop_settings()


def env(k, default=''):
    return os.environ.get(k) or default


def up():
    return env('UPSTREAM_REPO', 'DrBradStanfield/roadmap')


def sh(args, **kw):
    try:
        r = sp.run(args, capture_output=True, text=True, timeout=kw.pop('timeout', 120), **kw)
    except (OSError, sp.TimeoutExpired) as e:
        return 127, '', str(e)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def state_dir():
    sd = env('STATE_DIR')
    if not sd:
        sys.exit('loop.py: STATE_DIR is not set (loop.env)')
    os.makedirs(sd, exist_ok=True)
    return sd


# ---------------------------------------------------------------- PRs known to this state folder

def prs_file():
    return os.path.join(state_dir(), 'prs.jsonl')


def known_prs():
    out = {}
    p = prs_file()
    if os.path.exists(p):
        with open(p) as f:
            for n, ln in enumerate(f, 1):
                if ln.strip():
                    try:
                        r = json.loads(ln)
                    except ValueError:
                        sys.exit(f'loop.py: {p}:{n} is damaged; repair it by hand')
                    out[int(r['pr'])] = r
    return out


def add_prs(nums, **rec):
    with open(prs_file(), 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        for n in nums:
            f.write(json.dumps({'pr': n, 'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), **rec}) + '\n')


def open_upstream_prs():
    """(problem, [numbers]) for open PRs by GH_FORK_OWNER on upstream."""
    owner = env('GH_FORK_OWNER')
    if not owner:
        return 'GH_FORK_OWNER is not set', []
    rc, out, err = sh(['gh', 'pr', 'list', '-R', up(), '--author', owner, '--state', 'open',
                       '--limit', '1000', '--json', 'number'])
    if rc:
        return f'could not list open PRs on {up()}: {err or out}', []
    try:
        return '', sorted(int(x['number']) for x in json.loads(out or '[]'))
    except (ValueError, KeyError, TypeError):
        return f'unreadable answer from gh pr list: {out[:200]}', []


def reconcile_problems():
    why, nums = open_upstream_prs()
    if why:
        return [why]
    unknown = [n for n in nums if n not in known_prs()]
    if unknown:
        shown = ', '.join(f'#{n}' for n in unknown[:15]) + (' ...' if len(unknown) > 15 else '')
        return [f'{len(unknown)} open PR(s) from {env("GH_FORK_OWNER")} on {up()} that no round in this '
                f'state folder opened and no owner adopted ({shown}); reconcile first: the owner runs '
                '`loop.py adopt --by <owner> --label <where they came from> N...`']
    return []


# ---------------------------------------------------------------- preflight

def node_major_wanted(workdir):
    for name in ('.nvmrc', '.node-version'):
        p = os.path.join(workdir, name)
        if os.path.exists(p):
            m = re.search(r'(\d+)', open(p).read())
            if m:
                return m.group(1), name
    wf = os.path.join(workdir, '.github', 'workflows')
    if os.path.isdir(wf):
        for f in sorted(os.listdir(wf)):
            m = re.search(r'node-version:\s*["\']?(\d+)', open(os.path.join(wf, f), errors='replace').read())
            if m:
                return m.group(1), f'.github/workflows/{f}'
    return None, None


def tool_path():
    extra = [p for p in (env('NODE_BIN_DIR'), env('EXTRA_PATH')) if p]
    return ':'.join(extra + [env('PATH')])


def preflight(finders, offline):
    probs, notes = [], []
    with_path = dict(os.environ, PATH=tool_path())
    for k in ('STATE_DIR', 'WORKDIR', 'OWNERS', 'MAINTAINER_LOGINS', 'GH_FORK_OWNER', 'COACH_CMD', 'ROLE_CMD'):
        if not env(k):
            probs.append(f'{k} is not set (loop.env)')
    if not env('ATTRIBUTION'):
        notes.append('ATTRIBUTION is not set: PR bodies will carry no sign-off line')
    wd = env('WORKDIR')
    if wd:
        for remote, want in (('upstream', up()), ('origin', f'{env("GH_FORK_OWNER")}/')):
            rc, url, _ = sh(['git', '-C', wd, 'remote', 'get-url', remote])
            if rc or want.lower() not in url.lower():
                probs.append(f'WORKDIR remote {remote} should point at {want.rstrip("/")} (got {url or "nothing"})')
        major, src = node_major_wanted(wd)
        rc, v, _ = sh(['node', '-v'], env=with_path)
        if rc:
            probs.append('node does not run (NODE_BIN_DIR, PATH)')
        elif not major:
            probs.append('cannot tell which Node CI uses (no .nvmrc, .node-version or node-version: in workflows)')
        elif not v.lstrip('v').startswith(major + '.'):
            probs.append(f'node is {v}, CI uses {major} ({src}); set NODE_BIN_DIR')
        lock = os.path.join(wd, 'package-lock.json')
        stamp = os.path.join(wd, 'node_modules', '.package-lock.json')
        if os.path.exists(lock) and not (os.path.exists(stamp) and os.path.getmtime(stamp) >= os.path.getmtime(lock)):
            probs.append('node_modules is missing or older than package-lock.json; run `npm ci --ignore-scripts` in WORKDIR')
    rc, v, _ = sh(['openssl', 'version'], env=with_path)
    if rc or not v.startswith('OpenSSL 3'):
        probs.append(f'OpenSSL 3 is not first on PATH (got {v or "nothing"}); put its bin folder in EXTRA_PATH')
    rc, _, _ = sh([env('GITLEAKS_BIN', 'gitleaks'), 'version'])
    if rc:
        probs.append('gitleaks does not run (GITLEAKS_BIN)')
    coach = env('COACH_CMD')
    if coach and not shutil.which(shlex.split(coach)[0]):
        probs.append(f'COACH_CMD: {shlex.split(coach)[0]} is not on PATH')
    role = env('ROLE_CMD')
    if role and not shutil.which(shlex.split(role)[0]):
        probs.append(f'ROLE_CMD: {shlex.split(role)[0]} is not on PATH')
    for f in finders:
        if f not in FINDER_TOOLS:
            probs.append(f'unknown finder {f}')
            continue
        key, kind = FINDER_TOOLS[f]
        val = env(key)
        ok = bool(val) and (os.path.isdir(val) if kind == 'dir' else os.path.isfile(val) if kind == 'file'
                            else bool(shutil.which(val)))
        if not ok:
            probs.append(f'{f}: its pinned tool is not installed ({key}={val or "unset"})')
    if offline:
        notes.append('offline: GitHub sign-in, upstream role and open-PR checks skipped')
    else:
        rc, who, err = sh(['gh', 'api', 'user', '-q', '.login'])
        if rc:
            probs.append(f'gh is not signed in: {err[:120]}')
        elif who != env('GH_FORK_OWNER'):
            probs.append(f'gh is signed in as {who}, not GH_FORK_OWNER {env("GH_FORK_OWNER")}')
        rc, perms, err = sh(['gh', 'api', f'repos/{up()}', '-q', '.permissions'])
        try:
            p = json.loads(perms) if not rc else None
        except ValueError:
            p = None
        if p is None:
            probs.append(f'could not read this account\'s role on {up()}')
        elif any(p.get(k) for k in ('admin', 'maintain', 'push')):
            probs.append(f'the account can write to {up()}; the loop must run from an account that cannot merge')
        probs += reconcile_problems()
    return probs, notes


# ---------------------------------------------------------------- run-role

def role_env(sd, ghdir):
    keep = {k: os.environ[k] for k in ROLE_KEEP if k in os.environ}
    keep.update({k: os.environ[k] for k in LE.KEYS if os.environ.get(k)})
    for name in filter(None, env('ROLE_PASS').split(',')):
        name = name.strip()
        if NEVER_PASS.search(name):
            sys.exit(f'loop.py: ROLE_PASS may not hand {name} to a role')
        if name in os.environ:
            keep[name] = os.environ[name]
    os.makedirs(ghdir, exist_ok=True)
    ssh_user = 'git' + '@'
    cfg = [('credential.helper', '')]  # an empty value clears every helper set elsewhere
    cfg += [('url.https://push-disabled-by-loop.invalid/.pushInsteadOf', u)
            for u in ('https://github.com/', ssh_user + 'github.com:', 'ssh://' + ssh_user + 'github.com/')]
    keep.update(GH_CONFIG_DIR=ghdir, GH_PROMPT_DISABLED='1', GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1',
                GIT_CONFIG_COUNT=str(len(cfg)), LOOP_CONFIG=LE.path() if os.path.exists(LE.path()) else os.devnull)
    for i, (k, v) in enumerate(cfg):
        keep[f'GIT_CONFIG_KEY_{i}'], keep[f'GIT_CONFIG_VALUE_{i}'] = k, v
    return keep


def record_dispatch(rd, entry):
    p = os.path.join(rd, 'dispatch.json')
    with open(os.path.join(rd, '.dispatch.lock'), 'w') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        d = {'agents': []}
        if os.path.exists(p):
            with open(p) as f:
                d = json.load(f)
        d.setdefault('agents', []).append(entry)
        with open(p + '.tmp', 'w') as f:
            json.dump(d, f, indent=1)
        os.replace(p + '.tmp', p)


def watch(verb, role, mid):
    sh([sys.executable, '-I', os.path.join(HERE, 'coach', 'watch.py'), verb, role, '--id', mid])


def run_role(a):
    if a.role not in ROLES:
        sys.exit(f'loop.py: unknown role {a.role} ({", ".join(ROLES)})')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', a.id or a.role) or not re.fullmatch(r'[A-Za-z0-9._-]+', a.round):
        sys.exit('loop.py: --id and --round may hold only letters, digits, . _ -')
    cmd = env('ROLE_CMD')
    if not cmd:
        sys.exit('loop.py: ROLE_CMD is not set (loop.env): the agent CLI that takes a prompt, e.g. claude -p')
    sd = state_dir()
    rd = os.path.join(sd, 'rounds', a.round)
    mid = a.id or a.role
    os.makedirs(os.path.join(rd, 'logs'), exist_ok=True)
    with open(a.prompt_file) as f:
        prompt = f.read()
    final_out = os.path.join(rd, 'findings', mid) if a.role == 'finder' else ''
    out = ''
    if a.role == 'finder':
        if os.path.exists(final_out) and os.listdir(final_out):
            sys.exit(f'loop.py: {final_out} already has output; a finder never overwrites another run')
        out = tempfile.mkdtemp(prefix=f'finder-{mid}-')
        known = os.path.join(rd, 'known.json')
        if os.path.exists(known):
            shutil.copy(known, os.path.join(out, 'known.json'))
        prompt = prompt.replace('$OUT', out).replace('$KNOWN', os.path.join(out, 'known.json'))
    e = role_env(sd, os.path.join(sd, '.no-gh'))
    if out:
        e.update(OUT=out, KNOWN=os.path.join(out, 'known.json'))
    argv = shlex.split(cmd) + [prompt]
    record_dispatch(rd, {'role': a.role, 'id': mid, 'runtime': shlex.split(cmd)[0], 'started': time.time(),
                         'env_names': sorted(e), 'github': 'gh signed out (empty GH_CONFIG_DIR); git credential '
                         'helpers off; github.com push URLs rewritten to fail; no SSH agent socket',
                         'not_enforced': 'files under HOME and the macOS keychain stay reachable to a process '
                         'running as this user', 'writes': final_out or 'per its template'})
    watch('begin', a.role, mid)
    try:
        with open(os.path.join(rd, 'logs', f'{a.role}-{mid}.log'), 'a') as log:
            rc = sp.run(argv, env=e, stdout=log, stderr=sp.STDOUT, cwd=a.cwd or None).returncode
    finally:
        watch('end', a.role, mid)
        if out:
            os.makedirs(os.path.dirname(final_out), exist_ok=True)
            if os.path.exists(final_out):
                os.rmdir(final_out)  # empty, checked above
            shutil.move(out, final_out)
    print(f'{a.role} {mid} exit {rc}')
    return rc


# ---------------------------------------------------------------- main

def main(argv):
    ap = argparse.ArgumentParser(prog='loop.py', description='Start checks and role launcher.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    pf = sub.add_parser('preflight')
    pf.add_argument('--finders', default=','.join(FINDER_TOOLS))
    pf.add_argument('--offline', action='store_true')
    sub.add_parser('reconcile')
    rp = sub.add_parser('record-pr')
    rp.add_argument('round')
    rp.add_argument('n', type=int, nargs='+')
    ad = sub.add_parser('adopt')
    ad.add_argument('--by', required=True)
    ad.add_argument('--label', required=True)
    ad.add_argument('n', type=int, nargs='+')
    rr = sub.add_parser('run-role')
    rr.add_argument('role')
    rr.add_argument('--round', required=True)
    rr.add_argument('--prompt-file', required=True)
    rr.add_argument('--id', default='')
    rr.add_argument('--cwd', default='')
    a = ap.parse_args(argv)

    if a.cmd == 'preflight':
        probs, notes = preflight([f for f in a.finders.split(',') if f], a.offline)
        for n in notes:
            print('note: ' + n)
        for p in probs:
            print('MISSING: ' + p)
        print('ready' if not probs else f'{len(probs)} problem(s); fix them before starting')
        return 1 if probs else 0
    if a.cmd == 'reconcile':
        probs = reconcile_problems()
        print('\n'.join(probs) if probs else 'every open PR is known to this state folder')
        return 1 if probs else 0
    if a.cmd == 'record-pr':
        add_prs(a.n, round=a.round, by='coordinator')
        print(f'recorded {len(a.n)} PR(s) for {a.round}')
        return 0
    if a.cmd == 'adopt':
        owners = [o.strip().lower() for o in env('OWNERS', 'austin').split(',') if o.strip()]
        if a.by.lower() not in owners:
            sys.exit(f'loop.py: {a.by!r} is not an owner; only an owner adopts PRs')
        add_prs(a.n, round='adopted', label=a.label, by=a.by.lower())
        print(f'adopted {len(a.n)} PR(s): they now count for follow-up and the start gate')
        return 0
    if a.cmd == 'run-role':
        return run_role(a)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
