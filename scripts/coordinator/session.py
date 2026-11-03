#!/usr/bin/env python3
"""Loop session: who started the loop, in which mode, on what scope, and what the owner asked for.

No AI and no network. The Coordinator never opens a round without an active session, and only
the owner (or the owner's own agent, acting on the owner's words) starts one.

Modes:
  automated  the Coordinator talks with the owner first, then runs rounds on its own until the
             owner stops it. Owner requests become owner pins and excludes in the next plan.
  manual     one pass on a scope agreed with the owner (areas, finders, finding kinds), for
             example "only the iPhone app code" or "only security issues". The session ends
             when that pass closes.

Commands (STATE_DIR must be set):
  session.py start --mode automated|manual --by NAME --request TEXT
                   [--areas A,B] [--exclude A,B] [--finders F,G] [--kinds K,L] [--agreed TEXT]
      Refused while a session is active. --request is the owner's words, verbatim.
      --agreed is the plan the Coordinator proposed and the owner accepted, in plain words.
  session.py request --by NAME TEXT [--areas A,B] [--exclude A,B] [--finders F,G] [--kinds K,L]
      An owner request during a session. The Coordinator takes it into the next plan.
  session.py taken ROUND        the Coordinator marks open requests as used by ROUND's plan.
  session.py stop --by NAME [--reason TEXT]
      No new rounds and no new finders. PRs already open keep their outcome watching and
      repairs, so the maintainer is never left with an unanswered fix request.
  session.py round-opened ROUND the Coordinator records that ROUND opened (refused without a session).
  session.py pass-done ROUND    the Coordinator records a closed round; a manual session ends.
  session.py prs N              the Coordinator records how many loop PRs still await the
                                maintainer or a repair. A stopped or finished session keeps a
                                Coordinator running for those only (outcomes and repairs, no rounds).
  session.py may-open-round     exit 0 if a round may open now (prints why either way).
  session.py gate               for schedulers: exit 0 if no Coordinator is working and either a
                                session is active or open PRs still need following up. Chain the
                                Coordinator after it. Never passes before the first `start`.
  session.py status             the session as JSON.

Owners: OWNERS (comma separated names, default "austin"). Anything from another person reaches
the loop through an owner.

What the owner check is and is not: `--by` is a typed name. It stops mistakes (a scheduler, a
finder or a stray message cannot start the loop by accident) and records who asked. It does not
authenticate anyone: whoever can run this script can type an owner's name. The real controls are
the Coordinator template (it starts a session only on the owner's own words in its conversation
with them) and who has access to the machine and the state folder.

Automated sessions expire: after SESSION_MAX_DAYS days (default 14) or SESSION_MAX_ROUNDS rounds
(default 10), whichever comes first, no new round opens and the owner must start a new session.
Follow-up on open PRs continues, as after a stop.
"""
import argparse
import fcntl
import json
import os
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

HERE = os.path.dirname(os.path.abspath(__file__))
WATCH = os.path.join(HERE, '..', 'coach', 'watch.py')


def state_dir():
    sd = os.environ.get('STATE_DIR')
    if not sd:
        sys.exit('session.py: STATE_DIR is not set')
    return os.path.abspath(os.path.expanduser(sd))


def owners():
    return [o.strip().lower() for o in os.environ.get('OWNERS', 'austin').split(',') if o.strip()]


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def csv(v):
    return [x.strip() for x in (v or '').split(',') if x.strip()]


def paths(sd):
    return os.path.join(sd, 'session.json'), os.path.join(sd, 'requests.jsonl'), os.path.join(sd, 'session.lock')


def load(sd):
    p = paths(sd)[0]
    try:
        with open(p) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except ValueError:
        sys.exit(f'session.py: {p} is not valid JSON; fix it by hand, do not guess')


def save(sd, s):
    p = paths(sd)[0]
    tmp = p + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(s, f, indent=2)
        f.write('\n')
    os.replace(tmp, p)


def requests(sd):
    out = []
    try:
        with open(paths(sd)[1]) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return out


def pulse():
    """Owner talk is loop activity: the Coach must see it."""
    if os.path.exists(WATCH):
        sp.run([sys.executable, '-I', WATCH, 'pulse', 'owner'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)


def scope(a):
    return {'areas': csv(a.areas), 'exclude': csv(a.exclude), 'finders': csv(a.finders), 'kinds': csv(a.kinds)}


def check_owner(name):
    if name.strip().lower() not in owners():
        sys.exit(f'session.py: {name!r} is not an owner ({", ".join(owners())}); '
                 'requests from anyone else reach the loop through an owner')


def limits():
    return float(os.environ.get('SESSION_MAX_DAYS', '14')), int(os.environ.get('SESSION_MAX_ROUNDS', '10'))


def expired(s):
    """Why an automated session has run out, or ''. Manual sessions end by themselves."""
    if not s or s.get('mode') != 'automated' or s.get('status') != 'active':
        return ''
    days, rounds = limits()
    started = s.get('started_epoch')
    if started is None:
        try:
            started = time.mktime(time.strptime(s['started_at'][:19], '%Y-%m-%dT%H:%M:%S'))
        except (KeyError, ValueError):
            return 'start time unreadable'
    if time.time() - started > days * 86400:
        return f'older than {days:g} days'
    if len(s.get('rounds', [])) >= rounds:
        return f'ran {rounds} rounds'
    return ''


def active(s):
    return bool(s) and s.get('status') == 'active' and not expired(s)


def may_open(s):
    why = expired(s)
    if why:
        return False, f'automated session expired ({why}): the owner must start a new one'
    if not active(s):
        return False, 'no active session: the owner has not started the loop'
    if s['mode'] == 'manual' and s.get('rounds'):
        return False, 'manual pass already ran'
    if s.get('round_in_progress'):
        return False, f"round {s['round_in_progress']} is still open"
    return True, f"{s['mode']} session started by {s['started_by']}"


def coordinator_working():
    if not os.path.exists(WATCH):
        return False
    r = sp.run([sys.executable, '-I', WATCH, 'status', '--json'], capture_output=True, text=True)
    try:
        return 'coordinator' in json.loads(r.stdout).get('working', [])
    except ValueError:
        return False


def main(argv):
    ap = argparse.ArgumentParser(prog='session.py', description=(__doc__ or '').split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    st = sub.add_parser('start')
    st.add_argument('--mode', required=True, choices=['automated', 'manual'])
    rq = sub.add_parser('request')
    rq.add_argument('text')
    for p in (st, rq):
        p.add_argument('--by', required=True)
        for k in ('areas', 'exclude', 'finders', 'kinds'):
            p.add_argument('--' + k, default='')
    st.add_argument('--request', required=True)
    st.add_argument('--agreed', default='')
    tk = sub.add_parser('taken')
    tk.add_argument('round')
    sp_ = sub.add_parser('stop')
    sp_.add_argument('--by', required=True)
    sp_.add_argument('--reason', default='')
    pd = sub.add_parser('pass-done')
    pd.add_argument('round')
    pr = sub.add_parser('prs')
    pr.add_argument('n', type=int)
    ro = sub.add_parser('round-opened')
    ro.add_argument('round')
    for name in ('may-open-round', 'gate', 'status'):
        sub.add_parser(name)
    a = ap.parse_args(argv)

    sd = state_dir()
    os.makedirs(sd, exist_ok=True)
    with open(paths(sd)[2], 'w') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        s = load(sd)

        if a.cmd == 'start':
            check_owner(a.by)
            if s and expired(s):
                s.update(status='expired', expired_reason=expired(s), expired_at=now_iso())
            if active(s):
                sys.exit(f"session.py: a {s['mode']} session is already active (started {s['started_at']}); stop it first")
            sc = scope(a)
            if a.mode == 'manual' and not any(sc.values()):
                sys.exit('session.py: a manual pass needs a scope (--areas, --finders or --kinds)')
            if not a.request.strip():
                sys.exit('session.py: --request must hold the owner\'s words')
            s = {'mode': a.mode, 'status': 'active', 'started_by': a.by, 'started_at': now_iso(), 'started_epoch': time.time(),
                 'request_verbatim': a.request, 'agreed': a.agreed, 'scope': sc,
                 'rounds': [], 'round_in_progress': None}
            save(sd, s)
            pulse()
            print(f'started {a.mode} session')
        elif a.cmd == 'request':
            check_owner(a.by)
            if not active(s):
                sys.exit('session.py: no active session; a request without one would never run. Start a session.')
            with open(paths(sd)[1], 'a') as f:
                f.write(json.dumps({'at': now_iso(), 'by': a.by, 'text': a.text, **scope(a), 'taken_by': None}) + '\n')
            pulse()
            print('request recorded; the next round plan takes it')
        elif a.cmd == 'taken':
            rows = requests(sd)
            n = 0
            for r in rows:
                if not r.get('taken_by'):
                    r['taken_by'] = a.round
                    n += 1
            tmp = paths(sd)[1] + '.tmp'
            with open(tmp, 'w') as f:
                f.writelines(json.dumps(r) + '\n' for r in rows)
            os.replace(tmp, paths(sd)[1])
            print(f'{n} request(s) taken by {a.round}')
        elif a.cmd == 'stop':
            check_owner(a.by)
            if not active(s):
                print('no active session')
                return 0
            s.update(status='stopped', stopped_by=a.by, stopped_at=now_iso(), stop_reason=a.reason)
            save(sd, s)
            pulse()
            print('stopped: no new rounds; open PRs keep outcome watching and repairs')
        elif a.cmd == 'round-opened':
            ok, why = may_open(s)
            if not ok:
                sys.exit(f'session.py: refused: {why}')
            s['round_in_progress'] = a.round
            save(sd, s)
            print(f'round {a.round} opened')
        elif a.cmd == 'pass-done':
            if not s:
                sys.exit('session.py: no session')
            if s.get('round_in_progress') not in (None, a.round):
                sys.exit(f"session.py: open round is {s['round_in_progress']}, not {a.round}")
            if a.round not in s['rounds']:
                s['rounds'].append(a.round)
            s['round_in_progress'] = None
            if s['mode'] == 'manual' and s['status'] == 'active':
                s.update(status='done', done_at=now_iso())
            save(sd, s)
            print(f"recorded {a.round}; session {s['status']}")
        elif a.cmd == 'prs':
            if not s:
                sys.exit('session.py: no session')
            s['awaiting_prs'] = max(0, a.n)
            save(sd, s)
            print(f"{s['awaiting_prs']} PR(s) awaiting follow-up")
        elif a.cmd == 'may-open-round':
            ok, why = may_open(s)
            print(why)
            return 0 if ok else 1
        elif a.cmd == 'gate':
            if not s or not (active(s) or s.get('awaiting_prs', 0) > 0):
                return 1
            return 1 if coordinator_working() else 0
        elif a.cmd == 'status':
            if s and expired(s):
                s = dict(s, status='expired', expired_reason=expired(s))
            print(json.dumps({'session': s, 'open_requests': [r for r in requests(sd) if not r.get('taken_by')]}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
