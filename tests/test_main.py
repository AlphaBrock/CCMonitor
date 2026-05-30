"""
Main Entry Tests
================

Tests for root-level and package entry points.
"""
from __future__ import annotations

import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import __main__ as package_main


ROOT_MAIN_PATH = Path(__file__).resolve().parents[1] / 'main.py'


class TestRootMainEntry(unittest.TestCase):
    """Tests for the root-level debug entry point."""

    def test_root_main_delegates_to_package_main(self):
        """Root main.py delegates to the package entry main()."""
        with patch('src.__main__.main') as mock_main:
            runpy.run_path(str(ROOT_MAIN_PATH), run_name='__main__')

        mock_main.assert_called_once_with()


class TestPackageMainEntry(unittest.TestCase):
    """Tests for the package entry main flow."""

    def _fake_modules(self, ensure_result: bool, restart_requested: bool = False) -> tuple[types.ModuleType, MagicMock, MagicMock]:
        """Build the fake modules needed for entry point tests."""
        fake_webview = types.ModuleType('webview')
        fake_webview.windows = []
        fake_webview.create_window = MagicMock()
        fake_webview.start = MagicMock()

        app_instance = MagicMock()
        app_instance.restart_requested = restart_requested

        def start_side_effect(*, func):
            func()

        fake_webview.start.side_effect = start_side_effect

        fake_app_module = types.ModuleType('src.runtime.app')
        fake_app_module.CCMonitor = MagicMock(return_value=app_instance)
        fake_app_module.crash_log = MagicMock()

        fake_single_instance = types.ModuleType('src.runtime.single_instance')
        fake_single_instance.ensure_single_instance = MagicMock(return_value=ensure_result)
        fake_single_instance.release_instance_lock = MagicMock()

        return fake_webview, fake_app_module, fake_single_instance

    def test_main_returns_when_other_instance_exists(self):
        """When another instance is detected, the GUI should not start."""
        fake_webview, fake_app_module, fake_single_instance = self._fake_modules(ensure_result=False)

        with patch.dict(sys.modules, {
            'webview': fake_webview,
            'src.runtime.app': fake_app_module,
            'src.runtime.single_instance': fake_single_instance,
        }), patch('src.__main__.ctypes.windll.user32.SetProcessDpiAwarenessContext'):
            package_main.main([])

        fake_single_instance.ensure_single_instance.assert_called_once_with()
        fake_webview.create_window.assert_not_called()
        fake_webview.start.assert_not_called()

    def test_main_starts_webview_and_runs_app(self):
        """Without a duplicate instance, the keep-alive window is created and the app runs."""
        fake_webview, fake_app_module, fake_single_instance = self._fake_modules(ensure_result=True)

        with patch.dict(sys.modules, {
            'webview': fake_webview,
            'src.runtime.app': fake_app_module,
            'src.runtime.single_instance': fake_single_instance,
        }), patch('src.__main__.ctypes.windll.user32.SetProcessDpiAwarenessContext'):
            package_main.main([])

        fake_single_instance.ensure_single_instance.assert_called_once_with()
        fake_webview.create_window.assert_called_once_with('', html='', hidden=True)
        fake_webview.start.assert_called_once()
        fake_app_module.CCMonitor.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
