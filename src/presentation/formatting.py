"""
Formatting
===========

Pure functions for formatting usage data: time-until-reset strings,
elapsed period percentages, credit amounts, status lines, and tooltip text.
"""
from __future__ import annotations

import locale as _locale
from datetime import datetime, timedelta, timezone
from typing import Any

from .i18n import ACTIVE_LANG, T
from .settings import CURRENCY_SYMBOL, TOOLTIP_FIELDS, USAGE_PROVIDER, _SYSTEM_CURRENCY_SYMBOL

__all__ = [
    'elapsed_pct', 'expand_popup_fields', 'field_period', 'format_credits',
    'format_dashboard_tooltip', 'format_tooltip',
    'midnight_positions', 'parse_field_name', 'popup_label', 'provider_auth_expired_label',
    'provider_auth_expired_short', 'provider_label', 'provider_popup_title', 'provider_tooltip_title',
    'time_until', 'tooltip_label',
]

PERIOD_5H = 5 * 3600
PERIOD_7D = 7 * 24 * 3600

_NUMBER_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
    'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12,
}
_UNIT_SUFFIXES = {'hour': 'h', 'day': 'd'}
_TITLE_CASE_EXCEPTIONS = {'oauth': 'OAuth', 'api': 'API', 'ai': 'AI'}
_PROVIDER_LABELS = {'claude': 'Claude', 'codex': 'Codex'}
_PROVIDER_TOOLTIP_ORDER = ('codex', 'claude')


def parse_field_name(field: str) -> tuple[int, str, str | None] | None:
    """Parse an API field name into its numeric, unit, and variant components.

    Parameters
    ----------
    field : str
        API field name, e.g. ``'five_hour'``, ``'seven_day_sonnet'``.

    Returns
    -------
    tuple or None
        ``(number, unit, variant)`` where *number* is the parsed digit,
        *unit* is the raw unit word (e.g. ``'hour'``, ``'day'``), and
        *variant* is the remaining suffix or ``None``.
        Returns ``None`` if the number word or unit is not recognized.
    """
    parts = field.split('_', 2)
    if len(parts) < 2:
        return None

    number = _NUMBER_WORDS.get(parts[0])
    unit = parts[1]
    if number is None or unit not in _UNIT_SUFFIXES:
        return None

    variant = parts[2] if len(parts) > 2 else None
    return (number, unit, variant)


def _title_case_variant(text: str) -> str:
    """Title-case a variant string, respecting abbreviation exceptions."""
    return ' '.join(_TITLE_CASE_EXCEPTIONS.get(w.lower(), w.title()) for w in text.split('_'))


def tooltip_label(field: str) -> str:
    """Generate a short tooltip label from an API field name.

    Parameters
    ----------
    field : str
        API field name, e.g. ``'five_hour'``, ``'seven_day_sonnet'``.

    Returns
    -------
    str
        Short label like ``'5h'``, ``'7d'``, or ``'7d Sonnet'``.
        Falls back to title case of the full field name if unparseable.
    """
    parsed = parse_field_name(field)
    if parsed is None:
        return _title_case_variant(field)

    number, unit, variant = parsed
    label = f'{number}{_UNIT_SUFFIXES[unit]}'
    if variant:
        label += f' {_title_case_variant(variant)}'
    return label


def popup_label(field: str) -> str:
    """Generate a popup bar label from an API field name using i18n templates.

    Parameters
    ----------
    field : str
        API field name, e.g. ``'five_hour'``, ``'seven_day_sonnet'``.

    Returns
    -------
    str
        Localized label like ``'Session (5hr)'`` or ``'Weekly (Sonnet)'``.
        Falls back to title case with abbreviation exceptions if unparseable.
    """
    parsed = parse_field_name(field)
    if parsed is None:
        return _title_case_variant(field)

    number, unit, variant = parsed
    if variant:
        suffix = _title_case_variant(variant)
    elif unit == 'hour':
        suffix = f'{number}hr'
    else:
        suffix = f'{number} {unit}'

    template_key = 'session_label' if unit == 'hour' else 'weekly_label'
    return T[template_key].format(suffix=suffix)


def provider_popup_title() -> str:
    """Return the popup title for the configured usage provider."""
    if USAGE_PROVIDER == 'codex':
        return 'Codex 用量' if ACTIVE_LANG.startswith('zh') else 'Usage Monitor for Codex'
    return T['popup_title']


def provider_tooltip_title() -> str:
    """Return the tray tooltip title for the configured usage provider."""
    if USAGE_PROVIDER == 'codex':
        return 'Codex 用量' if ACTIVE_LANG.startswith('zh') else 'Codex Usage'
    return T['tooltip_title']


def provider_auth_expired_label() -> str:
    """Return the auth-expired label for the configured usage provider."""
    if USAGE_PROVIDER == 'codex':
        return 'Codex 会话已过期' if ACTIVE_LANG.startswith('zh') else 'Codex Session Expired'
    return T['auth_expired_label']


def provider_auth_expired_short() -> str:
    """Return the short auth-expired guidance for the configured usage provider."""
    if USAGE_PROVIDER == 'codex':
        return '请重新运行 codex 登录。' if ACTIVE_LANG.startswith('zh') else 'Run codex to log in again.'
    return T['auth_expired_short']


def field_period(field: str) -> int | None:
    """Return the period duration in seconds for a field, or None if unknown.

    Parameters
    ----------
    field : str
        API field name, e.g. ``'five_hour'``, ``'seven_day_sonnet'``.
    """
    parsed = parse_field_name(field)
    if parsed is None:
        return None

    number, unit, _ = parsed
    if unit == 'hour':
        return number * 3600
    if unit == 'day':
        return number * 24 * 3600
    return None


def _field_sort_key(field: str) -> tuple[int, int, int, str]:
    """Sort key for default field ordering: shorter periods first, base before variants."""
    parsed = parse_field_name(field)
    if parsed is None:
        return (2, 0, 0, field)

    number, unit, variant = parsed
    unit_order = 0 if unit == 'hour' else 1
    variant_order = 0 if variant is None else 1
    return (unit_order, number, variant_order, variant or '')


def expand_popup_fields(popup_fields: list[str], usage_data: dict[str, Any]) -> list[str]:
    """Expand a popup_fields setting into concrete field names based on API data.

    Parameters
    ----------
    popup_fields : list[str]
        User-configured field list, possibly containing ``'*'`` wildcard.
    usage_data : dict
        Raw API response dict.

    Returns
    -------
    list[str]
        Ordered list of field names to display, with null/missing fields removed.
    """
    available = {
        key for key, value in usage_data.items()
        if isinstance(value, dict) and 'utilization' in value and 'resets_at' in value
        and value.get('utilization') is not None
    }

    result: list[str] = []
    seen: set[str] = set()

    for field in popup_fields:
        if field == '*':
            remaining = sorted((f for f in available if f not in seen), key=_field_sort_key)
            for f in remaining:
                seen.add(f)
                result.append(f)
        elif field in available and field not in seen:
            seen.add(field)
            result.append(field)

    return result


def elapsed_pct(resets_at: str, period_seconds: int) -> float | None:
    """Return elapsed percentage of a usage period, or None if not calculable.

    Parameters
    ----------
    resets_at : str
        ISO 8601 timestamp when the limit resets.
    period_seconds : int
        Total duration of the period in seconds (e.g. 18000 for 5h).

    Returns
    -------
    float or None
        Percentage of the period that has already elapsed (0-100),
        or None if the value cannot be determined.
    """
    if not resets_at or period_seconds <= 0:
        return None

    try:
        reset = datetime.fromisoformat(resets_at)
        now = datetime.now(timezone.utc)
        remaining = (reset - now).total_seconds()
        elapsed = period_seconds - remaining

        return max(0.0, min(100.0, elapsed / period_seconds * 100))
    except Exception:
        return None


def midnight_positions(resets_at: str, period_seconds: int) -> list[float]:
    """Return relative positions (0.0-1.0) of local midnight boundaries within a usage period.

    Parameters
    ----------
    resets_at : str
        ISO 8601 timestamp when the limit resets.
    period_seconds : int
        Total duration of the period in seconds.

    Returns
    -------
    list[float]
        Positions where local midnights fall within the period, each in the
        range (0.0, 1.0) exclusive.  Positions that would round to 0px at
        typical bar widths are omitted.
    """
    if not resets_at or period_seconds <= 0:
        return []

    try:
        reset_utc = datetime.fromisoformat(resets_at)
        start_utc = reset_utc - timedelta(seconds=period_seconds)

        start_local = start_utc.astimezone()
        end_local = reset_utc.astimezone()

        # First midnight after the period start
        midnight = (start_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        positions = []
        while midnight < end_local:
            elapsed = (midnight - start_local).total_seconds()
            rel = elapsed / period_seconds
            if rel > 0.003:
                positions.append(rel)
            midnight += timedelta(days=1)

        return positions
    except Exception:
        return []


def time_until(iso_str: str) -> str:
    """Return human-readable reset time.

    Same day:  "Resets in 2h 20m (14:30)"
    Tomorrow:  "Resets tomorrow, 12:00"
    Later:     "Resets Sat., 12:00"
    """
    try:
        reset = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        diff = reset - now

        total_min = max(0, int(diff.total_seconds() / 60))
        if total_min == 0:
            return ''

        reset_local = reset.astimezone()
        today = datetime.now().date()
        if reset_local.second >= 30:
            reset_local = reset_local.replace(second=0) + timedelta(minutes=1)
        else:
            reset_local = reset_local.replace(second=0)
        reset_date = reset_local.date()
        time_str = reset_local.strftime('%H:%M')

        if reset_date == today:
            if total_min >= 60:
                duration = T['duration_hm'].format(h=total_min // 60, m=total_min % 60)
            else:
                duration = T['duration_m'].format(m=total_min)
            return T['resets_in'].format(duration=duration, clock=time_str)

        if reset_date == today + timedelta(days=1):
            return T['resets_tomorrow'].format(clock=time_str)

        wd = T['weekdays'][reset_local.weekday()]
        return T['resets_weekday'].format(day=wd, clock=time_str)
    except Exception:
        return ''


def format_credits(cents: float) -> str:
    """Format a cent amount as a localized currency string.

    Uses the system locale for formatting (decimal separator, symbol placement,
    grouping).  If the user overrides ``currency_symbol`` in settings, the
    system symbol is replaced in the formatted output.

    Parameters
    ----------
    cents : float
        Amount in cents (e.g. 420.0 for 4.20 in the base currency unit).
    """
    amount = cents / 100

    try:
        formatted = _locale.currency(amount, grouping=True)

        if CURRENCY_SYMBOL != _SYSTEM_CURRENCY_SYMBOL and _SYSTEM_CURRENCY_SYMBOL:
            formatted = formatted.replace(_SYSTEM_CURRENCY_SYMBOL, CURRENCY_SYMBOL)

        return formatted
    except (ValueError, _locale.Error):
        if CURRENCY_SYMBOL:
            return f'{CURRENCY_SYMBOL}\u00a0{amount:.2f}'
        return f'{amount:.2f}'


def format_tooltip(data: dict[str, Any]) -> str:
    """Format usage data as short tooltip text."""
    if 'error' in data:
        if data.get('auth_error'):
            return f"{provider_auth_expired_label()}\n{provider_auth_expired_short()}"
        error = data['error']
        server_msg = data.get('server_message')
        if server_msg:
            error += f' {server_msg}'
        return f"{T['error_label']}\n{error[:80]}"

    lines = [provider_tooltip_title()]
    for key in TOOLTIP_FIELDS:
        entry = data.get(key)
        if entry and entry.get('utilization') is not None:
            short = tooltip_label(key)
            pct = f"{entry['utilization']:.0f}%"
            reset = time_until(entry.get('resets_at', ''))
            line = f'{short}: {pct}'
            if reset:
                line += f' ({reset})'
            lines.append(line)

    return '\n'.join(lines)


def provider_label(provider_id: str) -> str:
    """Return the short display name for a provider id (e.g. ``'Claude'``)."""
    return _PROVIDER_LABELS.get(provider_id, provider_id.title())


def format_dashboard_tooltip(provider_responses: dict[str, dict[str, Any]], selected: str = 'auto') -> str:
    """Format a compact tray tooltip for one or all providers.

    The Windows tray tooltip is limited to ~127 characters, so each
    provider is condensed to a single line without reset times.

    Parameters
    ----------
    provider_responses : dict
        Mapping of provider id to its latest raw API response.
    selected : str
        ``'auto'`` shows every available provider; ``'codex'`` or
        ``'claude'`` shows only that one.

    Returns
    -------
    str
        One line per shown provider, or the generic title when no
        provider has data yet.
    """
    lines: list[str] = []
    for provider_id in _PROVIDER_TOOLTIP_ORDER:
        if selected != 'auto' and provider_id != selected:
            continue
        data = provider_responses.get(provider_id)
        if not data:
            continue
        lines.append(_provider_tooltip_line(provider_id, data))

    if not lines:
        return provider_tooltip_title()

    return '\n'.join(lines)


def _provider_tooltip_line(provider_id: str, data: dict[str, Any]) -> str:
    """Build a one-line compact tooltip summary for a single provider."""
    label = provider_label(provider_id)
    if 'error' in data:
        return f"{label}: {data['error'][:40]}"

    parts: list[str] = []
    for key in TOOLTIP_FIELDS:
        entry = data.get(key)
        if entry and entry.get('utilization') is not None:
            parts.append(f"{tooltip_label(key)} {entry['utilization']:.0f}%")

    if not parts:
        return f'{label}: -'

    return f'{label}  ' + ' · '.join(parts)
