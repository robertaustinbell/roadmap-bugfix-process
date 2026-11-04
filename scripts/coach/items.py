#!/usr/bin/env python3
"""Coach feedback items: how a role reads the Coach's advice and answers it.

The Coach appends items to $STATE_DIR/coach/items.jsonl (agents/coach.md). Roles never edit that
file. They read their open items at the start of a run and reply here; replies go to
$STATE_DIR/coach-responses.jsonl, which the Coach reads and never writes.

  items.py open ROLE                       open items addressed to ROLE, as JSON lines
                                           (no reply from ROLE yet, not withdrawn)
  items.py reply ID applied|not_applied|disputed --role ROLE --note TEXT [--evidence PATH ...]
                                           record ROLE's answer to item ID

Replies are append-only and one per item: a second reply to the same item is refused.
`applied` means the role did what the item suggested in this run; `not_applied` needs a reason;
`disputed` needs evidence. Advice never overrides a role's template, the evidence bar or a gate.

Configuration: STATE_DIR (required).
"""
import fcntl
import json
import os
import re
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

VERBS = ('applied', 'not_applied', 'disputed')
ROLES = ('coordinator', 'decider', 'bug-fixer', 'repair', 'adversary', 'independent-reviewer', 'ocr-pipeline-agent',
         'fmsm', 'tech-debt-audit', 'trail-of-bits', 'open-code-review')


def paths():
    sd = os.environ.get('STATE_DIR')
    if not sd:
        sys.exit('items.py: STATE_DIR is not set')
    sd = os.path.abspath(os.path.expanduser(sd))
    return os.path.join(sd, 'coach', 'items.jsonl'), os.path.join(sd, 'coach-responses.jsonl')


def read_lines(path):
    """Parse a JSONL file. A bad line is reported, not skipped silently, and never fatal for others."""
    out, bad = [], 0
    if not os.path.exists(path):
        return out, bad
    with open(path, encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except ValueError:
                bad += 1
                continue
            if isinstance(obj, dict):
                out.append(obj)
            else:
                bad += 1
    return out, bad


def open_items(role):
    items_p, resp_p = paths()
    items, bad_i = read_lines(items_p)
    resps, bad_r = read_lines(resp_p)
    withdrawn = {i.get('withdraws') for i in items if i.get('withdraws')}
    answered = {r.get('item') for r in resps if r.get('role') == role}
    todo = [i for i in items
            if i.get('to') == role and i.get('id') and not i.get('withdraws')
            and i['id'] not in withdrawn and i['id'] not in answered]
    return todo, bad_i + bad_r


def reply(item_id, verb, role, note, evidence):
    if verb not in VERBS:
        sys.exit(f'items.py: verb must be one of {", ".join(VERBS)}')
    if role not in ROLES:
        sys.exit(f'items.py: unknown role {role!r}')
    if not note.strip():
        sys.exit('items.py: --note is required (what you did, why not, or why it is wrong)')
    if verb == 'disputed' and not evidence:
        sys.exit('items.py: a dispute needs --evidence')
    items_p, resp_p = paths()
    items, _ = read_lines(items_p)
    item = next((i for i in items if i.get('id') == item_id and not i.get('withdraws')), None)
    if item is None:
        sys.exit(f'items.py: no item {item_id}')
    if any(i.get('withdraws') == item_id for i in items):
        sys.exit(f'items.py: item {item_id} was withdrawn by the Coach')
    if item.get('to') != role:
        sys.exit(f'items.py: item {item_id} is addressed to {item.get("to")}, not {role}')
    os.makedirs(os.path.dirname(resp_p), exist_ok=True)
    with open(resp_p, 'a+', encoding='utf-8') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        for ln in f:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get('item') == item_id and r.get('role') == role:
                sys.exit(f'items.py: {role} already replied to {item_id}')
        rec = {'item': item_id, 'role': role, 'reply': verb, 'note': note.strip(),
               'evidence': evidence, 'at': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        f.seek(0, os.SEEK_END)
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return rec


def main(argv):
    if len(argv) >= 2 and argv[0] == 'open':
        todo, bad = open_items(argv[1])
        for i in todo:
            print(json.dumps(i, ensure_ascii=False))
        if bad:
            print(f'items.py: {bad} unreadable line(s) skipped; tell the Coach', file=sys.stderr)
        return 0
    if len(argv) >= 3 and argv[0] == 'reply':
        item_id, verb, rest = argv[1], argv[2], argv[3:]
        opts, ev, k = {}, [], 0
        while k < len(rest):
            if rest[k] in ('--role', '--note') and k + 1 < len(rest):
                opts[rest[k][2:]] = rest[k + 1]
                k += 2
            elif rest[k] == '--evidence' and k + 1 < len(rest):
                ev.append(rest[k + 1])
                k += 2
            else:
                sys.exit(__doc__)
        if not re.fullmatch(r'C-[0-9A-Za-z-]+', item_id):
            sys.exit('items.py: item ids look like C-20261103-04')
        print(json.dumps(reply(item_id, verb, opts.get('role', ''), opts.get('note', ''), ev)))
        return 0
    sys.exit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
