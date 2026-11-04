import json
import os

os.environ['LOOP_CONFIG'] = os.devnull  # never read a real loop.env in tests
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts', 'coordinator', 'session.py')


class Session(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = dict(os.environ, STATE_DIR=self.tmp.name, OWNERS='austin,brad')
        self.env.pop('COACH_CMD', None)

    def run_(self, *args):
        return subprocess.run([sys.executable, '-I', S, *args], env=self.env, capture_output=True, text=True)

    def state(self):
        with open(os.path.join(self.tmp.name, 'session.json')) as f:
            return json.load(f)

    def test_nothing_runs_before_the_owner_starts_it(self):
        self.assertEqual(self.run_('gate').returncode, 1)
        self.assertEqual(self.run_('may-open-round').returncode, 1)
        self.assertNotEqual(self.run_('round-opened', 'R1').returncode, 0)

    def test_only_an_owner_can_start_stop_or_request(self):
        r = self.run_('start', '--mode', 'automated', '--by', 'someone', '--request', 'go')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('not an owner', r.stderr)
        self.run_('start', '--mode', 'automated', '--by', 'austin', '--request', 'go')
        self.assertNotEqual(self.run_('request', '--by', 'bot', 'x').returncode, 0)
        self.assertNotEqual(self.run_('stop', '--by', 'bot').returncode, 0)
        self.assertEqual(self.state()['status'], 'active')

    def test_automated_runs_rounds_until_stopped(self):
        self.assertEqual(self.run_('start', '--mode', 'automated', '--by', 'austin',
                                   '--request', 'find bugs, health code first').returncode, 0)
        self.assertEqual(self.state()['request_verbatim'], 'find bugs, health code first')
        for rnd in ('R1', 'R2'):
            self.assertEqual(self.run_('may-open-round').returncode, 0)
            self.assertEqual(self.run_('round-opened', rnd).returncode, 0)
            self.assertEqual(self.run_('may-open-round').returncode, 1, 'one round at a time')
            self.assertEqual(self.run_('pass-done', rnd).returncode, 0)
        self.assertEqual(self.state()['status'], 'active')
        self.run_('stop', '--by', 'austin', '--reason', 'done for now')
        self.assertEqual(self.run_('may-open-round').returncode, 1)
        self.assertEqual(self.run_('gate').returncode, 1)

    def test_manual_needs_a_scope_and_runs_one_pass(self):
        r = self.run_('start', '--mode', 'manual', '--by', 'austin', '--request', 'just look')
        self.assertIn('needs a scope', r.stderr)
        self.assertEqual(self.run_('start', '--mode', 'manual', '--by', 'austin', '--request',
                                   'only security issues', '--kinds', 'security',
                                   '--finders', 'trail-of-bits').returncode, 0)
        self.assertEqual(self.state()['scope']['kinds'], ['security'])
        self.run_('round-opened', 'R1')
        self.run_('pass-done', 'R1')
        self.assertEqual(self.state()['status'], 'done')
        self.assertEqual(self.run_('may-open-round').returncode, 1)
        self.assertEqual(self.run_('round-opened', 'R2').returncode, 1)

    def test_open_prs_keep_the_follow_up_running_after_stop(self):
        self.run_('start', '--mode', 'manual', '--by', 'austin', '--request', 'iPhone app only',
                  '--areas', 'ios-app')
        self.run_('round-opened', 'R1')
        self.run_('pass-done', 'R1')
        self.run_('prs', '2')
        self.assertEqual(self.run_('gate').returncode, 0, 'follow up on PRs Brad has not addressed')
        self.assertEqual(self.run_('may-open-round').returncode, 1, 'but never a new round')
        self.run_('prs', '0')
        self.assertEqual(self.run_('gate').returncode, 1)

    def test_a_second_start_is_refused(self):
        self.run_('start', '--mode', 'automated', '--by', 'austin', '--request', 'go')
        r = self.run_('start', '--mode', 'manual', '--by', 'brad', '--request', 'x', '--areas', 'a')
        self.assertIn('already active', r.stderr)

    def test_requests_are_kept_until_a_plan_takes_them(self):
        self.assertNotEqual(self.run_('request', '--by', 'austin', 'sleep import').returncode, 0,
                            'a request with no session would never run')
        self.run_('start', '--mode', 'automated', '--by', 'austin', '--request', 'go')
        self.run_('request', '--by', 'brad', 'look at the sleep import code', '--areas', 'sleep-import')
        st = json.loads(self.run_('status').stdout)
        self.assertEqual([r['text'] for r in st['open_requests']], ['look at the sleep import code'])
        self.run_('taken', 'R1')
        self.assertEqual(json.loads(self.run_('status').stdout)['open_requests'], [])

    def test_automated_session_expires_after_max_rounds(self):
        self.env['SESSION_MAX_ROUNDS'] = '2'
        self.run_('start', '--mode', 'automated', '--by', 'austin', '--request', 'go')
        for rnd in ('R1', 'R2'):
            self.run_('round-opened', rnd)
            self.run_('pass-done', rnd)
        r = self.run_('may-open-round')
        self.assertEqual(r.returncode, 1)
        self.assertIn('expired', r.stdout)
        self.assertEqual(self.run_('gate').returncode, 1)
        self.assertEqual(json.loads(self.run_('status').stdout)['session']['status'], 'expired')
        self.run_('prs', '1')
        self.assertEqual(self.run_('gate').returncode, 0, 'open PRs still get follow-up')
        self.assertEqual(self.run_('start', '--mode', 'automated', '--by', 'austin',
                                   '--request', 'again').returncode, 0, 'the owner can start a new one')

    def test_automated_session_expires_after_max_days(self):
        self.run_('start', '--mode', 'automated', '--by', 'austin', '--request', 'go')
        st = self.state()
        st['started_epoch'] -= 15 * 86400
        with open(os.path.join(self.tmp.name, 'session.json'), 'w') as f:
            json.dump(st, f)
        r = self.run_('may-open-round')
        self.assertIn('older than 14 days', r.stdout)
        self.env['SESSION_MAX_DAYS'] = '30'
        self.assertEqual(self.run_('may-open-round').returncode, 0)

    def test_answer_to_a_human_review_item_reaches_the_decider_once(self):
        self.assertNotEqual(self.run_('answer', 'HR-1', '--by', 'mallory', '--words', 'x').returncode, 0)
        self.assertNotEqual(self.run_('answer', 'not-an-id', '--by', 'austin', '--words', 'x').returncode, 0)
        r = self.run_('answer', 'HR-20261103-1', '--by', 'austin', '--choice', '1',
                      '--words', 'Brad: yes, add the spellings that equal mIU/L')
        self.assertEqual(r.returncode, 0, r.stderr)
        open_ = json.loads(self.run_('answers').stdout)
        self.assertEqual([x['item'] for x in open_], ['HR-20261103-1'])
        self.assertEqual(open_[0]['words'], 'Brad: yes, add the spellings that equal mIU/L')
        self.assertEqual(self.run_('answer-used', 'HR-20261103-1', '--round', 'R2').returncode, 0)
        self.assertEqual(json.loads(self.run_('answers').stdout), [])
        self.assertNotEqual(self.run_('answer-used', 'HR-9', '--round', 'R2').returncode, 0)
        with open(os.path.join(self.tmp.name, 'owner-talk.jsonl')) as f:
            talk = [json.loads(x) for x in f]
        self.assertEqual(talk[-1]['kind'], 'answer')
        self.assertEqual(talk[-1]['item'], 'HR-20261103-1')

    def test_say_logs_owner_talk_and_checks_owner_names(self):
        self.assertEqual(self.run_('say', '--who', 'owner', '--name', 'austin', '--kind', 'kit-approval',
                                   '--words', 'ok, use the new kit').returncode, 0)
        self.assertNotEqual(self.run_('say', '--who', 'owner', '--name', 'eve', '--kind', 'start',
                                      '--words', 'go').returncode, 0)

    def test_owner_talk_counts_as_activity_for_the_coach(self):
        self.run_('start', '--mode', 'automated', '--by', 'austin', '--request', 'go')
        self.assertTrue(os.path.isdir(os.path.join(self.tmp.name, 'activity')))
        w = subprocess.run([sys.executable, '-I', os.path.join(ROOT, 'scripts', 'coach', 'watch.py'),
                            'status'], env=self.env, capture_output=True, text=True)
        self.assertIn('cooldown', w.stdout)


if __name__ == '__main__':
    unittest.main()
