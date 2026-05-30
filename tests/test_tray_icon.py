"""
Tray Icon Tests
================

无第三方图像库的托盘图标渲染与主题检测测试。
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import src.ui.tray_icon as tray_icon_mod


class TestTaskbarUsesLightTheme(unittest.TestCase):
    """Tests for taskbar_uses_light_theme()."""

    @patch.object(tray_icon_mod, 'winreg')
    def test_returns_true_for_light_theme(self, mock_winreg):
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.QueryValueEx.return_value = (1, 4)

        self.assertTrue(tray_icon_mod.taskbar_uses_light_theme())

    @patch.object(tray_icon_mod, 'winreg')
    def test_returns_false_for_dark_theme(self, mock_winreg):
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock(return_value=mock_key)
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.QueryValueEx.return_value = (0, 4)

        self.assertFalse(tray_icon_mod.taskbar_uses_light_theme())

    @patch.object(tray_icon_mod, 'winreg')
    def test_returns_false_on_os_error(self, mock_winreg):
        mock_winreg.OpenKey.side_effect = OSError

        self.assertFalse(tray_icon_mod.taskbar_uses_light_theme())

    @patch.object(tray_icon_mod, 'winreg')
    def test_reads_correct_registry_path(self, mock_winreg):
        mock_winreg.OpenKey.return_value.__enter__ = MagicMock()
        mock_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_winreg.QueryValueEx.return_value = (0, 4)

        tray_icon_mod.taskbar_uses_light_theme()

        mock_winreg.OpenKey.assert_called_once_with(
            mock_winreg.HKEY_CURRENT_USER, tray_icon_mod.THEME_REG_KEY,
        )


class TestCreateIconImage(unittest.TestCase):
    """Tests for create_icon_image()."""

    def test_returns_64x64_bgra_bitmap(self):
        bitmap = tray_icon_mod.create_icon_image(0, 0)

        self.assertEqual(bitmap.size, (64, 64))
        self.assertEqual(bitmap.mode, 'BGRA')
        self.assertEqual(len(bitmap.pixels), 64 * 64 * 4)

    def test_low_high_and_full_usage_render_without_error(self):
        for top, bottom in ((30, 20), (75, 20), (100, 20)):
            bitmap = tray_icon_mod.create_icon_image(top, bottom)
            self.assertEqual(bitmap.size, (64, 64))

    def test_dark_and_light_taskbar_produce_different_bitmaps(self):
        dark = tray_icon_mod.create_icon_image(50, 50, light_taskbar=False)
        light = tray_icon_mod.create_icon_image(50, 50, light_taskbar=True)

        self.assertNotEqual(dark.tobytes(), light.tobytes())

    def test_boundary_zero_differs_from_one(self):
        zero = tray_icon_mod.create_icon_image(0, 0)
        one = tray_icon_mod.create_icon_image(1, 0)

        self.assertNotEqual(zero.tobytes(), one.tobytes())

    def test_text_uses_antialiased_alpha_levels(self):
        bitmap = tray_icon_mod.create_icon_image(0, 0)
        alpha_values = {
            bitmap.rgba_at(x, y)[3]
            for y in range(0, 43)
            for x in range(64)
        }

        self.assertTrue(any(0 < alpha < 255 for alpha in alpha_values))

    def test_full_bar_fill_at_100_percent(self):
        full = tray_icon_mod.create_icon_image(100, 100)
        zero = tray_icon_mod.create_icon_image(0, 0)

        self.assertNotEqual(full.tobytes(), zero.tobytes())
        self.assertEqual(full.rgba_at(63, 59)[3], 255)

    def test_extra_usage_dollar_and_blocked_cross_differ(self):
        blocked = tray_icon_mod.create_icon_image(100, 20, extra_usage_available=False)
        paid = tray_icon_mod.create_icon_image(100, 20, extra_usage_available=True)

        self.assertNotEqual(blocked.tobytes(), paid.tobytes())


class TestCreateIconImageOverageMode(unittest.TestCase):
    """Tests for create_icon_image() overage-mode bars."""

    def test_overage_mode_returns_64x64_bgra(self):
        bitmap = tray_icon_mod.create_icon_image(80, 80, mode_top='overage', mode_bottom='overage', time_pct_top=60, time_pct_bottom=60)

        self.assertEqual(bitmap.size, (64, 64))
        self.assertEqual(bitmap.mode, 'BGRA')

    def test_overage_mode_time_pct_at_100_falls_back_to_utilization(self):
        fallback = tray_icon_mod.create_icon_image(50, 50, mode_top='overage', mode_bottom='overage', time_pct_top=100, time_pct_bottom=100)
        utilization = tray_icon_mod.create_icon_image(50, 50)

        self.assertEqual(fallback.tobytes(), utilization.tobytes())

    def test_on_pace_produces_empty_bar(self):
        bitmap = tray_icon_mod.create_icon_image(60, 60, mode_top='overage', mode_bottom='overage', time_pct_top=60, time_pct_bottom=60)

        for y in (47, 59):
            self.assertNotEqual(bitmap.rgba_at(0, y)[3], 255)

    def test_below_pace_produces_empty_bar(self):
        bitmap = tray_icon_mod.create_icon_image(40, 40, mode_top='overage', mode_bottom='overage', time_pct_top=60, time_pct_bottom=60)

        for y in (47, 59):
            self.assertNotEqual(bitmap.rgba_at(0, y)[3], 255)

    def test_half_fill_at_midpoint_of_over_budget_range(self):
        bitmap = tray_icon_mod.create_icon_image(80, 80, mode_top='overage', mode_bottom='overage', time_pct_top=60, time_pct_bottom=60)

        for y in (47, 59):
            self.assertEqual(bitmap.rgba_at(31, y)[3], 255)
            self.assertNotEqual(bitmap.rgba_at(32, y)[3], 255)

    def test_full_bar_at_100_percent_usage(self):
        bitmap = tray_icon_mod.create_icon_image(100, 100, mode_top='overage', mode_bottom='overage', time_pct_top=60, time_pct_bottom=60)

        for y in (47, 59):
            self.assertEqual(bitmap.rgba_at(63, y)[3], 255)

    def test_mixed_modes_top_overage_bottom_utilization(self):
        bitmap = tray_icon_mod.create_icon_image(80, 50, mode_top='overage', mode_bottom='utilization', time_pct_top=60)

        self.assertEqual(bitmap.size, (64, 64))


class TestCreateStatusImage(unittest.TestCase):
    """Tests for create_status_image()."""

    def test_returns_64x64_bgra_bitmap(self):
        bitmap = tray_icon_mod.create_status_image('!')

        self.assertEqual(bitmap.size, (64, 64))
        self.assertEqual(bitmap.mode, 'BGRA')
        self.assertEqual(len(bitmap.pixels), 64 * 64 * 4)

    def test_light_taskbar_variant(self):
        dark = tray_icon_mod.create_status_image('!', light_taskbar=False)
        light = tray_icon_mod.create_status_image('!', light_taskbar=True)

        self.assertNotEqual(dark.tobytes(), light.tobytes())

    def test_auth_error_text_differs_from_generic_error(self):
        generic = tray_icon_mod.create_status_image('!')
        auth = tray_icon_mod.create_status_image('C!')

        self.assertNotEqual(generic.tobytes(), auth.tobytes())


if __name__ == '__main__':
    unittest.main()
