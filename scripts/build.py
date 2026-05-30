"""
Build Script
=============

Builds a standalone EXE for CCMonitor using PyInstaller.

Usage:
    python scripts/build.py

Produces:
    dist/CCMonitor.exe
"""
from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
SPEC = ROOT / 'packaging' / 'ccmonitor.spec'
ARCHIVE_ENTRY_LIMIT = 12
MAX_EXE_SIZE_MIB = 10.5
TRACKED_PACKAGES = (
    'pyinstaller',
    'pyinstaller-hooks-contrib',
    'pywebview',
    'pythonnet',
    'clr_loader',
    'requests',
    'urllib3',
    'certifi',
    'charset-normalizer',
    'cffi',
)


def build() -> None:
    """Run PyInstaller to produce the standalone EXE."""
    print_build_environment()
    print('Starting PyInstaller build ...')
    cmd = [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', str(SPEC)]
    subprocess.check_call(cmd, cwd=str(ROOT))

    exe = DIST / 'CCMonitor.exe'
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f'\nBuild successful!  {exe}  ({size_mb:.1f} MB)')
        print_archive_summary(exe)
        enforce_size_limit(size_mb)
    else:
        print('\nBuild failed - EXE not found.')
        sys.exit(1)


def print_build_environment() -> None:
    """Print the build environment versions that affect PyInstaller output."""
    print(f'Python: {sys.version.split()[0]} ({sys.executable})')
    for package_name in TRACKED_PACKAGES:
        try:
            version = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            version = 'not installed'
        print(f'{package_name}: {version}')
    print()


def print_archive_summary(exe: Path) -> None:
    """Print the largest compressed entries inside the one-file PyInstaller archive."""
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(exe))
    entries = []
    for name, entry in reader.toc.items():
        _position, compressed_length, uncompressed_length, _is_compressed, typecode = entry
        entries.append((compressed_length, uncompressed_length, typecode, name))

    total_compressed = sum(entry[0] for entry in entries)
    total_uncompressed = sum(entry[1] for entry in entries)
    print(f'Archive payload: {format_bytes(total_compressed)} compressed, {format_bytes(total_uncompressed)} uncompressed')
    print(f'Largest archive entries (top {ARCHIVE_ENTRY_LIMIT}):')
    for compressed_length, uncompressed_length, typecode, name in sorted(entries, reverse=True)[:ARCHIVE_ENTRY_LIMIT]:
        print(f'  {format_bytes(compressed_length):>9} compressed  {format_bytes(uncompressed_length):>9} uncompressed  {typecode}  {name}')


def enforce_size_limit(size_mb: float) -> None:
    """Fail release builds when dependency drift produces an oversized EXE."""
    if size_mb <= MAX_EXE_SIZE_MIB:
        return

    print(f'\nBuild failed - EXE is {size_mb:.1f} MiB, above the {MAX_EXE_SIZE_MIB:.1f} MiB size limit.')
    print('Check the archive summary above for newly bundled dependencies or runtime files.')
    sys.exit(1)


def format_bytes(size: int) -> str:
    """Format byte counts as MiB for build diagnostics."""
    return f'{size / (1024 * 1024):.2f} MiB'


if __name__ == '__main__':
    build()
