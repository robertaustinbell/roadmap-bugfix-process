"""loop.py: preflight, reconcile, adopt, and the role launcher's environment."""
import json
import os
import shutil
import stat
import subprocess as sp
import sys
import tempfile
import textwrap
import unittest

os.environ['LOOP_CONFIG'] = os.devnull  # never read a real loop.env in tests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOP = os.path.join(ROOT, 'scripts', 'loop.py')


def exe(path, body):
    with open(path, 'w') as f:
        f.write('#!/bin/sh\n' + textwrap.dedent(body))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, 'bin')
        os.makedirs(self.bin)
        self.sd = os.path.join(self.tmp, 'state')
        # gh answers from files the test writes
        exe(os.path.join(self.bin, 'gh'), f"""
            case "$1 $2" in
              "pr list") cat {self.tmp}/open.json ;;
              "api user") echo loopbot ;;
              "api repos/up/repo") cat {self.tmp}/perms.json ;;
              *) echo "unexpected gh $*" >&2; exit 9 ;;
            esac
        """)
        with open(os.path.join(self.tmp, 'open.json'), 'w') as f:
            f.write('[{"number": 5}, {"number": 6}]')
        with open(os.path.join(self.tmp, 'perms.json'), 'w') as f:
            f.write('{"admin": false, "maintain": false, "push": false, "pull": true}')
        self.env = {'PATH': self.bin + ':' + os.environ['PATH'], 'HOME': self.tmp, 'LOOP_CONFIG': os.devnull,
                    'STATE_DIR': self.sd, 'UPSTREAM_REPO': 'up/repo', 'GH_FORK_OWNER': 'loopbot',
                    'OWNERS': 'austin', 'MAINTAINER_LOGINS': 'brad'}

    def run_(self, *args, **extra):
        return sp.run([sys.executable, '-I', LOOP, *args], env=dict(self.env, **extra),
                      capture_output=True, text=True, timeout=60)


class Reconcile(Base):
    def test_a_new_state_folder_cannot_hide_open_prs(self):
        r = self.run_('reconcile')
        self.assertEqual(r.returncode, 1)
        self.assertIn('#5, #6', r.stdout)

    def test_recorded_and_adopted_prs_are_known(self):
        self.assertEqual(self.run_('record-pr', 'R1', '5').returncode, 0)
        self.assertEqual(self.run_('reconcile').returncode, 1)
        self.assertNotEqual(self.run_('adopt', '--by', 'mallory', '--label', 'x', '6').returncode, 0)
        self.assertEqual(self.run_('adopt', '--by', 'austin', '--label', 'Nov 2 driver', '6').returncode, 0)
        self.assertEqual(self.run_('reconcile').returncode, 0)

    def test_gh_failure_is_a_problem_not_a_pass(self):
        exe(os.path.join(self.bin, 'gh'), 'echo boom >&2; exit 1\n')
        r = self.run_('reconcile')
        self.assertEqual(r.returncode, 1)
        self.assertIn('could not list', r.stdout)


class Preflight(Base):
    def test_lists_every_missing_piece_at_once(self):
        r = self.run_('preflight', '--offline', '--finders', 'fmsm,trail-of-bits')
        self.assertEqual(r.returncode, 1)
        for want in ('WORKDIR is not set', 'COACH_CMD is not set', 'ROLE_CMD is not set',
                     'fmsm: its pinned tool', 'trail-of-bits: its pinned tool'):
            self.assertIn(want, r.stdout)

    def test_missing_secret_rules_on_upstream_main_is_a_problem(self):
        wd = os.path.join(self.tmp, 'roadmap')
        os.makedirs(wd)
        sp.run(['git', 'init', '-q', wd], check=True)
        r = self.run_('preflight', '--offline', '--finders', '', WORKDIR=wd)
        self.assertEqual(r.returncode, 1)
        self.assertIn('tools/secret-rules.mjs is not on upstream/main', r.stdout)

    def test_write_access_to_upstream_is_refused(self):
        with open(os.path.join(self.tmp, 'perms.json'), 'w') as f:
            f.write('{"admin": false, "maintain": false, "push": true}')
        r = self.run_('preflight', '--finders', '')
        self.assertIn('can write to up/repo', r.stdout)

    def test_wrong_gh_account_and_unknown_prs_are_reported(self):
        r = self.run_('preflight', '--finders', '', GH_FORK_OWNER='someoneelse')
        self.assertIn('signed in as loopbot', r.stdout)


class RunRole(Base):
    def setUp(self):
        super().setUp()
        # a stand-in agent CLI: dumps its environment and git's effective config, writes a finding
        self.agent = os.path.join(self.bin, 'agent')
        exe(self.agent, f"""
            {sys.executable} - "$1" <<'EOF'
import json, os, subprocess, sys
out = os.environ.get('OUT') or os.environ['STATE_DIR']
cfg = subprocess.run(['git', 'config', '--get-all', 'credential.helper'], capture_output=True, text=True).stdout
push = subprocess.run(['git', 'ls-remote', '--get-url', '--push', 'https://github.com/x/y'],
                      capture_output=True, text=True).stdout
gh = subprocess.run(['git', 'config', '--get-regexp', 'pushinsteadof'], capture_output=True, text=True).stdout
others = os.path.exists(os.path.join(os.environ['STATE_DIR'], 'rounds', 'R1', 'findings', 'other', 'secret.json'))
json.dump({{'env': dict(os.environ), 'helpers': cfg.split(), 'rewrites': gh, 'prompt': sys.argv[1],
           'sees_other_by_path': others}}, open(os.path.join(out, 'seen.json'), 'w'))
EOF
        """)
        self.prompt = os.path.join(self.tmp, 'p.txt')
        with open(self.prompt, 'w') as f:
            f.write('write to $OUT, read $KNOWN')
        rd = os.path.join(self.sd, 'rounds', 'R1')
        os.makedirs(rd)
        with open(os.path.join(rd, 'known.json'), 'w') as f:
            f.write('{"items": []}')
        self.env.update(ROLE_CMD='agent', GH_TOKEN='ghp_x', GITHUB_TOKEN='y', SSH_AUTH_SOCK='/tmp/s',
                        OPENAI_API_KEY='k', ANTHROPIC_API_KEY='a', ROLE_PASS='ANTHROPIC_API_KEY')

    def test_finder_gets_no_credentials_and_its_own_folder(self):
        r = self.run_('run-role', 'finder', '--round', 'R1', '--id', 'fmsm', '--prompt-file', self.prompt)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        out = os.path.join(self.sd, 'rounds', 'R1', 'findings', 'fmsm')
        with open(os.path.join(out, 'seen.json')) as f:
            seen = json.load(f)
        e = seen['env']
        for k in ('GH_TOKEN', 'GITHUB_TOKEN', 'SSH_AUTH_SOCK', 'OPENAI_API_KEY'):
            self.assertNotIn(k, e)
        self.assertEqual(e['ANTHROPIC_API_KEY'], 'a', 'ROLE_PASS hands the model login through')
        self.assertEqual(os.listdir(e['GH_CONFIG_DIR']), [], 'gh is signed out')
        self.assertEqual(seen['helpers'], [], 'no git credential helper')
        self.assertIn('push-disabled-by-loop.invalid', seen['rewrites'])
        self.assertNotIn(self.sd, e['OUT'], 'finder output is staged outside the state folder')
        self.assertIn(e['OUT'], seen['prompt'])
        self.assertTrue(os.path.exists(os.path.join(out, 'known.json')), 'its own copy of known.json')
        with open(os.path.join(self.sd, 'rounds', 'R1', 'dispatch.json')) as f:
            d = json.load(f)
        self.assertEqual(d['agents'][0]['id'], 'fmsm')
        self.assertNotIn('GH_TOKEN', d['agents'][0]['env_names'])
        self.assertNotIn('ghp_x', json.dumps(d), 'dispatch.json holds names, never values')

    def test_git_push_to_github_cannot_reach_github(self):
        repo = os.path.join(self.tmp, 'r')
        sp.run(['git', 'init', '-q', repo], check=True)
        sp.run(['git', '-C', repo, 'remote', 'add', 'origin', 'https://github.com/x/y.git'], check=True)
        exe(self.agent, f'git -C {repo} remote get-url --push origin > "$STATE_DIR/pushurl"\n')
        self.assertEqual(self.run_('run-role', 'decider', '--round', 'R1', '--prompt-file', self.prompt).returncode, 0)
        with open(os.path.join(self.sd, 'pushurl')) as f:
            self.assertIn('push-disabled-by-loop.invalid', f.read())

    def test_role_pass_cannot_hand_over_github_or_ssh(self):
        r = self.run_('run-role', 'decider', '--round', 'R1', '--prompt-file', self.prompt, ROLE_PASS='GH_TOKEN')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('may not hand GH_TOKEN', r.stderr)

    def test_adversary_role_starts_with_no_credentials(self):
        exe(self.agent, 'env > "$STATE_DIR/adversary-env.txt"\n')
        r = self.run_('run-role', 'adversary', '--round', 'R1', '--id', 'adv-fix1', '--prompt-file', self.prompt)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        with open(os.path.join(self.sd, 'adversary-env.txt')) as f:
            seen = f.read()
        for k in ('GH_TOKEN=', 'GITHUB_TOKEN=', 'SSH_AUTH_SOCK=', 'OPENAI_API_KEY='):
            self.assertNotIn(k, seen)
        with open(os.path.join(self.sd, 'rounds', 'R1', 'dispatch.json')) as f:
            self.assertEqual(json.load(f)['agents'][-1]['role'], 'adversary')

    def test_unknown_role_and_bad_ids_are_refused(self):
        self.assertNotEqual(self.run_('run-role', 'merger', '--round', 'R1', '--prompt-file', self.prompt).returncode, 0)
        self.assertNotEqual(self.run_('run-role', 'finder', '--round', '../x', '--prompt-file', self.prompt).returncode, 0)

    def test_finder_never_overwrites_earlier_output(self):
        self.assertEqual(self.run_('run-role', 'finder', '--round', 'R1', '--id', 'f', '--prompt-file', self.prompt).returncode, 0)
        r = self.run_('run-role', 'finder', '--round', 'R1', '--id', 'f', '--prompt-file', self.prompt)
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
