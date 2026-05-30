"""
Win Tray Tests
===============

Windows 原生托盘适配器单元测试。
"""
from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.ui import tray_icon as tray_icon_mod
from src.ui import win_tray
from src.ui.tray_icon import TrayIconBitmap


def _fake_windll() -> SimpleNamespace:
    user32 = MagicMock()
    shell32 = MagicMock()
    gdi32 = MagicMock()
    kernel32 = MagicMock()
    user32.RegisterWindowMessageW.return_value = 9001
    user32.CreateWindowExW.return_value = 100
    user32.GetMessageW.return_value = 0
    user32.TrackPopupMenu.return_value = 1000
    user32.CreatePopupMenu.return_value = 200
    kernel32.GetModuleHandleW.return_value = 300
    shell32.Shell_NotifyIconW.return_value = True
    return SimpleNamespace(user32=user32, shell32=shell32, gdi32=gdi32, kernel32=kernel32)


def _bitmap() -> TrayIconBitmap:
    return TrayIconBitmap(64, 64, bytes(64 * 64 * 4))


class TestMenuModel(unittest.TestCase):
    def test_submenu_action_is_detected(self):
        submenu = win_tray.Menu(win_tray.MenuItem('Child'))
        item = win_tray.MenuItem('Parent', submenu)

        self.assertIs(item.submenu, submenu)
        self.assertIsNone(item.action)

    def test_separator_is_exported_on_menu_and_module(self):
        self.assertIs(win_tray.Menu.SEPARATOR, win_tray.SEPARATOR)

    def test_default_action_is_invoked(self):
        action = MagicMock()
        icon = SimpleNamespace()
        item = win_tray.MenuItem('Show', action, default=True)

        win_tray._invoke_action(icon, item)

        action.assert_called_once_with(icon, item)

    def test_dynamic_menu_state_is_evaluated(self):
        item = win_tray.MenuItem(
            'State',
            checked=lambda menu_item: True,
            radio=lambda menu_item: True,
            enabled=lambda menu_item: False,
            visible=lambda menu_item: True,
        )

        self.assertTrue(win_tray._visible(item))
        self.assertFalse(win_tray._enabled(item))
        self.assertTrue(win_tray._checked(item))
        self.assertTrue(win_tray._radio(item))


class TestNativeIcon(unittest.TestCase):
    def setUp(self):
        self.fake = _fake_windll()
        self.patch = patch('src.ui.win_tray.ctypes.windll', self.fake)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_visible_adds_and_deletes_shell_icon(self):
        icon = win_tray.Icon('test', icon=_bitmap(), title='loading')
        icon._hwnd = 100

        with patch('src.ui.win_tray._create_hicon', return_value=500):
            icon.visible = True
            icon.visible = False

        self.assertGreaterEqual(self.fake.shell32.Shell_NotifyIconW.call_count, 3)

    def test_create_window_uses_pointer_sized_hinstance_argtype(self):
        icon = win_tray.Icon('test', icon=_bitmap(), title='loading')

        self.assertIs(self.fake.user32.CreateWindowExW.argtypes[10], win_tray.HINSTANCE)

        large_instance = 0x00007FF600000000
        self.fake.kernel32.GetModuleHandleW.return_value = large_instance
        icon._create_window()

        self.assertEqual(self.fake.user32.CreateWindowExW.call_args[0][10], large_instance)

    def test_dibsection_argtype_tolerates_tray_icon_configuration(self):
        tray_icon_mod._configure_gdi_text_api()
        win_tray._configure_win32_api()

        self.assertIs(self.fake.gdi32.CreateDIBSection.argtypes[1], ctypes.c_void_p)

    def test_title_update_modifies_tooltip(self):
        icon = win_tray.Icon('test', icon=_bitmap(), title='old')
        icon._hwnd = 100
        icon._visible = True

        icon.title = 'new tooltip'

        code, data_ref = self.fake.shell32.Shell_NotifyIconW.call_args[0]
        data = ctypes.cast(data_ref, ctypes.POINTER(win_tray.NOTIFYICONDATAW)).contents
        self.assertEqual(code, win_tray.NIM_MODIFY)
        self.assertTrue(data.uFlags & win_tray.NIF_TIP)
        self.assertTrue(data.uFlags & win_tray.NIF_SHOWTIP)
        self.assertEqual(data.szTip, 'new tooltip')

    def test_notify_uses_shell_balloon(self):
        icon = win_tray.Icon('test', icon=_bitmap(), title='title')
        icon._hwnd = 100
        icon._visible = True

        icon.notify('body', 'caption')

        code, data_ref = self.fake.shell32.Shell_NotifyIconW.call_args[0]
        data = ctypes.cast(data_ref, ctypes.POINTER(win_tray.NOTIFYICONDATAW)).contents
        self.assertEqual(code, win_tray.NIM_MODIFY)
        self.assertTrue(data.uFlags & win_tray.NIF_INFO)
        self.assertEqual(data.szInfo, 'body')
        self.assertEqual(data.szInfoTitle, 'caption')

    def test_create_hicon_initializes_mask_bitmap(self):
        bitmap = _bitmap()
        color_bits = (ctypes.c_ubyte * len(bitmap.pixels))()

        def create_dib_section(hdc, info, colors, bits_ref, section, offset):
            ctypes.cast(bits_ref, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.cast(color_bits, ctypes.c_void_p)
            return 700

        self.fake.gdi32.CreateDIBSection.side_effect = create_dib_section
        self.fake.gdi32.CreateBitmap.return_value = 800
        self.fake.user32.CreateIconIndirect.return_value = 900

        self.assertEqual(win_tray._create_hicon(bitmap), 900)
        self.assertIsNotNone(self.fake.gdi32.CreateBitmap.call_args[0][4])
        self.assertEqual(self.fake.gdi32.DeleteObject.call_count, 2)

    def test_right_click_menu_dispatches_selected_command(self):
        action = MagicMock()
        icon = win_tray.Icon('test', icon=_bitmap(), title='title', menu=win_tray.Menu(win_tray.MenuItem('Show', action)))
        icon._hwnd = 100

        icon._show_menu()

        action.assert_called_once()
        self.fake.user32.DestroyMenu.assert_called_once()

    def test_window_proc_handles_v4_context_menu_event_loword(self):
        icon = win_tray.Icon('test', icon=_bitmap(), title='title')
        lparam = win_tray.WM_CONTEXTMENU | (icon._uid << 16)

        with patch.object(icon, '_show_menu') as show_menu:
            result = icon._window_proc(100, win_tray.WM_TRAY, 0, lparam)

        self.assertEqual(result, 0)
        show_menu.assert_called_once()

    def test_window_proc_handles_v4_select_event_loword(self):
        icon = win_tray.Icon('test', icon=_bitmap(), title='title')
        lparam = win_tray.NIN_SELECT | (icon._uid << 16)

        with patch.object(icon, '_invoke_default') as invoke_default:
            result = icon._window_proc(100, win_tray.WM_TRAY, 0, lparam)

        self.assertEqual(result, 0)
        invoke_default.assert_called_once()

    def test_legacy_right_click_event_still_supported(self):
        icon = win_tray.Icon('test', icon=_bitmap(), title='title')

        with patch.object(icon, '_show_menu') as show_menu:
            result = icon._window_proc(100, win_tray.WM_TRAY, 0, win_tray.WM_RBUTTONUP)

        self.assertEqual(result, 0)
        show_menu.assert_called_once()

    def test_run_starts_setup_thread_and_message_loop(self):
        setup = MagicMock()
        icon = win_tray.Icon('test', icon=_bitmap(), title='title')

        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                self.target(*self.args)

        with patch('src.ui.win_tray.threading.Thread', ImmediateThread):
            icon.run(setup=setup)

        self.fake.user32.CreateWindowExW.assert_called()
        setup.assert_called_once()


if __name__ == '__main__':
    unittest.main()
