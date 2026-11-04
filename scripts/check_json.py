#!/usr/bin/env python3
"""Check a JSON file against one of the kit's schemas.

    python3 scripts/check_json.py FILE SCHEMA

SCHEMA is a path, or a name in templates/ (verdict, finding, candidate, decision,
review-verdict). Exit 0 = valid, 1 = invalid (errors printed), 2 = could not check.

Needs the jsonschema package. If this Python lacks it and `uvx` is on PATH, the check reruns
itself under uvx with jsonschema; otherwise it fails loudly rather than passing. A role that
cannot check its output must say so, never assume it is valid.
"""
import json
import os
import shutil
import subprocess as sp
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def schema_path(s):
    if os.path.exists(s):
        return s
    p = os.path.join(ROOT, 'templates', s if s.endswith('.json') else s + '.schema.json')
    if not os.path.exists(p):
        sys.exit(f'check_json: no schema {s!r}')
    return p


def errors(doc, schema):
    import jsonschema
    v = jsonschema.validators.validator_for(schema)(schema)
    return sorted((list(e.absolute_path), e.message) for e in v.iter_errors(doc))


def main(argv):
    no_uvx = argv[:1] == ['--no-uvx']
    argv = argv[1:] if no_uvx else argv
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        uvx = shutil.which('uvx')
        if not uvx or no_uvx:
            print('check_json: jsonschema is not installed and uvx is not on PATH: could not check',
                  file=sys.stderr)
            return 2
        return sp.call([uvx, '-q', '--with', 'jsonschema', 'python', '-I', os.path.abspath(__file__), '--no-uvx']
                       + [os.path.abspath(a) if os.path.exists(a) else a for a in argv])
    path, s = argv
    try:
        with open(path) as f:
            doc = json.load(f)
        with open(schema_path(s)) as f:
            schema = json.load(f)
    except (OSError, ValueError) as e:
        print(f'check_json: {e}', file=sys.stderr)
        return 1
    errs = errors(doc, schema)
    for where, msg in errs:
        print(f'{path}: {"/".join(map(str, where)) or "(top)"}: {msg}')
    print(f'{path}: {"valid" if not errs else f"{len(errs)} error(s)"}')
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
