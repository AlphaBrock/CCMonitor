"""
i18n Tests
===========

Unit tests for detect_lang_code(), load_translations(), and locale file consistency.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.presentation.i18n import LOCALE_DIR, _system_lang, detect_lang_code, load_translations

MOCK_LOCALE_FILES = ['en.json', 'de.json', 'es.json', 'fr.json', 'ja.json', 'pt-BR.json', 'uk.json', 'zh-CN.json', 'zh-TW.json']

NORMALIZE_MAP = {
    'de_DE': 'de_DE.ISO8859-1',
    'en_US': 'en_US.ISO8859-1',
    'pt_BR': 'pt_BR.ISO8859-1',
    'ja_JP': 'ja_JP.eucJP',
    'fr_FR': 'fr_FR.ISO8859-1',
    'zh_CN': 'zh_CN.eucCN',
    'zh_TW': 'zh_TW.big5',
    'German_Germany': 'German_Germany',
    'German': 'de_DE.ISO8859-1',
    'Spanish_Mexico': 'Spanish_Mexico',
    'Spanish': 'es_ES.ISO8859-1',
    'Ukrainian_Ukraine': 'Ukrainian_Ukraine',
    'Ukrainian': 'Ukrainian',
    '': '',
}


def _mock_normalize(locale_string):
    """Simulate locale.normalize() for cross-platform test determinism."""
    return NORMALIZE_MAP.get(locale_string, locale_string)


# ---------------------------------------------------------------------------
# detect_lang_code
# ---------------------------------------------------------------------------

@patch('src.presentation.i18n.locale.normalize', side_effect=_mock_normalize)
class TestDetectLangCode(unittest.TestCase):
    """Tests for detect_lang_code()."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._locale_dir = Path(self._tmp.name)
        for name in MOCK_LOCALE_FILES:
            (self._locale_dir / name).write_text('{}')
        self._patch_dir = patch('src.presentation.i18n.LOCALE_DIR', self._locale_dir)
        self._patch_dir.start()

    def tearDown(self):
        self._patch_dir.stop()
        self._tmp.cleanup()

    def test_de_DE_resolves_to_base(self, _mock_norm):
        """Standard ISO locale falls back to base language file."""
        self.assertEqual(detect_lang_code('de_DE'), 'de')

    def test_en_US_resolves_to_base(self, _mock_norm):
        self.assertEqual(detect_lang_code('en_US'), 'en')

    def test_fr_FR_resolves_to_base(self, _mock_norm):
        """Regional locale without regional file falls back to base."""
        self.assertEqual(detect_lang_code('fr_FR'), 'fr')

    def test_pt_BR_regional_file_found(self, _mock_norm):
        """Regional variant with matching file returns region-specific code."""
        self.assertEqual(detect_lang_code('pt_BR'), 'pt-BR')

    def test_zh_CN_regional_file_found(self, _mock_norm):
        self.assertEqual(detect_lang_code('zh_CN'), 'zh-CN')

    def test_zh_TW_regional_file_found(self, _mock_norm):
        self.assertEqual(detect_lang_code('zh_TW'), 'zh-TW')

    def test_ja_JP_no_regional_file(self, _mock_norm):
        """Locale with region but no regional file falls back to base."""
        self.assertEqual(detect_lang_code('ja_JP'), 'ja')

    def test_german_germany_windows_name(self, _mock_norm):
        """Windows-style long locale name resolves via normalize retry."""
        self.assertEqual(detect_lang_code('German_Germany'), 'de')

    def test_spanish_mexico_windows_name(self, _mock_norm):
        """Windows-style name without regional file falls back to base."""
        self.assertEqual(detect_lang_code('Spanish_Mexico'), 'es')

    def test_ukrainian_windows_name(self, _mock_norm):
        """Windows-style name with manual override resolves correctly."""
        self.assertEqual(detect_lang_code('Ukrainian_Ukraine'), 'uk')

    def test_base_code_without_region(self, _mock_norm):
        """Base language code without region resolves directly."""
        self.assertEqual(detect_lang_code('fr'), 'fr')

    def test_unknown_locale_falls_back_to_en(self, _mock_norm):
        """Completely unknown locale falls back to English."""
        self.assertEqual(detect_lang_code('xx_YY'), 'en')

    def test_unknown_windows_name_falls_back_to_en(self, _mock_norm):
        """Windows-style name where normalize retry also fails."""
        self.assertEqual(detect_lang_code('Klingon_Qonos'), 'en')

    def test_empty_string_falls_back_to_en(self, _mock_norm):
        self.assertEqual(detect_lang_code(''), 'en')

    def test_zh_CN_bcp47_tag(self, _mock_norm):
        """BCP 47 tag with hyphen resolves to regional file."""
        self.assertEqual(detect_lang_code('zh-CN'), 'zh-CN')

    def test_zh_TW_bcp47_tag(self, _mock_norm):
        self.assertEqual(detect_lang_code('zh-TW'), 'zh-TW')

    def test_pt_BR_bcp47_tag(self, _mock_norm):
        """BCP 47 tag with matching regional file returns region-specific code."""
        self.assertEqual(detect_lang_code('pt-BR'), 'pt-BR')

    def test_de_DE_bcp47_tag(self, _mock_norm):
        """BCP 47 tag without regional file falls back to base."""
        self.assertEqual(detect_lang_code('de-DE'), 'de')

    def test_en_US_bcp47_tag(self, _mock_norm):
        self.assertEqual(detect_lang_code('en-US'), 'en')


# ---------------------------------------------------------------------------
# load_translations
# ---------------------------------------------------------------------------

class TestLoadTranslations(unittest.TestCase):
    """Tests for load_translations()."""

    @patch('src.presentation.settings.LANGUAGE', '')
    @patch('src.presentation.i18n.locale.normalize', side_effect=_mock_normalize)
    @patch('src.presentation.i18n._system_lang', return_value='de-DE')
    def test_loads_detected_locale(self, _mock_sys, _mock_norm):
        """Loads the JSON file matching the detected system locale."""
        with TemporaryDirectory() as tmp:
            locale_dir = Path(tmp)
            (locale_dir / 'en.json').write_text('{"title": "English"}')
            (locale_dir / 'de.json').write_text('{"title": "Deutsch"}')

            with patch('src.presentation.i18n.LOCALE_DIR', locale_dir):
                translations, lang_code = load_translations()

        self.assertEqual(translations['title'], 'Deutsch')
        self.assertEqual(lang_code, 'de')

    @patch('src.presentation.settings.LANGUAGE', '')
    @patch('src.presentation.i18n.locale.normalize', side_effect=_mock_normalize)
    @patch('src.presentation.i18n._system_lang', return_value='')
    def test_empty_lang_falls_back_to_english(self, _mock_sys, _mock_norm):
        """Empty string from _system_lang() falls back to English."""
        with TemporaryDirectory() as tmp:
            locale_dir = Path(tmp)
            (locale_dir / 'en.json').write_text('{"title": "English"}')

            with patch('src.presentation.i18n.LOCALE_DIR', locale_dir):
                translations, lang_code = load_translations()

        self.assertEqual(translations['title'], 'English')
        self.assertEqual(lang_code, 'en')

    @patch('src.presentation.settings.LANGUAGE', '')
    @patch('src.presentation.i18n.locale.normalize', side_effect=_mock_normalize)
    @patch('src.presentation.i18n._system_lang', return_value='zh-CN')
    def test_loads_regional_locale_from_bcp47(self, _mock_sys, _mock_norm):
        """BCP 47 tag from Win32 API resolves to regional locale file."""
        with TemporaryDirectory() as tmp:
            locale_dir = Path(tmp)
            (locale_dir / 'en.json').write_text('{"title": "English"}')
            (locale_dir / 'zh-CN.json').write_text('{"title": "Chinese"}')

            with patch('src.presentation.i18n.LOCALE_DIR', locale_dir):
                translations, lang_code = load_translations()

        self.assertEqual(translations['title'], 'Chinese')
        self.assertEqual(lang_code, 'zh-CN')

    def test_language_setting_overrides_locale(self):
        """LANGUAGE setting bypasses locale detection entirely."""
        with TemporaryDirectory() as tmp:
            locale_dir = Path(tmp)
            (locale_dir / 'en.json').write_text('{"title": "English"}')
            (locale_dir / 'ja.json').write_text('{"title": "Japanese"}')

            with patch('src.presentation.settings.LANGUAGE', 'ja'), \
                 patch('src.presentation.i18n.LOCALE_DIR', locale_dir):
                translations, lang_code = load_translations()

        self.assertEqual(translations['title'], 'Japanese')
        self.assertEqual(lang_code, 'ja')

    @patch('src.presentation.settings.LANGUAGE', 'xx')
    @patch('src.presentation.i18n.locale.normalize', side_effect=_mock_normalize)
    @patch('src.presentation.i18n._system_lang', return_value='de-DE')
    def test_invalid_language_setting_falls_back_to_locale(self, _mock_sys, _mock_norm):
        """Invalid LANGUAGE setting falls back to locale detection."""
        with TemporaryDirectory() as tmp:
            locale_dir = Path(tmp)
            (locale_dir / 'en.json').write_text('{"title": "English"}')
            (locale_dir / 'de.json').write_text('{"title": "Deutsch"}')

            with patch('src.presentation.i18n.LOCALE_DIR', locale_dir):
                translations, lang_code = load_translations()

        self.assertEqual(translations['title'], 'Deutsch')
        self.assertEqual(lang_code, 'de')


# ---------------------------------------------------------------------------
# locale file consistency
# ---------------------------------------------------------------------------

class TestLocaleConsistency(unittest.TestCase):
    """Verify all locale files are consistent with en.json (reference)."""

    @classmethod
    def setUpClass(cls):
        cls.locale_files = sorted(LOCALE_DIR.glob('*.json'))
        cls.translations = {}
        for path in cls.locale_files:
            cls.translations[path.stem] = json.loads(path.read_text(encoding='utf-8'))
        cls.reference = cls.translations['en']

    def test_at_least_two_locale_files_exist(self):
        self.assertGreaterEqual(len(self.locale_files), 2)

    def test_all_files_have_same_keys_as_english(self):
        """Every locale file must have exactly the same keys as en.json."""
        ref_keys = set(self.reference.keys())

        for lang, data in self.translations.items():
            if lang == 'en':
                continue
            lang_keys = set(data.keys())
            missing = ref_keys - lang_keys
            extra = lang_keys - ref_keys
            self.assertFalse(missing, f'{lang}.json missing keys: {missing}')
            self.assertFalse(extra, f'{lang}.json has extra keys: {extra}')

    def test_weekdays_have_seven_entries(self):
        """Every locale must have exactly 7 weekday names."""
        for lang, data in self.translations.items():
            self.assertEqual(len(data['weekdays']), 7, f'{lang}.json weekdays count != 7')

    def test_format_placeholders_match_english(self):
        """Format placeholders ({name}) in each translation must match en.json."""
        placeholder_re = re.compile(r'\{(\w+)\}')

        for key, en_value in self.reference.items():
            if not isinstance(en_value, str):
                continue
            en_placeholders = set(placeholder_re.findall(en_value))
            if not en_placeholders:
                continue

            for lang, data in self.translations.items():
                if lang == 'en':
                    continue
                lang_placeholders = set(placeholder_re.findall(data[key]))
                self.assertEqual(
                    en_placeholders, lang_placeholders,
                    f'{lang}.json key "{key}": placeholders {lang_placeholders} != expected {en_placeholders}',
                )

    def test_no_empty_translations(self):
        """No translation value should be an empty string."""
        for lang, data in self.translations.items():
            for key, value in data.items():
                if isinstance(value, str):
                    self.assertNotEqual(value, '', f'{lang}.json key "{key}" is empty')

    def test_value_types_match_english(self):
        """Value types (str, list) must match en.json for each key."""
        for lang, data in self.translations.items():
            if lang == 'en':
                continue
            for key in self.reference:
                self.assertIsInstance(
                    data[key], type(self.reference[key]),
                    f'{lang}.json key "{key}": expected {type(self.reference[key]).__name__}, '
                    f'got {type(data[key]).__name__}',
                )


# ---------------------------------------------------------------------------
# _system_lang
# ---------------------------------------------------------------------------

class TestSystemLang(unittest.TestCase):
    """Tests for _system_lang()."""

    @patch('src.presentation.i18n.ctypes')
    def test_returns_win32_locale_name(self, mock_ctypes):
        """Returns the BCP 47 tag from GetUserDefaultLocaleName."""
        mock_ctypes.create_unicode_buffer.return_value.value = 'zh-CN'
        mock_ctypes.windll.kernel32.GetUserDefaultLocaleName.return_value = 5
        self.assertEqual(_system_lang(), 'zh-CN')

    @patch('src.presentation.i18n.locale.getlocale', return_value=('de_DE', 'UTF-8'))
    @patch('src.presentation.i18n.ctypes')
    def test_falls_back_to_getlocale_on_api_failure(self, mock_ctypes, _mock_get):
        """Falls back to locale.getlocale() when Win32 API returns 0."""
        mock_ctypes.windll.kernel32.GetUserDefaultLocaleName.return_value = 0
        self.assertEqual(_system_lang(), 'de_DE')

    @patch('src.presentation.i18n.locale.getlocale', return_value=(None, None))
    @patch('src.presentation.i18n.ctypes')
    def test_returns_empty_when_both_fail(self, mock_ctypes, _mock_get):
        """Returns empty string when Win32 API fails and getlocale() returns None."""
        mock_ctypes.windll.kernel32.GetUserDefaultLocaleName.return_value = 0
        self.assertEqual(_system_lang(), '')


if __name__ == '__main__':
    unittest.main()
