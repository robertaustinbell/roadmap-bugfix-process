#!/usr/bin/env python3
"""One settings file for the whole loop, read by every script.

Every script loads it before reading its settings, so a subagent, a cron job or a Coach started
by the watch gets the same values without anyone exporting them. A variable already set in the
environment wins over the file, so a one-off override still works.

File: $LOOP_CONFIG if set, else `loop.env` in the kit root (git-ignored; copy loop.env.example).
Format: KEY=VALUE lines, `#` comments, optional quotes around the value. Only the keys in KEYS
are accepted, so a typo fails loudly instead of being ignored. Secrets never go in this file:
a name that looks like a token, key or password is refused.

    python3 scripts/loopenv.py show     effective settings and where each came from
    python3 scripts/loopenv.py check    exit 1 if the file is invalid or a required key is missing
"""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# key: (required for a real run, what it is)
KEYS = {
    'STATE_DIR': (True, 'loop state folder, outside every repo'),
    'WORKDIR': (True, 'roadmap clone: upstream = DrBradStanfield/roadmap, origin = the fork'),
    'GH_FORK_OWNER': (True, 'GitHub login that owns the fork'),
    'OWNERS': (True, 'comma-separated owner names who may start, stop or aim the loop'),
    'MAINTAINER_LOGINS': (True, 'comma-separated GitHub logins whose actions count as addressed'),
    'COACH_CMD': (True, 'command that starts the Coach as a separate agent'),
    'ROLE_CMD': (True, 'agent CLI that takes a prompt as its last argument, for loop.py run-role, with a turn budget '
                       'long enough for a Bug fixer\'s gates (e.g. claude -p --max-turns 400, or '
                       'hermes chat --oneshot --max-turns 400 -q)'),
    'ROLE_PASS': (False, 'comma-separated variable NAMES the agent CLI needs for its model login; never GitHub or SSH'),
    'FMSM_SKILL_DIR': (False, 'pinned fuck-my-shit-mountain skill folder (finder fmsm)'),
    'TOB_SKILLS_DIR': (False, 'pinned Trail of Bits skills clone (finder trail-of-bits)'),
    'TECH_DEBT_SKILL': (False, 'pinned tech-debt-audit SKILL.md (finder tech-debt-audit)'),
    'ATTRIBUTION': (False, 'line added to PR bodies naming who runs the loop'),
    'REPAIR_CAP': (False, '2 or 3 maintainer-requested repair rounds (default 3)'),
    'SESSION_MAX_DAYS': (False, 'an automated session ends after this many days (default 14)'),
    'SESSION_MAX_ROUNDS': (False, 'an automated session ends after this many rounds (default 10)'),
    'UPSTREAM_REPO': (False, 'default DrBradStanfield/roadmap'),
    'UPSTREAM_REMOTE': (False, 'default upstream'),
    'PUSH_REMOTE': (False, 'default origin'),
    'KNOWN_FLAKY': (False, 'comma-separated test files known to be flaky'),
    'DRIVER_MAX_LOAD': (False, 'publish driver waits while load average is above this'),
    'SUITE_TIMEOUT_MIN': (False, 'full suite timeout in minutes (default 45)'),
    'SUITE_MAX_WORKERS': (False, 'test workers for the full suite (default 4)'),
    'GITLEAKS_BIN': (False, 'secret scanner command (default gitleaks)'),
    'KEEP_AWAKE': (False, 'command prefix that keeps the machine awake; empty for none'),
    'NODE_BIN_DIR': (False, 'folder with the node binary CI uses'),
    'EXTRA_PATH': (False, 'extra PATH entries for the suite'),
    'ALLOW_FORCE_WITH_LEASE': (False, '1 allows force-with-lease repair pushes (default off)'),
    'COOLDOWN_MIN': (False, 'Coach keeps watching this many minutes after activity (default 30)'),
    'ACTIVITY_TTL_MIN': (False, 'a begun agent counts as working this long (default 120)'),
    'WATCH_FILES': (False, 'files whose change counts as activity for the Coach'),
    'WATCH_VERBOSE': (False, 'non-empty: watch.py tick always prints'),
    'OCR_PIPELINE_CONFIG': (False, 'path to the OCR pipeline JSON config'),
    'OCR_BASE_DIR': (False, 'OCR pipeline: base folder (or set it in the OCR JSON config)'),
    'OCR_PIPELINE_DIR': (False, 'OCR pipeline: pipeline state folder'),
    'ROADMAP_WORKTREE': (False, 'OCR pipeline: roadmap worktree to scan'),
    'UPSTREAM_BRANCH': (False, 'OCR pipeline: upstream branch (default main)'),
    'OCR_BIN': (False, 'OCR pipeline: the ocr command'),
    'ROUND_DIR': (False, 'OCR pipeline: round folder'),
    'FIXES_DIR': (False, 'OCR pipeline: fixes folder'),
    'PUBLISH_DRIVER': (False, 'OCR pipeline: path to scripts/publish/driver.py'),
    'NOTIFY_CMD': (False, 'command that receives notices on stdin'),
}
# Read by scripts but never from the file: set per process, not per installation.
INTERNAL = {'LOOP_CONFIG', 'COACH_TRIGGER', 'DRIVER_PATH', 'PATH'}
SECRET = re.compile(r'TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL|^GH_TOKEN$|^GITHUB_TOKEN$', re.I)
LINE = re.compile(r'^(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$')


class ConfigError(Exception):
    pass


def path():
    return os.environ.get('LOOP_CONFIG') or os.path.join(ROOT, 'loop.env')


def parse(text, where='loop.env'):
    out = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        m = LINE.match(line)
        if not m:
            raise ConfigError(f'{where}:{n}: not KEY=VALUE')
        key, val = m.group(1), m.group(2).strip()
        if SECRET.search(key):
            raise ConfigError(f'{where}:{n}: {key} looks like a secret; secrets never go in this file')
        if key not in KEYS:
            raise ConfigError(f'{where}:{n}: unknown setting {key} (see loop.env.example)')
        if len(val) >= 2 and val[0] == val[-1] and val[0] in '"\'':
            val = val[1:-1]
        if not val:
            continue  # an empty line from loop.env.example means "not set"
        out[key] = os.path.expanduser(val) if key in ('STATE_DIR', 'WORKDIR', 'NODE_BIN_DIR', 'OCR_PIPELINE_CONFIG') else val
    return out


def read():
    p = path()
    if not os.path.exists(p):
        if os.environ.get('LOOP_CONFIG'):
            raise ConfigError(f'LOOP_CONFIG points at {p}, which does not exist')
        return {}
    with open(p, encoding='utf-8') as f:
        return parse(f.read(), p)


def load():
    """Fill unset environment variables from the file. Returns the keys it set."""
    try:
        vals = read()
    except ConfigError as e:
        sys.exit(f'loop settings: {e}')
    set_ = []
    for k, v in vals.items():
        if not os.environ.get(k):  # unset or empty both mean "not set", as in the file
            os.environ[k] = v
            set_.append(k)
    return set_


def main(argv):
    cmd = argv[0] if argv else 'show'
    try:
        vals = read()
    except ConfigError as e:
        print(f'invalid: {e}')
        return 1
    if cmd == 'show':
        print(f'file: {path()}{"" if os.path.exists(path()) else " (missing)"}')
        for k, (req, what) in KEYS.items():
            if os.environ.get(k):
                src, v = 'environment', os.environ[k]
            elif k in vals:
                src, v = 'file', vals[k]
            else:
                src, v = 'default' if not req else 'MISSING', ''
            print(f'{k:22} {src:11} {v}')
        return 0
    if cmd == 'check':
        missing = [k for k, (req, _) in KEYS.items() if req and not os.environ.get(k) and k not in vals]
        if missing:
            print('missing: ' + ', '.join(missing))
            return 1
        print('ok')
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
