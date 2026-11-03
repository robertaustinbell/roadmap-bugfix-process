#!/usr/bin/env python3
"""Gate for the OCR pipeline agent job. Prints one line; the agent only needs to run when it changes.

Sanitized from a working implementation; review before running.

Output:
  idle                                  nothing for the agent (paused, agent_hold, or no part in an agent stage)
  work part=<name> stage=<stage> bucket=<3h bucket> fp=<fingerprint>

- The active part is the first part that is not `done`. There is work when it is `scanned` or
  `reviewing` and has no `owner`.
- fp is a hash of fix-folder review/state file mtimes. When a tick leaves new work (a repair waiting for
  re-review, a new folder), the line changes and the next tick runs at once.
- bucket changes every 3 hours, so a part that stays in an agent stage gets another run even if
  nothing changed (this retries after a tick that failed part way).
- While an agent run holds agent.lock (younger than 2 hours), the last line is printed again, so the
  output does not change and a second run does not overlap the first.

Modes:
  monitor.py         print the line (Hermes cron "monitor" scripts: the agent runs when the output changes)
  monitor.py --gate  for plain cron/launchd: print the line, exit 0 when the agent should run now
                     (not idle, and different from the line at the last successful gate), else exit 1

Configuration: OCR_PIPELINE_DIR (or OCR_BASE_DIR + /pipeline) and FIXES_DIR, from env or from the JSON
file named by OCR_PIPELINE_CONFIG, else ocr-pipeline.json next to this script.
"""
import glob
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config():
    path = os.environ.get('OCR_PIPELINE_CONFIG') or os.path.join(HERE, 'ocr-pipeline.json')
    cfg = {}
    if os.path.exists(path):
        with open(path) as f:
            cfg = json.load(f)
    for k in ('OCR_BASE_DIR', 'OCR_PIPELINE_DIR', 'FIXES_DIR'):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def compute(P, F):
    LAST = os.path.join(P, '.monitor-last')
    LOCK = os.path.join(P, 'agent.lock')
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 2 * 3600:
        return open(LAST).read() if os.path.exists(LAST) else 'idle', True
    with open(os.path.join(P, 'state.json')) as f:
        st = json.load(f)
    out = 'idle'
    if not st.get('paused') and not st.get('agent_hold'):  # agent_hold: scans continue, agent waits
        for p in st['parts']:
            if p['stage'] == 'done':
                continue
            if p['stage'] in ('scanned', 'reviewing') and not p.get('owner'):
                files = []
                if F:
                    for pat in ('ocr*/review*.md', 'ocr*/STATE.json', 'ocr*/READY-FOR-REVIEW', 'published.jsonl'):
                        files += glob.glob(os.path.join(F, pat))
                fp = hashlib.sha1('|'.join(f'{x}:{os.path.getmtime(x):.0f}' for x in sorted(files)).encode()).hexdigest()[:12]
                out = f"work part={p['name']} stage={p['stage']} bucket={int(time.time() // 10800)} fp={fp}"
            break
    with open(LAST, 'w') as f:
        f.write(out)
    return out, False


def main():
    cfg = load_config()
    base = cfg.get('OCR_BASE_DIR')
    P = cfg.get('OCR_PIPELINE_DIR') or (os.path.join(base, 'pipeline') if base else None)
    if not P:
        print('idle', end='')
        return 1 if '--gate' in sys.argv else 0
    P = os.path.abspath(os.path.expanduser(P))
    F = os.path.abspath(os.path.expanduser(cfg['FIXES_DIR'])) if cfg.get('FIXES_DIR') else None
    try:
        out, locked = compute(P, F)
    except Exception:
        out, locked = 'idle', False  # never fail the scheduler on a transient read error
    print(out, end='')
    if '--gate' not in sys.argv:
        return 0
    gate_f = os.path.join(P, '.monitor-gate-last')
    prev = open(gate_f).read() if os.path.exists(gate_f) else ''
    if locked or out == 'idle' or out == prev:
        return 1
    with open(gate_f, 'w') as f:
        f.write(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
