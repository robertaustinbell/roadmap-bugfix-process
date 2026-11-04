"""scripts/data/quality_ledger.py: the maintainer's review results, one line per result."""
import json
import os
import shutil
import subprocess as sp
import sys
import tempfile
import unittest

os.environ['LOOP_CONFIG'] = os.devnull  # never read a real loop.env in tests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QL = os.path.join(ROOT, 'scripts', 'data', 'quality_ledger.py')
H = 'a' * 40


class QualityLedger(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.sd, True)

    def run_(self, *args):
        return sp.run([sys.executable, '-I', QL, *args], capture_output=True, text=True,
                      env={'PATH': os.environ['PATH'], 'STATE_DIR': self.sd, 'LOOP_CONFIG': os.devnull})

    def rows(self):
        with open(os.path.join(self.sd, 'pr-quality.jsonl')) as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def test_sent_back_with_findings_is_recorded_with_its_fields(self):
        r = self.run_('record', '--pr', '812', '--head', H, '--outcome', 'sent_back', '--findings', '3',
                      '--category', 'ac_overpromise', '--category', 'cross_tab')
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.rows()[0]
        self.assertEqual((row['pr'], row['head'], row['outcome'], row['findings'], row['categories']),
                         (812, H, 'sent_back', 3, ['ac_overpromise', 'cross_tab']))

    def test_bad_records_are_refused(self):
        for args in (['--outcome', 'sent_back'],                                     # no findings
                     ['--outcome', 'merged', '--findings', '2'],                      # no category
                     ['--outcome', 'merged', '--findings', '1', '--category', 'style'],
                     ['--outcome', 'approved']):
            with self.subTest(args):
                self.assertNotEqual(self.run_('record', '--pr', '5', '--head', H, *args).returncode, 0)
        self.assertNotEqual(self.run_('record', '--pr', '5', '--head', H[:12], '--outcome', 'merged').returncode, 0)

    def test_same_pr_and_head_is_recorded_once(self):
        self.assertEqual(self.run_('record', '--pr', '5', '--head', H, '--outcome', 'merged').returncode, 0)
        self.assertNotEqual(self.run_('record', '--pr', '5', '--head', H, '--outcome', 'merged').returncode, 0)

    def test_tally_counts_outcomes_findings_and_categories(self):
        self.run_('record', '--pr', '5', '--head', H, '--outcome', 'merged')
        self.run_('record', '--pr', '6', '--head', 'b' * 40, '--outcome', 'sent_back', '--findings', '2',
                  '--category', 'stalled_body', '--category', 'secret_fixture')
        t = json.loads(self.run_('tally').stdout)
        self.assertEqual(t['reviews'], 2)
        self.assertEqual(t['outcomes']['merged'], 1)
        self.assertEqual(t['findings'], 2)
        self.assertEqual(t['categories']['secret_fixture'], 1)
        self.assertEqual(t['clean_rate'], 0.5)


if __name__ == '__main__':
    unittest.main()
