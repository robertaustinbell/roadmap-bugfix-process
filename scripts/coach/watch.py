#!/usr/bin/env python3
"""Coach watch: keep the Coach running whenever any loop agent is working, and for a while after.

No AI and no network. It only records who is working and starts the Coach command. The Coach
itself is read-only on loop state (agents/coach.md); this script never changes loop state either.

How activity is recorded (all files under $STATE_DIR/activity/):
  watch.py run ROLE -- CMD...   run CMD; ROLE counts as working until CMD exits.
                                For launchers that start a process (OCR scans, scripted agents).
  watch.py begin ROLE [--id X]  ROLE is working. For agents started inside an agent runtime,
                                which have no process id. Expires after ACTIVITY_TTL_MIN unless
                                begun again; call `end` when the agent returns.
  watch.py end ROLE [--id X]    ROLE stopped.
  watch.py pulse ROLE           something happened just now (a publish, a maintainer action).
  WATCH_FILES                   files whose change counts as a pulse (publish ledger,
                                scorecard.csv, outcomes.jsonl). Checked on every `tick`.

Deciding:
  watch.py status [--json]      active   - an agent other than the Coach is working
                                cooldown - nobody is working, the last activity was less than
                                           COOLDOWN_MIN minutes ago
                                idle     - neither
  watch.py [tick]               (no arguments means tick, for schedulers)
                                if status is active or cooldown and the Coach is not running,
                                start COACH_CMD. Run it from every scheduler tick and every time
                                a launcher starts an agent. Safe to run often: one Coach at a time.

The Coach polls `watch.py status` and writes its feedback and exits once it reads `idle`.

Configuration (env vars):
  STATE_DIR        required. The loop state folder.
  COACH_CMD        command that starts one Coach run (argv split with shlex). Without it, `tick`
                   only reports what it would do.
  COOLDOWN_MIN     default 30.
  ACTIVITY_TTL_MIN default 120. A `begin` older than this with no `end` stops counting.
  WATCH_FILES      paths separated by os.pathsep; relative paths are under STATE_DIR.
                   Default: scorecard.csv, outcomes.jsonl.
"""
import fcntl
import json
import os
import re
import shlex
import subprocess as sp
import sys
import time


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

COACH = 'coach'


def cfg():
    sd = os.environ.get('STATE_DIR')
    if not sd:
        sys.exit('watch.py: STATE_DIR is not set')
    sd = os.path.abspath(os.path.expanduser(sd))
    files = os.environ.get('WATCH_FILES', os.pathsep.join(['scorecard.csv', 'outcomes.jsonl']))
    return {
        'state': sd,
        'dir': os.path.join(sd, 'activity'),
        'cooldown': float(os.environ.get('COOLDOWN_MIN', '30')) * 60,
        'ttl': float(os.environ.get('ACTIVITY_TTL_MIN', '120')) * 60,
        'cmd': os.environ.get('COACH_CMD', ''),
        'files': [f if os.path.isabs(f) else os.path.join(sd, f) for f in files.split(os.pathsep) if f],
    }


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False


def safe(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', name or ''):
        sys.exit(f'watch.py: bad name {name!r} (letters, digits, . _ - only)')
    return name


def write_json(path, data):
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def marker(c, role, mid):
    return os.path.join(c['dir'], f'{safe(role)}--{safe(mid)}.json')


def last_activity(c, now):
    p = os.path.join(c['dir'], 'last.json')
    t = (read_json(p) or {}).get('t', 0)
    if t > now:
        # a clock jump or a bad write: correct it once, so it cannot hold the cool-down open
        write_json(p, {'t': now})
        return now
    return t


def touch_last(c, t):
    os.makedirs(c['dir'], exist_ok=True)
    p = os.path.join(c['dir'], 'last.json')
    if t > last_activity(c, t):
        write_json(p, {'t': t})


def pulse_from_files(c, now):
    """A changed watched file counts as activity at the time it changed."""
    seen_p = os.path.join(c['dir'], 'files.json')
    seen = read_json(seen_p) or {}
    changed = False
    for f in c['files']:
        try:
            st = os.stat(f)
        except OSError:
            continue
        sig = [st.st_mtime_ns, st.st_size]
        if seen.get(f) != sig:
            if f in seen:  # the first sighting is a baseline, not an event
                touch_last(c, min(st.st_mtime, now))
            seen[f] = sig
            changed = True
    if changed:
        os.makedirs(c['dir'], exist_ok=True)
        write_json(seen_p, seen)


def working(c, now):
    """Roles currently working, Coach excluded. Dead or expired markers are closed out."""
    out = []
    if not os.path.isdir(c['dir']):
        return out
    for name in sorted(os.listdir(c['dir'])):
        if '--' not in name or not name.endswith('.json'):
            continue
        p = os.path.join(c['dir'], name)
        m = read_json(p)
        if not m:
            continue
        if m.get('pid') is not None:
            live = alive(m['pid'])
        else:
            live = now - m.get('t', 0) < c['ttl']
        if live:
            if m.get('role') != COACH:
                out.append(m.get('role'))
        else:
            # it stopped without saying so: count it as having stopped now, then forget it
            touch_last(c, now)
            try:
                os.remove(p)
            except OSError:
                pass
    return out


def status(c, now=None):
    now = time.time() if now is None else now
    pulse_from_files(c, now)
    roles = working(c, now)
    last = last_activity(c, now)
    if roles:
        state = 'active'
    elif last and now - last < c['cooldown']:
        state = 'cooldown'
    else:
        state = 'idle'
    return {'status': state, 'working': roles, 'last_activity': last or None,
            'cooldown_ends': (last + c['cooldown']) if state == 'cooldown' else None}


def begin(c, role, mid, pid=None):
    os.makedirs(c['dir'], exist_ok=True)
    now = time.time()
    write_json(marker(c, role, mid), {'role': role, 'id': mid, 'pid': pid, 't': now})
    touch_last(c, now)


def end(c, role, mid):
    try:
        os.remove(marker(c, role, mid))
    except FileNotFoundError:
        pass
    touch_last(c, time.time())


def coach_running(c):
    m = read_json(os.path.join(c['dir'], 'coach.pid.json'))
    return bool(m and alive(m.get('pid')))


def tick(c):
    os.makedirs(c['dir'], exist_ok=True)
    with open(os.path.join(c['dir'], '.tick.lock'), 'w') as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 'busy'
        s = status(c)
        if s['status'] == 'idle':
            return 'idle'
        if coach_running(c):
            return 'coach running'
        if not c['cmd']:
            return 'would start coach (COACH_CMD not set)'
        log = open(os.path.join(c['dir'], 'coach.out'), 'a')
        env = dict(os.environ, COACH_TRIGGER=s['status'])
        pr = sp.Popen(shlex.split(c['cmd']), stdout=log, stderr=sp.STDOUT, env=env,
                      start_new_session=True)
        write_json(os.path.join(c['dir'], 'coach.pid.json'), {'pid': pr.pid, 't': time.time(),
                                                              'trigger': s['status']})
        return f'started coach pid {pr.pid} ({s["status"]})'


def main(argv):
    if argv and argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    c = cfg()
    if not argv:
        argv = ['tick']
    verb, rest = argv[0], argv[1:]

    def opt_id():
        if '--id' in rest:
            i = rest.index('--id')
            if i + 1 >= len(rest) or not rest[i + 1] or rest[i + 1].startswith('-'):
                sys.exit('watch.py: --id needs a value')
            return rest[i + 1]
        return 'main'

    if verb == 'run':
        if '--' not in rest or rest.index('--') != 1:
            sys.exit('usage: watch.py run ROLE -- CMD...')
        role, cmd = rest[0], rest[2:]
        if not cmd:
            sys.exit('usage: watch.py run ROLE -- CMD...')
        pr = sp.Popen(cmd)
        mid = f'pid{pr.pid}'
        begin(c, role, mid, pid=pr.pid)
        tick(c)
        try:
            rc = pr.wait()
        finally:
            end(c, role, mid)
        return rc
    if verb == 'begin' and rest:
        begin(c, rest[0], opt_id())
        print(tick(c))
        return 0
    if verb == 'end' and rest:
        end(c, rest[0], opt_id())
        return 0
    if verb == 'pulse' and rest:
        safe(rest[0])
        touch_last(c, time.time())
        print(tick(c))
        return 0
    if verb == 'status':
        s = status(c)
        print(json.dumps(s) if '--json' in rest else s['status'])
        return 0
    if verb == 'tick':
        out = tick(c)
        if out.startswith('started') or verb != 'tick' or os.environ.get('WATCH_VERBOSE'):
            print(out)  # a scheduler delivers stdout: stay quiet unless a Coach started
        return 0
    sys.exit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
