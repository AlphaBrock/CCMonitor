"""
-------------------------------------------------
   File Name   :     win_tray.py
   Description :     Windows 原生系统托盘适配器
   Company     :     JohnWick
   Author      :     linjcciam1314@gmail.com
   Date        :     2026-05-29
-------------------------------------------------
"""
from __future__ import annotations

import ctypes
import threading
from dataclasses import dataclass
from typing import Any, Callable

from ctypes import wintypes

from src.ui.tray_icon import TrayIconBitmap

__all__ = ['Icon', 'Menu', 'MenuItem', 'SEPARATOR']

LRESULT = ctypes.c_ssize_t
ULONG_PTR = wintypes.WPARAM
HICON = wintypes.HANDLE
HBITMAP = wintypes.HANDLE
HCURSOR = wintypes.HANDLE
HBRUSH = wintypes.HANDLE
HMENU = wintypes.HMENU
HINSTANCE = wintypes.HINSTANCE
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_CONTEXTMENU = 0x007B
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_USER = 0x0400
WM_APP = 0x8000
WM_NULL = 0x0000
WM_TRAY = WM_USER + 42
WM_STOP = WM_APP + 42
NIN_SELECT = WM_USER
NIN_KEYSELECT = WM_USER + 1

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIM_SETVERSION = 0x00000004
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIF_SHOWTIP = 0x00000080
NOTIFYICON_VERSION_4 = 4
NIIF_INFO = 0x00000001

BI_RGB = 0
DIB_RGB_COLORS = 0

MIIM_STATE = 0x00000001
MIIM_ID = 0x00000002
MIIM_SUBMENU = 0x00000004
MIIM_TYPE = 0x00000010
MIIM_STRING = 0x00000040
MIIM_FTYPE = 0x00000100
MFT_STRING = 0x00000000
MFT_SEPARATOR = 0x00000800
MFT_RADIOCHECK = 0x00000200
MFS_ENABLED = 0x00000000
MFS_CHECKED = 0x00000008
MFS_DISABLED = 0x00000003
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080


class GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', wintypes.DWORD),
        ('Data2', wintypes.WORD),
        ('Data3', wintypes.WORD),
        ('Data4', ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('hWnd', wintypes.HWND),
        ('uID', wintypes.UINT),
        ('uFlags', wintypes.UINT),
        ('uCallbackMessage', wintypes.UINT),
        ('hIcon', HICON),
        ('szTip', wintypes.WCHAR * 128),
        ('dwState', wintypes.DWORD),
        ('dwStateMask', wintypes.DWORD),
        ('szInfo', wintypes.WCHAR * 256),
        ('uVersion', wintypes.UINT),
        ('szInfoTitle', wintypes.WCHAR * 64),
        ('dwInfoFlags', wintypes.DWORD),
        ('guidItem', GUID),
        ('hBalloonIcon', HICON),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.UINT),
        ('style', wintypes.UINT),
        ('lpfnWndProc', WNDPROC),
        ('cbClsExtra', ctypes.c_int),
        ('cbWndExtra', ctypes.c_int),
        ('hInstance', HINSTANCE),
        ('hIcon', HICON),
        ('hCursor', HCURSOR),
        ('hbrBackground', HBRUSH),
        ('lpszMenuName', wintypes.LPCWSTR),
        ('lpszClassName', wintypes.LPCWSTR),
        ('hIconSm', HICON),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', ctypes.c_long),
        ('biHeight', ctypes.c_long),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', ctypes.c_long),
        ('biYPelsPerMeter', ctypes.c_long),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ('bmiHeader', BITMAPINFOHEADER),
        ('bmiColors', wintypes.DWORD * 1),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ('fIcon', wintypes.BOOL),
        ('xHotspot', wintypes.DWORD),
        ('yHotspot', wintypes.DWORD),
        ('hbmMask', HBITMAP),
        ('hbmColor', HBITMAP),
    ]


class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


class MENUITEMINFOW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.UINT),
        ('fMask', wintypes.UINT),
        ('fType', wintypes.UINT),
        ('fState', wintypes.UINT),
        ('wID', wintypes.UINT),
        ('hSubMenu', HMENU),
        ('hbmpChecked', HBITMAP),
        ('hbmpUnchecked', HBITMAP),
        ('dwItemData', ULONG_PTR),
        ('dwTypeData', wintypes.LPWSTR),
        ('cch', wintypes.UINT),
        ('hbmpItem', HBITMAP),
    ]


@dataclass(frozen=True)
class _Separator:
    pass


SEPARATOR = _Separator()


class Menu:
    """托盘菜单容器。"""

    SEPARATOR = SEPARATOR

    def __init__(self, *items: Any) -> None:
        self.items = tuple(items)


class MenuItem:
    """托盘菜单项。"""

    def __init__(
        self,
        text: str,
        action: Callable[..., Any] | Menu | None = None,
        *,
        checked: Callable[..., bool] | bool | None = None,
        radio: Callable[..., bool] | bool = False,
        default: bool = False,
        visible: Callable[..., bool] | bool = True,
        enabled: Callable[..., bool] | bool = True,
    ) -> None:
        self.text = text
        self.action = None if isinstance(action, Menu) else action
        self.submenu = action if isinstance(action, Menu) else None
        self.checked = checked
        self.radio = radio
        self.default = default
        self.visible = visible
        self.enabled = enabled


class Icon:
    """Windows Shell_NotifyIconW 托盘图标。"""

    def __init__(self, name: str, icon: TrayIconBitmap | None = None, title: str | None = None, menu: Menu | None = None) -> None:
        _configure_win32_api()
        self.name = name
        self.menu = menu or Menu()
        self._icon_bitmap = icon
        self._title = title or ''
        self._visible = False
        self._running = False
        self._hwnd: wintypes.HWND | None = None
        self._hicon: HICON | None = None
        self._uid = 1
        self._lock = threading.RLock()
        self._class_name = f'CCMonitorTrayWindow-{id(self)}'
        self._wndproc = WNDPROC(self._window_proc)
        self._taskbar_created = ctypes.windll.user32.RegisterWindowMessageW('TaskbarCreated')

    @property
    def icon(self) -> TrayIconBitmap | None:
        return self._icon_bitmap

    @icon.setter
    def icon(self, value: TrayIconBitmap | None) -> None:
        with self._lock:
            self._icon_bitmap = value
            if self._visible and self._hwnd:
                self._replace_hicon()
                self._notify_icon(NIM_MODIFY, NIF_ICON)

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        with self._lock:
            self._title = value or ''
            if self._visible and self._hwnd:
                self._notify_icon(NIM_MODIFY, NIF_TIP)

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        with self._lock:
            if value == self._visible:
                return
            if value:
                self._add_icon()
            else:
                self._delete_icon()
            self._visible = value

    def run(self, setup: Callable[['Icon'], Any] | None = None) -> None:
        """创建隐藏窗口并进入托盘消息循环。"""
        self._register_window_class()
        self._create_window()
        self._running = True
        if setup is not None:
            threading.Thread(target=setup, args=(self,), daemon=True).start()
        self._message_loop()

    def stop(self) -> None:
        """停止托盘消息循环。"""
        self._running = False
        if self._hwnd:
            ctypes.windll.user32.PostMessageW(self._hwnd, WM_STOP, 0, 0)

    def notify(self, message: str, title: str | None = None) -> None:
        """显示 Windows 托盘通知气泡。"""
        if not self._visible or not self._hwnd:
            return
        data = self._notify_data(NIF_INFO)
        data.szInfo = _truncate(message, 255)
        data.szInfoTitle = _truncate(title or self._title, 63)
        data.dwInfoFlags = NIIF_INFO
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))

    def _message_loop(self) -> None:
        message = wintypes.MSG()
        while ctypes.windll.user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(message))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(message))

    def _window_proc(self, hwnd: wintypes.HWND, msg: int, wparam: wintypes.WPARAM, lparam: wintypes.LPARAM) -> int:
        if msg == WM_TRAY:
            event = _loword(lparam)
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK, NIN_SELECT, NIN_KEYSELECT):
                self._invoke_default()
                return 0
            if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu()
                return 0
        if msg == self._taskbar_created:
            if self._visible:
                self._visible = False
                self.visible = True
            return 0
        if msg in (WM_STOP, WM_CLOSE):
            if self._hwnd:
                ctypes.windll.user32.DestroyWindow(self._hwnd)
            return 0
        if msg == WM_DESTROY:
            self._delete_icon()
            self._destroy_hicon()
            self._hwnd = None
            self._visible = False
            ctypes.windll.user32.PostQuitMessage(0)
            return 0
        if msg == WM_COMMAND:
            return 0
        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _register_window_class(self) -> None:
        instance = ctypes.windll.kernel32.GetModuleHandleW(None)
        wndclass = WNDCLASSEXW(
            cbSize=ctypes.sizeof(WNDCLASSEXW),
            style=0,
            lpfnWndProc=self._wndproc,
            cbClsExtra=0,
            cbWndExtra=0,
            hInstance=instance,
            hIcon=None,
            hCursor=None,
            hbrBackground=None,
            lpszMenuName=None,
            lpszClassName=self._class_name,
            hIconSm=None,
        )
        ctypes.windll.user32.RegisterClassExW(ctypes.byref(wndclass))

    def _create_window(self) -> None:
        instance = ctypes.windll.kernel32.GetModuleHandleW(None)
        self._hwnd = ctypes.windll.user32.CreateWindowExW(
            0, self._class_name, self.name, 0,
            0, 0, 0, 0,
            None, None, instance, None,
        )
        if not self._hwnd:
            raise ctypes.WinError()

    def _add_icon(self) -> None:
        if not self._hwnd:
            return
        self._replace_hicon()
        self._notify_icon(NIM_ADD, NIF_MESSAGE | NIF_ICON | NIF_TIP)
        version_data = self._notify_data(0)
        version_data.uVersion = NOTIFYICON_VERSION_4
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(version_data))

    def _delete_icon(self) -> None:
        if self._hwnd:
            self._notify_icon(NIM_DELETE, 0)

    def _notify_icon(self, code: int, flags: int) -> None:
        data = self._notify_data(flags)
        ctypes.windll.shell32.Shell_NotifyIconW(code, ctypes.byref(data))

    def _notify_data(self, flags: int) -> NOTIFYICONDATAW:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = self._uid
        data.uFlags = flags | (NIF_SHOWTIP if flags & NIF_TIP else 0)
        data.uCallbackMessage = WM_TRAY
        data.hIcon = self._hicon
        data.szTip = _truncate(self._title, 127)
        return data

    def _replace_hicon(self) -> None:
        self._destroy_hicon()
        if self._icon_bitmap is not None:
            self._hicon = _create_hicon(self._icon_bitmap)

    def _destroy_hicon(self) -> None:
        if self._hicon:
            ctypes.windll.user32.DestroyIcon(self._hicon)
            self._hicon = None

    def _invoke_default(self) -> None:
        item = _first_default_item(self.menu)
        if item is not None and _enabled(item):
            _invoke_action(self, item)

    def _show_menu(self) -> None:
        if not self._hwnd:
            return
        command_map: dict[int, MenuItem] = {}
        next_id = [1000]
        hmenu = _build_menu(self.menu, command_map, next_id)
        try:
            point = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            ctypes.windll.user32.SetForegroundWindow(self._hwnd)
            command_id = ctypes.windll.user32.TrackPopupMenu(
                hmenu,
                TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                point.x,
                point.y,
                0,
                self._hwnd,
                None,
            )
            ctypes.windll.user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
            item = command_map.get(command_id)
            if item is not None and _enabled(item):
                _invoke_action(self, item)
        finally:
            ctypes.windll.user32.DestroyMenu(hmenu)


def _configure_win32_api() -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    gdi32 = ctypes.windll.gdi32
    shell32 = ctypes.windll.shell32
    user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        HMENU,
        HINSTANCE,
        ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.CreatePopupMenu.restype = HMENU
    user32.InsertMenuItemW.argtypes = [HMENU, wintypes.UINT, wintypes.BOOL, ctypes.POINTER(MENUITEMINFOW)]
    user32.InsertMenuItemW.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
    user32.TrackPopupMenu.restype = wintypes.UINT
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.DestroyMenu.argtypes = [HMENU]
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
    user32.CreateIconIndirect.restype = HICON
    user32.DestroyIcon.argtypes = [HICON]
    user32.DestroyIcon.restype = wintypes.BOOL
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = HINSTANCE
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = HBITMAP
    gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
    gdi32.CreateBitmap.restype = HBITMAP
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL


def _create_hicon(bitmap: TrayIconBitmap) -> HICON:
    color_bitmap = _create_color_bitmap(bitmap)
    mask_stride = ((bitmap.width + 15) // 16) * 2
    mask_bits = (ctypes.c_ubyte * (mask_stride * bitmap.height))()
    mask_pointer = ctypes.cast(mask_bits, ctypes.c_void_p)
    mask_bitmap = ctypes.windll.gdi32.CreateBitmap(bitmap.width, bitmap.height, 1, 1, mask_pointer)
    try:
        icon_info = ICONINFO(True, 0, 0, mask_bitmap, color_bitmap)
        hicon = ctypes.windll.user32.CreateIconIndirect(ctypes.byref(icon_info))
        if not hicon:
            raise ctypes.WinError()
        return hicon
    finally:
        ctypes.windll.gdi32.DeleteObject(color_bitmap)
        ctypes.windll.gdi32.DeleteObject(mask_bitmap)


def _create_color_bitmap(bitmap: TrayIconBitmap) -> HBITMAP:
    header = BITMAPINFOHEADER(
        biSize=ctypes.sizeof(BITMAPINFOHEADER),
        biWidth=bitmap.width,
        biHeight=-bitmap.height,
        biPlanes=1,
        biBitCount=32,
        biCompression=BI_RGB,
        biSizeImage=len(bitmap.pixels),
        biXPelsPerMeter=0,
        biYPelsPerMeter=0,
        biClrUsed=0,
        biClrImportant=0,
    )
    info = BITMAPINFO(header, (wintypes.DWORD * 1)(0))
    bits = ctypes.c_void_p()
    hdc = ctypes.windll.user32.GetDC(None)
    try:
        info_pointer = ctypes.cast(ctypes.byref(info), ctypes.c_void_p)
        hbitmap = ctypes.windll.gdi32.CreateDIBSection(hdc, info_pointer, DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        if not hbitmap or not bits.value:
            raise ctypes.WinError()
        ctypes.memmove(bits, bitmap.pixels, len(bitmap.pixels))
        return hbitmap
    finally:
        ctypes.windll.user32.ReleaseDC(None, hdc)


def _build_menu(menu: Menu, command_map: dict[int, MenuItem], next_id: list[int]) -> HMENU:
    hmenu = ctypes.windll.user32.CreatePopupMenu()
    for item in menu.items:
        if item is SEPARATOR:
            _insert_separator(hmenu)
            continue
        if not isinstance(item, MenuItem) or not _visible(item):
            continue

        if item.submenu is not None:
            submenu = _build_menu(item.submenu, command_map, next_id)
            _insert_menu_item(hmenu, item, 0, submenu)
        else:
            command_id = next_id[0]
            next_id[0] += 1
            command_map[command_id] = item
            _insert_menu_item(hmenu, item, command_id, None)
    return hmenu


def _insert_separator(hmenu: HMENU) -> None:
    info = MENUITEMINFOW()
    info.cbSize = ctypes.sizeof(MENUITEMINFOW)
    info.fMask = MIIM_FTYPE
    info.fType = MFT_SEPARATOR
    ctypes.windll.user32.InsertMenuItemW(hmenu, 0xFFFFFFFF, True, ctypes.byref(info))


def _insert_menu_item(hmenu: HMENU, item: MenuItem, command_id: int, submenu: HMENU | None) -> None:
    text = _text(item)
    buffer = ctypes.create_unicode_buffer(text)
    info = MENUITEMINFOW()
    info.cbSize = ctypes.sizeof(MENUITEMINFOW)
    info.fMask = MIIM_FTYPE | MIIM_STATE | MIIM_STRING
    info.fType = MFT_STRING | (MFT_RADIOCHECK if _radio(item) else 0)
    info.fState = MFS_ENABLED
    if _checked(item):
        info.fState |= MFS_CHECKED
    if not _enabled(item):
        info.fState |= MFS_DISABLED
    info.dwTypeData = ctypes.cast(buffer, wintypes.LPWSTR)
    info.cch = len(text)

    if submenu:
        info.fMask |= MIIM_SUBMENU
        info.hSubMenu = submenu
    else:
        info.fMask |= MIIM_ID
        info.wID = command_id

    ctypes.windll.user32.InsertMenuItemW(hmenu, 0xFFFFFFFF, True, ctypes.byref(info))


def _first_default_item(menu: Menu) -> MenuItem | None:
    for item in menu.items:
        if item is SEPARATOR:
            continue
        if not isinstance(item, MenuItem) or not _visible(item):
            continue
        if item.default:
            return item
        if item.submenu is not None:
            nested = _first_default_item(item.submenu)
            if nested is not None:
                return nested
    return None


def _invoke_action(icon: Icon, item: MenuItem) -> None:
    if item.action is None:
        return
    item.action(icon, item)


def _visible(item: MenuItem) -> bool:
    return bool(_resolve(item.visible, item))


def _enabled(item: MenuItem) -> bool:
    return bool(_resolve(item.enabled, item))


def _checked(item: MenuItem) -> bool:
    return bool(_resolve(item.checked, item))


def _radio(item: MenuItem) -> bool:
    return bool(_resolve(item.radio, item))


def _text(item: MenuItem) -> str:
    return str(_resolve(item.text, item))


def _resolve(value: Any, item: MenuItem) -> Any:
    if callable(value):
        return value(item)
    return value


def _truncate(value: str, limit: int) -> str:
    return (value or '')[:limit]


def _loword(value: int) -> int:
    return int(value) & 0xFFFF
