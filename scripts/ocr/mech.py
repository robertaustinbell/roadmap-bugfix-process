#!/usr/bin/env python3
"""OCR pipeline: mechanics tick (no AI). Run every 15 minutes.

Sanitized from a working implementation; review before running.

What one tick does:
- Sends any notices the agent queued with `st.py notify` (through notify(), see below).
- Keeps the publish driver running (optional; only when ROUND_DIR is set).
- Sends a stall notice when the active part sits too long in an agent stage.
- Scans, but only while state['round_open'] is true. The Coordinator opens a round with
  `st.py round open` together with the other finders. In a round the tick scans new parts back to back,
  one at a time, in part order. When the usage limit of the model subscription hits, it sets
  round_open=false and leaves the stopped part `queued`; that part resumes from its saved OCR session
  next round. There is no timed retry.

Agent stages (scanned / reviewing) belong to the agent job (agents/ocr-pipeline-agent.md).

Subcommands:
  mech.py                 one tick (what the scheduler runs)
  mech.py scan-part NAME  scan one part with `ocr` (the tick launches this in the background)
  mech.py list            show each part's scan files and status

Configuration (env var, else the same key in the JSON file named by OCR_PIPELINE_CONFIG,
else ocr-pipeline.json next to this script):
  OCR_BASE_DIR      required. Holds parts/<name>.txt (one repo path per line) and results/.
  OCR_PIPELINE_DIR  default <OCR_BASE_DIR>/pipeline. Holds state.json, logs, locks.
  ROADMAP_WORKTREE  required for scans. A detached git worktree of the repo; scans run here.
  UPSTREAM_REMOTE   default "upstream". UPSTREAM_BRANCH default "main".
  OCR_BIN           default "ocr".
  KEEP_AWAKE        command prefix that stops the machine sleeping, e.g. "caffeinate -ims" on macOS.
                    Default: "caffeinate -ims" if caffeinate exists, else nothing.
  ROUND_DIR         optional. Folder the publish driver serves; the tick keeps one driver running there.
  FIXES_DIR         optional. Passed to the driver as --fixes-dir.
  PUBLISH_DRIVER    default ../publish/driver.py relative to this script.
  NOTIFY_CMD        optional. Command that receives each notice on stdin (argv split with shlex).
                    Without it, notices are printed to stdout (Hermes cron delivers stdout).

Our notices are plain status lines. Nothing here posts to GitHub.
"""
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

HERE = os.path.dirname(os.path.abspath(__file__))
REPING_S = 24 * 3600                                   # re-send a still-open stall once a day
STALL_S = {'scanned': 6 * 3600, 'reviewing': 18 * 3600}
LIMIT_PAT = ('usage_limit', 'usage limit', 'rate_limit_exceeded', 'insufficient_quota')
SCAN_STAGES = ('queued', 'scanning', 'usage-wait', 'scan-failed')


def load_config():
    path = os.environ.get('OCR_PIPELINE_CONFIG') or os.path.join(HERE, 'ocr-pipeline.json')
    cfg = {}
    if os.path.exists(path):
        with open(path) as f:
            cfg = json.load(f)
    keys = ('OCR_BASE_DIR', 'OCR_PIPELINE_DIR', 'ROADMAP_WORKTREE', 'UPSTREAM_REMOTE', 'UPSTREAM_BRANCH',
            'OCR_BIN', 'KEEP_AWAKE', 'ROUND_DIR', 'FIXES_DIR', 'PUBLISH_DRIVER', 'NOTIFY_CMD')
    for k in keys:
        if os.environ.get(k) is not None:
            cfg[k] = os.environ[k]
    if not cfg.get('OCR_BASE_DIR'):
        print('mech.py: OCR_BASE_DIR is not set (env or ocr-pipeline.json)', file=sys.stderr)
        sys.exit(0)  # exit 0 so a scheduler does not alert every tick; the message is in its log
    x = lambda v: os.path.abspath(os.path.expanduser(v)) if v else v
    cfg['OCR_BASE_DIR'] = x(cfg['OCR_BASE_DIR'])
    cfg['OCR_PIPELINE_DIR'] = x(cfg.get('OCR_PIPELINE_DIR') or os.path.join(cfg['OCR_BASE_DIR'], 'pipeline'))
    cfg['ROADMAP_WORKTREE'] = x(cfg.get('ROADMAP_WORKTREE'))
    cfg['ROUND_DIR'] = x(cfg.get('ROUND_DIR'))
    cfg['FIXES_DIR'] = x(cfg.get('FIXES_DIR'))
    cfg['PUBLISH_DRIVER'] = x(cfg.get('PUBLISH_DRIVER') or os.path.join(HERE, '..', 'publish', 'driver.py'))
    cfg.setdefault('UPSTREAM_REMOTE', 'upstream')
    cfg.setdefault('UPSTREAM_BRANCH', 'main')
    cfg.setdefault('OCR_BIN', 'ocr')
    if cfg.get('KEEP_AWAKE') is None:
        cfg['KEEP_AWAKE'] = 'caffeinate -ims' if shutil.which('caffeinate') else ''
    return cfg


CFG = load_config()
B = CFG['OCR_BASE_DIR']
P = CFG['OCR_PIPELINE_DIR']
RESULTS = os.path.join(B, 'results')
STATE = os.path.join(P, 'state.json')
REPO = CFG['ROADMAP_WORKTREE']
KEEP_AWAKE = shlex.split(CFG['KEEP_AWAKE'])
now = time.time()
msgs = []


def log(m, name='mech.log'):
    os.makedirs(P, exist_ok=True)
    with open(os.path.join(P, name), 'a') as f:
        f.write(time.strftime('%F %T ') + m + '\n')


def notify(texts):
    """Deliver notices. Pluggable: NOTIFY_CMD gets the text on stdin; otherwise print to stdout."""
    texts = [t for t in texts if t]
    if not texts:
        return
    body = '\n\n'.join(texts)
    cmd = CFG.get('NOTIFY_CMD')
    if cmd:
        r = sp.run(shlex.split(cmd), input=body, text=True, capture_output=True)
        if r.returncode:
            log(f'NOTIFY_CMD failed rc={r.returncode}: {(r.stderr or r.stdout)[-300:]}')
            print(body)  # fall back to stdout so the notice is not lost
    else:
        print(body)


def alive(pid):
    """True if a process with this pid exists (no signal is sent)."""
    try:
        os.getpgid(int(pid))
        return True
    except Exception:
        return False


def ping(part, key, text):
    """Queue a notice once per key; send it again after REPING_S if the problem is still there."""
    sent = part.setdefault('pings', {})
    if now - sent.get(key, 0) >= REPING_S:
        sent[key] = now
        msgs.append(text)
        log('PING ' + text)


def git(*args, capture=False):
    return sp.run(['git', *args], cwd=REPO, capture_output=capture, text=True)


# ---------------------------------------------------------------------------------------------
# scan-part: scan one part with ocr, stop on the first usage-limit error, remember the session
# (Python port of the shell helper the working setup used.)
# ---------------------------------------------------------------------------------------------

def stop_group(pgid):
    """End the scan's whole process group. ocr does not stop on SIGINT, so use TERM, then KILL."""
    sp.run(['pkill', '-TERM', '-g', str(pgid)], capture_output=True)
    for _ in range(16):
        if not alive(pgid):
            return
        time.sleep(0.5)
    sp.run(['pkill', '-KILL', '-g', str(pgid)], capture_output=True)


def scan_part(name):
    if not REPO:
        sys.exit('ROADMAP_WORKTREE is not set')
    lst = os.path.join(B, 'parts', f'{name}.txt')
    if not os.path.exists(lst):
        sys.exit(f'No such part: {name}')
    os.makedirs(RESULTS, exist_ok=True)
    logf = os.path.join(RESULTS, f'{name}.log')
    sessf = os.path.join(RESULTS, f'{name}.session')
    outf = os.path.join(RESULTS, f'{name}.json')
    donef = os.path.join(RESULTS, f'{name}.done')
    if os.path.exists(donef):
        print(f'{name} already done: {outf}')
        return 0
    with open(lst) as f:
        listed = [ln.strip() for ln in f if ln.strip()]
    # Part lists go stale: skip files that no longer exist on the checked-out commit.
    paths = [p for p in listed if os.path.exists(os.path.join(REPO, p))]
    if not paths:
        print(f'No files from {name} exist on this commit; marking it done')
        open(donef, 'w').close()
        return 0
    args = [CFG['OCR_BIN'], 'scan', '--timeout', '0', '--format', 'json', '--output', outf, '--path', ','.join(paths)]
    if os.path.exists(sessf):
        sid = open(sessf).read().strip()
        if sid:
            args += ['--resume', sid]
    with open(logf, 'a') as lf:
        start = lf.tell()
        lf.write(f'=== {name}  {time.strftime("%F %T")}  files={len(paths)}/{len(listed)}'
                 f'{"  resume=" + args[-1] if "--resume" in args else ""}\n')
        lf.flush()
        proc = sp.Popen(KEEP_AWAKE + args, cwd=REPO, stdout=lf, stderr=sp.STDOUT, start_new_session=True)

    def new_text():
        with open(logf, errors='replace') as f:
            f.seek(start)
            return f.read()

    limit = False
    while proc.poll() is None:
        if any(p in new_text() for p in LIMIT_PAT):
            # After the limit hits, ocr keeps dispatching and fails every remaining file at once. Stop now.
            limit = True
            with open(logf, 'a') as lf:
                lf.write(f'\n*** Usage limit hit. Stopping {name}; it resumes from its session next round. ***\n')
            stop_group(proc.pid)
            break
        time.sleep(3)
    try:
        rc = proc.wait(timeout=60)
    except sp.TimeoutExpired:
        stop_group(proc.pid)
        rc = proc.wait()
    text = new_text()

    # A session with zero finished files cannot be resumed; start fresh next time.
    if 'has no completed scan items' in text:
        if os.path.exists(sessf):
            os.remove(sessf)
        print(f'Nothing to resume yet for {name}; it starts fresh next time.')
        return 1

    m = re.findall(r'Session: ([0-9a-f-]{36})', text)
    sid = m[-1] if m else ''
    if not sid:
        r = sp.run([CFG['OCR_BIN'], 'session', 'list'], cwd=REPO, capture_output=True, text=True)
        for ln in r.stdout.splitlines():
            cols = ln.split()
            if len(cols) > 1 and cols[1] == 'full_scan':
                sid = cols[0]
                break
    if sid:
        with open(sessf, 'w') as f:
            f.write(sid + '\n')

    if rc == 0 and not limit and 'Scan subtask error' not in text:
        open(donef, 'w').close()
        print(f'{name} finished cleanly. Results: {outf}')
        return 0
    if rc == 0 and not limit:
        print(f'{name} finished, but some files errored (see {logf}). A new scan of the part retries them.')
        return 1
    print(f'{name} stopped (exit {rc}, usage limit: {limit}).')
    return 2


def list_parts():
    for f in sorted(glob.glob(os.path.join(B, 'parts', '*.txt'))):
        n = os.path.splitext(os.path.basename(f))[0]
        c = sum(1 for ln in open(f) if ln.strip())
        if os.path.exists(os.path.join(RESULTS, f'{n}.done')):
            s = 'done'
        elif os.path.exists(os.path.join(RESULTS, f'{n}.session')):
            s = 'partial (will resume)'
        else:
            s = 'not started'
        print(f'{n:<36} {c:>3} files  {s}')


# ---------------------------------------------------------------------------------------------
# tick
# ---------------------------------------------------------------------------------------------

def launch_scan(part):
    name = part['name']
    if not REPO:
        log(f'cannot scan {name}: ROADMAP_WORKTREE is not set')
        return
    if not os.path.exists(os.path.join(RESULTS, f'{name}.session')):
        # fresh part: scan the maintainer's current main
        up = f"{CFG['UPSTREAM_REMOTE']}/{CFG['UPSTREAM_BRANCH']}"
        git('fetch', '-q', CFG['UPSTREAM_REMOTE'])
        git('checkout', '-q', '--detach', up)
        part['base'] = git('rev-parse', 'HEAD', capture=True).stdout.strip()
    logf = os.path.join(RESULTS, f'{name}.log')
    part['log_start'] = os.path.getsize(logf) if os.path.exists(logf) else 0
    out = open(os.path.join(P, f'scan-{name}.out'), 'a')
    pr = sp.Popen([sys.executable, os.path.abspath(__file__), 'scan-part', name],
                  stdout=out, stderr=sp.STDOUT, start_new_session=True)
    keep_since = part.get('stage') == 'usage-wait' and part.get('stage_since')
    part.update(stage='scanning', pid=pr.pid, last_try=now, stage_since=keep_since or now)
    log(f'launched scan {name} pid {pr.pid} base {part.get("base", "")[:8]}')


def new_log(part):
    logf = os.path.join(RESULTS, f'{part["name"]}.log')
    if not os.path.exists(logf):
        return ''
    with open(logf, errors='replace') as f:
        f.seek(part.get('log_start', 0))
        return f.read()


def keep_driver_running():
    rd = CFG.get('ROUND_DIR')
    if not rd or not os.path.isdir(rd):
        return
    # A driver stopped on purpose, or a finished round, is left alone.
    if os.path.exists(os.path.join(rd, 'stop-driver')) or os.path.exists(os.path.join(rd, '_done-round')):
        return
    pidf = os.path.join(rd, 'driver.pid')
    if os.path.exists(pidf):
        try:
            if alive(open(pidf).read().strip()):
                return
        except Exception:
            pass
    cmd = KEEP_AWAKE + [sys.executable, '-I', CFG['PUBLISH_DRIVER'], 'run', '--round-dir', rd]
    if CFG.get('FIXES_DIR'):
        cmd += ['--fixes-dir', CFG['FIXES_DIR']]
    sp.Popen(cmd, cwd=rd, stdout=open(os.path.join(rd, 'driver.out'), 'a'), stderr=sp.STDOUT, start_new_session=True)
    log('publish driver was not running; launched it')


def tick(st):
    keep_driver_running()

    for part in st['parts']:
        # agent-queued notices (decisions, blockers) go out through this one channel
        for n in part.pop('notify', []):
            msgs.append(n)
            log('NOTIFY ' + n)

    active = next((p for p in st['parts'] if p['stage'] != 'done'), None)
    if active is None:
        if not st.get('finished_pinged'):
            st['finished_pinged'] = True
            msgs.append('OCR pipeline: all parts are done. Per-part reports are in the pipeline folder (NN-REPORT.md).')
        return

    # One-shot: tell the owner when every already-scanned part has been worked through.
    if st.get('notify_backlog_drained') and not any(p['stage'] in ('scanned', 'reviewing') for p in st['parts']):
        st.pop('notify_backlog_drained')
        done = [p['name'] for p in st['parts'] if p['stage'] == 'done']
        msgs.append('OCR pipeline: everything scanned so far has been triaged, fixed and posted (done: '
                    + ', '.join(done) + '). More scanning happens when the Coordinator opens the next round.')
        log('backlog drained notice queued')

    # Agent side: the first unfinished part. Stall notices only for it.
    if st.get('active') != active['name']:
        st['active'], st['active_since'] = active['name'], now
    if active['stage'] in STALL_S and not st.get('agent_hold'):
        since = max(active.get('stage_since', now), st['active_since'])
        if now - since > STALL_S[active['stage']]:
            ping(active, 'stall-' + active['stage'],
                 f'OCR pipeline may be stuck: part {active["name"]} has been in stage "{active["stage"]}" '
                 f'for {int((now - since) / 3600)} h. Check agent.log in the pipeline folder.')

    # Scan side: only inside a Coordinator-opened round. A scan already running when the round
    # closes may finish. One scan at a time, in part order. Parts in `held` are skipped.
    part = next((p for p in st['parts'] if p['stage'] in SCAN_STAGES), None)
    if part is None:
        return
    name, stage = part['name'], part['stage']
    if not st.get('round_open') and stage != 'scanning':
        return

    if stage in ('queued', 'usage-wait'):  # usage-wait: legacy stage, treated as queued inside a round
        launch_scan(part)
    elif stage == 'scanning':
        if part.get('pid') and alive(part['pid']):
            return
        text = new_log(part)
        if os.path.exists(os.path.join(RESULTS, f'{name}.done')):
            part.update(stage='scanned', stage_since=now, scan_retries=0)
            part.get('pings', {}).pop('scanfail', None)
            log(f'{name} scanned')
            st.setdefault('round_scanned', []).append(name)
            nxt = next((p for p in st['parts'] if p['stage'] == 'queued'), None)
            if nxt and st.get('round_open'):  # keep going in the same tick while this round has usage
                launch_scan(nxt)
        elif any(p in text for p in LIMIT_PAT):
            # Usage ran out: this round's scanning is over. The part resumes from its saved session next round.
            part.update(stage='queued', stage_since=now)
            st['round_open'] = False
            done = ', '.join(st.get('round_scanned', [])) or 'none finished'
            msgs.append(f"OCR: this round's scanning stopped when the model usage limit was reached "
                        f'(parts finished this round: {done}). Part {name} resumes when the Coordinator '
                        f'opens the next round.')
            log(f'{name} usage limit: round scanning closed')
        else:
            part['scan_retries'] = part.get('scan_retries', 0) + 1
            if part['scan_retries'] <= 3:
                log(f'{name} scan ended without .done (retry {part["scan_retries"]})')
                launch_scan(part)
            else:
                part['stage'] = 'scan-failed'
                ping(part, 'scanfail', f'OCR pipeline stalled: the scan of part {name} keeps failing '
                     f'(not a usage limit). See results/{name}.log.')
    elif stage == 'scan-failed':
        ping(part, 'scanfail', f'OCR pipeline still stalled on part {name} (scan failing).')


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == 'scan-part' and len(sys.argv) == 3:
            sys.exit(scan_part(sys.argv[2]))
        if sys.argv[1] == 'list':
            list_parts()
            return
        sys.exit(__doc__)
    os.makedirs(P, exist_ok=True)
    if not os.path.exists(STATE):
        log('no state.json yet; run st.py init')
        return
    with open(os.path.join(P, '.mech.lock'), 'w') as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return  # another tick (or st.py) holds the lock
        with open(STATE) as f:
            st = json.load(f)
        if st.get('paused'):
            return
        try:
            tick(st)
        except Exception as e:  # log locally, never spam; a crash shows in mech.log
            log(f'ERROR {e!r}')
        tmp = STATE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(st, f, indent=1)
        os.replace(tmp, STATE)
    notify(msgs)


if __name__ == '__main__':
    main()
