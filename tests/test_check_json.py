"""check_json.py and the gate-result schema it is most used for."""
import copy
import json
import os
import shutil
import subprocess as sp
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, 'scripts', 'check_json.py')
# Ask the same kind of process the check runs in (isolated mode), not this test process: a
# package on PYTHONPATH here may be invisible there.
HAVE = sp.run([sys.executable, '-I', '-c', 'import jsonschema'], capture_output=True).returncode == 0
UVX = shutil.which('uvx')

GATE = {'result': 'pass'}
VERDICT = {
    'fix_id': 'FIX-1', 'finding_id': 'C-1', 'base': 'a' * 40, 'head': 'b' * 40, 'ran_at': '2026-11-04T00:00:00Z',
    'gates': {'protected_tests': dict(GATE), 'tsc': dict(GATE), 'crap': dict(GATE), 'mutation': dict(GATE),
              'incremental_review': dict(GATE)},
    'overall': 'pass',
}


class CheckJson(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_check(self, doc, schema='verdict', env=None):
        p = os.path.join(self.d, 'x.json')
        with open(p, 'w') as f:
            json.dump(doc, f)
        r = sp.run([sys.executable, '-I', CHECK, p, schema], capture_output=True, text=True,
                   env=env or dict(os.environ))
        return r.returncode, r.stdout + r.stderr

    @unittest.skipUnless(UVX or HAVE, 'needs jsonschema or uvx')
    def test_valid_and_invalid_through_whatever_is_available(self):
        self.assertEqual(self.run_check(VERDICT)[0], 0)
        self.assertEqual(self.run_check({'nope': 1})[0], 1)

    def test_without_jsonschema_or_uvx_it_fails_loudly(self):
        # an empty PATH hides uvx; -I hides any user site-packages
        env = {'PATH': self.d, 'HOME': self.d}
        if HAVE:
            self.skipTest('this Python has jsonschema; the fallback path is not reachable here')
        rc, out = self.run_check(VERDICT, env=env)
        self.assertEqual(rc, 2)
        self.assertIn('could not check', out)

    @unittest.skipUnless(HAVE, 'jsonschema not installed')
    def test_valid_and_invalid(self):
        self.assertEqual(self.run_check(VERDICT)[0], 0)
        bad = copy.deepcopy(VERDICT)
        del bad['head']
        rc, out = self.run_check(bad)
        self.assertEqual(rc, 1)
        self.assertIn('head', out)

    @unittest.skipUnless(HAVE, 'jsonschema not installed')
    def test_not_applicable_needs_a_reason_and_does_not_fail(self):
        v = copy.deepcopy(VERDICT)
        v['gates']['tsc'] = {'result': 'not_applicable'}
        self.assertEqual(self.run_check(v)[0], 1)
        v['gates']['tsc']['reason'] = 'no TypeScript in this repo'
        self.assertEqual(self.run_check(v)[0], 0)

    @unittest.skipUnless(HAVE, 'jsonschema not installed')
    def test_secret_scan_suite_and_extra_gates_can_fail_the_verdict(self):
        for gates in ({'secret_scan': {'result': 'fail', 'reason': 'r'}},
                      {'suite': {'result': 'could_not_run', 'reason': 'r'}},
                      {'extra': [{'name': 'check_kit', 'result': 'fail', 'reason': 'r'}]}):
            with self.subTest(gates=list(gates)):
                v = copy.deepcopy(VERDICT)
                v['gates'].update(gates)
                self.assertEqual(self.run_check(v)[0], 1, 'overall pass must be refused')
                v['overall'] = 'fail'
                self.assertEqual(self.run_check(v)[0], 0)

    def test_unknown_schema_name_is_refused(self):
        rc, out = self.run_check(VERDICT, schema='no-such')
        self.assertNotEqual(rc, 0)


if __name__ == '__main__':
    unittest.main()
