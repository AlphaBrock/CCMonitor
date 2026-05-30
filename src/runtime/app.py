"""
Application
=============

System tray application class with adaptive polling and event handling.
"""
from __future__ import annotations

import ctypes
import math
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timedelta, timezone
from typing import Any

from .cache import DashboardCache, UsageCache
from .idle import get_idle_seconds, is_workstation_locked
from src.integrations.api import api_headers, auth_warning_text
from src import __version__
from src.integrations.autostart import is_autostart_enabled, set_autostart, sync_autostart_path
from src.integrations.claude_cli import PROJECT_URL, check_latest_version
from src.integrations.command import run_event_command
from src.presentation.formatting import elapsed_pct, field_period, format_credits, format_dashboard_tooltip, parse_field_name, popup_label
from src.presentation.i18n import ACTIVE_LANG, T, available_languages
from src.presentation.settings import (
    ALERT_TIME_AWARE, ALERT_TIME_AWARE_BELOW, ICON_FIELDS, IDLE_PAUSE, LANGUAGE,
    ON_RESET_COMMAND, ON_STARTUP_COMMAND, ON_THRESHOLD_COMMAND,
    POLL_ERROR, POLL_FAST, POLL_FAST_EXTRA, POLL_INTERVAL, TRAY_PROVIDER, get_alert_thresholds,
    save_language_setting, save_tray_provider,
)
from src.ui import win_tray as tray
from src.ui.popup import UsagePopup
from src.ui.tray_icon import create_icon_image, create_status_image, taskbar_uses_light_theme, watch_theme_change

__all__ = ['CCMonitor', 'crash_log']

_VALID_TRAY_PROVIDERS = frozenset({'auto', 'claude', 'codex'})
_TRAY_PROVIDER_TO_VIEW = {'auto': 'all', 'claude': 'claude', 'codex': 'codex'}
_PROVIDER_VIEW_TO_TRAY = {'all': 'auto', 'claude': 'claude', 'codex': 'codex'}


def _future_iso(**kwargs: float) -> str:
    """Return an ISO 8601 timestamp offset from now by the given timedelta kwargs."""
    return (datetime.now(timezone.utc) + timedelta(**kwargs)).isoformat()


class CCMonitor:
    """System tray application displaying Claude and Codex usage."""

    def __init__(self) -> None:
        """Set up the tray icon with context menu and polling state."""
        self.running = True
        self.dashboard_cache = DashboardCache()
        self.cache: UsageCache = self.dashboard_cache.primary

        # Last raw API response (may contain 'error') - for icon and polling decisions
        self._last_response: dict[str, Any] = {}

        # Latest raw response per provider - drives the tray provider selector
        self._last_responses: dict[str, dict[str, Any]] = {}

        # Provider shown in the tray icon + tooltip ('auto' shows all)
        self._tray_provider = TRAY_PROVIDER

        # Notification state
        self._prev_utilization: dict[str, float] = {}
        self._prev_account_uuid: str | None = None
        self._first_update_done = False
        self._notified_thresholds: dict[str, float] = {}

        # Adaptive polling state
        self._fast_polls_remaining = 0
        self._idle_reset_pending = False
        self._deferred_notifications: dict[str, tuple[str, str]] = {}

        # Popup window state
        self.popup: UsagePopup | None = None
        self._next_poll_time: float | None = None

        # Theme state
        self._light_taskbar = taskbar_uses_light_theme()

        self.restart_requested = False

        self._update_checking = False

        self.icon = tray.Icon(
            'usage_monitor',
            icon=create_icon_image(0, 0, self._light_taskbar),
            title=T['loading'],
            menu=tray.Menu(
                tray.MenuItem(T['menu_show'], self.on_show_popup, default=True),
                tray.SEPARATOR,
                tray.MenuItem(
                    T['autostart'], self.on_toggle_autostart,
                    checked=lambda item: is_autostart_enabled(),
                    visible=getattr(sys, 'frozen', False),
                ),
                tray.MenuItem(T['menu_provider'], tray.Menu(
                    tray.MenuItem(
                        T['provider_auto'], self._make_provider_handler('auto'),
                        checked=lambda item: self._tray_provider == 'auto', radio=True,
                    ),
                    tray.SEPARATOR,
                    tray.MenuItem(
                        'Claude', self._make_provider_handler('claude'),
                        checked=lambda item: self._tray_provider == 'claude', radio=True,
                    ),
                    tray.MenuItem(
                        'Codex', self._make_provider_handler('codex'),
                        checked=lambda item: self._tray_provider == 'codex', radio=True,
                    ),
                )),
                tray.MenuItem(T['menu_language'], tray.Menu(
                    tray.MenuItem(
                        T['menu_language_auto'],
                        self._make_lang_handler(''),
                        checked=lambda item: not LANGUAGE,
                    ),
                    tray.SEPARATOR,
                    *self._build_language_items(),
                )),
                tray.MenuItem(T['test_commands'], tray.Menu(
                    tray.MenuItem(T['test_reset_5h'], self.on_test_reset_5h, enabled=bool(ON_RESET_COMMAND)),
                    tray.MenuItem(T['test_reset_7d'], self.on_test_reset_7d, enabled=bool(ON_RESET_COMMAND)),
                    tray.MenuItem(T['test_threshold_5h'], self.on_test_threshold_5h, enabled=bool(ON_THRESHOLD_COMMAND)),
                    tray.MenuItem(T['test_threshold_7d'], self.on_test_threshold_7d, enabled=bool(ON_THRESHOLD_COMMAND)),
                    tray.MenuItem(T['test_startup'], self.on_test_startup, enabled=bool(ON_STARTUP_COMMAND)),
                ), enabled=bool(ON_RESET_COMMAND or ON_STARTUP_COMMAND or ON_THRESHOLD_COMMAND)),
                tray.MenuItem(T['check_update'], self.on_check_update),
                tray.MenuItem(T['restart'], self.on_restart),
                tray.SEPARATOR,
                tray.MenuItem(T['menu_project'], self.on_open_project),
                tray.SEPARATOR,
                tray.MenuItem(T['quit'], self.on_quit),
            ),
        )

    @property
    def provider_view(self) -> str:
        return _TRAY_PROVIDER_TO_VIEW.get(getattr(self, '_tray_provider', 'auto'), 'all')

    # Menu actions

    def on_show_popup(self, icon: Any = None, item: Any = None) -> None:
        self._ensure_popup().show()

    def on_toggle_autostart(self, icon: Any = None, item: Any = None) -> None:
        set_autostart(not is_autostart_enabled())

    def on_restart(self, icon: Any = None, item: Any = None) -> None:
        self.restart_requested = True
        self.on_quit(icon, item)

    def on_open_project(self, icon: Any = None, item: Any = None) -> None:
        webbrowser.open(PROJECT_URL)

    def on_check_update(self, icon: Any = None, item: Any = None) -> None:
        if self._update_checking:
            return
        self._update_checking = True
        threading.Thread(target=self._do_check_update, daemon=True).start()

    def _do_check_update(self) -> None:
        """Run the update check in a background thread."""
        try:
            result = check_latest_version(__version__)
            if result.error:
                self.icon.notify(T['update_check_error'], T['popup_title'])
            elif result.available:
                self.icon.notify(
                    T['update_available'].format(new=result.version, current=__version__),
                    T['update_available_title'],
                )
                webbrowser.open(result.url)
            else:
                self.icon.notify(
                    T['update_latest'].format(current=__version__),
                    T['popup_title'],
                )
        except Exception:
            self.icon.notify(T['update_check_error'], T['popup_title'])
        finally:
            self._update_checking = False

    def _build_language_items(self) -> list:
        """Build tray menu items for each available language."""
        items = []
        for code, name in available_languages():
            items.append(tray.MenuItem(
                name,
                self._make_lang_handler(code),
                checked=lambda item, c=code: ACTIVE_LANG == c and bool(LANGUAGE),
            ))
        return items

    def _make_lang_handler(self, lang_code: str):
        """Return a menu click handler that switches to the given language."""
        def handler(icon: Any = None, item: Any = None) -> None:
            save_language_setting(lang_code)
            self.restart_requested = True
            self.on_quit(icon, item)
        return handler

    def _make_provider_handler(self, provider: str):
        """Return a menu click handler that switches the tray display provider.

        Applied live (no restart): tray display and popup provider filtering
        change together. Alerts and event commands keep using the configured
        primary provider.
        """
        def handler(icon: Any = None, item: Any = None) -> None:
            self.set_tray_provider(provider)
        return handler

    def set_tray_provider(self, provider: str) -> str:
        if provider not in _VALID_TRAY_PROVIDERS:
            return self._tray_provider

        self._tray_provider = provider
        save_tray_provider(provider)
        self._render_tray()
        popup = getattr(self, 'popup', None)
        if popup is not None:
            popup.sync_provider_view()

        return self._tray_provider

    def set_tray_provider_from_view(self, view_id: str) -> str:
        provider = _PROVIDER_VIEW_TO_TRAY.get(view_id)
        if provider is None:
            return self.provider_view

        self.set_tray_provider(provider)
        return self.provider_view

    def on_test_reset_5h(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(ON_RESET_COMMAND, {
            'USAGE_MONITOR_EVENT': 'reset',
            'USAGE_MONITOR_VARIANT': 'five_hour',
            'USAGE_MONITOR_UTILIZATION': '0',
            'USAGE_MONITOR_PREV_UTILIZATION': '95',
            'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': '0',
            'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': '45',
            'USAGE_MONITOR_RESETS_AT': _future_iso(hours=5),
            'USAGE_MONITOR_TITLE': T['notify_reset_title'],
            'USAGE_MONITOR_MESSAGE': T['notify_reset'],
        })

    def on_test_reset_7d(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(ON_RESET_COMMAND, {
            'USAGE_MONITOR_EVENT': 'reset',
            'USAGE_MONITOR_VARIANT': 'seven_day',
            'USAGE_MONITOR_UTILIZATION': '0',
            'USAGE_MONITOR_PREV_UTILIZATION': '99',
            'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': '12',
            'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': '0',
            'USAGE_MONITOR_RESETS_AT': _future_iso(days=7),
            'USAGE_MONITOR_TITLE': T['notify_reset_title'],
            'USAGE_MONITOR_MESSAGE': T['notify_reset'],
        })

    def on_test_threshold_5h(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(ON_THRESHOLD_COMMAND, {
            'USAGE_MONITOR_EVENT': 'threshold',
            'USAGE_MONITOR_VARIANT': 'five_hour',
            'USAGE_MONITOR_UTILIZATION': '82',
            'USAGE_MONITOR_THRESHOLD': '80',
            'USAGE_MONITOR_RESETS_AT': _future_iso(hours=3),
            'USAGE_MONITOR_TITLE': T['notify_threshold_title'],
            'USAGE_MONITOR_MESSAGE': T['notify_threshold_generic'].format(label=popup_label('five_hour'), pct='82'),
        })

    def on_test_threshold_7d(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(ON_THRESHOLD_COMMAND, {
            'USAGE_MONITOR_EVENT': 'threshold',
            'USAGE_MONITOR_VARIANT': 'seven_day',
            'USAGE_MONITOR_UTILIZATION': '81',
            'USAGE_MONITOR_THRESHOLD': '80',
            'USAGE_MONITOR_RESETS_AT': _future_iso(days=4),
            'USAGE_MONITOR_TITLE': T['notify_threshold_title'],
            'USAGE_MONITOR_MESSAGE': T['notify_threshold_generic'].format(label=popup_label('seven_day'), pct='81'),
        })

    def on_test_startup(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(ON_STARTUP_COMMAND, {
            'USAGE_MONITOR_EVENT': 'startup',
            'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': '0',
            'USAGE_MONITOR_RESETS_AT_FIVE_HOUR': '',
            'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': '45',
            'USAGE_MONITOR_RESETS_AT_SEVEN_DAY': _future_iso(days=3),
        })

    def on_quit(self, icon: Any = None, item: Any = None) -> None:
        self.running = False
        if self.popup is not None:
            self.popup.close()
        self.icon.stop()

    # Popup

    def _ensure_popup(self) -> UsagePopup:
        """Create the popup window on first access."""
        if self.popup is None:
            self.popup = UsagePopup(self)
        return self.popup

    # Tray rendering

    def _icon_response(self) -> dict[str, Any]:
        """Return the raw response that drives the tray icon glyph and bars.

        ``'auto'`` uses the primary provider (default Claude); an explicit
        ``'codex'``/``'claude'`` selection uses that provider's response.
        """
        if self._tray_provider == 'auto':
            return self._last_response
        return self._last_responses.get(self._tray_provider, {})

    def _sync_tray_responses_from_cache(self) -> bool:
        """从 dashboard cache 补齐托盘提示需要的 provider 数据。"""
        changed = False
        snapshot = self.dashboard_cache.snapshot
        for provider_id, provider_snapshot in snapshot.providers.items():
            if not provider_snapshot.usage:
                continue

            current_response = self._last_responses.get(provider_id)
            if not current_response:
                self._last_responses[provider_id] = provider_snapshot.usage
                changed = True

            if provider_id == self.dashboard_cache.primary_provider and not self._last_response:
                self._last_response = provider_snapshot.usage
                changed = True

        return changed

    def refresh_tray_from_cache_snapshot(self) -> None:
        """在 UI 已收到 cache 数据但托盘尚未同步时刷新托盘。"""
        if self._sync_tray_responses_from_cache():
            self._render_tray()

    def _render_tray(self) -> None:
        """Re-render tray icon and tooltip from current state."""
        self._sync_tray_responses_from_cache()
        data = self._icon_response()
        if 'error' in data:
            self.icon.icon = create_status_image('C!' if data.get('auth_error') else '!', self._light_taskbar)
        else:
            top_field, top_mode = ICON_FIELDS[0].split(':', 1) if ':' in ICON_FIELDS[0] else (ICON_FIELDS[0], 'utilization')
            bottom_field, bottom_mode = ICON_FIELDS[1].split(':', 1) if ':' in ICON_FIELDS[1] else (ICON_FIELDS[1], 'utilization')
            top_entry = data.get(top_field) or {}
            bottom_entry = data.get(bottom_field) or {}
            pct_top = top_entry.get('utilization', 0) or 0
            pct_bottom = bottom_entry.get('utilization', 0) or 0
            top_period = field_period(top_field)
            bottom_period = field_period(bottom_field)
            time_pct_top = elapsed_pct(top_entry.get('resets_at', ''), top_period) if top_mode == 'overage' and top_period else None
            time_pct_bottom = elapsed_pct(bottom_entry.get('resets_at', ''), bottom_period) if bottom_mode == 'overage' and bottom_period else None
            extra = data.get('extra_usage') or {}
            extra_limit = extra.get('monthly_limit') or 0
            extra_used = extra.get('used_credits') or 0
            extra_usage_available = bool(extra.get('is_enabled')) and extra_limit > 0 and extra_used < extra_limit
            self.icon.icon = create_icon_image(
                pct_top, pct_bottom, self._light_taskbar,
                mode_top=top_mode, mode_bottom=bottom_mode,
                time_pct_top=time_pct_top, time_pct_bottom=time_pct_bottom,
                extra_usage_available=extra_usage_available,
            )
        self.icon.title = format_dashboard_tooltip(self._last_responses, self._tray_provider)

    def _on_theme_changed(self) -> None:
        """Re-render the tray icon when the Windows theme changes."""
        light = taskbar_uses_light_theme()
        if light == self._light_taskbar:
            return

        self._light_taskbar = light
        if self._last_response or self._last_responses:
            self._render_tray()

    # Update orchestration

    def update(self) -> None:
        """Request a data refresh from the cache and process the result."""
        provider_data_changed = False
        if self.cache is self.dashboard_cache.primary:
            dashboard_result = self.dashboard_cache.update_all()
            result = dashboard_result.primary
            for provider_id, provider_result in dashboard_result.providers.items():
                if provider_result.data is not None:
                    self._last_responses[provider_id] = provider_result.data
                    provider_data_changed = True
        else:
            result = self.cache.update()
            if result.data is not None:
                self._last_responses[self.dashboard_cache.primary_provider] = result.data
                provider_data_changed = True
        snapshot_data_changed = self._sync_tray_responses_from_cache()
        if result.data is None:
            if provider_data_changed or snapshot_data_changed:
                self._render_tray()
            return

        self._last_response = result.data
        self._render_tray()

        # Handle CLI update notification from token refresh
        if result.token_refresh and result.token_refresh.updated:
            self.icon.notify(
                T['notify_update'].format(old=result.token_refresh.old_version, new=result.token_refresh.new_version),
                T['notify_update_title'],
            )

        if 'error' in result.data:
            return

        # Detect account switch: re-fetch profile if the access token changed, then compare UUIDs.
        # When the user runs 'claude auth login', the token changes and the next profile fetch
        # returns a different account UUID, preventing a false quota-reset notification.
        self.cache.ensure_profile()
        current_profile = self.cache.profile
        current_account_uuid = current_profile.get('account', {}).get('uuid') if isinstance(current_profile, dict) else None
        if self._prev_account_uuid is not None and current_account_uuid is not None and current_account_uuid != self._prev_account_uuid:
            email = current_profile.get('account', {}).get('email', '')
            message = T['notify_account_switched'].format(email=email) if email else T['notify_account_switched_title']
            self._notify_or_defer('account_switched', message, T['notify_account_switched_title'])
            self._prev_utilization = {}
            self._notified_thresholds = {}
            self._prev_account_uuid = current_account_uuid
            return
        self._prev_account_uuid = current_account_uuid

        # Collect all quota fields with utilization (extra_usage has a different structure)
        quota_fields: dict[str, float] = {}
        for key, value in result.data.items():
            if key == 'extra_usage':
                continue
            if isinstance(value, dict) and 'utilization' in value:
                quota_fields[key] = value.get('utilization', 0) or 0

        # Notify when quota resets after being nearly exhausted, but only if no other quota is blocking usage.
        # While idle/locked, defer notifications until the user returns (avoids lock screen privacy concerns).
        for key, pct in quota_fields.items():
            prev = self._prev_utilization.get(key)
            if prev is None:
                continue

            parsed = parse_field_name(key)
            if parsed is None:
                continue

            _, unit, _ = parsed
            reset_threshold = 95 if unit == 'hour' else 98
            any_blocking = any(other_pct >= 99 for other_key, other_pct in quota_fields.items() if other_key != key)

            if prev > reset_threshold and pct < prev and not any_blocking:
                self._notify_or_defer('reset', T['notify_reset'], T['notify_reset_title'])

        # Run reset command on any detected usage drop (independent of notification threshold)
        for key, pct in quota_fields.items():
            prev = self._prev_utilization.get(key)
            if prev is not None and pct < prev:
                self._run_reset_command(key, pct, prev, data=result.data, entry=result.data.get(key, {}))
                self._idle_reset_pending = False

        self._check_threshold_alerts(result.data)

        # Adaptive polling: speed up when icon top field usage is increasing
        icon_top_key = ICON_FIELDS[0].split(':', 1)[0]
        icon_top_pct = quota_fields.get(icon_top_key, 0)
        icon_top_prev = self._prev_utilization.get(icon_top_key)
        if icon_top_prev is not None and icon_top_pct > icon_top_prev:
            self._fast_polls_remaining = POLL_FAST_EXTRA + 1
        elif self._fast_polls_remaining > 0:
            self._fast_polls_remaining -= 1

        self._prev_utilization = quota_fields

        if not self._first_update_done:
            self._run_startup_command(result.data)

        self._first_update_done = True

    # Notifications

    def _notify_or_defer(self, category: str, message: str, title: str) -> None:
        """Show a notification immediately, or defer it if the user is away.

        Parameters
        ----------
        category : str
            Deduplication key (e.g. ``'reset'``, ``'threshold_five_hour'``).
            While deferred, only the latest notification per category is
            kept so the user does not get a flood on return.
        message : str
            Notification body text.
        title : str
            Notification title.
        """
        if self._is_user_away():
            self._deferred_notifications[category] = (message, title)
        else:
            self.icon.notify(message, title)

    def _flush_deferred_notifications(self) -> None:
        """Show all deferred notifications and clear the queue."""
        for message, title in self._deferred_notifications.values():
            self.icon.notify(message, title)
        self._deferred_notifications.clear()

    def _check_threshold_alerts(self, data: dict[str, Any]) -> None:
        """Show a notification when usage crosses a configured threshold.

        Dynamically detects all quota fields in the API response.  For
        each field, finds the highest threshold exceeded by current
        utilization.  If it exceeds a threshold not yet notified, shows a
        single notification with the current usage percentage.  When usage
        drops (e.g. after reset), tracking resets so thresholds can
        re-trigger in the next cycle.
        """
        for variant_key, entry in data.items():
            if variant_key == 'extra_usage':
                continue
            if not isinstance(entry, dict) or entry.get('utilization') is None:
                continue

            pct = entry['utilization']
            thresholds = get_alert_thresholds(variant_key)
            if not thresholds:
                continue

            exceeded = [t for t in thresholds if pct >= t]
            highest_exceeded = max(exceeded) if exceeded else 0
            last_notified = self._notified_thresholds.get(variant_key, 0)

            if ALERT_TIME_AWARE and highest_exceeded > last_notified and highest_exceeded < ALERT_TIME_AWARE_BELOW:
                period = field_period(variant_key)
                if period:
                    time_pct = elapsed_pct(entry.get('resets_at'), period)
                    if time_pct is not None and pct <= time_pct:
                        self._notified_thresholds[variant_key] = highest_exceeded
                        continue

            if highest_exceeded > last_notified:
                title = T['notify_threshold_title']
                label = popup_label(variant_key)
                message = T['notify_threshold_generic'].format(label=label, pct=f'{pct:.0f}')
                self._notify_or_defer(f'threshold_{variant_key}', message, title)
                self._run_threshold_command(variant_key, pct, highest_exceeded, entry, title, message)
                self._notified_thresholds[variant_key] = highest_exceeded
            elif highest_exceeded < last_notified:
                self._notified_thresholds[variant_key] = highest_exceeded

        self._check_extra_usage_alerts(data)

    def _check_extra_usage_alerts(self, data: dict[str, Any]) -> None:
        """Show a notification when extra usage crosses a configured threshold.

        Extra usage has a different data format (``used_credits`` /
        ``monthly_limit``) and no time-based reset, so it is handled
        separately from the sliding-window quotas.
        """
        extra = data.get('extra_usage')
        if not extra or not extra.get('is_enabled'):
            return

        limit = extra.get('monthly_limit', 0) or 0
        if limit <= 0:
            return

        used = extra.get('used_credits', 0) or 0
        pct = used / limit * 100

        thresholds = get_alert_thresholds('extra_usage')
        if not thresholds:
            return

        exceeded = [t for t in thresholds if pct >= t]
        highest_exceeded = max(exceeded) if exceeded else 0
        last_notified = self._notified_thresholds.get('extra_usage', 0)

        if highest_exceeded > last_notified:
            title = T['notify_threshold_title']
            message = T['notify_threshold_extra_usage'].format(
                pct=f'{pct:.0f}', used=format_credits(used), limit=format_credits(limit),
            )
            self._notify_or_defer('threshold_extra_usage', message, title)
            self._run_threshold_command(
                'extra_usage', pct, highest_exceeded, extra, title, message,
                extra_used=format_credits(used), extra_limit=format_credits(limit),
            )
            self._notified_thresholds['extra_usage'] = highest_exceeded
        elif highest_exceeded < last_notified:
            self._notified_thresholds['extra_usage'] = highest_exceeded

    # Event commands

    def _run_startup_command(self, data: dict[str, Any]) -> None:
        """Run the user-configured startup command if set.

        Fires once after the first successful API update.  Receives the
        full quota state so the command can decide what to do (e.g. only
        ping Claude when no five-hour session is active).
        """
        if not ON_STARTUP_COMMAND:
            return

        env_vars: dict[str, str] = {
            'USAGE_MONITOR_EVENT': 'startup',
        }
        for key, entry in data.items():
            if key == 'extra_usage' or not isinstance(entry, dict) or 'utilization' not in entry:
                continue
            env_vars[f'USAGE_MONITOR_UTILIZATION_{key.upper()}'] = str(round(entry.get('utilization', 0) or 0))
            env_vars[f'USAGE_MONITOR_RESETS_AT_{key.upper()}'] = entry.get('resets_at') or ''

        extra = data.get('extra_usage') or {}
        if extra.get('is_enabled'):
            limit = extra.get('monthly_limit', 0) or 0
            used = extra.get('used_credits', 0) or 0
            env_vars['USAGE_MONITOR_EXTRA_USED'] = format_credits(used)
            env_vars['USAGE_MONITOR_EXTRA_LIMIT'] = format_credits(limit)

        run_event_command(ON_STARTUP_COMMAND, env_vars)

    def _run_reset_command(
        self, variant: str, pct: float, prev_pct: float, *, data: dict[str, Any], entry: dict[str, Any],
    ) -> None:
        """Run the user-configured reset command if set."""
        if not ON_RESET_COMMAND:
            return

        pct_5h = (data.get('five_hour') or {}).get('utilization', 0) or 0
        pct_7d = (data.get('seven_day') or {}).get('utilization', 0) or 0
        run_event_command(ON_RESET_COMMAND, {
            'USAGE_MONITOR_EVENT': 'reset',
            'USAGE_MONITOR_VARIANT': variant,
            'USAGE_MONITOR_UTILIZATION': str(round(pct)),
            'USAGE_MONITOR_PREV_UTILIZATION': str(round(prev_pct)),
            'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': str(round(pct_5h)),
            'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': str(round(pct_7d)),
            'USAGE_MONITOR_RESETS_AT': entry.get('resets_at', ''),
            'USAGE_MONITOR_TITLE': T['notify_reset_title'],
            'USAGE_MONITOR_MESSAGE': T['notify_reset'],
        })

    def _run_threshold_command(
        self, variant: str, pct: float, threshold: float,
        entry: dict[str, Any], title: str, message: str,
        *, extra_used: str = '', extra_limit: str = '',
    ) -> None:
        """Run the user-configured threshold command if set.

        Skipped on the first update (before ``_first_update_done`` is set)
        so that already-exceeded thresholds at app startup do not trigger
        commands.  Notifications still fire - commands react to *events*,
        not *state*.
        """
        if not ON_THRESHOLD_COMMAND or not self._first_update_done:
            return

        env_vars = {
            'USAGE_MONITOR_EVENT': 'threshold',
            'USAGE_MONITOR_VARIANT': variant,
            'USAGE_MONITOR_UTILIZATION': str(round(pct)),
            'USAGE_MONITOR_THRESHOLD': str(round(threshold)),
            'USAGE_MONITOR_RESETS_AT': entry.get('resets_at', ''),
            'USAGE_MONITOR_TITLE': title,
            'USAGE_MONITOR_MESSAGE': message,
        }
        if extra_used:
            env_vars['USAGE_MONITOR_EXTRA_USED'] = extra_used
        if extra_limit:
            env_vars['USAGE_MONITOR_EXTRA_LIMIT'] = extra_limit

        run_event_command(ON_THRESHOLD_COMMAND, env_vars)

    # Polling

    def _seconds_until_next_reset(self) -> float | None:
        """Return seconds until the earliest upcoming quota reset, or None."""
        now = datetime.now(timezone.utc)
        earliest = None
        for key, entry in self._last_response.items():
            if not isinstance(entry, dict) or not entry.get('resets_at'):
                continue
            try:
                reset_time = datetime.fromisoformat(entry['resets_at'])
                seconds = (reset_time - now).total_seconds()
                if seconds > 0 and (earliest is None or seconds < earliest):
                    earliest = seconds
            except Exception:
                continue

        return earliest

    def _calculate_poll_interval(self) -> int:
        """Determine the next poll interval based on current state.

        Returns
        -------
        int
            Seconds to wait before the next poll.
        """
        data = self._last_response

        if data.get('rate_limited'):
            remaining = self.cache.rate_limit_remaining
            interval = max(math.ceil(remaining), POLL_INTERVAL) if remaining > 0 else POLL_INTERVAL
        elif 'error' in data:
            interval = POLL_ERROR
        elif self._fast_polls_remaining > 0:
            interval = POLL_FAST
        else:
            interval = POLL_INTERVAL

        # Align next poll to an imminent reset for faster feedback.
        # The +5s buffer guards against minor timing differences
        # (clocks, caches, processing delays). Follow-up uses POLL_FAST
        # regardless of user activity (quota was likely exhausted).
        next_reset = self._seconds_until_next_reset()
        if next_reset is not None and next_reset + 5 <= interval * 1.5:
            interval = max(int(next_reset) + 5, POLL_FAST)
            self._fast_polls_remaining = max(self._fast_polls_remaining, 2)

        return interval

    def _is_user_away(self) -> bool:
        """Return True if the user is idle or the workstation is locked."""
        if is_workstation_locked():
            return True
        return IDLE_PAUSE > 0 and get_idle_seconds() >= IDLE_PAUSE

    def _wait_for_activity(self, until: float | None = None) -> None:
        """Block until user activity resumes or the app is stopping.

        Parameters
        ----------
        until : float | None
            Optional deadline (``time.time()`` epoch).  When set, the
            wait ends even if the user is still away, allowing a
            time-critical poll (e.g. quota reset command) to proceed.
        """
        while self.running and self._is_user_away():
            if until is not None and time.time() >= until:
                break
            time.sleep(2)

    def poll_loop(self) -> None:
        """Poll the API in a loop with adaptive intervals.

        Pauses polling when the user is idle or the workstation is
        locked.  On resume, polls immediately if the regular interval
        has elapsed since the last successful fetch.
        """
        if self.cache is self.dashboard_cache.primary:
            self.dashboard_cache.ensure_profiles()
        else:
            self.cache.ensure_profile()
        while self.running:
            self.update()
            interval = self._calculate_poll_interval()

            target = time.time() + interval
            self._next_poll_time = target
            while self.running and time.time() < target:
                time.sleep(1)
                # If another thread (popup) fetched successfully,
                # push the next poll forward to avoid a redundant
                # fetch right after.
                lst = self.cache.last_success_time
                if lst is not None:
                    new_target = max(target, lst + interval)
                    if new_target != target:
                        target = new_target
                        self._next_poll_time = target

                # Pause polling while the user is away.
                # Regular polling stops entirely during idle/lock.
                # The only exception: when on_reset_command is configured
                # and a quota reset is due, the idle pause is interrupted
                # so the command fires on time.  The flag
                # _idle_reset_pending keeps polling at POLL_INTERVAL
                # until the reset is actually confirmed (usage drop) -
                # this covers server-side delays and transient network
                # errors.  The flag is cleared when update() detects the
                # drop, or when the user returns (they'll see it anyway).
                if self._is_user_away():
                    reset_deadline = None
                    if ON_RESET_COMMAND:
                        next_reset = self._seconds_until_next_reset()
                        if next_reset is not None:
                            reset_deadline = time.time() + next_reset + 5
                            self._idle_reset_pending = True
                        elif self._idle_reset_pending:
                            reset_deadline = time.time() + POLL_INTERVAL

                    self._wait_for_activity(until=reset_deadline)

                    if reset_deadline is not None and self._is_user_away():
                        # Woke up for a reset while still idle - poll once
                        break

                    # User returned - show any notifications deferred
                    # during idle and poll immediately if interval elapsed.
                    # _idle_reset_pending is intentionally kept: if the
                    # user locks again before a successful poll confirms
                    # the reset (e.g. network was down), idle polling
                    # must resume.  The flag is only cleared by update()
                    # when a usage drop is actually detected.
                    self._flush_deferred_notifications()
                    lst = self.cache.last_success_time
                    if lst is not None and time.time() - lst >= interval:
                        break

    # Lifecycle

    def _on_icon_ready(self, icon: Any) -> None:
        """Called by tray in a separate thread once the tray icon is set up."""
        try:
            icon.visible = True
            if getattr(sys, 'frozen', False):
                sync_autostart_path()
            if not api_headers():
                warning_body, warning_title = auth_warning_text()
                icon.notify(warning_body, warning_title)
            self.on_show_popup()
            threading.Thread(target=watch_theme_change, args=(self._on_theme_changed,), daemon=True).start()
            self.poll_loop()
        except Exception:
            crash_log(traceback.format_exc())

    def run(self) -> None:
        self.icon.run(setup=self._on_icon_ready)


def crash_log(msg: str) -> None:
    """Show a crash message box (for windowless EXE builds)."""
    ctypes.windll.user32.MessageBoxW(0, msg[:2000], 'CCMonitor - Error', 0x10)
