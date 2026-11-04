"""Tests for scripts/publish/driver.py. Standard library only.

Run from the repo root:  python3 -m unittest discover -s tests -v
Set DRIVER_PATH to test another copy of the driver (scripts/mutation_check.py does this).

Every gate has a hostile case here. A gate that no test can tell apart from "always pass" is
ceremony; scripts/mutation_check.py removes each gate in turn and expects this file to fail.
"""
import ast
import contextlib
import io
import importlib.util
import json
import os

os.environ['LOOP_CONFIG'] = os.devnull  # never read a real loop.env in tests
import shutil
import subprocess as sp
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.environ.get('DRIVER_PATH') or os.path.join(ROOT, 'scripts', 'publish', 'driver.py')
SCHEMA = os.path.join(ROOT, 'templates', 'review-verdict.schema.json')


def put(path, text, mode='w'):
    with open(path, mode) as f:
        f.write(text)


def lines(path):
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def text(path):
    with open(path) as f:
        return f.read()


def load_driver():
    spec = importlib.util.spec_from_file_location('driver_under_test', DRIVER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


D = load_driver()
A = 'a' * 40
B = 'b' * 40

GOOD_BODY = textwrap.dedent('''\
    ## Summary

    The weekly chart dropped the last day. An off-by-one in the range end. Restores US-12 AC3.

    ## Testing

    - **Failing test first:** `keeps the last day` in `app/lib/range.test.ts` failed at base.
    - **Targeted tests** at head: 3 files, 812 passed, 0 failed.
    - **CI** on the pushed head: the loop reports the head only after every check passes.
    - **Known limits:** none beyond the acceptance criterion.

    ```sh
    npx vitest run app/lib/range.test.ts
    ```

    ## Risk

    **low**: one helper with two callers; `Array<string>` signature unchanged.

    ## How to revert

    A plain `git revert` of the merge commit is complete.
    No data or config change.
    ''')


def verdict(**over):
    v = {
        'fix_id': 'ocr05-range-end', 'round': 1, 'scope': 'full_diff', 'base': B, 'head': A,
        'reviewer': {'role': 'independent_reviewer', 'fresh_context': True, 'wrote_fix': False,
                     'model': 'm', 'same_model': True},
        'verdict': 'approve',
        'findings': [],
        'checks': {k: 'yes' for k in ('red_at_base', 'green_at_head', 'protected_tests_untouched',
                                      'claims_match_assertions', 'single_fix_scope')},
    }
    v.update(over)
    return v


class StrictJson(unittest.TestCase):
    def test_duplicate_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'r.json')
            put(p, '{"verdict": "changes", "verdict": "approve"}')
            with self.assertRaises(ValueError):
                D.strict_load(p)

    def test_nested_duplicate_and_nan_are_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'r.json')
            put(p, '{"checks": {"a": 1, "a": 2}}')
            with self.assertRaises(ValueError):
                D.strict_load(p)
            put(p, '{"x": NaN}')
            with self.assertRaises(ValueError):
                D.strict_load(p)


class LedgerAndTimes(unittest.TestCase):
    def test_damaged_ledger_line_stops_with_file_and_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'published.jsonl')
            put(p, '{"pr": 1, "effect": "open"}\n{"pr": 2, "eff\n')
            with self.assertRaises(SystemExit) as e:
                D.ledger_records(p, 'pr', 1)
            self.assertIn('published.jsonl:2', str(e.exception))

    def test_good_ledger_still_reads(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'published.jsonl')
            put(p, '{"pr": 1}\n\n{"pr": 2}\n{"pr": 1, "x": 1}\n')
            self.assertEqual(len(D.ledger_records(p, 'pr', 1)), 2)

    def test_times_compare_by_instant_not_by_text(self):
        gh = D.utc_time('2026-11-03T12:00:00Z', 'gh')
        local = D.utc_time('2026-11-03T08:00:00-05:00', 'meta')  # 13:00Z
        self.assertGreater(local, gh)
        self.assertLess('2026-11-03T08:00:00-05:00', '2026-11-03T12:00:00Z', 'text order is wrong here')

    def test_time_without_zone_is_refused(self):
        for bad in ('2026-11-03T12:00:00', 'yesterday', ''):
            with self.subTest(bad):
                with self.assertRaises(SystemExit):
                    D.utc_time(bad, 'meta')


class Verdict(unittest.TestCase):
    def test_valid_approve_passes(self):
        self.assertEqual(D.verdict_problems(verdict(), A), [])

    def test_prefix_head_is_refused(self):
        self.assertTrue(D.verdict_problems(verdict(head=A[:7]), A))

    def test_other_head_is_refused(self):
        self.assertTrue(D.verdict_problems(verdict(), B))

    def test_head_sharing_a_short_prefix_is_refused(self):
        self.assertTrue(D.verdict_problems(verdict(head=A[:12] + 'c' * 28), A))

    def test_short_head_on_both_sides_is_refused(self):
        self.assertTrue(D.verdict_problems(verdict(head=A[:7]), A[:7]))

    def test_approve_without_red_at_base_is_refused(self):
        for state in ('no', 'not_checked', 'not_applicable'):
            v = verdict()
            v['checks']['red_at_base'] = state
            self.assertTrue(D.verdict_problems(v, A), state)

    def test_approve_without_green_at_head_is_refused(self):
        v = verdict()
        v['checks']['green_at_head'] = 'no'
        self.assertTrue(D.verdict_problems(v, A))

    def test_unknown_field_is_refused(self):
        self.assertTrue(D.verdict_problems(verdict(passed=True), A))

    def test_blocking_finding_is_refused(self):
        f = {'id': 'R1-1', 'class': 'must_fix', 'summary': 'wrong end', 'evidence_kind': 'reading'}
        self.assertTrue(D.verdict_problems(verdict(findings=[f]), A))

    def test_non_optional_should_fix_is_refused(self):
        f = {'id': 'R1-1', 'class': 'should_fix', 'summary': 'rename it', 'evidence_kind': 'reading'}
        self.assertTrue(D.verdict_problems(verdict(findings=[f]), A))

    def test_still_open_is_refused(self):
        self.assertTrue(D.verdict_problems(verdict(still_open=['R1-1']), A))

    def test_reviewer_who_wrote_fix_is_refused(self):
        v = verdict()
        v['reviewer']['wrote_fix'] = True
        self.assertTrue(D.verdict_problems(v, A))

    def test_independent_reviewer_without_fresh_context_is_refused(self):
        v = verdict()
        v['reviewer']['fresh_context'] = False
        self.assertTrue(D.verdict_problems(v, A))

    def test_changes_verdict_is_refused(self):
        self.assertTrue(D.verdict_problems(verdict(verdict='changes'), A))

    def test_duplicate_verdict_file_does_not_approve(self):
        with tempfile.TemporaryDirectory() as t:
            raw = json.dumps(verdict())
            raw = raw.replace('"verdict": "approve"', '"verdict": "changes", "verdict": "approve"')
            put(os.path.join(t, 'review-1.json'), raw)
            self.assertFalse(D.review_approves(t, A))

    def test_text_changed_after_review_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            put(os.path.join(t, 'pr-body.md'), GOOD_BODY)
            v = verdict(text_sha256={'pr-body.md': D.sha256_file(os.path.join(t, 'pr-body.md'))})
            put(os.path.join(t, 'review-1.json'), json.dumps(v))
            self.assertTrue(D.review_approves(t, A, ('pr-body.md',)))
            put(os.path.join(t, 'pr-body.md'), '\nedited after review\n', 'a')
            self.assertFalse(D.review_approves(t, A, ('pr-body.md',)))

    def test_missing_digest_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            put(os.path.join(t, 'pr-body.md'), GOOD_BODY)
            put(os.path.join(t, 'review-1.json'), json.dumps(verdict()))
            self.assertFalse(D.review_approves(t, A, ('pr-body.md',)))


class VerdictToken(unittest.TestCase):
    def test_variants_are_refused(self):
        for s in ('VERDICT: APPROVE', 'verdict : approve', 'VERDICT\uff1a APPROVE', 'VER\u200bDICT: x',
                  '\uff36\uff25\uff32\uff24\uff29\uff23\uff34: x', 'Verdict\t:'):
            with self.assertRaises(SystemExit, msg=repr(s)):
                D.no_verdict_token(s, 'test')

    def test_plain_word_is_allowed(self):
        D.no_verdict_token('The reviewer verdict is stored locally.', 'test')


class Body(unittest.TestCase):
    def test_good_body_passes(self):
        self.assertEqual(D.body_problems(GOOD_BODY), [])

    def test_template_itself_is_refused(self):
        self.assertTrue(D.body_problems(text(os.path.join(ROOT, 'templates', 'pr-body.md'))))

    def test_missing_section_is_refused(self):
        self.assertTrue(D.body_problems(GOOD_BODY.replace('## Risk', '## Notes')))

    def test_heading_only_section_is_refused(self):
        b = GOOD_BODY.split('## How to revert')[0] + '## How to revert\n\n'
        self.assertTrue(D.body_problems(b))

    def test_section_inside_comment_is_refused(self):
        b = GOOD_BODY.replace('## Risk', '<!--\n## Risk').replace('No data or config change.', 'No data or config change.\n-->')
        self.assertTrue(D.body_problems(b))

    def test_duplicate_section_is_refused(self):
        self.assertTrue(D.body_problems(GOOD_BODY + '\n## Risk\n\nhigh\n'))

    def test_placeholder_is_refused(self):
        self.assertTrue(D.body_problems(GOOD_BODY.replace('812 passed', '<passed> passed')))
        self.assertTrue(D.body_problems(GOOD_BODY.replace('`app/lib/range.test.ts`', '`<file>`', 1)))


class Artifacts(unittest.TestCase):
    def test_markers_are_found(self):
        for s in ('text [truncated] more', '... 4,432 bytes omitted ...', '<truncated>',
                  '<<<<<<< HEAD', '>>>>>>> branch', '=======', '[OUTPUT TRUNCATED - 9 lines omitted]'):
            self.assertTrue(D.artifact_problems(s, 'x'), s)

    def test_ordinary_text_passes(self):
        self.assertEqual(D.artifact_problems('One fix... and a <= b, and === in JS.\n', 'x'), [])


class SuiteEnv(unittest.TestCase):
    def env(self, base):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        return D.suite_env(base, self.home)

    def test_only_listed_variables_reach_the_suite(self):
        env = self.env({'PATH': '/bin', 'HOME': '/home-of/me', 'LANG': 'C', 'GH_TOKEN': 'x', 'GITHUB_TOKEN': 'x',
                        'OPENAI_API_KEY': 'x', 'MY_SECRET': 'x', 'NPM_TOKEN': 'x', 'AWS_ACCESS_KEY_ID': 'x',
                        'SSH_AUTH_SOCK': '/tmp/agent.sock', 'GH_CONFIG_DIR': '/home-of/me/.config/gh',
                        'ODD_NAME': 'leak'})
        self.assertEqual(sorted(env), ['CI', 'HOME', 'LANG', 'PATH', 'TMPDIR', 'TZ',
                                       'XDG_CACHE_HOME', 'XDG_CONFIG_HOME'])

    def test_home_is_throwaway_and_no_ssh_agent(self):
        env = self.env({'PATH': '/bin', 'HOME': os.path.expanduser('~'), 'SSH_AUTH_SOCK': '/tmp/a'})
        self.assertNotEqual(os.path.realpath(env['HOME']), os.path.realpath(os.path.expanduser('~')))
        self.assertEqual(env['HOME'], self.home)
        self.assertNotIn('SSH_AUTH_SOCK', env)
        self.assertTrue(os.path.isdir(env['TMPDIR']))


class Addressed(unittest.TestCase):
    """Who counts for the start gate: only MAINTAINER_LOGINS, never a passer-by or our own close."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ledger = os.path.join(self.tmp, 'published.jsonl')
        put(self.ledger, '{"pr": 7}\n')
        self.old = (D.run, D.FORK_OWNER, os.environ.get('MAINTAINER_LOGINS'))
        D.FORK_OWNER = 'loopbot'
        os.environ['MAINTAINER_LOGINS'] = 'brad'
        self.pr = {'state': 'OPEN', 'reviews': [], 'comments': []}
        self.closed_by = 'brad'

        def fake(args, cwd=None, check=True):
            if args[:3] == ['gh', 'pr', 'view']:
                return json.dumps(self.pr)
            if args[:2] == ['gh', 'api'] and args[2].endswith('/events'):
                return self.closed_by
            raise AssertionError(args)
        D.run = fake

    def tearDown(self):
        D.run, D.FORK_OWNER = self.old[0], self.old[1]
        if self.old[2] is None:
            os.environ.pop('MAINTAINER_LOGINS', None)
        else:
            os.environ['MAINTAINER_LOGINS'] = self.old[2]

    def rc(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return D.addressed([self.ledger])

    def test_unset_maintainer_logins_refuses(self):
        os.environ.pop('MAINTAINER_LOGINS')
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            D.addressed([self.ledger])

    def test_drive_by_comment_does_not_count(self):
        self.pr['comments'] = [{'author': {'login': 'passerby'}}]
        self.assertEqual(self.rc(), 1)

    def test_maintainer_comment_counts(self):
        self.pr['comments'] = [{'author': {'login': 'brad'}}]
        self.assertEqual(self.rc(), 0)

    def test_self_close_does_not_count(self):
        self.pr['state'], self.closed_by = 'CLOSED', 'loopbot'
        self.assertEqual(self.rc(), 1)

    def test_maintainer_close_counts(self):
        self.pr['state'] = 'CLOSED'
        self.assertEqual(self.rc(), 0)

    def test_merge_counts(self):
        self.pr['state'] = 'MERGED'
        self.assertEqual(self.rc(), 0)


def check_run(name, status='completed', conclusion='success', **kw):
    return dict({'name': name, 'status': status, 'conclusion': conclusion, 'html_url': f'https://ci.example/{name}'}, **kw)


class CiClassify(unittest.TestCase):
    """The CI gate's reading of GitHub check runs for one head (sample shapes from the check-runs API)."""

    def test_success_skipped_and_neutral_are_green(self):
        runs = [check_run('test (1/6)'), check_run('gitleaks', conclusion='skipped'), check_run('audit', conclusion='neutral')]
        self.assertEqual(D.classify_checks(runs), ('green', []))

    def test_any_failure_is_red_and_named(self):
        runs = [check_run('test (1/6)'), check_run('typecheck', conclusion='failure'), check_run('build', conclusion='cancelled')]
        state, bad = D.classify_checks(runs)
        self.assertEqual(state, 'red')
        self.assertEqual([r['name'] for r in bad], ['typecheck', 'build'])

    def test_unknown_or_missing_conclusion_is_red(self):
        for c in ('timed_out', 'action_required', 'stale', 'startup_failure', None, 'something-new'):
            with self.subTest(c):
                self.assertEqual(D.classify_checks([check_run('a'), check_run('b', conclusion=c)])[0], 'red')

    def test_running_or_queued_is_pending_even_with_a_failure(self):
        runs = [check_run('a', conclusion='failure'), check_run('b', status='in_progress', conclusion=None)]
        self.assertEqual(D.classify_checks(runs), ('pending', []))
        self.assertEqual(D.classify_checks([check_run('a', status='queued', conclusion=None)])[0], 'pending')

    def test_no_runs_yet_is_pending_not_green(self):
        self.assertEqual(D.classify_checks([]), ('pending', []))

    def test_api_sample_is_read(self):
        sample = json.loads('{"total_count": 2, "check_runs": [{"id": 11, "name": "test (2/6)", "status": "completed", '
                            '"conclusion": "success", "app": {"slug": "github-actions"}}, {"id": 12, "name": '
                            '"user-stories", "status": "completed", "conclusion": "failure", "app": {"slug": "github-actions"}}]}')
        state, bad = D.classify_checks(sample['check_runs'])
        self.assertEqual((state, [r['id'] for r in bad]), ('red', [12]))


class InReviewGuard(unittest.TestCase):
    HEAD = '0123456789abcdef0123456789abcdef01234567'

    def batch(self, body, branch='claude/batch-20261104', n=900):
        return {'number': n, 'headRefName': branch, 'body': body}

    def test_full_head_in_a_batch_body_matches(self):
        prs = [self.batch(f'Batch of three:\n812 {self.HEAD}\n815 {"e" * 40}\n')]
        self.assertEqual(D.in_review_by(self.HEAD, prs), [900])

    def test_short_head_in_a_group_body_matches(self):
        prs = [self.batch(f'- #812 at `{self.HEAD[:12]}`', branch='claude/group-sync', n=901)]
        self.assertEqual(D.in_review_by(self.HEAD, prs), [901])

    def test_other_heads_do_not_match(self):
        other = 'f' + self.HEAD[1:]
        prs = [self.batch(f'812 {other}'), self.batch(f'812 {self.HEAD[:6]} only six characters')]
        self.assertEqual(D.in_review_by(self.HEAD, prs), [])

    def test_head_inside_a_longer_hex_run_does_not_match(self):
        self.assertEqual(D.in_review_by(self.HEAD, [self.batch('sha256 ' + 'aa' + self.HEAD + 'bb' * 11)]), [])

    def test_only_batch_and_group_branches_count(self):
        prs = [self.batch(f'{self.HEAD}', branch='fix/other'), self.batch(f'{self.HEAD}', branch='claude/batchy')]
        self.assertEqual(D.in_review_by(self.HEAD, prs), [])


class Drift(unittest.TestCase):
    """The driver's gate constants and the published schema must say the same thing."""

    def setUp(self):
        self.s = json.loads(text(SCHEMA))

    def test_enums_match(self):
        self.assertEqual(tuple(self.s['properties']['verdict']['enum']), D.VERDICTS)
        self.assertEqual(tuple(self.s['$defs']['checkState']['enum']), D.CHECK_STATES)

    def test_approve_rule_matches(self):
        rule = [r for r in self.s['allOf'] if r['if']['properties'].get('verdict', {}).get('const') == 'approve']
        self.assertEqual(len(rule), 1)
        checks = rule[0]['then']['properties']['checks']['properties']
        self.assertEqual(sorted(checks), sorted(D.APPROVE_NEEDS_YES))
        self.assertTrue(all(v == {'const': 'yes'} for v in checks.values()))
        self.assertTrue(set(D.APPROVE_NEEDS_YES) <= set(self.s['properties']['checks']['required']))

    def test_text_digest_names_match(self):
        names = self.s['properties']['text_sha256']['propertyNames']['enum']
        self.assertEqual(sorted(names), sorted(D.POST_FILES_NEW + D.POST_FILES_REPAIR))

    def test_no_assert_gates(self):
        """python -O strips assert statements; a gate must not vanish under -O."""
        tree = ast.parse(text(DRIVER))
        self.assertEqual([n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assert)], [])


# ---------------------------------------------------------------------------------------------
# end-to-end: real git repos, a fake gh that records calls, a fake gitleaks
# ---------------------------------------------------------------------------------------------

# A stand-in for the roadmap repo's tools/secret-rules.mjs: one made-up shape, so no fixture here
# looks like a real credential.
FAKE_RULES = 'export const PATTERNS = { fake_key: "FAKEKEY_[0-9]{6}" };\n'

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
st_path = os.environ['FAKE_GH_STATE']
st = json.load(open(st_path)) if os.path.exists(st_path) else {"prs": []}
a = sys.argv[1:]
with open(os.environ['FAKE_GH_LOG'], 'a') as f:
    f.write(json.dumps(a) + '\n')
def opt(name):
    return a[a.index(name) + 1] if name in a else None
def save():
    json.dump(st, open(st_path, 'w'))
def view(pr):
    return {"number": pr["number"], "url": pr["url"], "author": {"login": pr["owner"]}, "baseRefName": "main",
            "headRefOid": pr["head"], "headRefName": pr["branch"], "isDraft": False, "title": pr["title"],
            "body": pr["body"], "state": pr["state"], "comments": pr.get("comments", []),
            "headRepositoryOwner": {"login": pr["owner"]}, "reviews": []}
if a[:2] == ["pr", "list"]:
    br = opt("--head")
    if br is None:  # the in-review guard lists every open PR
        print(json.dumps(st.get("batches", [])))
    else:
        print(json.dumps([view(p) for p in st["prs"] if p["branch"] == br]))
elif a[0] == "api" and "/check-runs" in a[1]:
    head = a[1].split("/commits/")[1].split("/")[0]
    runs = st.get("checks", {}).get(head, [])
    print(json.dumps({"total_count": len(runs), "check_runs": runs}))
elif a[:2] == ["run", "view"]:
    print("step 1 ok\nError: expected 3 to be 4\n" + os.environ.get("FAKE_GH_LOG_EXTRA", ""))
elif a[:2] == ["pr", "comment"]:  # a repair: the push before it moved the head
    pr = [p for p in st["prs"] if str(p["number"]) == a[2]][0]
    pr["head"] = os.environ["FAKE_GH_PUSHED_HEAD"]
    pr.setdefault("comments", []).append({"body": open(opt("--body-file")).read()})
    save()
    print(pr["url"] + "#issuecomment-1")
elif a[:2] == ["pr", "edit"]:
    pr = [p for p in st["prs"] if str(p["number"]) == a[2]][0]
    if "--body-file" in a:
        pr["body"] = open(opt("--body-file")).read()
    save()
elif a[:2] == ["pr", "create"]:
    owner, br = opt("--head").split(":")
    if os.environ.get("FAKE_GH_FAIL_CREATE"):
        sys.exit("HTTP 502")
    n = 100 + len(st["prs"])
    head = os.environ["FAKE_GH_PUSHED_HEAD"]
    st["prs"].append({"number": n, "url": f"https://github.com/up/repo/pull/{n}", "owner": owner, "branch": br,
                      "head": head, "title": opt("--title"), "body": open(opt("--body-file")).read(), "state": "OPEN"})
    save()
    print(st["prs"][-1]["url"])
elif a[:2] == ["pr", "view"]:
    if os.environ.get("FAKE_GH_FAIL_VIEW"):
        sys.exit("HTTP 502")
    key = a[2]
    pr = [p for p in st["prs"] if p["url"] == key or str(p["number"]) == key][0]
    print(json.dumps(view(pr)))
else:
    sys.exit("fake gh: unsupported " + " ".join(a))
'''


def git(args, cwd):
    return sp.run(['git', '-c', 'commit.gpgsign=false', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid'] + args,
                  cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        t = self.t
        up, fork, wt = (os.path.join(t, x) for x in ('up.git', 'fork.git', 'wt'))
        seed = os.path.join(t, 'seed')
        os.makedirs(seed)
        git(['init', '-q', '-b', 'main'], seed)
        put(os.path.join(seed, 'range.ts'), 'export const end = (n) => n - 1\n')
        os.makedirs(os.path.join(seed, 'tools'))
        put(os.path.join(seed, 'tools', 'secret-rules.mjs'), FAKE_RULES)
        git(['add', '.'], seed)
        git(['commit', '-qm', 'base'], seed)
        git(['clone', '-q', '--bare', seed, up], t)
        git(['clone', '-q', '--bare', seed, fork], t)
        git(['clone', '-q', up, wt], t)
        git(['remote', 'rename', 'origin', 'upstream'], wt)
        git(['remote', 'add', 'origin', fork], wt)
        git(['checkout', '-qb', 'fix/range-end'], wt)
        put(os.path.join(wt, 'range.ts'), 'export const end = (n) => n\n')
        git(['commit', '-qam', 'Keep the last day in the weekly range'], wt)
        self.wt, self.fork = wt, fork
        self.head = git(['rev-parse', 'HEAD'], wt)
        self.base = git(['rev-parse', 'upstream/main'], wt)
        self.fixes = os.path.join(t, 'fixes')
        self.F = os.path.join(self.fixes, 'ocr05-range-end')
        os.makedirs(self.F)
        self.write_folder()
        self.bin = os.path.join(t, 'bin')
        os.makedirs(self.bin)
        for name, src in (('gh', FAKE_GH), ('gitleaks', '#!/bin/sh\nexit 0\n')):
            p = os.path.join(self.bin, name)
            put(p, src)
            os.chmod(p, 0o755)
        self.log = os.path.join(t, 'gh.log')
        self.state = os.path.join(t, 'gh.json')
        self.sd = os.path.join(t, 'state')
        os.makedirs(self.sd)
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ['PATH'], GH_FORK_OWNER='me',
                        UPSTREAM_REPO='up/repo', GITLEAKS_BIN=os.path.join(self.bin, 'gitleaks'),
                        FAKE_GH_LOG=self.log, FAKE_GH_STATE=self.state, FAKE_GH_PUSHED_HEAD=self.head,
                        WORKDIR=wt, STATE_DIR=self.sd)
        for k in ('ATTRIBUTION', 'LOCAL_SUITE', 'SHARED_SUITE_PATHS'):
            self.env.pop(k, None)

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def write_folder(self, body=GOOD_BODY, head=None):
        F, head = self.F, head or self.head
        put(f'{F}/STATE.json', json.dumps({'worktree': self.wt, 'branch': 'fix/range-end', 'head': head}))
        put(f'{F}/pr-title.txt', 'Weekly chart drops the last day\n')
        put(f'{F}/pr-body.md', body)
        dig = {n: D.sha256_file(f'{F}/{n}') for n in ('pr-title.txt', 'pr-body.md')}
        put(f'{F}/review-1.json', json.dumps(verdict(head=head, base=self.base, text_sha256=dig)))

    def publish(self, *extra, env=None):
        return sp.run([sys.executable, '-I', DRIVER, 'publish', self.F, *extra], capture_output=True, text=True,
                      env=env or self.env)

    def gh_calls(self):
        return lines(self.log) if os.path.exists(self.log) else []

    def writes(self):
        return [c for c in self.gh_calls() if c[:2] in (['pr', 'create'], ['pr', 'comment'], ['pr', 'edit'], ['pr', 'merge'])]

    def ledger(self):
        p = os.path.join(self.fixes, 'published.jsonl')
        return lines(p) if os.path.exists(p) else []

    def fork_has_branch(self):
        return sp.run(['git', 'rev-parse', '--verify', '-q', 'refs/heads/fix/range-end'], cwd=self.fork,
                      capture_output=True).returncode == 0

    def test_dry_run_passes_and_writes_nothing(self):
        r = self.publish()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.writes(), [])
        self.assertFalse(self.fork_has_branch())
        self.assertEqual(self.ledger(), [])

    def test_go_publishes_with_attempt_then_observed(self):
        r = self.publish('--go')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([c[:2] for c in self.writes()], [['pr', 'create']])
        self.assertEqual([x['status'] for x in self.ledger()], ['attempted', 'observed_succeeded'])
        self.assertTrue(self.fork_has_branch())

    def test_rerun_after_lost_readback_adopts_instead_of_duplicating(self):
        r = self.publish('--go', env=dict(self.env, FAKE_GH_FAIL_VIEW='1'))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual([x['status'] for x in self.ledger()], ['attempted'])
        r = self.publish('--go')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len([c for c in self.writes() if c[:2] == ['pr', 'create']]), 1)
        self.assertEqual(self.ledger()[-1]['status'], 'observed_succeeded')
        self.assertTrue(self.ledger()[-1].get('adopted'))

    def test_already_published_is_refused(self):
        self.assertEqual(self.publish('--go').returncode, 0)
        r = self.publish('--go')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('already published', r.stdout + r.stderr)

    def test_body_edited_after_review_is_refused(self):
        put(f'{self.F}/pr-body.md', '\nOne more line.\n', 'a')
        r = self.publish()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('changed after review', r.stdout + r.stderr)

    def test_untracked_file_is_refused(self):
        put(os.path.join(self.wt, 'helper.test.ts'), 'local only\n')
        r = self.publish()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('untracked', (r.stdout + r.stderr).lower())

    def test_branch_with_no_fix_commits_is_refused(self):
        git(['reset', '-q', '--hard', 'upstream/main'], self.wt)
        self.write_folder(head=self.base)
        r = self.publish()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('no fix commits', r.stdout + r.stderr)

    def test_body_without_risk_is_refused(self):
        self.write_folder(body=GOOD_BODY.replace('## Risk', '## Notes'))
        r = self.publish()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Risk', r.stdout + r.stderr)

    def test_conflict_marker_in_diff_is_refused(self):
        put(os.path.join(self.wt, 'range.ts'), '<<<<<<< HEAD\nexport const end = (n) => n\n')
        git(['commit', '-qam', 'oops'], self.wt)
        head = git(['rev-parse', 'HEAD'], self.wt)
        self.env['FAKE_GH_PUSHED_HEAD'] = head
        self.write_folder(head=head)
        r = self.publish()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('marker', (r.stdout + r.stderr).lower())

    def repair_folder(self, body=None):
        """Publish the PR, add a repair commit, and lay out <round>/pr<N>/ for `driver.py repair`."""
        self.assertEqual(self.publish('--go').returncode, 0)
        n = self.ledger()[-1]['number']
        old = self.head
        put(os.path.join(self.wt, 'range.ts'), 'export const end = (n) => n // reviewed\n')
        git(['commit', '-qam', 'Address review: comment the range end'], self.wt)
        new = git(['rev-parse', 'HEAD'], self.wt)
        d = os.path.join(self.t, 'round', f'pr{n}')
        os.makedirs(d)
        put(f'{d}/STATE.json', json.dumps({'worktree': self.wt, 'branch': 'fix/range-end', 'head': new}))
        put(f'{d}/meta.json', json.dumps({'head_at_start': old, 'addressed_comment_at': '2026-01-01T00:00:00Z'}))
        put(f'{d}/comment.md', 'Done: the range end now has a comment.\n')
        if body is not None:
            put(f'{d}/body.md', body)
        names = [x for x in ('comment.md', 'body.md') if os.path.exists(f'{d}/{x}')]
        dig = {x: D.sha256_file(f'{d}/{x}') for x in names}
        v = verdict(head=new, base=self.base, round=2, scope='delta', previous_head=old, still_open=[],
                    resolved=['R1-1'], text_sha256=dig)
        v['reviewer']['role'] = 'delta_reviewer'
        put(f'{d}/review-2.json', json.dumps(v))
        return d

    def repair(self, d, *extra):
        return sp.run([sys.executable, '-I', DRIVER, 'repair', d, *extra], capture_output=True, text=True, env=self.env)

    def test_repair_dry_run_passes(self):
        d = self.repair_folder(body=GOOD_BODY)
        r = self.repair(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_repair_body_without_risk_is_refused(self):
        d = self.repair_folder(body=GOOD_BODY.replace('## Risk', '## Notes'))
        r = self.repair(d)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Risk', r.stdout + r.stderr)

    def test_repair_comment_edited_after_review_is_refused(self):
        d = self.repair_folder()
        put(f'{d}/comment.md', 'something else\n', 'a')
        r = self.repair(d)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('changed after review', r.stdout + r.stderr)

    def test_verdict_token_in_body_is_refused(self):
        self.write_folder(body=GOOD_BODY.replace('one helper', 'VERDICT : approve, one helper'))
        r = self.publish()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('VERDICT', r.stdout + r.stderr)

    # --- local suite: off by default, optional for shared code

    def test_no_local_suite_by_default(self):
        self.assertFalse(os.path.exists(f'{self.F}/suite.json'))
        self.assertEqual(self.publish().returncode, 0)

    def test_shared_mode_needs_the_suite_for_shared_paths(self):
        r = self.publish(env=dict(self.env, LOCAL_SUITE='shared', SHARED_SUITE_PATHS='range.*'))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('suite has not passed at head', r.stdout + r.stderr)
        r = self.publish(env=dict(self.env, LOCAL_SUITE='shared', SHARED_SUITE_PATHS='packages/health-core/*merge*'))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unknown_local_suite_mode_is_refused(self):
        r = self.publish(env=dict(self.env, LOCAL_SUITE='always'))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('LOCAL_SUITE', r.stdout + r.stderr)

    # --- secret-fixture check: the roadmap repo's own rules, on the added lines

    def commit_line(self, line):
        put(os.path.join(self.wt, 'range.test.ts'), line + '\n')
        git(['add', 'range.test.ts'], self.wt)
        git(['commit', '-qm', 'add a fixture'], self.wt)
        head = git(['rev-parse', 'HEAD'], self.wt)
        self.env['FAKE_GH_PUSHED_HEAD'] = head
        self.write_folder(head=head)

    @unittest.skipUnless(shutil.which('node'), 'node is needed for the secret-fixture check')
    def test_secret_shaped_fixture_is_refused_by_file_line_and_rule_not_value(self):
        value = 'FAKEKEY' + '_' + '424242'  # matches the fake rule only; assembled so this file holds no match
        self.commit_line(f"const token = '{value}'")
        r = self.publish('--go')
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('range.test.ts:1 fake_key', out)
        self.assertNotIn(value, out)
        self.assertEqual(self.writes(), [])
        self.assertFalse(self.fork_has_branch())

    @unittest.skipUnless(shutil.which('node'), 'node is needed for the secret-fixture check')
    def test_plain_fixture_passes_the_secret_check(self):
        self.commit_line("const token = 'test-token-good'")
        r = self.publish()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_secret_rules_refuse_rather_than_skip(self):
        bare = os.path.join(self.t, 'no-rules')
        os.makedirs(bare)
        git(['init', '-q'], bare)
        r = self.publish(env=dict(self.env, WORKDIR=bare))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('secret-rules.mjs is missing', r.stdout + r.stderr)

    def test_unset_workdir_refuses(self):
        env = dict(self.env)
        env.pop('WORKDIR')
        r = self.publish(env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('WORKDIR', r.stdout + r.stderr)

    # --- in-review push guard

    def gh_state(self):
        with open(self.state) as f:
            return json.load(f)

    def set_gh_state(self, **kw):
        st = self.gh_state() if os.path.exists(self.state) else {'prs': []}
        st.update(kw)
        put(self.state, json.dumps(st))

    def test_repair_to_a_head_in_brads_review_is_refused(self):
        d = self.repair_folder()
        self.set_gh_state(batches=[{'number': 950, 'headRefName': 'claude/batch-20261104',
                                    'body': f'100 {self.head}\n'}])
        r = self.repair(d, '--go')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("in Brad's review", r.stdout + r.stderr)
        self.assertIn('#950', r.stdout + r.stderr)
        self.assertEqual([c[:2] for c in self.writes()], [['pr', 'create']], 'nothing pushed or posted')

    def test_repair_is_allowed_when_no_batch_names_the_head(self):
        d = self.repair_folder()
        self.set_gh_state(batches=[{'number': 950, 'headRefName': 'claude/batch-20261104', 'body': f'100 {"e" * 40}\n'},
                                   {'number': 951, 'headRefName': 'fix/x', 'body': f'100 {self.head}\n'}])
        r = self.repair(d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # --- the CI gate on the pushed head

    def ci(self, *extra):
        return sp.run([sys.executable, '-I', DRIVER, 'ci', self.F, '--wait-min', '0', *extra], capture_output=True,
                      text=True, env=self.env)

    def published(self, body=GOOD_BODY):
        self.write_folder(body=body)
        r = self.publish('--go')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return self.ledger()[-1]['number']

    def outbox(self):
        p = os.path.join(self.sd, 'report-outbox.txt')
        return text(p) if os.path.exists(p) else ''

    def test_ci_green_writes_ci_green_ledger_and_report_line(self):
        n = self.published()
        self.set_gh_state(checks={self.head: [check_run('test (1/6)'), check_run('gitleaks', conclusion='skipped')]})
        r = self.ci()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(text(f'{self.F}/CI-GREEN').split('\n')[0], self.head)
        self.assertFalse(os.path.exists(f'{self.F}/CI-PENDING'))
        self.assertEqual(self.outbox(), f'PR #{n} ready, head {self.head}\n')
        self.assertEqual([(x['status'], x['head']) for x in lines(os.path.join(self.fixes, 'ci.jsonl'))],
                         [('green', self.head)])
        self.assertEqual(self.ci().returncode, 0)
        self.assertEqual(self.outbox().count('ready'), 1, 'reported once')

    def test_ci_red_writes_failing_jobs_and_never_reports(self):
        self.published()
        self.set_gh_state(checks={self.head: [check_run('test (1/6)'),
                                              check_run('typecheck', conclusion='failure', id=77, app={'slug': 'github-actions'})]})
        secretish = 'gh' + 'p_' + 'x' * 36  # assembled at run time: no secret shape in this file
        r = sp.run([sys.executable, '-I', DRIVER, 'ci', self.F, '--wait-min', '0'], capture_output=True, text=True,
                   env=dict(self.env, FAKE_GH_LOG_EXTRA=f'echo {secretish}'))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        red = text(f'{self.F}/CI-RED.md')
        self.assertEqual(red.split('\n')[0], f'CI is red at {self.head}')
        self.assertIn('typecheck: failure', red)
        self.assertIn('expected 3 to be 4', red)
        self.assertNotIn(secretish, red)
        self.assertNotIn('test (1/6)', red)
        self.assertEqual(self.outbox(), '')
        self.assertFalse(os.path.exists(f'{self.F}/CI-GREEN'))

    def test_ci_still_running_is_pending_and_not_reported(self):
        self.published()
        self.set_gh_state(checks={self.head: [check_run('test (1/6)', status='in_progress', conclusion=None)]})
        self.assertEqual(self.ci().returncode, 3)
        self.assertEqual(text(f'{self.F}/CI-PENDING').split('\n')[0], self.head)
        self.assertEqual(self.outbox(), '')
        self.set_gh_state(checks={self.head: [check_run('test (1/6)')]})
        self.assertEqual(self.ci().returncode, 0)
        self.assertFalse(os.path.exists(f'{self.F}/CI-PENDING'))

    def test_ci_reads_only_the_pushed_head(self):
        self.published()
        self.set_gh_state(checks={'c' * 40: [check_run('test (1/6)')]})
        self.assertEqual(self.ci().returncode, 3, 'green checks on another commit do not count')

    def test_ci_after_a_repair_push_reads_the_new_head(self):
        d = self.repair_folder()
        with open(f'{d}/STATE.json') as f:
            new = json.load(f)['head']
        self.env['FAKE_GH_PUSHED_HEAD'] = new
        r = self.repair(d, '--go')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.set_gh_state(checks={new: [check_run('test (1/6)', conclusion='failure')]})
        r = sp.run([sys.executable, '-I', DRIVER, 'ci', d, '--wait-min', '0'], capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertEqual(text(f'{d}/CI-RED.md').split('\n')[0], f'CI is red at {new}')
        self.assertEqual(self.outbox(), '')

    def test_ci_needs_a_published_head(self):
        r = self.ci()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('has not pushed this head', r.stdout + r.stderr)

    def test_ci_fills_the_ci_line_in_the_pr_body(self):
        body = GOOD_BODY.replace('- **CI** on the pushed head: the loop reports the head only after every check passes.',
                                 f'- **CI** at `{self.head[:12]}`: pending')
        n = self.published(body=body)
        self.set_gh_state(checks={self.head: [check_run('test (1/6)')]})
        self.assertEqual(self.ci().returncode, 0)
        pr = [p for p in self.gh_state()['prs'] if p['number'] == n][0]
        self.assertIn(f'- **CI** at `{self.head[:12]}`: all checks passed ([checks](https://github.com/up/repo/pull/{n}/checks))',
                      pr['body'])
        self.assertNotIn('pending', pr['body'])


if __name__ == '__main__':
    unittest.main()
