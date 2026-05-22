"""
Popup Tests
============

Tests for the desktop popup window and frontend data shaping.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.presentation.i18n import T
from src.runtime.cache import CacheSnapshot
from src.ui.popup import UsagePopup, build_text_bar, init_config, snapshot_to_dict, tone_for_percent, usage_entries


def _snap(
    usage: dict | None = None,
    profile: dict | None = None,
    last_success_time: float | None = None,
    refreshing: bool = False,
    last_error: str | None = None,
    version: int = 1,
) -> CacheSnapshot:
    return CacheSnapshot(
        usage=usage or {},
        profile=profile,
        last_success_time=last_success_time,
        refreshing=refreshing,
        last_error=last_error,
        version=version,
    )


class _FakeEvent:
    def __init__(self) -> None:
        self._handlers = []

    def __iadd__(self, handler):
        self._handlers.append(handler)
        return self

    def fire(self) -> None:
        for handler in list(self._handlers):
            handler()


class _FakeWindow:
    def __init__(self) -> None:
        self.events = SimpleNamespace(loaded=_FakeEvent(), closed=_FakeEvent())
        self.native = SimpleNamespace(Handle=SimpleNamespace(ToInt32=lambda: 1234))
        self.on_top = False
        self.show_calls = 0
        self.hide_calls = 0
        self.restore_calls = 0
        self.destroy_calls = 0
        self.resize_calls: list[tuple[int, int]] = []
        self.move_calls: list[tuple[int, int]] = []
        self.js_calls: list[str] = []

    def show(self) -> None:
        self.show_calls += 1

    def hide(self) -> None:
        self.hide_calls += 1

    def restore(self) -> None:
        self.restore_calls += 1

    def destroy(self) -> None:
        self.destroy_calls += 1

    def resize(self, width: int, height: int) -> None:
        self.resize_calls.append((width, height))

    def move(self, x: int, y: int) -> None:
        self.move_calls.append((x, y))

    def evaluate_js(self, script: str) -> None:
        self.js_calls.append(script)


class TestUsageEntries(unittest.TestCase):
    def test_only_five_hour_and_seven_day_are_returned(self):
        usage = {
            'five_hour': {'utilization': 42, 'resets_at': '2026-01-01T00:00:00Z'},
            'seven_day': {'utilization': 10, 'resets_at': '2026-01-07T00:00:00Z'},
            'seven_day_sonnet': {'utilization': 90, 'resets_at': '2026-01-07T00:00:00Z'},
        }

        self.assertEqual(usage_entries(usage), [
            ('five_hour', usage['five_hour']),
            ('seven_day', usage['seven_day']),
        ])

    def test_missing_or_null_entries_are_skipped(self):
        usage = {
            'five_hour': None,
            'seven_day': {'utilization': None, 'resets_at': '2026-01-07T00:00:00Z'},
        }

        self.assertEqual(usage_entries(usage), [])


class TestPopupFormatting(unittest.TestCase):
    def test_tone_boundaries(self):
        self.assertEqual(tone_for_percent(0), 'normal')
        self.assertEqual(tone_for_percent(49), 'normal')
        self.assertEqual(tone_for_percent(50), 'mid')
        self.assertEqual(tone_for_percent(79), 'mid')
        self.assertEqual(tone_for_percent(80), 'warn')
        self.assertEqual(tone_for_percent(99), 'warn')
        self.assertEqual(tone_for_percent(100), 'danger')

    def test_text_bar_uses_fixed_length(self):
        self.assertEqual(build_text_bar(0), '░' * 20)
        self.assertEqual(build_text_bar(50), '█' * 10 + '░' * 10)
        self.assertEqual(build_text_bar(100), '█' * 20)
        self.assertEqual(build_text_bar(150), '█' * 20)


class TestSnapshotToDict(unittest.TestCase):
    def test_usage_rows_are_fixed_to_two_fields(self):
        usage = {
            'five_hour': {'utilization': 42, 'resets_at': '2026-01-01T05:00:00Z'},
            'seven_day': {'utilization': 78, 'resets_at': '2026-01-07T00:00:00Z'},
            'seven_day_opus': {'utilization': 91, 'resets_at': '2026-01-07T00:00:00Z'},
        }

        result = snapshot_to_dict(_snap(usage=usage))

        self.assertEqual([row['field'] for row in result['usage']], ['five_hour', 'seven_day'])
        self.assertNotIn('installations', result)

    def test_usage_row_contains_text_bar_and_tone(self):
        usage = {'five_hour': {'utilization': 84, 'resets_at': '2027-01-01T05:00:00+00:00'}}

        result = snapshot_to_dict(_snap(usage=usage))
        row = result['usage'][0]

        self.assertEqual(row['pct_text'], '84%')
        self.assertEqual(row['tone'], 'warn')
        self.assertEqual(row['bar_text'], build_text_bar(84))
        self.assertNotEqual(row['reset_text'], '')

    def test_extra_usage_uses_same_text_bar_shape(self):
        usage = {
            'extra_usage': {
                'is_enabled': True,
                'monthly_limit': 20.0,
                'used_credits': 11.0,
            },
        }

        result = snapshot_to_dict(_snap(usage=usage))

        self.assertEqual(result['extra']['pct_text'], '55%')
        self.assertEqual(result['extra']['tone'], 'mid')
        self.assertEqual(result['extra']['bar_text'], build_text_bar(55))

    def test_status_is_refreshing_without_usage_or_error(self):
        result = snapshot_to_dict(_snap())
        self.assertEqual(result['status']['text'], T['status_refreshing'])
        self.assertFalse(result['status']['is_error'])

    def test_status_uses_error_text_when_present(self):
        result = snapshot_to_dict(_snap(last_error='offline'))
        self.assertEqual(result['status']['text'], 'offline')
        self.assertTrue(result['status']['is_error'])

    def test_profile_is_extracted(self):
        profile = {
            'account': {'email': 'user@example.com'},
            'organization': {'organization_type': 'pro_team'},
        }

        result = snapshot_to_dict(_snap(profile=profile))

        self.assertEqual(result['profile']['email'], 'user@example.com')
        self.assertEqual(result['profile']['plan'], 'Pro Team')


class TestInitConfig(unittest.TestCase):
    def testinit_config_contains_four_bar_colors(self):
        config = init_config(_snap(), pinned=True)

        self.assertTrue(config['window']['pinned'])
        self.assertIn('bar_fg', config['colors'])
        self.assertIn('bar_fg_mid', config['colors'])
        self.assertIn('bar_fg_warn', config['colors'])
        self.assertIn('bar_fg_danger', config['colors'])
        self.assertNotIn('claude_code', config['t'])


class TestUsagePopupWindow(unittest.TestCase):
    def setUp(self):
        self.fake_window = _FakeWindow()
        self.fake_windll = SimpleNamespace(user32=MagicMock(), dwmapi=MagicMock())
        self.fake_windll.user32.GetWindowLongW.return_value = 0
        self.fake_windll.user32.GetDpiForWindow.return_value = 96
        self.fake_windll.user32.GetDpiForSystem.return_value = 96
        self.fake_windll.user32.FindWindowW.return_value = 88
        self.fake_windll.user32.MonitorFromWindow.return_value = 99

        self.app = SimpleNamespace(
            cache=SimpleNamespace(snapshot=_snap(version=1)),
            _next_poll_time=None,
        )

        self.create_patch = patch('src.ui.popup.webview.create_window', return_value=self.fake_window)
        self.windll_patch = patch('src.ui.popup.ctypes.windll', self.fake_windll)
        self.create_patch.start()
        self.windll_patch.start()
        self.popup = UsagePopup(self.app)
        self.popup._popup_hwnd = 1234

    def tearDown(self):
        self.windll_patch.stop()
        self.create_patch.stop()

    def test_popup_starts_pending_show(self):
        self.assertTrue(self.popup._pending_show)

    def test_show_restores_visible_window_after_layout(self):
        self.popup._layout_ready = True
        self.popup.show()

        self.assertEqual(self.fake_window.show_calls, 1)
        self.assertEqual(self.fake_window.restore_calls, 1)
        self.assertTrue(self.popup._visible)

    def test_hide_keeps_window_instance_and_does_not_destroy(self):
        self.popup._layout_ready = True
        self.popup.hide()

        self.assertEqual(self.fake_window.hide_calls, 1)
        self.assertEqual(self.fake_window.destroy_calls, 0)
        self.assertFalse(self.popup._visible)

    def test_toggle_pin_updates_on_top_state(self):
        self.popup._layout_ready = True

        pinned = self.popup.toggle_pin()

        self.assertTrue(pinned)
        self.fake_windll.user32.SetWindowPos.assert_called_once()
        self.assertEqual(self.fake_windll.user32.SetWindowPos.call_args.args[1], -1)

    def test_initial_position_uses_top_right_corner(self):
        def fill_monitor_info(_monitor, monitor_info_ptr):
            monitor_info = monitor_info_ptr._obj
            monitor_info.rcMonitor.left = 0
            monitor_info.rcMonitor.top = 0
            monitor_info.rcMonitor.right = 1920
            monitor_info.rcMonitor.bottom = 1080
            monitor_info.rcWork.left = 0
            monitor_info.rcWork.top = 0
            monitor_info.rcWork.right = 1920
            monitor_info.rcWork.bottom = 1040
            return 1

        self.fake_windll.user32.GetMonitorInfoW.side_effect = fill_monitor_info

        x, y = self.popup._tray_position(380, 320)

        self.assertEqual((x, y), (1528, 12))

    def test_report_height_triggers_first_layout(self):
        with patch.object(self.popup, '_resize_and_position') as mock_resize, \
             patch.object(self.popup, '_reveal_after_layout') as mock_reveal:
            self.popup.report_height(280)

        mock_resize.assert_called_once_with(280)
        mock_reveal.assert_called_once_with()

    def test_close_destroys_window(self):
        self.popup.close()

        self.assertEqual(self.fake_window.destroy_calls, 1)
        self.assertFalse(self.popup._running)


if __name__ == '__main__':
    unittest.main()
