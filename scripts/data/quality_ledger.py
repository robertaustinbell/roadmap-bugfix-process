#!/usr/bin/env python3
"""The quality tally: what the maintainer's review found in each loop PR.

Local gates say a PR is ready; the maintainer's review result says whether it was. After each
review result (merged, or sent back with findings), record one line. This is the real quality
measure, and the categories show which gate to strengthen next.

    quality_ledger.py record --pr N --head SHA --outcome merged|sent_back|closed
                             [--findings K] [--category C ...] [--note TEXT]
    quality_ledger.py tally [--since YYYY-MM-DD]

Categories: ac_overpromise, cross_tab, stalled_body, input_parsing, secret_fixture,
ac_number_reuse, other. `--findings` counts the maintainer's findings in that review (0 for a
clean merge); every finding needs a category, so a sent-back PR names at least one.

File: $STATE_DIR/pr-quality.jsonl (append-only; one line per review result). Configuration:
STATE_DIR (required).
"""
import argparse
import datetime
import fcntl
import json
import os
import re
import sys

OUTCOMES = ('merged', 'sent_back', 'closed')
CATEGORIES = ('ac_overpromise', 'cross_tab', 'stalled_body', 'input_parsing', 'secret_fixture',
              'ac_number_reuse', 'other')
SHA40 = re.compile(r'[0-9a-f]{40}')


def _loop_settings():
    """Fill unset settings from the kit's loop.env (scripts/loopenv.py)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'loopenv.py')
    if os.path.exists(p):
        import importlib.util
        spec = importlib.util.spec_from_file_location('loopenv', p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.load()


def ledger_path():
    sd = os.environ.get('STATE_DIR')
    if not sd:
        sys.exit('quality_ledger.py: STATE_DIR is not set')
    os.makedirs(sd, exist_ok=True)
    return os.path.join(sd, 'pr-quality.jsonl')


def problems(rec):
    """Every reason this record is not a valid review result. Empty means valid."""
    p = []
    if not isinstance(rec.get('pr'), int) or rec['pr'] < 1:
        p.append('pr must be a positive number')
    if not (isinstance(rec.get('head'), str) and SHA40.fullmatch(rec['head'])):
        p.append('head must be the full 40-character SHA the maintainer reviewed')
    if rec.get('outcome') not in OUTCOMES:
        p.append(f"outcome must be one of {', '.join(OUTCOMES)}")
    n, cats = rec.get('findings'), rec.get('categories') or []
    if not isinstance(n, int) or n < 0:
        p.append('findings must be 0 or more')
    bad = sorted(set(cats) - set(CATEGORIES))
    if bad:
        p.append(f'unknown categories {bad}; use {", ".join(CATEGORIES)}')
    if isinstance(n, int) and n > 0 and not cats:
        p.append('findings above 0 need at least one category')
    if isinstance(n, int) and n < len(cats):
        p.append('more categories than findings')
    if rec.get('outcome') == 'sent_back' and not n:
        p.append('sent_back needs at least one finding')
    return p


def read(path):
    out = []
    if os.path.exists(path):
        with open(path) as f:
            for i, ln in enumerate(f, 1):
                if ln.strip():
                    try:
                        out.append(json.loads(ln))
                    except ValueError:
                        sys.exit(f'quality_ledger.py: {path}:{i} is damaged; repair it by hand')
    return out


def record(path, rec):
    p = problems(rec)
    if p:
        sys.exit('quality_ledger.py: ' + '; '.join(p))
    if any(r.get('pr') == rec['pr'] and r.get('head') == rec['head'] for r in read(path)):
        sys.exit(f"quality_ledger.py: PR #{rec['pr']} at {rec['head'][:12]} is already recorded")
    rec = dict(rec, at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'))
    with open(path, 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(rec) + '\n')
    return rec


def tally(recs, since=''):
    recs = [r for r in recs if str(r.get('at', '')) >= since]
    t = {'reviews': len(recs), 'outcomes': {o: 0 for o in OUTCOMES}, 'findings': 0,
         'categories': {c: 0 for c in CATEGORIES}}
    for r in recs:
        t['outcomes'][r['outcome']] = t['outcomes'].get(r['outcome'], 0) + 1
        t['findings'] += r.get('findings', 0)
        for c in r.get('categories', []):
            t['categories'][c] = t['categories'].get(c, 0) + 1
    decided = t['outcomes']['merged'] + t['outcomes']['sent_back']
    t['clean_first_review'] = sum(1 for r in recs if r['outcome'] == 'merged' and not r.get('findings'))
    t['clean_rate'] = round(t['clean_first_review'] / decided, 2) if decided else None
    return t


def main(argv):
    _loop_settings()
    ap = argparse.ArgumentParser(prog='quality_ledger.py', description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('record')
    r.add_argument('--pr', type=int, required=True)
    r.add_argument('--head', required=True)
    r.add_argument('--outcome', required=True)
    r.add_argument('--findings', type=int, default=0)
    r.add_argument('--category', action='append', default=[])
    r.add_argument('--note', default='')
    t = sub.add_parser('tally')
    t.add_argument('--since', default='')
    a = ap.parse_args(argv)
    path = ledger_path()
    if a.cmd == 'record':
        rec = {'pr': a.pr, 'head': a.head.lower(), 'outcome': a.outcome, 'findings': a.findings,
               'categories': a.category}
        if a.note:
            rec['note'] = a.note
        print(json.dumps(record(path, rec)))
        return 0
    print(json.dumps(tally(read(path), a.since), indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
