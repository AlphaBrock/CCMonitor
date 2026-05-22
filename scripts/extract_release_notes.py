"""
Extract Release Notes
======================

Extract the changelog section for a given version from CHANGELOG.md.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_SECTION_PATTERN = r'^## \[{version}\] - \d{{4}}-\d{{2}}-\d{{2}}\s*$'
_VERSION_PATTERN = re.compile(r'^\d+\.\d+\.\d+$')


def extract_release_notes(changelog_text: str, version: str) -> str:
    """Extract the changelog section content for a given version."""
    if not _VERSION_PATTERN.fullmatch(version):
        raise ValueError(f'Invalid version tag: {version}')

    lines = changelog_text.splitlines()
    header = re.compile(_SECTION_PATTERN.format(version=re.escape(version)))
    start = None

    for index, line in enumerate(lines):
        if header.match(line):
            start = index + 1
            break

    if start is None:
        raise ValueError(f'Version {version} not found in CHANGELOG.md')

    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith('## ['):
            end = index
            break

    notes = '\n'.join(lines[start:end]).strip()
    if not notes:
        raise ValueError(f'No release notes found for version {version}')

    return notes + '\n'


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 2:
        print('Usage: python scripts/extract_release_notes.py CHANGELOG.md X.Y.Z', file=sys.stderr)
        return 1

    changelog_path = Path(arguments[0])
    version = arguments[1]

    try:
        changelog_text = changelog_path.read_text(encoding='utf-8')
        sys.stdout.write(extract_release_notes(changelog_text, version))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
