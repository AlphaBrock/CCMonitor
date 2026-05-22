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


def write_release_notes(changelog_path: Path, version: str, output_path: Path | None = None) -> str:
    """Extract release notes and optionally write them to a UTF-8 file.

    Parameters
    ----------
    changelog_path : Path
        Path to the changelog file.
    version : str
        Release version without the ``v`` prefix.
    output_path : Path | None, default: None
        Optional destination file path. When provided, the extracted notes
        are written using UTF-8 encoding.

    Returns
    -------
    str
        Extracted release notes content.
    """
    changelog_text = changelog_path.read_text(encoding='utf-8')
    notes = extract_release_notes(changelog_text, version)
    if output_path is not None:
        output_path.write_text(notes, encoding='utf-8')
    return notes


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) not in (2, 3):
        print('Usage: python scripts/extract_release_notes.py CHANGELOG.md X.Y.Z [OUTPUT.md]', file=sys.stderr)
        return 1

    changelog_path = Path(arguments[0])
    version = arguments[1]
    output_path = Path(arguments[2]) if len(arguments) == 3 else None

    try:
        notes = write_release_notes(changelog_path, version, output_path)
        if output_path is None:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stdout.write(notes)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
