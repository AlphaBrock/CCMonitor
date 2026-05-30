"""
-------------------------------------------------
   File Name   :     tray_icon.py
   Description :     原生托盘图标位图渲染
   Company     :     JohnWick
   Author      :     linjcciam1314@gmail.com
   Date        :     2026-05-29
-------------------------------------------------
"""
from __future__ import annotations

import ctypes
import winreg
from dataclasses import dataclass
from typing import Callable, Iterable

from ctypes import wintypes

from src.presentation.settings import ICON_DARK, ICON_LIGHT

__all__ = ['TrayIconBitmap', 'taskbar_uses_light_theme', 'watch_theme_change', 'create_icon_image', 'create_status_image']

THEME_REG_KEY = r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'
THEME_REG_VALUE = 'SystemUsesLightTheme'
REG_NOTIFY_CHANGE_LAST_SET = 0x00000004

_SIZE = 64
_TEXT_SCALE = 4
_MAIN_TEXT_AREA = 43

FW_BOLD = 700
TRANSPARENT_BK = 1
ANTIALIASED_QUALITY = 4
CLEARTYPE_QUALITY = 5
DT_CENTER = 0x00000001
DT_VCENTER = 0x00000004
DT_SINGLELINE = 0x00000020
DT_NOCLIP = 0x00000100
BI_RGB = 0
DIB_RGB_COLORS = 0


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


@dataclass(frozen=True)
class TrayIconBitmap:
    """托盘图标 BGRA 位图。"""

    width: int
    height: int
    pixels: bytes

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    @property
    def mode(self) -> str:
        return 'BGRA'

    def tobytes(self) -> bytes:
        return self.pixels

    def rgba_at(self, x: int, y: int) -> tuple[int, int, int, int]:
        """按 RGBA 顺序读取单个像素，便于测试断言。"""
        index = (y * self.width + x) * 4
        blue, green, red, alpha = self.pixels[index:index + 4]
        return red, green, blue, alpha


class _Canvas:
    """64x64 BGRA 画布。"""

    def __init__(self, width: int = _SIZE, height: int = _SIZE) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 4)

    def fill_rect(self, left: int, top: int, right: int, bottom: int, color: tuple[int, int, int, int]) -> None:
        """填充矩形，坐标包含右下边界。"""
        min_x = max(0, left)
        max_x = min(self.width - 1, right)
        min_y = max(0, top)
        max_y = min(self.height - 1, bottom)
        if min_x > max_x or min_y > max_y:
            return

        red, green, blue, alpha = color
        for y in range(min_y, max_y + 1):
            row = y * self.width * 4
            for x in range(min_x, max_x + 1):
                index = row + x * 4
                self.pixels[index:index + 4] = bytes((blue, green, red, alpha))

    def blend_mask(self, mask: bytes, mask_width: int, mask_height: int, left: int, top: int, color: tuple[int, int, int, int]) -> None:
        """按灰度蒙版把文字混合到透明 BGRA 画布。"""
        red, green, blue, alpha = color
        for y in range(mask_height):
            target_y = top + y
            if target_y < 0 or target_y >= self.height:
                continue
            row = target_y * self.width * 4
            mask_row = y * mask_width
            for x in range(mask_width):
                target_x = left + x
                if target_x < 0 or target_x >= self.width:
                    continue
                mask_alpha = mask[mask_row + x]
                if not mask_alpha:
                    continue
                effective_alpha = mask_alpha * alpha // 255
                index = row + target_x * 4
                self.pixels[index:index + 4] = bytes((blue, green, red, effective_alpha))

    def to_bitmap(self) -> TrayIconBitmap:
        return TrayIconBitmap(self.width, self.height, bytes(self.pixels))


def taskbar_uses_light_theme() -> bool:
    """读取 Windows 任务栏是否为浅色主题。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEME_REG_KEY) as key:
            value, _ = winreg.QueryValueEx(key, THEME_REG_VALUE)
            return bool(value)
    except OSError:
        return False


def watch_theme_change(callback: Callable[[], None]) -> None:
    """阻塞等待系统主题变化，并在变化后执行回调。"""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEME_REG_KEY, 0, winreg.KEY_READ) as key:
        while True:
            if ctypes.windll.advapi32.RegNotifyChangeKeyValue(int(key), False, REG_NOTIFY_CHANGE_LAST_SET, None, False) != 0:
                return
            callback()


def create_icon_image(
    pct_top: float, pct_bottom: float, light_taskbar: bool = False,
    *, mode_top: str = 'utilization', mode_bottom: str = 'utilization',
    time_pct_top: float | None = None, time_pct_bottom: float | None = None,
    extra_usage_available: bool = False,
) -> TrayIconBitmap:
    """创建主托盘图标位图。"""
    colors = ICON_DARK if light_taskbar else ICON_LIGHT
    foreground = _rgba(colors['fg'])
    foreground_half = _rgba(colors['fg_half'])
    canvas = _Canvas()

    any_exhausted = pct_top >= 100 or pct_bottom >= 100
    if any_exhausted and not extra_usage_available:
        text = '✕'
    elif any_exhausted:
        text = '$'
    elif pct_top > 0:
        text = f'{pct_top:.0f}'
    else:
        text = 'C'

    _draw_text(canvas, text, foreground, area_height=_MAIN_TEXT_AREA, font_size=_main_text_size(text), symbol=text == '✕')
    _draw_bars(canvas, foreground, foreground_half, ((pct_top, mode_top, time_pct_top), (pct_bottom, mode_bottom, time_pct_bottom)))
    return canvas.to_bitmap()


def create_status_image(text: str, light_taskbar: bool = False) -> TrayIconBitmap:
    """创建错误或状态托盘图标位图。"""
    colors = ICON_DARK if light_taskbar else ICON_LIGHT
    foreground = _rgba(colors['fg_dim'])
    canvas = _Canvas()
    _draw_text(canvas, text, foreground, area_height=_SIZE, font_size=_status_text_size(text), symbol=False)
    return canvas.to_bitmap()


def _draw_bars(
    canvas: _Canvas,
    foreground: tuple[int, int, int, int],
    background: tuple[int, int, int, int],
    bars: Iterable[tuple[float, str, float | None]],
) -> None:
    bar_height = 9
    gap = 3
    positions = (_SIZE - bar_height - gap - bar_height, _SIZE - bar_height)

    for y, (pct, mode, time_pct) in zip(positions, bars):
        canvas.fill_rect(0, y, _SIZE - 1, y + bar_height - 1, background)
        fill_width = _bar_fill_width(pct, mode, time_pct)
        if fill_width > 0:
            canvas.fill_rect(0, y, fill_width - 1, y + bar_height - 1, foreground)


def _bar_fill_width(pct: float, mode: str, time_pct: float | None) -> int:
    if mode == 'overage' and time_pct is not None and time_pct < 100:
        overage = max(0.0, pct - time_pct)
        return max(0, min(_SIZE, int(_SIZE * min(1.0, overage / (100 - time_pct)))))
    return max(0, min(_SIZE, int(_SIZE * pct / 100)))


def _draw_text(canvas: _Canvas, text: str, color: tuple[int, int, int, int], *, area_height: int, font_size: int, symbol: bool) -> None:
    mask = _render_text_mask(text, area_height=area_height, font_size=font_size, symbol=symbol)
    canvas.blend_mask(mask, _SIZE, area_height, 0, 0, color)


def _render_text_mask(text: str, *, area_height: int, font_size: int, symbol: bool) -> bytes:
    _configure_gdi_text_api()

    width = _SIZE * _TEXT_SCALE
    height = area_height * _TEXT_SCALE
    byte_count = width * height * 4
    info = BITMAPINFO(
        BITMAPINFOHEADER(
            biSize=ctypes.sizeof(BITMAPINFOHEADER),
            biWidth=width,
            biHeight=-height,
            biPlanes=1,
            biBitCount=32,
            biCompression=BI_RGB,
            biSizeImage=byte_count,
            biXPelsPerMeter=0,
            biYPelsPerMeter=0,
            biClrUsed=0,
            biClrImportant=0,
        ),
        (wintypes.DWORD * 1)(0),
    )
    bits = ctypes.c_void_p()
    hdc = ctypes.windll.gdi32.CreateCompatibleDC(None)
    if not hdc:
        return bytes(_SIZE * area_height)

    hbitmap = None
    font = None
    old_bitmap = None
    old_font = None
    try:
        info_pointer = ctypes.cast(ctypes.byref(info), ctypes.c_void_p)
        hbitmap = ctypes.windll.gdi32.CreateDIBSection(hdc, info_pointer, DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        if not hbitmap or not bits.value:
            return bytes(_SIZE * area_height)
        ctypes.memset(bits, 0, byte_count)
        old_bitmap = ctypes.windll.gdi32.SelectObject(hdc, hbitmap)

        face_name = 'Segoe UI Symbol' if symbol else 'Arial'
        font = ctypes.windll.gdi32.CreateFontW(
            -font_size * _TEXT_SCALE,
            0,
            0,
            0,
            FW_BOLD,
            False,
            False,
            False,
            0,
            0,
            0,
            CLEARTYPE_QUALITY,
            0,
            face_name,
        )
        if not font:
            return bytes(_SIZE * area_height)
        old_font = ctypes.windll.gdi32.SelectObject(hdc, font)
        ctypes.windll.gdi32.SetBkMode(hdc, TRANSPARENT_BK)
        ctypes.windll.gdi32.SetTextColor(hdc, 0x00FFFFFF)
        rect = wintypes.RECT(0, 0, width, height)
        ctypes.windll.user32.DrawTextW(hdc, text, len(text), ctypes.byref(rect), DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOCLIP)
        source = ctypes.string_at(bits, byte_count)
        return _downsample_text_mask(source, width, height, area_height)
    finally:
        if old_font:
            ctypes.windll.gdi32.SelectObject(hdc, old_font)
        if old_bitmap:
            ctypes.windll.gdi32.SelectObject(hdc, old_bitmap)
        if font:
            ctypes.windll.gdi32.DeleteObject(font)
        if hbitmap:
            ctypes.windll.gdi32.DeleteObject(hbitmap)
        ctypes.windll.gdi32.DeleteDC(hdc)


def _downsample_text_mask(source: bytes, source_width: int, source_height: int, target_height: int) -> bytes:
    target = bytearray(_SIZE * target_height)
    scale_area = _TEXT_SCALE * _TEXT_SCALE
    for target_y in range(target_height):
        for target_x in range(_SIZE):
            total = 0
            for offset_y in range(_TEXT_SCALE):
                source_y = target_y * _TEXT_SCALE + offset_y
                row = source_y * source_width * 4
                for offset_x in range(_TEXT_SCALE):
                    source_x = target_x * _TEXT_SCALE + offset_x
                    index = row + source_x * 4
                    blue = source[index]
                    green = source[index + 1]
                    red = source[index + 2]
                    total += max(red, green, blue)
            target[target_y * _SIZE + target_x] = min(255, total // scale_area)
    return bytes(target)


def _configure_gdi_text_api() -> None:
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.CreateFontW.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPCWSTR,
    ]
    gdi32.CreateFontW.restype = wintypes.HFONT
    gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.SetBkMode.restype = ctypes.c_int
    gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi32.SetTextColor.restype = wintypes.COLORREF
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT]
    user32.DrawTextW.restype = ctypes.c_int


def _main_text_size(text: str) -> int:
    if text in {'C', '✕', '$'}:
        return 36
    if len(text) <= 2:
        return 31
    return 25


def _status_text_size(text: str) -> int:
    if len(text) <= 1:
        return 42
    if len(text) == 2:
        return 34
    return 28


def _rgba(value: list[int] | tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return int(value[0]), int(value[1]), int(value[2]), int(value[3])
