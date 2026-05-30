"""
Usage Popup
============

Desktop popup window and frontend data bridge.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import webview  # type: ignore[import-untyped]  # no type stubs available

from src import __version__
from src.integrations.local_usage import LocalUsageSummary, local_usage_summary
from src.presentation.formatting import format_credits, parse_field_name, popup_label, time_until, tooltip_label
from src.presentation.i18n import T
from src.presentation.settings import (
    BAR_BG, BAR_FG, BAR_FG_DANGER, BAR_FG_MID, BAR_FG_WARN, BG,
    FG, FG_DIM, FG_HEADING, FG_LINK,
)

if TYPE_CHECKING:
    from src.runtime.app import CCMonitor
    from src.runtime.cache import CacheSnapshot, DashboardSnapshot


_POPUP_DIR = Path(__file__).parent / 'popup'
BASELINE_DPI = 96
_BAR_WIDTH = 20
_CHECK_MS = 1000
_VISIBLE_USAGE_FIELDS = ('five_hour', 'seven_day')
_PROVIDER_ORDER = ('codex', 'claude')
_PROVIDER_TITLES = {'codex': 'Codex', 'claude': 'Claude'}
_VALID_PROVIDER_VIEWS = frozenset({'all', 'codex', 'claude'})
_TRAY_PROVIDER_TO_VIEW = {'auto': 'all', 'codex': 'codex', 'claude': 'claude'}
_GWL_EXSTYLE = -20
_WS_EX_APPWINDOW = 0x00040000
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_LAYERED = 0x00080000
_LWA_ALPHA = 0x00000002
_SW_RESTORE = 9
_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2

__all__ = [
    'BASELINE_DPI',
    'MONITORINFO',
    'UsagePopup',
    'build_text_bar',
    'init_config',
    'snapshot_to_dict',
    'tone_for_percent',
    'usage_entries',
]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.wintypes.DWORD),
        ('rcMonitor', ctypes.wintypes.RECT),
        ('rcWork', ctypes.wintypes.RECT),
        ('dwFlags', ctypes.wintypes.DWORD),
    ]


def _usage_label(field: str) -> str:
    """Return the fixed quota label used in the popup window."""
    parsed = parse_field_name(field)
    if parsed is None:
        return popup_label(field)

    _, unit, _ = parsed
    template_key = 'session_label' if unit == 'hour' else 'weekly_label'
    return T[template_key].format(suffix=tooltip_label(field))


def tone_for_percent(percent: float) -> str:
    """Map a percentage to one of four color tones."""
    if percent >= 100:
        return 'danger'
    if percent >= 80:
        return 'warn'
    if percent >= 50:
        return 'mid'
    return 'normal'


def build_text_bar(percent: float, length: int = _BAR_WIDTH) -> str:
    """Build a fixed-length text progress bar using block characters."""
    if length <= 0:
        return ''

    filled = int(round(max(0.0, min(percent, 100.0)) / 100 * length))
    filled = max(0, min(length, filled))
    return ('█' * filled) + ('░' * (length - filled))


def usage_entries(usage: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return only the two fixed quotas displayed in the popup window."""
    entries: list[tuple[str, dict[str, Any]]] = []

    for field in _VISIBLE_USAGE_FIELDS:
        entry = usage.get(field)
        if not isinstance(entry, dict) or entry.get('utilization') is None:
            continue
        entries.append((field, entry))

    return entries


def _normalize_provider_view(view_id: str | None) -> str:
    if view_id in _VALID_PROVIDER_VIEWS:
        return str(view_id)
    return 'all'


def _provider_view_from_tray(tray_provider: str | None) -> str:
    return _TRAY_PROVIDER_TO_VIEW.get(str(tray_provider or ''), 'all')


def _status_dict(snap: CacheSnapshot, next_poll_time: float | None) -> dict[str, Any]:
    """Convert cache state into a status dict consumable by the frontend."""
    if not snap.usage:
        if snap.last_error:
            return {'text': snap.last_error[:120], 'is_error': True}
        return {'text': T['status_refreshing'], 'is_error': False, 'refreshing': True}

    return {
        'last_success_time': snap.last_success_time,
        'next_poll_time': next_poll_time,
        'refreshing': snap.refreshing,
        'error': snap.last_error[:120] if snap.last_error else None,
    }


def _usage_row(field: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Convert a single quota entry into a frontend row dict."""
    percent = float(entry.get('utilization', 0) or 0)
    resets_at = entry.get('resets_at') or ''
    return {
        'field': field,
        'label': _usage_label(field),
        'pct_text': f'{percent:.0f}%',
        'tone': tone_for_percent(percent),
        'bar_text': build_text_bar(percent),
        'reset_text': time_until(resets_at) if resets_at else '',
    }


def _session_usage_row(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    if not usage:
        return None

    entry = usage.get('five_hour')
    if not isinstance(entry, dict) or entry.get('utilization') is None:
        return None

    return _usage_row('five_hour', entry)


def snapshot_to_dict(
    snap: CacheSnapshot | DashboardSnapshot,
    next_poll_time: float | None = None,
    provider_view: str | None = None,
) -> dict[str, Any]:
    """Convert a cache snapshot into data for frontend init and incremental updates."""
    if hasattr(snap, 'providers'):
        return _dashboard_to_dict(snap, next_poll_time=next_poll_time, provider_view=provider_view)  # type: ignore[arg-type]
    return _single_snapshot_to_dict(snap, next_poll_time=next_poll_time, provider_view=provider_view)


def _dashboard_to_dict(
    snap: DashboardSnapshot,
    next_poll_time: float | None = None,
    provider_view: str | None = None,
) -> dict[str, Any]:
    """Convert a dashboard snapshot into frontend data."""
    providers: list[dict[str, Any]] = []
    for provider_id in _PROVIDER_ORDER:
        provider_snap = snap.providers.get(provider_id)
        if provider_snap is None:
            continue
        providers.append(_provider_to_dict(provider_id, provider_snap, next_poll_time=next_poll_time))

    return {
        'providers': providers,
        'primary_provider': snap.primary_provider,
        'provider_view': _normalize_provider_view(provider_view),
    }


def _single_snapshot_to_dict(
    snap: CacheSnapshot,
    next_poll_time: float | None = None,
    provider_view: str | None = None,
) -> dict[str, Any]:
    """Convert a single-provider snapshot into frontend data."""
    provider_id = getattr(snap, 'provider_id', 'claude')
    return {
        'providers': [_provider_to_dict(provider_id, snap, next_poll_time=next_poll_time)],
        'primary_provider': provider_id,
        'provider_view': _normalize_provider_view(provider_view),
    }


def _provider_to_dict(provider_id: str, snap: CacheSnapshot, next_poll_time: float | None = None) -> dict[str, Any]:
    """Convert one provider snapshot into a frontend card dict."""
    profile = None
    if snap.profile:
        account = snap.profile.get('account', {})
        organization = snap.profile.get('organization', {})
        profile = {
            'email': account.get('email', ''),
            'plan': organization.get('organization_type', '').replace('_', ' ').title(),
        }

    usage_rows: list[dict[str, Any]] = []
    if snap.usage:
        for field, entry in usage_entries(snap.usage):
            usage_rows.append(_usage_row(field, entry))

    extra = None
    if snap.usage:
        extra_data = snap.usage.get('extra_usage')
        if isinstance(extra_data, dict) and extra_data.get('is_enabled'):
            limit = float(extra_data.get('monthly_limit', 0) or 0)
            used = float(extra_data.get('used_credits', 0) or 0)
            if limit > 0:
                percent = used / limit * 100
                extra = {
                    'pct_text': f'{percent:.0f}%',
                    'tone': tone_for_percent(percent),
                    'bar_text': build_text_bar(percent),
                    'spent_text': T['extra_usage_spent'].format(
                        used=format_credits(used),
                        limit=format_credits(limit),
                    ),
                }

    return {
        'id': provider_id,
        'title': _PROVIDER_TITLES.get(provider_id, provider_id.title()),
        'icon': '',
        'profile': profile,
        'session_usage': _session_usage_row(snap.usage),
        'usage': usage_rows,
        'extra': extra,
        'metrics': _local_metrics(provider_id),
        'status': _status_dict(snap, next_poll_time),
    }


def _local_metrics(provider_id: str) -> dict[str, Any]:
    """Build local token and cost metrics for one provider."""
    try:
        summary = local_usage_summary(provider_id)
    except Exception:
        summary = LocalUsageSummary(None, None, None, None, None)

    return {
        'items': [
            {'label': T['local_today'], 'value': _format_usd(summary.today_cost_usd)},
            {'label': T['local_30d_cost'], 'value': _format_usd(summary.total_cost_usd)},
            {'label': T['local_30d_tokens'], 'value': _format_tokens(summary.total_tokens)},
            {'label': T['local_latest_tokens'], 'value': _format_tokens(summary.latest_tokens)},
            {'label': T['local_top_model'], 'value': summary.top_model or '—'},
        ],
        'note': T['local_estimate_note'],
    }


def _format_usd(value: float | None) -> str:
    """Format a USD amount for local log estimates."""
    if value is None:
        return '—'
    return f'${value:,.2f}'


def _format_tokens(value: int | None) -> str:
    """Format a token count compactly."""
    if value is None:
        return '—'
    if value >= 1_000_000_000:
        return f'{value / 1_000_000_000:.1f}B'
    if value >= 1_000_000:
        return f'{value / 1_000_000:.1f}M'
    if value >= 1_000:
        return f'{value / 1_000:.0f}K'
    return str(value)


def init_config(
    snap: CacheSnapshot | DashboardSnapshot,
    *,
    pinned: bool,
    next_poll_time: float | None = None,
    provider_view: str | None = None,
) -> dict[str, Any]:
    """Build the frontend initialization config dict."""
    return {
        'colors': {
            'bg': BG,
            'fg': FG,
            'fg_dim': FG_DIM,
            'fg_heading': FG_HEADING,
            'fg_link': FG_LINK,
            'bar_bg': BAR_BG,
            'bar_fg': BAR_FG,
            'bar_fg_mid': BAR_FG_MID,
            'bar_fg_warn': BAR_FG_WARN,
            'bar_fg_danger': BAR_FG_DANGER,
        },
        't': {
            'title': T['dashboard_title'],
            'all': T['all_providers'],
            'account': T['account'],
            'email': T['email'],
            'plan': T['plan'],
            'usage': T['usage'],
            'extra_usage': T['extra_usage'],
            'local_metrics': T['local_metrics'],
            'view_brief': T['view_brief'],
            'view_details': T['view_details'],
            'session_unavailable': T['session_unavailable'],
            'status_updated_s': T['status_updated_s'],
            'status_updated': T['status_updated'],
            'status_next_update': T['status_next_update'],
            'status_refreshing': T['status_refreshing'],
            'pin_on': T['pin_on'],
            'pin_off': T['pin_off'],
            'duration_hm': T['duration_hm'],
            'duration_m': T['duration_m'],
            'duration_s': T['duration_s'],
        },
        'app_version': __version__,
        'window': {'pinned': pinned},
        'data': snapshot_to_dict(snap, next_poll_time=next_poll_time, provider_view=provider_view),
    }


class _PopupApi:
    """pywebview API exposed to the frontend page."""

    def __init__(self, popup: UsagePopup) -> None:
        self._popup = popup

    def hide_window(self) -> None:
        self._popup.hide()

    def toggle_pin(self) -> dict[str, bool]:
        return {'pinned': self._popup.toggle_pin()}

    def report_height(self, height: int) -> None:
        self._popup.report_height(height)

    def set_provider_view(self, view_id: str) -> str:
        return self._popup.set_provider_view(view_id)


class UsagePopup:
    """Desktop popup window controller."""

    WIDTH = 380

    def __init__(self, app: CCMonitor) -> None:
        self.app = app
        self._running = True
        self._pinned = False
        self._visible = False
        self._pending_show = True
        self._layout_ready = False
        self._popup_hwnd = 0
        self._last_height = 320
        self._last_version = self._current_snapshot().version
        self._last_next_poll_time = app._next_poll_time

        api = _PopupApi(self)
        self._window = webview.create_window(
            '',
            url=str(_POPUP_DIR / 'popup.html'),
            width=self.WIDTH,
            height=self._last_height,
            resizable=False,
            frameless=True,
            shadow=False,
            easy_drag=False,
            hidden=True,
            on_top=False,
            background_color=BG,
            js_api=api,
        )
        self._window.events.loaded += self._on_loaded
        self._window.events.closed += self._on_window_closed

    @property
    def pinned(self) -> bool:
        return self._pinned

    def show(self) -> None:
        """Show the window and bring it to the front."""
        self._pending_show = True
        if not self._layout_ready or not self._running:
            return

        try:
            self._window.show()
            self._window.restore()
        except Exception:
            return

        self._apply_pin_state(activate=self._pinned)
        self._bring_to_front()
        self._visible = True

    def hide(self) -> None:
        """Hide the window to the tray without exiting the process."""
        self._pending_show = False
        if not self._layout_ready or not self._running:
            return

        try:
            self._window.hide()
        except Exception:
            return

        self._visible = False

    def close(self) -> None:
        """Destroy the window."""
        self._running = False
        self._pending_show = False
        try:
            self._window.destroy()
        except Exception:
            pass

    def toggle_pin(self) -> bool:
        """Toggle the always-on-top pin state."""
        self._pinned = not self._pinned
        if self._layout_ready:
            self._apply_pin_state(activate=self._pinned and self._visible)
            if self._pinned and self._visible:
                self._bring_to_front()
        return self._pinned

    def report_height(self, height: int) -> None:
        """Handle a content height report from the frontend."""
        if not height:
            return

        if height != self._last_height or not self._layout_ready:
            self._last_height = height
            self._resize_and_position(height)

        if not self._layout_ready:
            self._reveal_after_layout()

    def set_provider_view(self, view_id: str) -> str:
        setter = getattr(self.app, 'set_tray_provider_from_view', None)
        if callable(setter):
            return setter(view_id)
        return self._provider_view()

    def sync_provider_view(self) -> None:
        if not self._running or not self._layout_ready:
            return

        try:
            self._window.evaluate_js(f'syncProviderView({json.dumps(self._provider_view())})')
        except Exception:
            return

    def _on_loaded(self) -> None:
        """Inject init data after page load and start the incremental update loop."""
        config = init_config(
            self._current_snapshot(),
            pinned=self._pinned,
            next_poll_time=self.app._next_poll_time,
            provider_view=self._provider_view(),
        )
        self._window.evaluate_js(f'init({json.dumps(config)})')
        self._refresh_tray_from_cache_snapshot()

        self._popup_hwnd = self._window.native.Handle.ToInt32()
        self._prepare_native_window()
        self._window.show()
        threading.Thread(target=self._update_loop, daemon=True).start()

    def _on_window_closed(self) -> None:
        self._running = False
        self._visible = False

    def _prepare_native_window(self) -> None:
        """Hide the taskbar icon and keep the window transparent until first layout."""
        ex_style = ctypes.windll.user32.GetWindowLongW(self._popup_hwnd, _GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            self._popup_hwnd,
            _GWL_EXSTYLE,
            (ex_style | _WS_EX_TOOLWINDOW | _WS_EX_LAYERED) & ~_WS_EX_APPWINDOW,
        )
        ctypes.windll.user32.SetLayeredWindowAttributes(self._popup_hwnd, 0, 0, _LWA_ALPHA)
        self._apply_rounded_corners()

    def _reveal_after_layout(self) -> None:
        """Reveal the real window after the first layout pass completes."""
        ex_style = ctypes.windll.user32.GetWindowLongW(self._popup_hwnd, _GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(self._popup_hwnd, _GWL_EXSTYLE, ex_style & ~_WS_EX_LAYERED)
        self._layout_ready = True
        self._apply_pin_state(activate=False)

        if self._pending_show:
            self.show()
        else:
            self.hide()

    def _update_loop(self) -> None:
        """Poll for cache version changes and push updates to the frontend."""
        while self._running:
            time.sleep(_CHECK_MS / 1000)
            if not self._running or not self._layout_ready:
                continue

            try:
                snap = self._current_snapshot()
                next_poll_time = self.app._next_poll_time
                if snap.version == self._last_version and next_poll_time == self._last_next_poll_time:
                    continue

                self._last_version = snap.version
                self._last_next_poll_time = next_poll_time
                payload = snapshot_to_dict(snap, next_poll_time=next_poll_time, provider_view=self._provider_view())
                self._window.evaluate_js(f'updateData({json.dumps(payload)})')
                self._refresh_tray_from_cache_snapshot()
            except Exception:
                self._running = False

    def _current_snapshot(self) -> CacheSnapshot | DashboardSnapshot:
        """Return the app dashboard snapshot, with a single-cache fallback for tests."""
        dashboard_cache = getattr(self.app, 'dashboard_cache', None)
        if dashboard_cache is not None:
            return dashboard_cache.snapshot
        return self.app.cache.snapshot

    def _provider_view(self) -> str:
        provider_view = getattr(self.app, 'provider_view', None)
        if isinstance(provider_view, str):
            return _normalize_provider_view(provider_view)
        return _provider_view_from_tray(getattr(self.app, '_tray_provider', None))

    def _refresh_tray_from_cache_snapshot(self) -> None:
        """让托盘复用已经展示到窗口里的 cache 数据。"""
        refresh_tray = getattr(self.app, 'refresh_tray_from_cache_snapshot', None)
        if refresh_tray is not None:
            refresh_tray()

    def _bring_to_front(self) -> None:
        """Bring the window to the foreground while preserving the current pin state."""
        if not self._popup_hwnd:
            return

        ctypes.windll.user32.ShowWindow(self._popup_hwnd, _SW_RESTORE)
        ctypes.windll.user32.BringWindowToTop(self._popup_hwnd)
        ctypes.windll.user32.SetForegroundWindow(self._popup_hwnd)

    def _apply_pin_state(self, *, activate: bool) -> None:
        """Toggle always-on-top via native Win32 calls to avoid pywebview callback deadlocks."""
        if not self._popup_hwnd:
            return

        insert_after = _HWND_TOPMOST if self._pinned else _HWND_NOTOPMOST
        flags = _SWP_NOMOVE | _SWP_NOSIZE
        if not activate:
            flags |= _SWP_NOACTIVATE

        ctypes.windll.user32.SetWindowPos(self._popup_hwnd, insert_after, 0, 0, 0, 0, flags)

    def _apply_rounded_corners(self) -> None:
        """Enable system-level rounded corners, falling back silently to CSS corners."""
        dwmapi = getattr(ctypes.windll, 'dwmapi', None)
        if dwmapi is None:
            return

        corner_preference = ctypes.c_int(_DWMWCP_ROUND)
        try:
            dwmapi.DwmSetWindowAttribute(
                self._popup_hwnd,
                _DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(corner_preference),
                ctypes.sizeof(corner_preference),
            )
        except Exception:
            return

    def _tray_position(self, physical_width: int, _physical_height: int) -> tuple[int, int]:
        """Calculate the top-right corner position on the taskbar's monitor for first show."""
        tray_hwnd = ctypes.windll.user32.FindWindowW('Shell_TrayWnd', None)
        hmon = ctypes.windll.user32.MonitorFromWindow(tray_hwnd, 2)

        monitor_info = MONITORINFO()
        monitor_info.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(monitor_info))
        work = monitor_info.rcWork

        dpi = ctypes.windll.user32.GetDpiForWindow(self._popup_hwnd) or ctypes.windll.user32.GetDpiForSystem()
        scale = dpi / BASELINE_DPI
        margin = 12

        x = work.right - physical_width - margin
        y = work.top + margin

        return int(x / scale), int(y / scale)

    def _resize_and_position(self, height: int) -> None:
        """Resize the window using pywebview logical pixels."""
        dpi = ctypes.windll.user32.GetDpiForWindow(self._popup_hwnd) or ctypes.windll.user32.GetDpiForSystem()
        scale = dpi / BASELINE_DPI
        physical_width = int(self.WIDTH * scale)
        physical_height = int(height * scale)

        self._window.resize(self.WIDTH, height)
        if not self._layout_ready:
            x, y = self._tray_position(physical_width, physical_height)
            self._window.move(x, y)
