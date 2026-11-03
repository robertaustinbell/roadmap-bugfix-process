#!/usr/bin/env python3
"""Regenerate data/pr-outcomes.csv from public GitHub data.

Needs the GitHub CLI (`gh`) logged in. Read-only: it never comments, labels or merges.

Usage:
  python3 scripts/data/pr_outcomes.py --author robertaustinbell --maintainer DrBradStanfield \
      --ledger-map ledger-map.json > data/pr-outcomes.csv

--ledger-map is optional JSON {"<pr number>": "<finder>"}. Without it, finder is guessed from the
branch name (branches containing "ocr" are Open Code Review) and everything else is "unattributed".
"""
import argparse, csv, datetime, json, subprocess, sys

REPO = 'DrBradStanfield/roadmap'


def gh(*args):
    r = subprocess.run(['gh', *args], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def days(a, b):
    if not a or not b:
        return ''
    f = lambda s: datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
    return round((f(b) - f(a)).total_seconds() / 86400, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=REPO)
    ap.add_argument('--author', required=True)
    ap.add_argument('--maintainer', required=True)
    ap.add_argument('--ledger-map')
    a = ap.parse_args()
    ledger = json.load(open(a.ledger_map)) if a.ledger_map else {}
    prs = gh('pr', 'list', '--repo', a.repo, '--author', a.author, '--state', 'all', '--limit', '1000',
             '--json', 'number,state,createdAt,mergedAt,closedAt,headRefName,title,url')
    w = csv.DictWriter(sys.stdout, fieldnames=['number', 'url', 'title', 'finder', 'state', 'created', 'decided',
                                               'days_to_decision', 'addressed', 'maintainer_note'])
    w.writeheader()
    for p in sorted(prs, key=lambda p: p['number']):
        finder = ledger.get(str(p['number'])) or ('open-code-review' if 'ocr' in p['headRefName'].lower() else 'unattributed')
        note, addressed = '', 'yes'
        if p['state'] != 'MERGED':
            d = gh('pr', 'view', str(p['number']), '--repo', a.repo, '--json', 'comments,reviews')
            mine = [c for c in d['comments'] + d.get('reviews', []) if c['author']['login'] == a.maintainer and c.get('body')]
            note = mine[-1]['body'].replace('\n', ' ')[:260] if mine else ''
            if p['state'] == 'OPEN':
                # Addressed = any maintainer action. CI and bot comments never count.
                addressed = 'yes (comment)' if mine or any(r['author']['login'] == a.maintainer for r in d.get('reviews', [])) else 'no'
        decided = p['mergedAt'] or p['closedAt']
        w.writerow(dict(number=p['number'], url=p['url'], title=p['title'], finder=finder, state=p['state'].lower(),
                        created=p['createdAt'][:10], decided=(decided or '')[:10],
                        days_to_decision=days(p['createdAt'], decided), addressed=addressed, maintainer_note=note))


if __name__ == '__main__':
    main()
