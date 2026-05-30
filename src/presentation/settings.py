"""
Settings
=========

User-overridable configuration and default theme constants.
"""
from __future__ import annotations

import ctypes
import json
import locale as _locale
import os
import sys
from pathlib import Path

__all__ = [
    'ALERT_TIME_AWARE', 'ALERT_TIME_AWARE_BELOW',
    'BAR_BG', 'BAR_FG', 'BAR_FG_DANGER', 'BAR_FG_MID', 'BAR_FG_WARN', 'BAR_MARKER', 'BG',
    'CURRENCY_SYMBOL',
    'FG', 'FG_DIM', 'FG_HEADING', 'FG_LINK',
    'ICON_DARK', 'ICON_FIELDS', 'ICON_LIGHT', 'IDLE_PAUSE',
    'LANGUAGE', 'MAX_BACKOFF',
    'ON_RESET_COMMAND', 'ON_STARTUP_COMMAND', 'ON_THRESHOLD_COMMAND',
    'POLL_ERROR', 'POLL_FAST', 'POLL_FAST_EXTRA', 'POLL_INTERVAL',
    'POPUP_FIELDS', 'SETTINGS_FILENAME', 'TOOLTIP_FIELDS', 'TRAY_PROVIDER', 'USAGE_PROVIDER',
    'get_alert_thresholds', 'save_language_setting', 'save_tray_provider',
]

SETTINGS_FILENAME = 'usage-monitor-settings.json'

_NUMERIC_BOUNDS: dict[str, int] = {
    'poll_interval': 1,
    'poll_fast': 1,
    'poll_fast_extra': 1,
    'poll_error': 1,
    'max_backoff': 1,
    'idle_pause': 0,
}
_COLOR_KEYS = frozenset({
    'bg', 'fg', 'fg_dim', 'fg_heading', 'fg_link',
    'bar_bg', 'bar_fg', 'bar_fg_mid', 'bar_fg_warn', 'bar_fg_danger',
    'bar_divider', 'bar_marker',
})
_ICON_KEYS = frozenset({'icon_light', 'icon_dark'})
_THRESHOLD_KEY_PREFIX = 'alert_thresholds_'
_PERCENT_KEYS = frozenset({'alert_time_aware_below'})
_STRING_KEYS = frozenset({'currency_symbol', 'language'})
_COMMAND_KEYS = frozenset({'on_reset_command', 'on_startup_command', 'on_threshold_command'})
_BOOL_KEYS = frozenset({'alert_time_aware'})
_STRING_LIST_KEYS = frozenset({'tooltip_fields'})
_WILDCARD_STRING_LIST_KEYS = frozenset({'popup_fields'})
_VALID_BAR_MODES = frozenset({'utilization', 'overage'})
_VALID_USAGE_PROVIDERS = frozenset({'claude', 'codex'})
_VALID_TRAY_PROVIDERS = frozenset({'auto', 'claude', 'codex'})


_SETTINGS_PATH: Path | None = None


def _load_settings() -> dict:
    """Read the first ``usage-monitor-settings.json`` found, or return ``{}``."""
    global _SETTINGS_PATH

    if getattr(sys, 'frozen', False):
        app_dir = Path(sys.executable).parent
    else:
        app_dir = Path(__file__).resolve().parents[2]

    home_claude = Path.home() / '.claude'
    custom_config = Path(os.environ['CLAUDE_CONFIG_DIR']) if os.environ.get('CLAUDE_CONFIG_DIR') else None

    search_paths = [app_dir / SETTINGS_FILENAME]
    if custom_config and custom_config != home_claude:
        search_paths.append(custom_config / SETTINGS_FILENAME)
    search_paths.append(home_claude / SETTINGS_FILENAME)

    for path in search_paths:
        if path.is_file():
            _SETTINGS_PATH = path
            try:
                text = path.read_text(encoding='utf-8').strip()
                if not text:
                    return {}
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise ValueError(f'Expected a JSON object, got {type(data).__name__}')
                return _validate(data, path)
            except (json.JSONDecodeError, ValueError) as exc:
                ctypes.windll.user32.MessageBoxW(
                    0, f'Invalid JSON in settings file:\n{path}\n\n{exc}',
                    'CCMonitor - Settings Error', 0x30,
                )
                return {}
            except OSError:
                return {}

    return {}


def _valid_rgba(value: object) -> bool:
    """Return True if *value* is a list of exactly 4 integers in 0\u2013255."""
    return (
        isinstance(value, list) and len(value) == 4
        and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in value)
    )


def _validate(data: dict, path: Path) -> dict:
    """Drop entries with invalid types or values and show a MessageBox listing errors."""
    errors: list[str] = []
    drop: list[str] = []

    for key, value in data.items():
        if key in _NUMERIC_BOUNDS:
            min_val = _NUMERIC_BOUNDS[key]
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f'  {key}: expected an integer, got {type(value).__name__}')
                drop.append(key)
            elif value < min_val:
                errors.append(f'  {key}: must be >= {min_val}, got {value}')
                drop.append(key)

        elif key in _COLOR_KEYS:
            if not isinstance(value, str):
                errors.append(f'  {key}: expected a color string, got {type(value).__name__}')
                drop.append(key)

        elif key.startswith(_THRESHOLD_KEY_PREFIX):
            if not isinstance(value, list):
                errors.append(f'  {key}: expected an array, got {type(value).__name__}')
                drop.append(key)
            else:
                bad = [v for v in value if isinstance(v, bool) or not isinstance(v, (int, float)) or not (1 <= v <= 100)]
                if bad:
                    errors.append(f'  {key}: all values must be numbers between 1 and 100')
                    drop.append(key)
                else:
                    data[key] = sorted(set(value))

        elif key in _PERCENT_KEYS:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f'  {key}: expected a number, got {type(value).__name__}')
                drop.append(key)
            elif not (1 <= value <= 100):
                errors.append(f'  {key}: must be between 1 and 100, got {value}')
                drop.append(key)

        elif key in _STRING_KEYS:
            if not isinstance(value, str):
                errors.append(f'  {key}: expected a string, got {type(value).__name__}')
                drop.append(key)

        elif key == 'usage_provider':
            if not isinstance(value, str):
                errors.append(f'  {key}: expected a string, got {type(value).__name__}')
                drop.append(key)
            elif value not in _VALID_USAGE_PROVIDERS:
                errors.append(f'  {key}: must be one of {", ".join(sorted(_VALID_USAGE_PROVIDERS))}, got {value}')
                drop.append(key)

        elif key == 'tray_provider':
            if not isinstance(value, str):
                errors.append(f'  {key}: expected a string, got {type(value).__name__}')
                drop.append(key)
            elif value not in _VALID_TRAY_PROVIDERS:
                errors.append(f'  {key}: must be one of {", ".join(sorted(_VALID_TRAY_PROVIDERS))}, got {value}')
                drop.append(key)

        elif key in _COMMAND_KEYS:
            if isinstance(value, str):
                data[key] = [value]
            elif isinstance(value, list):
                if any(not isinstance(item, str) for item in value):
                    errors.append(f'  {key}: all items must be strings')
                    drop.append(key)
            else:
                errors.append(f'  {key}: expected a string or array of strings, got {type(value).__name__}')
                drop.append(key)

        elif key in _BOOL_KEYS:
            if not isinstance(value, bool):
                errors.append(f'  {key}: expected true or false, got {type(value).__name__}')
                drop.append(key)

        elif key in _STRING_LIST_KEYS:
            if not isinstance(value, list):
                errors.append(f'  {key}: expected an array, got {type(value).__name__}')
                drop.append(key)
            elif any(not isinstance(item, str) or not item for item in value):
                errors.append(f'  {key}: all entries must be non-empty strings')
                drop.append(key)
            else:
                seen: set[str] = set()
                deduped: list[str] = []
                for item in value:
                    if item not in seen:
                        seen.add(item)
                        deduped.append(item)
                data[key] = deduped

        elif key in _WILDCARD_STRING_LIST_KEYS:
            if not isinstance(value, list):
                errors.append(f'  {key}: expected an array, got {type(value).__name__}')
                drop.append(key)
            elif any(not isinstance(item, str) or not item for item in value):
                errors.append(f'  {key}: all entries must be non-empty strings')
                drop.append(key)
            elif value.count('*') > 1:
                errors.append(f'  {key}: "*" may appear at most once')
                drop.append(key)
            else:
                seen_wc: set[str] = set()
                deduped_wc: list[str] = []
                for item in value:
                    if item == '*' or item not in seen_wc:
                        seen_wc.add(item)
                        deduped_wc.append(item)
                data[key] = deduped_wc

        elif key == 'icon_fields':
            if not isinstance(value, list):
                errors.append(f'  {key}: expected an array, got {type(value).__name__}')
                drop.append(key)
            elif len(value) != 2:
                errors.append(f'  {key}: expected exactly 2 entries, got {len(value)}')
                drop.append(key)
            elif any(not isinstance(item, str) or not item for item in value):
                errors.append(f'  {key}: all entries must be non-empty strings')
                drop.append(key)
            else:
                invalid_modes = [
                    item for item in value
                    if ':' in item and item.split(':', 1)[1] not in _VALID_BAR_MODES
                ]
                if invalid_modes:
                    errors.append(
                        f'  {key}: unknown bar mode in: {", ".join(invalid_modes)}'
                        f' (valid: {", ".join(sorted(_VALID_BAR_MODES))})'
                    )
                    drop.append(key)

        elif key in _ICON_KEYS:
            if not isinstance(value, dict):
                errors.append(f'  {key}: expected an object, got {type(value).__name__}')
                drop.append(key)
            else:
                bad = [k for k, v in value.items() if not _valid_rgba(v)]
                for k in bad:
                    errors.append(f'  {key}.{k}: expected [R, G, B, A] with integers 0\u2013255')
                    del value[k]

    for key in drop:
        del data[key]

    if errors:
        ctypes.windll.user32.MessageBoxW(
            0, f'Invalid values in settings file:\n{path}\n\n' + '\n'.join(errors),
            'CCMonitor - Settings Error', 0x30,
        )

    return data


def _icon_colors(key: str, defaults: dict[str, tuple]) -> dict[str, tuple]:
    """Merge icon color overrides from settings, converting JSON arrays to tuples."""
    overrides = _S.get(key, {})
    return {k: tuple(overrides[k]) if k in overrides else v for k, v in defaults.items()}


_S = _load_settings()

# Polling intervals (seconds)
POLL_INTERVAL = _S.get('poll_interval', 180)
POLL_FAST = _S.get('poll_fast', 120)
POLL_FAST_EXTRA = _S.get('poll_fast_extra', 2)
POLL_ERROR = _S.get('poll_error', 30)
MAX_BACKOFF = _S.get('max_backoff', 900)
IDLE_PAUSE = _S.get('idle_pause', 300)

# Popup window theme
BG = _S.get('bg', '#2d2a2e')
FG = _S.get('fg', '#fcfcfa')
FG_DIM = _S.get('fg_dim', '#939293')
FG_HEADING = _S.get('fg_heading', '#ffd866')
FG_LINK = _S.get('fg_link', '#78dce8')
BAR_BG = _S.get('bar_bg', '#403e41')
BAR_FG = _S.get('bar_fg', '#78dce8')
BAR_FG_MID = _S.get('bar_fg_mid', '#a9dc76')
BAR_FG_WARN = _S.get('bar_fg_warn', '#fc9867')
BAR_FG_DANGER = _S.get('bar_fg_danger', '#ff6188')
BAR_DIVIDER = _S.get('bar_divider', '#000c')
BAR_MARKER = _S.get('bar_marker', '#fffc')

# Tray icon colors
ICON_LIGHT = _icon_colors('icon_light', {
    'fg': (255, 255, 255, 255),
    'fg_half': (255, 255, 255, 80),
    'fg_dim': (255, 255, 255, 140),
})
ICON_DARK = _icon_colors('icon_dark', {
    'fg': (0, 0, 0, 255),
    'fg_half': (0, 0, 0, 80),
    'fg_dim': (0, 0, 0, 140),
})

# Tray icon fields
ICON_FIELDS: list[str] = _S.get('icon_fields', ['five_hour', 'seven_day'])

# 用量来源
USAGE_PROVIDER: str = _S.get('usage_provider', 'claude')

# 托盘显示的 provider（auto = 全部）
TRAY_PROVIDER: str = _S.get('tray_provider', 'auto')

# Tooltip fields
TOOLTIP_FIELDS: list[str] = _S.get('tooltip_fields', ['five_hour', 'seven_day'])

# Popup fields
POPUP_FIELDS: list[str] = _S.get('popup_fields', ['*'])

# Alert thresholds
ALERT_TIME_AWARE: bool = _S.get('alert_time_aware', True)
ALERT_TIME_AWARE_BELOW: float = _S.get('alert_time_aware_below', 90)

# Currency

def _detect_currency_symbol() -> str:
    """Detect the system locale currency symbol for monetary formatting."""
    try:
        _locale.setlocale(_locale.LC_MONETARY, '')
        return _locale.localeconv().get('currency_symbol', '') or ''
    except _locale.Error:
        return ''


_SYSTEM_CURRENCY_SYMBOL = _detect_currency_symbol()
CURRENCY_SYMBOL: str = _S.get('currency_symbol', _SYSTEM_CURRENCY_SYMBOL)

# Language override
LANGUAGE: str = _S.get('language', '')

# Event commands
ON_RESET_COMMAND: list[str] = _S.get('on_reset_command', [])
ON_STARTUP_COMMAND: list[str] = _S.get('on_startup_command', [])
ON_THRESHOLD_COMMAND: list[str] = _S.get('on_threshold_command', [])

_ALERT_THRESHOLDS: dict[str, list[float]] = {
    'five_hour': [50, 80, 95],
    'seven_day': [95],
    'extra_usage': [50, 80, 95],
}


def _write_setting(key: str, value: str | None) -> None:
    """Persist a single key to the settings file.

    Writes to the same file that was loaded at startup.  If no settings
    file existed, creates one at ``~/.claude/usage-monitor-settings.json``.
    A falsy *value* removes the key, reverting it to its default.

    Parameters
    ----------
    key : str
        Settings key to write.
    value : str or None
        Value to store, or empty/``None`` to remove the key.
    """
    target = _SETTINGS_PATH or (Path.home() / '.claude' / SETTINGS_FILENAME)

    existing: dict = {}
    if target.is_file():
        try:
            text = target.read_text(encoding='utf-8').strip()
            if text:
                data = json.loads(text)
                if isinstance(data, dict):
                    existing = data
        except (json.JSONDecodeError, OSError):
            pass

    if value:
        existing[key] = value
    else:
        existing.pop(key, None)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(existing, indent=4, ensure_ascii=False) + '\n', encoding='utf-8')


def save_language_setting(lang_code: str) -> None:
    """Save the language preference to the settings file.

    Parameters
    ----------
    lang_code : str
        Locale code to save (e.g. ``'zh-CN'``), or empty string to
        revert to auto-detection.
    """
    _write_setting('language', lang_code)


def save_tray_provider(provider: str) -> None:
    """Save the tray display provider to the settings file.

    Parameters
    ----------
    provider : str
        Provider to display in the tray icon and tooltip: ``'auto'``
        (show all), ``'codex'``, or ``'claude'``.
    """
    _write_setting('tray_provider', provider)


def get_alert_thresholds(variant_key: str) -> list[float]:
    """Return the alert thresholds for a usage variant.

    Uses a fallback chain: exact user override, built-in default for
    the exact key, user override for the base period, built-in default
    for the base period, then empty list (alerts disabled).

    Parameters
    ----------
    variant_key : str
        API variant key, e.g. ``'five_hour'``, ``'seven_day_sonnet'``,
        or ``'extra_usage'``.
    """
    exact_settings_key = f'{_THRESHOLD_KEY_PREFIX}{variant_key}'
    if exact_settings_key in _S:
        return _S[exact_settings_key]

    if variant_key in _ALERT_THRESHOLDS:
        return _ALERT_THRESHOLDS[variant_key]

    # Fallback to base period (strip variant suffix)
    parts = variant_key.split('_', 2)
    if len(parts) >= 3:
        base_key = f'{parts[0]}_{parts[1]}'
        base_settings_key = f'{_THRESHOLD_KEY_PREFIX}{base_key}'
        if base_settings_key in _S:
            return _S[base_settings_key]
        if base_key in _ALERT_THRESHOLDS:
            return _ALERT_THRESHOLDS[base_key]

    return []
