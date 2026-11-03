"""Tests for scripts/coach/watch.py. Standard library only.

Run from the repo root:  python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
import shutil
import subprocess as sp
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCH = os.path.join(ROOT, 'scripts', 'coach', 'watch.py')

spec = importlib.util.spec_from_file_location('watch', WATCH)
assert spec and spec.loader
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)


def put(path, data, mode='w'):
    with open(path, mode) as f:
        f.write(data)


def read(path):
    with open(path) as f:
        return f.read()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = dict(os.environ, STATE_DIR=self.tmp, COOLDOWN_MIN='30', ACTIVITY_TTL_MIN='120')
        self.env.pop('COACH_CMD', None)
        self.env.pop('WATCH_FILES', None)
        self.old = dict(os.environ)
        os.environ.clear()
        os.environ.update(self.env)
        self.c = W.cfg()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args, env=None):
        return sp.run([sys.executable, '-I', WATCH, *args], env=env or self.env,
                      capture_output=True, text=True, timeout=60)


class Status(Base):
    def test_nothing_ever_ran_is_idle(self):
        self.assertEqual(W.status(self.c)['status'], 'idle')

    def test_begun_agent_is_active(self):
        W.begin(self.c, 'decider', 'r1')
        s = W.status(self.c)
        self.assertEqual((s['status'], s['working']), ('active', ['decider']))

    def test_end_starts_cooldown_then_idle(self):
        W.begin(self.c, 'decider', 'r1')
        W.end(self.c, 'decider', 'r1')
        now = time.time()
        self.assertEqual(W.status(self.c, now)['status'], 'cooldown')
        self.assertEqual(W.status(self.c, now + 29 * 60)['status'], 'cooldown')
        self.assertEqual(W.status(self.c, now + 31 * 60)['status'], 'idle')

    def test_coach_alone_does_not_count_as_activity(self):
        W.begin(self.c, 'coach', 'main')
        os.remove(os.path.join(self.c['dir'], 'last.json'))
        self.assertEqual(W.status(self.c)['status'], 'idle')

    def test_begin_without_end_expires(self):
        W.begin(self.c, 'fixer', 'f1')
        later = time.time() + 121 * 60
        s = W.status(self.c, later)
        self.assertEqual(s['working'], [])
        self.assertEqual(s['status'], 'cooldown', 'an expired agent still gets the cool-down')
        self.assertEqual(W.status(self.c, later + 31 * 60)['status'], 'idle')

    def test_dead_pid_stops_counting(self):
        p = sp.Popen([sys.executable, '-c', 'pass'])
        p.wait()
        W.begin(self.c, 'ocr-scan', 'x', pid=p.pid)
        self.assertEqual(W.status(self.c)['working'], [])

    def test_live_pid_counts(self):
        W.begin(self.c, 'ocr-scan', 'x', pid=os.getpid())
        self.assertEqual(W.status(self.c, time.time() + 10 * 3600)['working'], ['ocr-scan'])

    def test_watched_file_change_is_a_pulse_but_first_sighting_is_not(self):
        f = os.path.join(self.tmp, 'scorecard.csv')
        put(f, 'a\n')
        self.assertEqual(W.status(self.c)['status'], 'idle')
        put(f, 'b\n', 'a')
        self.assertEqual(W.status(self.c)['status'], 'cooldown')

    def test_bad_names_refused(self):
        for bad in ('../x', 'a/b', '', '.hidden'):
            with self.subTest(bad), self.assertRaises(SystemExit):
                W.begin(self.c, bad, 'main')

    def test_future_timestamp_does_not_hold_cooldown_open(self):
        os.makedirs(self.c['dir'], exist_ok=True)
        W.write_json(os.path.join(self.c['dir'], 'last.json'), {'t': time.time() + 10 ** 6})
        self.assertEqual(W.status(self.c, time.time())['status'], 'cooldown')
        self.assertEqual(W.status(self.c, time.time() + 31 * 60)['status'], 'idle')


class Tick(Base):
    def coach_cmd(self, seconds):
        marker = os.path.join(self.tmp, 'coach-started')
        code = f"import os,time;open({marker!r},'a').write(os.environ['COACH_TRIGGER']+'\\n');time.sleep({seconds})"
        return marker, f'{sys.executable} -c "{code}"'

    def test_idle_never_starts_the_coach_and_a_scheduler_tick_is_silent(self):
        marker, cmd = self.coach_cmd(0)
        r = self.cli(env=dict(self.env, COACH_CMD=cmd))
        self.assertEqual((r.returncode, r.stdout), (0, ''))
        self.assertFalse(os.path.exists(marker))

    def test_activity_starts_exactly_one_coach(self):
        marker, cmd = self.coach_cmd(5)
        env = dict(self.env, COACH_CMD=cmd)
        self.assertIn('started coach', self.cli('begin', 'decider', env=env).stdout)
        self.assertEqual(self.cli('tick', env=dict(env, WATCH_VERBOSE='1')).stdout.strip(), 'coach running')
        self.assertEqual(self.cli('begin', 'fixer', '--id', 'f2', env=env).stdout.strip(), 'coach running')
        for _ in range(50):
            if os.path.exists(marker):
                break
            time.sleep(0.1)
        self.assertEqual(read(marker).split(), ['active'])

    def test_run_wraps_a_command_and_returns_its_exit_code(self):
        r = self.cli('run', 'ocr-scan', '--', sys.executable, '-c', 'import sys; sys.exit(3)')
        self.assertEqual(r.returncode, 3)
        s = json.loads(self.cli('status', '--json').stdout)
        self.assertEqual((s['status'], s['working']), ('cooldown', []))

    def test_run_counts_while_the_command_runs(self):
        p = sp.Popen([sys.executable, '-I', WATCH, 'run', 'ocr-scan', '--', sys.executable, '-c',
                      'import time; time.sleep(3)'], env=self.env)
        s = {}
        try:
            for _ in range(50):
                s = json.loads(self.cli('status', '--json').stdout)
                if s['working']:
                    break
                time.sleep(0.1)
            self.assertEqual(s.get('working'), ['ocr-scan'])
        finally:
            p.wait()

    def test_without_coach_cmd_tick_only_reports(self):
        W.begin(self.c, 'decider', 'r1')
        self.assertIn('COACH_CMD not set', W.tick(self.c))
        self.assertFalse(os.path.exists(os.path.join(self.c['dir'], 'coach.pid.json')))

    def test_watch_never_writes_outside_activity_dir(self):
        put(os.path.join(self.tmp, 'scorecard.csv'), 'a\n')
        before = sorted(os.listdir(self.tmp))
        W.begin(self.c, 'decider', 'r1')
        W.status(self.c)
        W.tick(self.c)
        W.end(self.c, 'decider', 'r1')
        self.assertEqual(sorted(os.listdir(self.tmp)), sorted(set(before) | {'activity'}))


MECH = os.path.join(ROOT, 'scripts', 'ocr', 'mech.py')


class MechStartsTheCoach(Base):
    """A real OCR mechanics tick, with a fake `ocr` and a fake Coach command."""

    def test_scan_is_registered_and_one_coach_starts(self):
        base = os.path.join(self.tmp, 'ocr')
        repo = os.path.join(self.tmp, 'repo')
        os.makedirs(os.path.join(base, 'parts'))
        os.makedirs(os.path.join(base, 'pipeline'))
        sp.run(['git', 'init', '-q', repo], check=True)
        put(os.path.join(repo, 'a.ts'), 'x\n')
        put(os.path.join(base, 'parts', '01-core.txt'), 'a.ts\n')
        put(os.path.join(base, 'pipeline', 'state.json'),
            json.dumps({'round_open': True, 'parts': [{'name': '01-core', 'stage': 'queued'}]}))
        fake_ocr = os.path.join(self.tmp, 'fake-ocr')
        put(fake_ocr, '#!/bin/sh\nsleep 3\nexit 0\n')
        os.chmod(fake_ocr, 0o755)
        coach_marker = os.path.join(self.tmp, 'coach-started')
        coach = f"{sys.executable} -c \"import time;open({coach_marker!r},'a').write('x');time.sleep(6)\""
        env = dict(self.env, OCR_BASE_DIR=base, ROADMAP_WORKTREE=repo, OCR_BIN=fake_ocr, KEEP_AWAKE='',
                   OCR_PIPELINE_CONFIG=os.path.join(self.tmp, 'none.json'), COACH_CMD=coach)
        env.pop('ROUND_DIR', None)
        r = sp.run([sys.executable, '-I', MECH], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        seen = None
        for _ in range(40):
            s = json.loads(self.cli('status', '--json').stdout)
            if s['working']:
                seen = s
                break
            time.sleep(0.1)
        self.assertEqual(seen and seen['working'], ['ocr-scan'], 'the scan counts as activity')
        for _ in range(40):
            if os.path.exists(coach_marker):
                break
            time.sleep(0.1)
        self.assertEqual(read(coach_marker), 'x', 'exactly one Coach started')
        # a second tick while the scan runs must not start another Coach
        sp.run([sys.executable, '-I', MECH], env=env, capture_output=True, text=True, timeout=60)
        time.sleep(0.5)
        self.assertTrue(W.coach_running(self.c))
        self.assertEqual(read(coach_marker), 'x', 'a second tick must not start a second Coach')
        for _ in range(100):
            if not json.loads(self.cli('status', '--json').stdout)['working']:
                break
            time.sleep(0.1)
        self.assertEqual(json.loads(self.cli('status', '--json').stdout)['status'], 'cooldown')

    def test_without_state_dir_mech_does_not_touch_the_coach(self):
        env = dict(self.env)
        env.pop('STATE_DIR')
        base = os.path.join(self.tmp, 'ocr2')
        os.makedirs(os.path.join(base, 'pipeline'))
        put(os.path.join(base, 'pipeline', 'state.json'), json.dumps({'parts': []}))
        env.update(OCR_BASE_DIR=base, OCR_PIPELINE_CONFIG=os.path.join(self.tmp, 'none.json'))
        r = sp.run([sys.executable, '-I', MECH], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'activity')))


ITEMS = os.path.join(ROOT, 'scripts', 'coach', 'items.py')


class Items(Base):
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.tmp, 'coach'))
        self.items = os.path.join(self.tmp, 'coach', 'items.jsonl')
        rows = [
            {'id': 'C-1', 'to': 'decider', 'suggestion': 'read the caller'},
            {'id': 'C-2', 'to': 'bug-fixer', 'suggestion': 'assert the symptom'},
            {'id': 'C-3', 'to': 'decider', 'suggestion': 'wrong advice'},
            {'id': 'C-4', 'withdraws': 'C-3', 'why': 'mistaken'},
        ]
        put(self.items, ''.join(json.dumps(r) + '\n' for r in rows) + 'not json\n')

    def items_cli(self, *args):
        return sp.run([sys.executable, '-I', ITEMS, *args], env=self.env, capture_output=True, text=True)

    def open_ids(self, role):
        r = self.items_cli('open', role)
        return [json.loads(ln)['id'] for ln in r.stdout.split('\n') if ln], r.stderr

    def test_open_lists_only_this_roles_unwithdrawn_items_and_reports_bad_lines(self):
        ids, err = self.open_ids('decider')
        self.assertEqual(ids, ['C-1'])
        self.assertIn('1 unreadable line', err)
        self.assertEqual(self.open_ids('bug-fixer')[0], ['C-2'])

    def test_reply_closes_the_item_for_that_role(self):
        r = self.items_cli('reply', 'C-1', 'applied', '--role', 'decider', '--note', 'traced the caller in D-3')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.open_ids('decider')[0], [])

    def test_second_reply_refused(self):
        self.items_cli('reply', 'C-1', 'applied', '--role', 'decider', '--note', 'x')
        r = self.items_cli('reply', 'C-1', 'not_applied', '--role', 'decider', '--note', 'y')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('already replied', r.stderr)

    def test_cannot_answer_another_roles_item(self):
        r = self.items_cli('reply', 'C-2', 'applied', '--role', 'decider', '--note', 'x')
        self.assertIn('addressed to bug-fixer', r.stderr)
        self.assertEqual(self.open_ids('bug-fixer')[0], ['C-2'])

    def test_reply_rules(self):
        cases = [
            (('C-1', 'ignored', '--role', 'decider', '--note', 'x'), 'verb must be'),
            (('C-1', 'applied', '--role', 'decider', '--note', ' '), '--note is required'),
            (('C-1', 'disputed', '--role', 'decider', '--note', 'no'), 'needs --evidence'),
            (('C-9', 'applied', '--role', 'decider', '--note', 'x'), 'no item C-9'),
            (('C-3', 'applied', '--role', 'decider', '--note', 'x'), 'was withdrawn'),
            (('C-1', 'applied', '--role', 'ghost', '--note', 'x'), 'unknown role'),
        ]
        for args, msg in cases:
            with self.subTest(args):
                r = self.items_cli('reply', *args)
                if msg:
                    self.assertNotEqual(r.returncode, 0)
                    self.assertIn(msg, r.stderr)

    def test_dispute_with_evidence_is_recorded(self):
        r = self.items_cli('reply', 'C-1', 'disputed', '--role', 'decider', '--note', 'caller is test-only',
                           '--evidence', 'src/a.ts:12')
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = json.loads(read(os.path.join(self.tmp, 'coach-responses.jsonl')))
        self.assertEqual((rec['reply'], rec['evidence']), ('disputed', ['src/a.ts:12']))

    def test_roles_never_write_the_coach_folder(self):
        before = read(self.items)
        self.items_cli('reply', 'C-1', 'applied', '--role', 'decider', '--note', 'x')
        self.assertEqual(read(self.items), before)
        self.assertEqual(sorted(os.listdir(os.path.join(self.tmp, 'coach'))), ['items.jsonl'])


if __name__ == '__main__':
    unittest.main()
