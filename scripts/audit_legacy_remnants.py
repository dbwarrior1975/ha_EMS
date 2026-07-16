#!/usr/bin/env python3
"""Report legacy/refactor-remnant terms outside known migration contexts.

By default this is a report-only DEV audit. Use --strict to return non-zero when
non-allowlisted hits are found.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

TERMS = (
    'v3_battery_device_id',
    'ev_policies_by_id',
    'policy_source',
    'ev_policy_mode',
    'relay1_active',
    'relay2_active',
    'adjustable_active',
    'legacy_device_bridge',
    'ems_adjustable_primary_load',
    'ems_adjustable_surplus_load_priority',
)

PATTERNS = (
    ('primary_load_field', re.compile(r'(^|[^A-Za-z0-9_])(primary_load)(\s*=|\s*:|\))')),
    ('plan_primary_load_attr', re.compile(r'\.primary_load\b')),
)

ALLOWLIST_PARTS = (
    'docs/dev/legacy_removed_fields.md',
    'scripts/audit_legacy_remnants.py',
    'CHANGELOG.md',
    'tests/contract/test_removed_fields',
    'tests/unit/test_config_loader.py',
    'tests/unit/test_direct_runtime.py',
    'tests/e2e_entity/scenario_runner.py',
    'tests/unit/test_engine.py',
)

SKIP_DIRS = {'.git', '.pytest_cache', '__pycache__'}
TEXT_SUFFIXES = {'.py', '.yaml', '.yml', '.md', '.txt', '.jinja', '.j2'}


def is_allowlisted(path: Path) -> bool:
    rel = str(path).replace('\\', '/')
    return any(part in rel for part in ALLOWLIST_PARTS)


def iter_files(root: Path):
    for path in root.rglob('*'):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict', action='store_true')
    parser.add_argument('root', nargs='?', default='.')
    args = parser.parse_args()

    root = Path(args.root).resolve()
    hits = []
    for path in iter_files(root):
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(root)
        for lineno, line in enumerate(text.splitlines(), 1):
            for term in TERMS:
                if term in line and not is_allowlisted(rel):
                    hits.append((str(rel), lineno, term, line.strip()))
            for name, pattern in PATTERNS:
                if pattern.search(line) and not is_allowlisted(rel):
                    hits.append((str(rel), lineno, name, line.strip()))

    if hits:
        print('Legacy/refactor-remnant audit hits:')
        for rel, lineno, term, line in hits:
            print(f'{rel}:{lineno}: {term}: {line}')
    else:
        print('No non-allowlisted legacy/refactor-remnant hits found.')
    return 1 if args.strict and hits else 0


if __name__ == '__main__':
    raise SystemExit(main())
