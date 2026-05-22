"""
Release Notes Script Tests
==========================

CHANGELOG 发布说明提取脚本的单元测试。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.extract_release_notes import extract_release_notes, main


CHANGELOG_SAMPLE = """# Changelog

## [Unreleased]

## [1.2.3] - 2026-05-22

### Added

- First line
- Second line
- 中文说明

### Changed

- Third line

## [1.2.2] - 2026-05-01

### Fixed

- Older release
"""


class TestExtractReleaseNotes(unittest.TestCase):
    def test_extracts_requested_version_block(self):
        result = extract_release_notes(CHANGELOG_SAMPLE, '1.2.3')

        self.assertIn('### Added', result)
        self.assertIn('- First line', result)
        self.assertIn('### Changed', result)
        self.assertNotIn('1.2.2', result)

    def test_rejects_missing_version(self):
        with self.assertRaisesRegex(ValueError, 'not found'):
            extract_release_notes(CHANGELOG_SAMPLE, '9.9.9')

    def test_rejects_invalid_tag_format(self):
        with self.assertRaisesRegex(ValueError, 'Invalid version tag'):
            extract_release_notes(CHANGELOG_SAMPLE, 'v1.2.3')

    def test_main_writes_utf8_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            changelog_path = Path(temp_dir) / 'CHANGELOG.md'
            output_path = Path(temp_dir) / 'release_notes.md'
            changelog_path.write_text(CHANGELOG_SAMPLE, encoding='utf-8')

            exit_code = main([str(changelog_path), '1.2.3', str(output_path)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(output_path.read_text(encoding='utf-8'), extract_release_notes(CHANGELOG_SAMPLE, '1.2.3'))
            self.assertIn('中文说明', output_path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
