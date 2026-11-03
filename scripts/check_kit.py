#!/usr/bin/env python3
"""Integrity check for this kit. Standard library only.

    python3 scripts/check_kit.py [repo_root]      exit 0 = clean

Checks every file git knows about (tracked, plus untracked files that are not ignored):

1. Public scrub. No local machine paths, private runtime names, personal phone numbers or
   e-mail addresses, transport artifacts or style bans, in file names or contents. Findings print the
   file, line and category only, never the matched text, so the report itself cannot leak.
2. Files that must not be published: symlinks, macOS metadata (`.DS_Store`, `._*`), empty files.
3. Relative links in Markdown resolve to a file (and to a heading, when a #fragment is given).
4. Required rules. Each rule in RULES must appear in its own file under its own heading, outside
   HTML comments and code blocks. Moving a rule into a comment, a code block or another
   section fails, so a rule cannot be quietly disabled.
5. Every agent template in agents/ is linked from at least one page, so none is orphaned.
6. Every skill in skills/ is valid for both the Agent Skills standard (Claude and others) and
   Hermes Agent: only standard frontmatter fields, a name that matches its folder, a
   description of 1024 characters or less whose first sentence fits Hermes's 60, string-only metadata, no links that leave the skill
   folder (it may be installed on its own), and a command named in it that exists in the kit.

What it does not prove: that the rules are followed, that the docs are correct, or that
nothing private is phrased in a way these patterns miss. A human still reviews each public change.
"""
import os
import re
import subprocess as sp
import sys

# category -> pattern. Matching is case-insensitive.
SCRUB = {
    'local path': r'/Users/[A-Za-z]|/home/[a-z][a-z0-9_-]*/|[A-Z]:\\Users\\',
    'private runtime folder': r'\.hermes\b',
    'private agent name': r'\bbobert\b|\bherbert\b',
    'private messaging channel': r'\btelegram\b|\bdiscord\b',
    'vendor product name in docs': r'\bchatgpt\b',
    'banned phrase': r'load-bearing',
    'em dash': '\u2014',
    'phone number': r'(?<![\w.-])(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]\d{3}[ .-]\d{4}(?![\w-])',
    'e-mail address': r'[A-Za-z0-9._%+-]+@(?!example\.(?:com|org|net|invalid)\b)(?!users\.noreply\.github\.com\b)'
                      r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}',
    'transport artifact': r'\[(?:output )?truncated\]|<truncated>|\b\d[\d,]* (?:bytes|lines|chars|characters|tokens) omitted\b',
}

# (path, category, why). Path-bound, not file-wide: only that file may contain that category.
ALLOW = [
    ('data/pr-outcomes.csv', 'private messaging channel',
     "titles of the upstream repo's own public PRs about its Discord bot"),
    ('tests/test_driver.py', 'transport artifact', 'fixtures that prove the driver refuses these markers'),
    ('scripts/publish/driver.py', 'transport artifact', 'the pattern the driver refuses'),
    ('scripts/check_kit.py', None, 'this file defines the patterns'),
    ('LICENSE', 'e-mail address', 'licence text'),
]

# (file, heading text, phrase). The phrase must sit under that heading (any level), outside
# comments and code, exactly once in the file's active text.
RULES = [
    ('README.md', 'Hard nevers', 'Never merge'),
    ('README.md', 'Hard nevers', 'One fix per PR'),
    ('README.md', 'Hard nevers', 'never contain a `VERDICT:` line'),
    ('docs/publishing.md', 'Hard rules', 'The loop never merges'),
    ('docs/publishing.md', 'Hard rules', 'Any approval is void after a new commit'),
    ('docs/process.md', 'Partial is never clean', 'never a clean scan'),
    ('docs/evidence-bar.md', 'Independent evidence', 'counts once'),
    ('docs/scorecard-and-test-set.md', 'Sealed answers and held-out cases', 'never in this repo'),
    ('docs/scorecard-and-test-set.md', 'What counts as evidence', 'Failures count the same as passes'),
    ('docs/roles.md', 'Enforced by tools, not by prompts', 'cannot merge'),
    ('docs/independent-review.md', 'Where the verdict lives (and where it must not)', 'Never post a `VERDICT:` line on GitHub'),
]

TEXT_EXT = {'.example', '.md', '.py', '.json', '.txt', '.csv', '.css', '.tsx', '.ts', '.js', '.yml', '.yaml', '.toml', ''}
BINARY_OK = {'.png', '.mp4', '.jpg', '.jpeg', '.gif', '.svg', '.pdf'}


def git_files(root):
    out = sp.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=root,
                 capture_output=True, text=True, check=True).stdout
    return sorted({f for f in out.split('\0') if f and os.path.lexists(os.path.join(root, f))})


def active(md):
    """Markdown with HTML comments and fenced code blocks blanked, line numbers kept."""
    md = re.sub(r'<!--.*?(?:-->|\Z)', lambda m: '\n' * m.group(0).count('\n'), md, flags=re.S)
    out, fence = [], None
    for ln in md.split('\n'):
        m = re.match(r' {0,3}(`{3,}|~{3,})', ln)
        if fence:
            if m and m.group(1)[0] == fence[0] and ln.strip() == m.group(1) and len(m.group(1)) >= len(fence):
                fence = None
            out.append('')
            continue
        if m:
            fence = m.group(1)
            out.append('')
            continue
        out.append(ln)
    return '\n'.join(out)


def slug(h):
    h = re.sub(r'[`*_]', '', h.strip().lower())
    h = re.sub(r'[^\w\- ]', '', h)
    return h.replace(' ', '-')


def headings(md):
    return [m.group(2).strip() for m in re.finditer(r'^(#{1,6})\s+(.+?)\s*#*\s*$', active(md), re.M)]


def sections(md):
    """heading -> text until the next heading of the same or higher level."""
    a = active(md).split('\n')
    hs = [(i, len(m.group(1)), m.group(2).strip()) for i, ln in enumerate(a)
          for m in [re.match(r'^(#{1,6})\s+(.+?)\s*#*\s*$', ln)] if m]
    out = {}
    for k, (i, lvl, name) in enumerate(hs):
        end = next((j for j, lv, _ in hs[k + 1:] if lv <= lvl), len(a))
        out.setdefault(name, []).append('\n'.join(a[i + 1:end]))
    return out


def allowed(path, cat):
    return any(p == path and (c is None or c == cat) for p, c, _ in ALLOW)


def check(root):
    problems = []
    files = git_files(root)
    if len(files) < 20:
        problems.append(f'only {len(files)} files found; wrong folder or not a git checkout?')
    texts = {}
    for f in files:
        full = os.path.join(root, f)
        base = os.path.basename(f)
        ext = os.path.splitext(f)[1].lower()
        if os.path.islink(full):
            problems.append(f'{f}: symlink (publish the file itself, or nothing)')
            continue
        if base == '.DS_Store' or base.startswith('._'):
            problems.append(f'{f}: macOS metadata file')
            continue
        if os.path.getsize(full) == 0:
            problems.append(f'{f}: empty file')
            continue
        for cat, pat in SCRUB.items():
            if re.search(pat, f, re.I) and not allowed(f, cat):
                problems.append(f'{f}: file name matches "{cat}"')
        if ext in BINARY_OK:
            continue
        if ext not in TEXT_EXT:
            problems.append(f'{f}: unknown file type; add it to TEXT_EXT or BINARY_OK after review')
            continue
        try:
            t = open(full, encoding='utf-8').read()
        except UnicodeDecodeError:
            problems.append(f'{f}: not UTF-8 text')
            continue
        texts[f] = t
        for cat, pat in SCRUB.items():
            if allowed(f, cat):
                continue
            for m in re.finditer(pat, t, re.I):
                problems.append(f'{f}:{t.count(chr(10), 0, m.start()) + 1}: {cat}')

    mds = {f: t for f, t in texts.items() if f.endswith('.md')}
    heads = {f: {slug(h) for h in headings(t)} for f, t in mds.items()}
    for f, t in mds.items():
        a = active(t)
        a = re.sub(r'`[^`\n]*`', '', a)
        for m in re.finditer(r'(?<!!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)|!\[[^\]\n]*\]\(([^)\s]+)\)', a):
            target = m.group(1) or m.group(2)
            if re.match(r'[a-z]+:', target) or target.startswith('mailto:'):
                continue
            line = a.count('\n', 0, m.start()) + 1
            path, _, frag = target.partition('#')
            dest = os.path.normpath(os.path.join(os.path.dirname(f), path)) if path else f
            if dest.startswith('..'):
                problems.append(f'{f}:{line}: link leaves the repo')
                continue
            if not os.path.exists(os.path.join(root, dest)):
                problems.append(f'{f}:{line}: broken link to {dest}')
            elif frag and dest.endswith('.md') and dest in heads and frag not in heads[dest]:
                problems.append(f'{f}:{line}: no heading #{frag} in {dest}')

    for f, heading, phrase in RULES:
        if f not in mds:
            problems.append(f'rule file missing: {f}')
            continue
        secs = sections(mds[f]).get(heading, [])
        if len(secs) != 1:
            problems.append(f'{f}: needs exactly one "{heading}" heading (found {len(secs)})')
            continue
        n_all = active(mds[f]).count(phrase)
        if phrase not in secs[0]:
            problems.append(f'{f}: rule "{phrase}" is not under "{heading}" (outside comments and code)')
        elif n_all != 1:
            problems.append(f'{f}: rule "{phrase}" appears {n_all} times; keep one home for it')

    problems += check_skills(root, files)

    linked = '\n'.join(mds.values())
    for f in files:
        if f.startswith('agents/') and f.endswith('.md') and os.path.basename(f) != 'README.md':
            if os.path.basename(f) not in linked.replace(f'# {os.path.basename(f)}', ''):
                problems.append(f'{f}: no page links to this agent template')
    return problems


SKILL_FIELDS = {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'}
SKILL_NAME = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')


def frontmatter(text):
    """Parse the small YAML subset skills use: top-level `key: value` and one level of
    `  key: value` under a mapping key. Returns (dict, error)."""
    if not text.startswith('---\n'):
        return None, 'must start with --- on the first line'
    end = text.find('\n---\n', 4)
    if end < 0:
        return None, 'frontmatter is not closed with ---'
    if not text[end + 5:].strip():
        return None, 'empty body'
    fm, cur = {}, None
    for line in text[4:end].split('\n'):
        if not line.strip():
            continue
        m = re.match(r'^( {2})?([A-Za-z][\w-]*):(?: (.*))?$', line)
        if not m:
            return None, f'unparsed frontmatter line: {line[:40]}'
        indent, key, val = m.groups()
        val = (val or '').strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in '"\'':
            val = val[1:-1]
        elif val and val[0] in '[{':
            return None, f'{key}: lists and inline maps are not plain strings'
        if indent:
            if cur is None:
                return None, f'{key}: indented key without a parent'
            fm[cur][key] = val
        elif val:
            fm[key], cur = val, None
        else:
            fm[key], cur = {}, key
    return fm, None


def check_skills(root, files):
    problems = []
    for f in files:
        if not (f.startswith('skills/') and f.endswith('/SKILL.md')):
            continue
        folder = f.split('/')[-2]
        with open(os.path.join(root, f), encoding='utf-8') as fh:
            text = fh.read()
        fm, err = frontmatter(text)
        if err:
            problems.append(f'{f}: {err}')
            continue
        extra = set(fm) - SKILL_FIELDS
        if extra:
            problems.append(f'{f}: fields outside the Agent Skills standard: {", ".join(sorted(extra))}')
        name, desc = fm.get('name', ''), fm.get('description', '')
        if not isinstance(name, str) or not SKILL_NAME.match(name) or len(name) > 64:
            problems.append(f'{f}: name must be lowercase letters, digits and single hyphens, 64 or less')
        elif name != folder:
            problems.append(f'{f}: name "{name}" must match its folder "{folder}"')
        first = desc.split('. ')[0].rstrip('.') + '.' if isinstance(desc, str) else ''
        if not isinstance(desc, str) or not desc or len(desc) > 1024:
            problems.append(f'{f}: description must be 1 to 1024 characters')
        elif len(first) > 60:
            problems.append(f'{f}: the description\'s first sentence must be 60 characters or less '
                            '(the Hermes index shows 60; the rest is for matching requests)')
        comp = fm.get('compatibility', '')
        if comp and (not isinstance(comp, str) or len(comp) > 500):
            problems.append(f'{f}: compatibility must be a string of 500 characters or less')
        meta = fm.get('metadata', {})
        if not isinstance(meta, dict) or any(not isinstance(v, str) or not v for v in meta.values()):
            problems.append(f'{f}: metadata must map keys to plain strings')
        body = active(text)
        for m in re.finditer(r'\]\(([^)#\s]+)', body):
            dest = m.group(1)
            if '://' in dest:
                continue
            if os.path.normpath(os.path.join(os.path.dirname(f), dest)).split(os.sep)[:2] != f.split('/')[:2]:
                problems.append(f'{f}: link {dest} leaves the skill folder; name kit paths as text')
        for script in set(re.findall(r'(scripts/[\w/]+\.py)', text)):
            if script not in files:
                problems.append(f'{f}: names {script}, which is not in the kit')
    return problems


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..'))
    problems = check(root)
    for p in problems:
        print(p)
    print(f'{len(problems)} problem(s)')
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
