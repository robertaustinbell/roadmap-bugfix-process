#!/usr/bin/env python3
"""OCR pipeline state editor. Safe edits to state.json under the same lock the mechanics tick takes.

Sanitized from a working implementation; review before running.

Usage:
  st.py show
  st.py init                            create state.json from <OCR_BASE_DIR>/parts/*.txt (refuses if it exists)
  st.py stage <part> <stage>            set a part's stage (also sets stage_since; clears owner)
  st.py notify <part> "<text>"          queue a one-line notice; the next mechanics tick sends it once
  st.py set <part> <key> <json-value>   set any field on a part (e.g. held_reason '"waiting on X"')
  st.py top <key> <json-value>          set a top-level field (e.g. agent_hold true, paused false)
  st.py round open|close                Coordinator only: open = OCR may scan new parts this round
                                        until the usage limit hits; close = no new scans

<part> is an exact part name or a prefix that matches exactly one part. (The original took the first
prefix match, so "04" silently hit "04a-...". This version refuses an ambiguous prefix.)

Stages: queued, scanning, scan-failed, scanned, reviewing, held, done.
("usage-wait" is a legacy stage from an older design; `round open` turns it back into queued.)

Where state lives (first match wins):
  1. --dir <pipeline dir> on the command line
  2. env OCR_PIPELINE_DIR
  3. env OCR_BASE_DIR + "/pipeline"
  4. the same keys in a JSON config file: env OCR_PIPELINE_CONFIG, else ocr-pipeline.json next to this script
"""
import fcntl
import glob
import json
import os
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

STAGES = {'queued', 'scanning', 'scan-failed', 'scanned', 'reviewing', 'held', 'done', 'usage-wait'}


def load_config():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.environ.get('OCR_PIPELINE_CONFIG') or os.path.join(here, 'ocr-pipeline.json')
    cfg = {}
    if os.path.exists(path):
        with open(path) as f:
            cfg = json.load(f)
    for k in ('OCR_BASE_DIR', 'OCR_PIPELINE_DIR'):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def pipeline_dir(argv):
    if '--dir' in argv:
        i = argv.index('--dir')
        d = argv[i + 1]
        del argv[i:i + 2]
        return os.path.abspath(os.path.expanduser(d)), None
    cfg = load_config()
    base = cfg.get('OCR_BASE_DIR')
    d = cfg.get('OCR_PIPELINE_DIR') or (os.path.join(base, 'pipeline') if base else None)
    if not d:
        sys.exit('Set OCR_PIPELINE_DIR or OCR_BASE_DIR (env or ocr-pipeline.json), or pass --dir.')
    return os.path.abspath(os.path.expanduser(d)), base


def save(state_path, st):
    tmp = state_path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, state_path)


def find_part(st, key):
    exact = [p for p in st['parts'] if p['name'] == key]
    if exact:
        return exact[0]
    hits = [p for p in st['parts'] if p['name'].startswith(key)]
    if len(hits) != 1:
        names = ', '.join(p['name'] for p in hits) or 'none'
        sys.exit(f'"{key}" must match exactly one part (matched: {names}). Use a longer prefix.')
    return hits[0]


def show(st):
    print('paused', bool(st.get('paused')), '| agent_hold', bool(st.get('agent_hold')),
          '| round_open', bool(st.get('round_open')),
          '| scanned this round:', ', '.join(st.get('round_scanned', [])) or '-')
    for p in st['parts']:
        since = time.strftime('%m-%d %H:%M', time.localtime(p.get('stage_since', 0)))
        print(f"{p['name']:<36} {p['stage']:<12} {p.get('owner', ''):<10} {since}")


def main():
    argv = sys.argv[1:]
    pdir, base = pipeline_dir(argv)
    os.makedirs(pdir, exist_ok=True)
    state_path = os.path.join(pdir, 'state.json')
    cmd = argv[0] if argv else 'show'

    with open(os.path.join(pdir, '.mech.lock'), 'w') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)

        if cmd == 'init':
            if os.path.exists(state_path):
                sys.exit('state.json already exists; edit it with the other commands.')
            if not base:
                sys.exit('init needs OCR_BASE_DIR (it reads <OCR_BASE_DIR>/parts/*.txt).')
            names = sorted(os.path.splitext(os.path.basename(x))[0] for x in glob.glob(os.path.join(base, 'parts', '*.txt')))
            if not names:
                sys.exit('No part lists found in <OCR_BASE_DIR>/parts/.')
            now = time.time()
            st = {'created': time.strftime('%F'), 'round_open': False, 'round_scanned': [],
                  'parts': [{'name': n, 'stage': 'queued', 'stage_since': now} for n in names]}
            save(state_path, st)
            print(f'created state.json with {len(names)} parts')
            return

        with open(state_path) as f:
            st = json.load(f)

        if cmd == 'show':
            show(st)
            return

        if cmd == 'round':
            if len(argv) < 2 or argv[1] not in ('open', 'close'):
                sys.exit('usage: st.py round open|close')
            if argv[1] == 'open':
                st.update(round_open=True, round_scanned=[], round_opened_at=time.time())
                for p in st['parts']:
                    if p['stage'] == 'usage-wait':
                        p['stage'] = 'queued'
            else:
                st['round_open'] = False
            save(state_path, st)
            print('round_open', st.get('round_open'))
            return

        if cmd == 'top':
            if len(argv) != 3:
                sys.exit('usage: st.py top <key> <json-value>')
            st[argv[1]] = json.loads(argv[2])
            save(state_path, st)
            print(argv[1], st[argv[1]])
            return

        if cmd not in ('stage', 'notify', 'set') or len(argv) < 3:
            sys.exit(__doc__)
        part = find_part(st, argv[1])
        if cmd == 'stage':
            if argv[2] not in STAGES:
                sys.exit(f'unknown stage {argv[2]!r}; one of {sorted(STAGES)}')
            part.update(stage=argv[2], stage_since=time.time())
            part.pop('owner', None)
        elif cmd == 'notify':
            part.setdefault('notify', []).append(argv[2])
        elif cmd == 'set':
            if len(argv) != 4:
                sys.exit('usage: st.py set <part> <key> <json-value>')
            part[argv[2]] = json.loads(argv[3])
        save(state_path, st)
        print(part['name'], part['stage'])


if __name__ == '__main__':
    main()
