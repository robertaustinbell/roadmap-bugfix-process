#!/usr/bin/env python3
"""Gate bypass check: remove each publish gate in turn and confirm tests/test_driver.py notices.

A gate whose removal changes no test outcome is either untested or ceremony. Each mutation below is
an exact text replacement in a temporary copy of scripts/publish/driver.py; the real file is never
touched. A mutation whose text no longer exists in the driver is an error (the list has drifted).

Run from the repo root:  python3 scripts/mutation_check.py
Exit 0 = every mutation was caught by at least one test.
"""
import os
import subprocess as sp
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (gate, exact text in driver.py, replacement that disables it)
MUTATIONS = [
    ('duplicate JSON keys', 'object_pairs_hook=_no_dupes, ', ''),
    ('full 40-char head', "    elif h != head:", "    elif not head.startswith(h[:7]):"),
    ('head must be a full SHA', "if not (isinstance(h, str) and SHA40.fullmatch(h)):", "if not isinstance(h, str):"),
    ('approve needs the five checks yes', "            if c.get(k) != 'yes':", "            if False:"),
    ('blocking findings', "if cls not in ('nit', 'pre_existing') and not", "if False and not"),
    ('still_open empty', "    if r.get('still_open'):", "    if False:"),
    ('reviewer did not write the fix', "if rv.get('wrote_fix') is not False:", "if False:"),
    ('fresh context', "and rv.get('fresh_context') is not True:", "and False:"),
    ('unknown fields', "    p = _unknown(r, s['properties'], 'verdict')", "    p = []"),
    ('verdict is approve', "    if r.get('verdict') != 'approve':", "    if False:"),
    ('posted text matches review', "if os.path.exists(fp) and not (isinstance(dig, dict)", "if False and not (isinstance(dig, dict)"),
    ('VERDICT token normalization', "t = unicodedata.normalize('NFKC', text).translate(ZERO_WIDTH)", "t = text"),
    ('VERDICT token spacing', r"VERDICT_RE = re.compile(r'verdict\s*:', re.I)", "VERDICT_RE = re.compile(r'verdict:', re.I)"),
    ('untracked files', "'--untracked-files=all'", "'--untracked-files=no'"),
    ('fix commits survive rebase', "need(ahead > 0 and diff,", "need(True,"),
    ('markers in the diff', "p = artifact_problems(added, 'the diff')", "p = []"),
    ('PR body sections', "        p = body_problems(body)\n        need(not p, 'PR body: ' + '; '.join(p))\n    text_checks({'comment'",
     "        pass\n    text_checks({'comment'"),
    ('PR body sections (new PR)', "    p = body_problems(body)\n    need(not p, 'PR body: ' + '; '.join(p))\n    text_checks({'title'",
     "    text_checks({'title'"),
    ('adopt an existing PR', '    prior = existing_pr(branch)', '    prior = None'),
    ('attempted before writing', "    ledger_append(ledger, dict(rec, status='attempted'))", '    pass'),
    ('already published', "need(not ledger_has(ledger, 'branch', branch),", "need(True,"),
    ('suite keeps only listed variables', 'env = {k: base[k] for k in SUITE_KEEP if k in base}', 'env = dict(base)'),
    ('suite gets a throwaway HOME', "               HOME=home, TMPDIR", "               TMPDIR"),
    ('maintainer logins required', "    need(maint, 'MAINTAINER_LOGINS is not set", "    need(True, 'MAINTAINER_LOGINS is not set"),
    ('only listed maintainers count', '        return login in maint\n', '        return True\n'),
    ('who closed it must count', '            if counts(who):\n', '            if True:\n'),
    ('placeholders in the body', '    if holes:\n', '    if False:\n'),
]


def main():
    src = open(os.path.join(ROOT, 'scripts', 'publish', 'driver.py')).read()
    drift = [g for g, old, _ in MUTATIONS if src.count(old) != 1]
    if drift:
        sys.exit(f'mutation text not found exactly once (update MUTATIONS): {drift}')
    base = sp.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_driver.py', '-q'], cwd=ROOT,
                  capture_output=True, text=True)
    if base.returncode:
        sys.exit('tests fail on the unmutated driver; fix that first\n' + base.stderr[-2000:])
    survived = []
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, 'scripts', 'publish'))
        os.symlink(os.path.join(ROOT, 'templates'), os.path.join(t, 'templates'))
        path = os.path.join(t, 'scripts', 'publish', 'driver.py')
        for gate, old, new in MUTATIONS:
            with open(path, 'w') as f:
                f.write(src.replace(old, new))
            r = sp.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_driver.py', '-q'], cwd=ROOT,
                       env=dict(os.environ, DRIVER_PATH=path), capture_output=True, text=True)
            caught = r.returncode != 0
            print(f"{'caught  ' if caught else 'SURVIVED'} {gate}")
            if not caught:
                survived.append(gate)
    print(f'{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} gate removals caught')
    sys.exit(1 if survived else 0)


if __name__ == '__main__':
    main()
