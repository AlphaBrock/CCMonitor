"""
Internationalization
=====================

Loads translations for the detected system language with English fallback.
"""
from __future__ import annotations

import ctypes
import json
import locale
from pathlib import Path
from typing import Any

__all__ = ['ACTIVE_LANG', 'LANG_NAMES', 'LOCALE_DIR', 'available_languages', 'detect_lang_code', 'load_translations', 'T']

LANG_NAMES: dict[str, str] = {
    'de': 'Deutsch',
    'en': 'English',
    'es': 'Español',
    'fr': 'Français',
    'hi': 'हिन्दी',
    'id': 'Bahasa Indonesia',
    'it': 'Italiano',
    'ja': '日本語',
    'ko': '한국어',
    'pt-BR': 'Português (Brasil)',
    'uk': 'Українська',
    'zh-CN': '简体中文',
    'zh-TW': '繁體中文',
}

LOCALE_DIR = Path(__file__).resolve().parents[2] / 'locale'


def _system_lang() -> str:
    """Get the BCP 47 locale tag via the Windows API, falling back to locale.getlocale()."""
    buf = ctypes.create_unicode_buffer(85)
    if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
        return buf.value
    return locale.getlocale()[0] or ''


def detect_lang_code(lang: str) -> str:
    """Detect locale file code from a locale string using convention-based lookup.

    Handles both BCP 47 tags (``'zh-CN'``) and POSIX-style locale strings
    (``'de_DE'``).  Lookup chain: ``{lang}-{REGION}.json`` -> ``{lang}.json``
    -> ``en.json``.  No mapping required - the locale directory structure *is*
    the configuration.

    Parameters
    ----------
    lang : str
        Locale string, e.g. ``'zh-CN'``, ``'de_DE'``, or ``'German_Germany'``.

    Returns
    -------
    str
        Locale file code (without ``.json``).
    """
    # Normalize encoding suffix and unify separator to underscore.
    normalized = locale.normalize(lang).split('.')[0].replace('-', '_')
    parts = normalized.split('_', 1)
    base = parts[0].lower()

    # On Windows, os.getlocale() returns e.g. 'German_Germany', and locale.normalize() fails to rewrite it to an ISO code,
    # so base becomes 'german'. Re-split using 'german' to hopefully trigger a match.
    if len(base) > 3:
        base = locale.normalize(parts[0]).split('.')[0].split('_')[0].lower()

    # Manual overrides for Windows locales that do not normalize cleanly to ISO codes.
    if base == 'ukrainian':
        base = 'uk'

    region = parts[1] if len(parts) > 1 and len(base) <= 3 else ''

    if region and (LOCALE_DIR / f'{base}-{region}.json').exists():
        return f'{base}-{region}'
    if (LOCALE_DIR / f'{base}.json').exists():
        return base

    return 'en'


def available_languages() -> list[tuple[str, str]]:
    """Return available locale codes with their native display names, sorted by name.

    Returns
    -------
    list[tuple[str, str]]
        Pairs of ``(code, display_name)`` sorted alphabetically by display name.
    """
    languages: list[tuple[str, str]] = []
    for path in sorted(LOCALE_DIR.glob('*.json')):
        code = path.stem
        name = LANG_NAMES.get(code, code)
        languages.append((code, name))

    return sorted(languages, key=lambda pair: pair[1].lower())


def load_translations() -> tuple[dict[str, Any], str]:
    """Load translations for the configured or detected system language, fallback to English.

    Returns
    -------
    tuple[dict[str, Any], str]
        The translation dict and the active locale code.
    """
    from src.presentation.settings import LANGUAGE

    if LANGUAGE:
        lang_file = LOCALE_DIR / f'{LANGUAGE}.json'
        if lang_file.exists():
            return json.loads(lang_file.read_text(encoding='utf-8')), LANGUAGE

    lang = _system_lang()
    lang_code = detect_lang_code(lang)

    return json.loads((LOCALE_DIR / f'{lang_code}.json').read_text(encoding='utf-8')), lang_code


T: dict[str, Any]
ACTIVE_LANG: str
T, ACTIVE_LANG = load_translations()
