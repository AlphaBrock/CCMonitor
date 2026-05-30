"""
Tray provider selector
=======================

Tests for the tray provider display selector: the ``tray_provider`` setting
and its persistence, the multi-provider tooltip formatter, the Opus 4.8
pricing fix, and the app-level provider menu handler / icon source selection.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.integrations.local_usage import _CLAUDE_PRICING, _claude_cost
from src.presentation import settings
from src.presentation.formatting import format_dashboard_tooltip, provider_label
from src.runtime.app import CCMonitor


def _make_render_app() -> CCMonitor:
    """Create an app instance with ``__init__`` stubbed for unit testing."""
    with patch.object(CCMonitor, '__init__', lambda self: None):
        return CCMonitor()


class TestProviderLabel(unittest.TestCase):

    def test_known_providers(self):
        self.assertEqual(provider_label('claude'), 'Claude')
        self.assertEqual(provider_label('codex'), 'Codex')

    def test_unknown_provider_title_cased(self):
        self.assertEqual(provider_label('gemini'), 'Gemini')


class TestDashboardTooltip(unittest.TestCase):

    def setUp(self):
        self.responses = {
            'claude': {
                'five_hour': {'utilization': 12, 'resets_at': ''},
                'seven_day': {'utilization': 45, 'resets_at': ''},
            },
            'codex': {
                'five_hour': {'utilization': 8, 'resets_at': ''},
            },
        }

    def test_auto_lists_all_providers(self):
        lines = format_dashboard_tooltip(self.responses, 'auto').split('\n')
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith('Codex'))
        self.assertIn('5h 8%', lines[0])
        self.assertTrue(lines[1].startswith('Claude'))
        self.assertIn('5h 12%', lines[1])
        self.assertIn('7d 45%', lines[1])

    def test_selected_provider_only(self):
        text = format_dashboard_tooltip(self.responses, 'codex')
        self.assertNotIn('Claude', text)
        self.assertIn('Codex', text)

    def test_compact_no_reset_and_within_windows_limit(self):
        text = format_dashboard_tooltip(self.responses, 'auto')
        self.assertNotIn('Resets', text)
        self.assertLessEqual(len(text), 127)

    def test_error_provider_shows_message(self):
        text = format_dashboard_tooltip({'codex': {'error': 'No Codex OAuth token.'}}, 'auto')
        self.assertIn('Codex', text)
        self.assertIn('No Codex OAuth token', text)

    def test_missing_provider_skipped(self):
        text = format_dashboard_tooltip(self.responses, 'auto')
        # Only providers present in the dict appear; an absent one is skipped.
        self.assertEqual(len(text.split('\n')), 2)

    def test_empty_falls_back_to_non_empty_title(self):
        self.assertTrue(format_dashboard_tooltip({}, 'auto'))


class TestOpus48Pricing(unittest.TestCase):

    def test_opus_4_8_is_priced(self):
        self.assertIn('claude-opus-4-8', _CLAUDE_PRICING)

    def test_opus_4_8_cost_is_computed(self):
        # 1M input * 5e-6 + 1M output * 2.5e-5 = 5 + 25 = 30
        cost = _claude_cost('claude-opus-4-8', 1_000_000, 0, 0, 1_000_000)
        self.assertIsNotNone(cost)
        self.assertAlmostEqual(cost, 30.0, places=6)


class TestTrayProviderSetting(unittest.TestCase):

    def test_valid_values(self):
        self.assertEqual(settings._VALID_TRAY_PROVIDERS, frozenset({'auto', 'claude', 'codex'}))

    def test_validate_accepts_auto(self):
        data = settings._validate({'tray_provider': 'auto'}, Path('settings.json'))
        self.assertEqual(data['tray_provider'], 'auto')

    def test_validate_drops_unknown(self):
        with patch('src.presentation.settings.ctypes') as mock_ctypes:
            data = settings._validate({'tray_provider': 'bogus'}, Path('settings.json'))
            self.assertNotIn('tray_provider', data)
            mock_ctypes.windll.user32.MessageBoxW.assert_called()

    def test_save_tray_provider_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / settings.SETTINGS_FILENAME
            with patch.object(settings, '_SETTINGS_PATH', target):
                settings.save_tray_provider('codex')
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['tray_provider'], 'codex')

    def test_save_tray_provider_preserves_other_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / settings.SETTINGS_FILENAME
            target.write_text(json.dumps({'language': 'zh-CN'}), encoding='utf-8')
            with patch.object(settings, '_SETTINGS_PATH', target):
                settings.save_tray_provider('claude')
            saved = json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(saved['tray_provider'], 'claude')
            self.assertEqual(saved['language'], 'zh-CN')


class TestProviderMenuHandler(unittest.TestCase):

    def test_handler_updates_persists_and_rerenders(self):
        app = _make_render_app()
        app._tray_provider = 'auto'
        app._render_tray = MagicMock()
        with patch('src.runtime.app.save_tray_provider') as mock_save:
            app._make_provider_handler('codex')()
        self.assertEqual(app._tray_provider, 'codex')
        mock_save.assert_called_once_with('codex')
        app._render_tray.assert_called_once()

    def test_set_tray_provider_syncs_open_popup(self):
        app = _make_render_app()
        app._tray_provider = 'auto'
        app._render_tray = MagicMock()
        app.popup = MagicMock()

        with patch('src.runtime.app.save_tray_provider') as mock_save:
            result = app.set_tray_provider('claude')

        self.assertEqual(result, 'claude')
        self.assertEqual(app.provider_view, 'claude')
        mock_save.assert_called_once_with('claude')
        app._render_tray.assert_called_once()
        app.popup.sync_provider_view.assert_called_once()

    def test_set_provider_view_maps_all_to_auto(self):
        app = _make_render_app()
        app._tray_provider = 'codex'
        app._render_tray = MagicMock()
        app.popup = None

        with patch('src.runtime.app.save_tray_provider') as mock_save:
            result = app.set_tray_provider_from_view('all')

        self.assertEqual(result, 'all')
        self.assertEqual(app._tray_provider, 'auto')
        mock_save.assert_called_once_with('auto')
        app._render_tray.assert_called_once()

    def test_invalid_provider_view_does_not_persist(self):
        app = _make_render_app()
        app._tray_provider = 'claude'
        app._render_tray = MagicMock()
        app.popup = MagicMock()

        with patch('src.runtime.app.save_tray_provider') as mock_save:
            result = app.set_tray_provider_from_view('bad')

        self.assertEqual(result, 'claude')
        self.assertEqual(app._tray_provider, 'claude')
        mock_save.assert_not_called()
        app._render_tray.assert_not_called()
        app.popup.sync_provider_view.assert_not_called()


class TestIconResponseSelection(unittest.TestCase):

    def setUp(self):
        self.app = _make_render_app()
        self.app._last_response = {'five_hour': {'utilization': 1}}
        self.app._last_responses = {'codex': {'five_hour': {'utilization': 99}}}

    def test_auto_icon_uses_primary_response(self):
        self.app._tray_provider = 'auto'
        self.assertEqual(self.app._icon_response(), self.app._last_response)

    def test_selected_uses_that_provider(self):
        self.app._tray_provider = 'codex'
        self.assertEqual(self.app._icon_response(), self.app._last_responses['codex'])

    def test_selected_missing_returns_empty(self):
        self.app._tray_provider = 'claude'  # not in _last_responses
        self.assertEqual(self.app._icon_response(), {})


if __name__ == '__main__':
    unittest.main()
