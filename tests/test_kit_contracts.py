"""The docs, agent templates and schemas must say the same thing, and scripts/check_kit.py must
catch what it claims to catch. Standard library only.

Run from the repo root:  python3 -m unittest discover -s tests -v
"""
import json
import os

os.environ['LOOP_CONFIG'] = os.devnull  # never read a real loop.env in tests
import re
import shutil
import subprocess as sp
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def text(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def schema(name):
    return json.loads(text(f'templates/{name}'))


def first_json_block(md, after):
    i = md.index(after)
    j = md.index('```json', i) + len('```json')
    return md[j:md.index('```', j)]


def top_keys(block):
    """Keys at the first nesting level of a JSON-like example (examples use `a | b` placeholders)."""
    return re.findall(r'^  "(\w+)":', block, re.M)


def table_column(md, heading, col=0):
    lines = md[md.index(heading):].split('\n')[1:]
    start = next(k for k, ln in enumerate(lines) if ln.startswith('|'))
    rows = []
    for ln in lines[start:]:
        if not ln.startswith('|'):
            break
        rows.append(ln)
    out = []
    for ln in rows[2:]:
        cell = ln.strip('|').split('|')[col].strip()
        out += re.findall(r'`([^`]+)`', cell)
    return out


class DecisionContract(unittest.TestCase):
    def setUp(self):
        self.s = schema('decision.schema.json')

    def test_decider_example_matches_schema(self):
        keys = top_keys(first_json_block(text('agents/decider.md'), '## Outputs'))
        self.assertEqual(sorted(keys), sorted(self.s['properties']))
        self.assertTrue(set(self.s['required']) <= set(keys))

    def test_statuses_match_evidence_bar(self):
        statuses = table_column(text('docs/evidence-bar.md'), '## Reachability and status labels')
        self.assertEqual(sorted(statuses), sorted(self.s['properties']['status']['enum']))

    def test_routes_match_process(self):
        routes = table_column(text('docs/process.md'), '### 3.4 Decide')
        self.assertEqual(sorted(routes), sorted(self.s['properties']['route']['enum']))

    def test_status_routes_in_evidence_bar_are_known_routes(self):
        md = text('docs/evidence-bar.md')
        routes = set(table_column(md, '## Reachability and status labels', col=2))
        self.assertTrue(routes <= set(self.s['properties']['route']['enum']), routes)


class ReviewContract(unittest.TestCase):
    def test_reviewer_example_fields_exist(self):
        s = schema('review-verdict.schema.json')
        keys = top_keys(first_json_block(text('agents/independent-reviewer.md'), '## Outputs'))
        self.assertTrue(set(keys) <= set(s['properties']), set(keys) - set(s['properties']))
        self.assertTrue(set(s['required']) | {'text_sha256'} <= set(keys))


class CandidateContract(unittest.TestCase):
    def test_process_example_fields_exist(self):
        s = schema('candidate.schema.json')
        keys = top_keys(first_json_block(text('docs/process.md'), '## 7. Common finding schema'))
        self.assertTrue(set(keys) <= set(s['properties']), set(keys) - set(s['properties']))

    def test_run_status_matches_process(self):
        s = schema('candidate.schema.json')
        md = text('docs/process.md')
        sec = md[md.index('#### Partial is never clean'):md.index('### 3.4 Decide')]
        line = [ln for ln in sec.split('\n') if 'Every finder run records a status' in ln][0]
        i = sec.index(line)
        named = re.findall(r'`([a-z_]+)`', sec[i:sec.index('\n- ', i + 1)])
        statuses = [n for n in named if n not in ('ok_and',)]
        enum = s['properties']['coverage']['properties']['run_status']['enum']
        self.assertTrue(set(enum) <= set(statuses), set(enum) - set(statuses))


class CoachFeedbackContract(unittest.TestCase):
    TEMPLATES = {
        'coordinator': 'agents/coordinator.md', 'decider': 'agents/decider.md',
        'bug-fixer': 'agents/bug-fixer.md', 'repair': 'agents/repair.md',
        'independent-reviewer': 'agents/independent-reviewer.md',
        'ocr-pipeline-agent': 'agents/ocr-pipeline-agent.md',
        'fmsm': 'agents/finders/fmsm.md', 'tech-debt-audit': 'agents/finders/tech-debt-audit.md',
        'trail-of-bits': 'agents/finders/trail-of-bits.md',
        'open-code-review': 'agents/finders/open-code-review.md',
    }

    def roles_in_items_py(self):
        m = re.search(r"ROLES = \(([^)]*)\)", text('scripts/coach/items.py'))
        return re.findall(r"'([a-z-]+)'", m.group(1))

    def test_every_role_reads_its_items(self):
        self.assertEqual(sorted(self.roles_in_items_py()), sorted(self.TEMPLATES))
        for role, path in self.TEMPLATES.items():
            with self.subTest(role):
                self.assertIn(f'items.py open {role}', text(path))

    def test_roles_md_lists_the_same_role_names(self):
        md = text('docs/roles.md')
        sec = md[md.index('#### How Coach feedback reaches a role'):md.index('## Authority matrix')]
        names = re.findall(r'`([a-z-]+)`', sec.split('Role names for `items.py`:')[1])
        self.assertEqual(sorted(names), sorted(self.TEMPLATES))

    def test_coach_md_lists_the_same_role_names(self):
        md = text('agents/coach.md')
        line = md[md.index('- `to` is one role:') + len('- `to` is one role:'):md.index('- A suggestion is')]
        self.assertEqual(sorted(re.findall(r'`([a-z-]+)`', line)), sorted(self.TEMPLATES))


class OwnerStartsTheLoop(unittest.TestCase):
    def test_coordinator_checks_the_session_and_is_watched_from_the_start(self):
        md = text('agents/coordinator.md')
        steps = md[md.index('## Steps'):]
        for needle in ('watch.py begin coordinator', 'session.py may-open-round',
                       'session.py round-opened', 'session.py start --mode',
                       'session.py request', 'session.py pass-done'):
            with self.subTest(needle):
                self.assertIn(needle, steps)
        self.assertLess(steps.index('watch.py begin coordinator'), steps.index('0. **Resume first.**'))

    def test_scheduled_coordinator_is_gated_and_watched(self):
        cron = text('schedules/crontab-example.txt')
        line = next(l for l in cron.splitlines() if 'agents/coordinator.md' in l)
        self.assertIn('session.py" gate &&', line)
        self.assertIn('watch.py" run coordinator --', line)


class SkillIsPortable(unittest.TestCase):
    SKILL = 'skills/roadmap-bugfix-loop/SKILL.md'

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, 'scripts'))
        import check_kit
        self.ck = check_kit

    def test_the_skill_passes_the_checker(self):
        self.assertEqual(self.ck.check_skills(ROOT, self.ck.git_files(ROOT)), [])

    def test_the_skill_starts_the_coordinator_watched_and_keeps_the_nevers(self):
        md = text(self.SKILL)
        for needle in ('agents/coordinator.md', 'watch.py begin coordinator', 'session.py start',
                       'Never merge', 'One fix per PR', 'VERDICT:', 'own agent with a fresh context'):
            with self.subTest(needle):
                self.assertIn(needle, md)

    def check_text(self, body, folder='demo-skill'):
        with tempfile.TemporaryDirectory() as d:
            rel = f'skills/{folder}/SKILL.md'
            os.makedirs(os.path.join(d, 'skills', folder))
            with open(os.path.join(d, rel), 'w') as f:
                f.write(body)
            return self.ck.check_skills(d, [rel])

    def test_checker_rejects_what_either_runtime_would_reject(self):
        ok = '---\nname: demo-skill\ndescription: Short.\n---\n\nBody\n'
        self.assertEqual(self.check_text(ok), [])
        bad = {
            'non-standard field': ok.replace('description:', 'version: 1\ndescription:'),
            'name/folder mismatch': ok.replace('name: demo-skill', 'name: other-skill'),
            'uppercase name': ok.replace('name: demo-skill', 'name: Demo-Skill'),
            'long first sentence': ok.replace('Short.', 'x' * 61 + '. Then more.'),
            'description over 1024': ok.replace('Short.', 'Short. ' + 'x' * 1020),
            'nested metadata': ok.replace('---\n\nBody', 'metadata:\n  hermes: [a, b]\n---\n\nBody'),
            'link out of the folder': ok.replace('Body', 'See [x](../../docs/process.md)'),
            'leading blank line': '\n' + ok,
            'empty body': '---\nname: demo-skill\ndescription: Short.\n---\n',
            'missing script': ok.replace('Body', 'Run scripts/nope.py'),
        }
        for why, body in bad.items():
            with self.subTest(why):
                self.assertNotEqual(self.check_text(body), [])


class SettingsInOneFile(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, 'scripts'))
        import loopenv
        self.le = loopenv

    def scripts(self):
        for d, _, fs in os.walk(os.path.join(ROOT, 'scripts')):
            for f in fs:
                if f.endswith('.py') and f not in ('loopenv.py', 'check_kit.py', 'mutation_check.py'):
                    yield os.path.join(d, f)

    def test_every_setting_a_script_reads_is_documented(self):
        read = set()
        for p in self.scripts():
            with open(p) as fh:
                src = fh.read()
            read |= set(re.findall(r"os\.environ(?:\.get\(|\[)'([A-Z][A-Z0-9_]+)'", src))
            for tup in re.findall(r"keys = \(([^)]*)\)", src):
                read |= set(re.findall(r"'([A-Z][A-Z0-9_]+)'", tup))
        missing = read - set(self.le.KEYS) - self.le.INTERNAL
        self.assertEqual(missing, set(), 'add these to KEYS in scripts/loopenv.py and loop.env.example')

    def test_every_script_that_reads_settings_loads_the_file(self):
        for p in self.scripts():
            with open(p) as fh:
                src = fh.read()
            if 'os.environ' in src:
                with self.subTest(os.path.relpath(p, ROOT)):
                    self.assertIn('_loop_settings()', src)

    def test_example_lists_every_key(self):
        ex = text('loop.env.example')
        for k in self.le.KEYS:
            with self.subTest(k):
                self.assertRegex(ex, r'(?m)^(# )?' + k + '=')

    def test_file_rules(self):
        P, E = self.le.parse, self.le.ConfigError
        self.assertEqual(P('# c\nSTATE_DIR="/s"\nOWNERS=\n'), {'STATE_DIR': '/s'})
        for bad in ('GH_TOKEN=x', 'API_KEY=x', 'STAET_DIR=/s', 'not a line'):
            with self.subTest(bad):
                with self.assertRaises(E):
                    P(bad)

    def test_environment_wins_and_subprocesses_inherit(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, 'loop.env')
            with open(cfg, 'w') as f:
                f.write(f'STATE_DIR={d}/state\nOWNERS=austin,brad\n')
            env = dict(os.environ, LOOP_CONFIG=cfg, OWNERS='austin')
            env.pop('STATE_DIR', None)
            s = os.path.join(ROOT, 'scripts', 'coordinator', 'session.py')
            r = sp.run([sys.executable, '-I', s, 'start', '--mode', 'automated', '--by', 'brad',
                        '--request', 'go'], env=env, capture_output=True, text=True)
            self.assertIn('not an owner', r.stderr, 'OWNERS from the environment beats the file')
            r = sp.run([sys.executable, '-I', s, 'start', '--mode', 'automated', '--by', 'austin',
                        '--request', 'go'], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.exists(os.path.join(d, 'state', 'session.json')), 'STATE_DIR came from the file')

    def test_missing_named_file_fails_loudly(self):
        env = dict(os.environ, LOOP_CONFIG='/nonexistent/loop.env')
        r = sp.run([sys.executable, '-I', os.path.join(ROOT, 'scripts', 'coordinator', 'session.py'), 'status'],
                   env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('does not exist', r.stderr)


class SchemasParse(unittest.TestCase):
    def test_every_schema_is_strict_json(self):
        def no_dupes(pairs):
            keys = [k for k, _ in pairs]
            dup = {k for k in keys if keys.count(k) > 1}
            if dup:
                raise ValueError(dup)
            return dict(pairs)
        for f in os.listdir(os.path.join(ROOT, 'templates')):
            if f.endswith('.json'):
                with self.subTest(f):
                    json.loads(text(f'templates/{f}'), object_pairs_hook=no_dupes)


class CheckKit(unittest.TestCase):
    """Run the real checker on a copy of this repo with one problem planted at a time."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.base = os.path.join(cls.tmp, 'base')
        shutil.copytree(ROOT, cls.base, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.repo = os.path.join(self.tmp, self.id().rsplit('.', 1)[-1])
        shutil.copytree(self.base, self.repo, symlinks=True)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def run_check(self):
        r = sp.run([sys.executable, '-I', os.path.join(self.repo, 'scripts', 'check_kit.py'), self.repo],
                   capture_output=True, text=True)
        return r.returncode, r.stdout

    def edit(self, rel, fn):
        p = os.path.join(self.repo, rel)
        with open(p, encoding='utf-8') as f:
            s = f.read()
        with open(p, 'w', encoding='utf-8') as f:
            f.write(fn(s))

    def assertCaught(self, category):
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertIn(category, out)
        return out

    def test_clean_copy_passes(self):
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)

    def test_em_dash(self):
        self.edit('docs/roles.md', lambda s: s + '\nA \u2014 B\n')
        self.assertCaught('em dash')

    def test_phone_number_and_finding_does_not_echo_it(self):
        self.edit('README.md', lambda s: s + '\nCall 864-555-' + '0142 any time.\n')
        out = self.assertCaught('phone number')
        self.assertNotIn('555', out)

    def test_local_path(self):
        self.edit('docs/process.md', lambda s: s + '\nSee /' + 'Users/someone/state for logs.\n')
        self.assertCaught('local path')

    def test_private_runtime_name_in_file_name(self):
        with open(os.path.join(self.repo, 'docs', 'bob' + 'ert-notes.md'), 'w') as f:
            f.write('# Notes\n')
        self.assertCaught('file name matches "private agent name"')

    def test_broken_link(self):
        self.edit('docs/roles.md', lambda s: s + '\nSee [gone](no-such-page.md).\n')
        self.assertCaught('broken link')

    def test_missing_anchor(self):
        self.edit('docs/roles.md', lambda s: s + '\nSee [x](process.md#no-such-heading).\n')
        self.assertCaught('no heading #no-such-heading')

    def test_rule_moved_into_comment(self):
        self.edit('docs/publishing.md', lambda s: s.replace('- **The loop never merges.**', '<!-- - **The loop never merges.** -->'))
        self.assertCaught('rule "The loop never merges"')

    def test_rule_moved_to_another_section(self):
        self.edit('README.md', lambda s: s.replace('- Never merge. Never mark our own work approved.\n', '')
                  + '\n## Notes\n\n- Never merge. Never mark our own work approved.\n')
        self.assertCaught('rule "Never merge" is not under "Hard nevers"')

    def test_rule_in_code_block_does_not_count(self):
        self.edit('docs/scorecard-and-test-set.md',
                  lambda s: s.replace('**Failures count the same as passes.**', '```\nFailures count the same as passes.\n```\n'))
        self.assertCaught('rule "Failures count the same as passes"')

    def test_macos_metadata(self):
        with open(os.path.join(self.repo, 'docs', '.DS_Store'), 'w') as f:
            f.write('x')
        # .DS_Store is gitignored, so only a force-added (tracked) one can be published
        sp.run(['git', 'add', '-f', 'docs/.DS_Store'], cwd=self.repo, check=True, capture_output=True)
        with open(os.path.join(self.repo, 'docs', '._process.md'), 'w') as f:
            f.write('x')
        out = self.assertCaught('macOS metadata')
        self.assertEqual(out.count('macOS metadata'), 2)

    def test_symlink(self):
        os.symlink(os.path.join(self.repo, 'README.md'), os.path.join(self.repo, 'docs', 'link.md'))
        self.assertCaught('symlink')

    def test_transport_artifact(self):
        self.edit('docs/roles.md', lambda s: s + '\n... 4,321 bytes ' + 'omitted ...\n')
        self.assertCaught('transport artifact')

    def test_orphan_agent_template(self):
        with open(os.path.join(self.repo, 'agents', 'orphan.md'), 'w') as f:
            f.write('# Agent template: Orphan\n')
        self.assertCaught('no page links to this agent template')


if __name__ == '__main__':
    unittest.main()
