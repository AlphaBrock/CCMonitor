"""
Codex API Tests
================

Unit tests for Codex OAuth credential loading, token refresh, and usage mapping.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import requests

from src.integrations.codex_api import (
    CODEX_AUTH_URL, CODEX_CLIENT_ID, CODEX_REFRESH_INTERVAL_SECONDS, CODEX_USAGE_URL, CODEX_USER_AGENT,
    CodexCredentialsError,
    api_headers, codex_auth_path, fetch_codex_usage, map_codex_usage_response,
    read_codex_access_token, read_codex_credentials, refresh_codex_token,
)


def _write_auth(path: Path, *, tokens: dict | None = None, last_refresh: str = '2999-01-01T00:00:00Z', api_key: str | None = None) -> None:
    """Write a Codex auth.json test fixture."""
    payload = {
        'OPENAI_API_KEY': api_key,
        'tokens': tokens if tokens is not None else {
            'access_token': 'access-old',
            'refresh_token': 'refresh-old',
            'id_token': 'id-old',
            'account_id': 'account-123',
        },
        'last_refresh': last_refresh,
    }
    path.write_text(json.dumps(payload), encoding='utf-8')


def _mock_response(payload: object, *, status_code: int = 200, headers: dict[str, str] | None = None) -> MagicMock:
    """Build a mocked requests.Response."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = payload
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    return response


class TestCodexAuthPath(unittest.TestCase):
    """Tests for Codex auth.json path resolution."""

    def test_codex_home_env_wins(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(codex_auth_path({'CODEX_HOME': tmp}), Path(tmp) / 'auth.json')

    def test_default_home_codex_path(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.object(Path, 'home', return_value=home):
                self.assertEqual(codex_auth_path({}), home / '.codex' / 'auth.json')


class TestReadCodexCredentials(unittest.TestCase):
    """Tests for Codex OAuth credential parsing."""

    def test_reads_codex_home_auth_json(self):
        with TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / 'auth.json'
            _write_auth(auth_file)

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                credentials = read_codex_credentials()

        self.assertEqual(credentials.access_token, 'access-old')
        self.assertEqual(credentials.refresh_token, 'refresh-old')
        self.assertEqual(credentials.id_token, 'id-old')
        self.assertEqual(credentials.account_id, 'account-123')
        self.assertEqual(credentials.path, auth_file)

    def test_reads_default_home_auth_json(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            auth_dir = home / '.codex'
            auth_dir.mkdir()
            _write_auth(auth_dir / 'auth.json')

            with patch.dict('os.environ', {}, clear=True), patch.object(Path, 'home', return_value=home):
                credentials = read_codex_credentials()

        self.assertEqual(credentials.access_token, 'access-old')

    def test_missing_file_raises_clear_error(self):
        with TemporaryDirectory() as tmp:
            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                with self.assertRaises(CodexCredentialsError) as ctx:
                    read_codex_credentials()

        self.assertIn('Codex', ctx.exception.message)

    def test_malformed_json_raises_clear_error(self):
        with TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / 'auth.json'
            auth_file.write_text('{broken', encoding='utf-8')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                with self.assertRaises(CodexCredentialsError) as ctx:
                    read_codex_credentials()

        self.assertIn('Invalid Codex auth.json', ctx.exception.server_message)

    def test_missing_tokens_raises_clear_error(self):
        with TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / 'auth.json'
            auth_file.write_text(json.dumps({'OPENAI_API_KEY': None}), encoding='utf-8')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                with self.assertRaises(CodexCredentialsError) as ctx:
                    read_codex_credentials()

        self.assertIn('no OAuth tokens', ctx.exception.server_message)

    def test_openai_api_key_is_not_supported(self):
        with TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / 'auth.json'
            _write_auth(auth_file, tokens=None, api_key='sk-test')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                with self.assertRaises(CodexCredentialsError) as ctx:
                    read_codex_credentials()

        self.assertIn('OPENAI_API_KEY', ctx.exception.server_message)

    def test_read_access_token_returns_none_on_invalid_credentials(self):
        with TemporaryDirectory() as tmp:
            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                self.assertIsNone(read_codex_access_token())

    def test_api_headers_include_required_codex_headers(self):
        with TemporaryDirectory() as tmp:
            _write_auth(Path(tmp) / 'auth.json')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                headers = api_headers()

        self.assertEqual(headers['Authorization'], 'Bearer access-old')
        self.assertEqual(headers['ChatGPT-Account-Id'], 'account-123')
        self.assertEqual(headers['User-Agent'], CODEX_USER_AGENT)


class TestCodexRefresh(unittest.TestCase):
    """Tests for Codex OAuth refresh behavior."""

    def test_needs_refresh_after_eight_days(self):
        with TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / 'auth.json'
            _write_auth(auth_file, last_refresh='2026-01-01T00:00:00Z')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                credentials = read_codex_credentials()

        now = datetime(2026, 1, 9, 0, 0, 1, tzinfo=timezone.utc)
        self.assertTrue(credentials.needs_refresh(now))

    def test_does_not_need_refresh_before_eight_days(self):
        with TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / 'auth.json'
            _write_auth(auth_file, last_refresh='2026-01-01T00:00:00Z')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                credentials = read_codex_credentials()

        now = datetime(2026, 1, 8, 23, 59, 59, tzinfo=timezone.utc)
        self.assertFalse(credentials.needs_refresh(now))
        self.assertEqual(CODEX_REFRESH_INTERVAL_SECONDS, 8 * 24 * 3600)

    @patch('src.integrations.codex_api.requests.post')
    def test_refresh_saves_new_tokens_and_preserves_account_id(self, mock_post):
        mock_post.return_value = _mock_response({
            'access_token': 'access-new',
            'refresh_token': 'refresh-new',
            'id_token': 'id-new',
        })

        with TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / 'auth.json'
            _write_auth(auth_file, last_refresh='2000-01-01T00:00:00Z')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                result = refresh_codex_token()
                saved = json.loads(auth_file.read_text(encoding='utf-8'))

        self.assertTrue(result.success)
        self.assertFalse(result.updated)
        self.assertEqual(saved['tokens']['access_token'], 'access-new')
        self.assertEqual(saved['tokens']['refresh_token'], 'refresh-new')
        self.assertEqual(saved['tokens']['id_token'], 'id-new')
        self.assertEqual(saved['tokens']['account_id'], 'account-123')
        self.assertIn('last_refresh', saved)
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args.args[0], CODEX_AUTH_URL)
        self.assertEqual(mock_post.call_args.kwargs['json']['client_id'], CODEX_CLIENT_ID)
        self.assertEqual(mock_post.call_args.kwargs['json']['refresh_token'], 'refresh-old')

    @patch('src.integrations.codex_api.requests.post')
    @patch('src.integrations.codex_api.requests.get')
    def test_fetch_usage_refreshes_stale_token_before_request(self, mock_get, mock_post):
        mock_post.return_value = _mock_response({'access_token': 'access-new', 'refresh_token': 'refresh-new'})
        mock_get.return_value = _mock_response({
            'rate_limit': {
                'primary_window': {'used_percent': 10, 'reset_at': 1735401600, 'limit_window_seconds': 18000},
            },
        })

        with TemporaryDirectory() as tmp:
            _write_auth(Path(tmp) / 'auth.json', last_refresh='2000-01-01T00:00:00Z')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                result = fetch_codex_usage()

        self.assertIn('five_hour', result)
        mock_post.assert_called_once()
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.args[0], CODEX_USAGE_URL)
        self.assertEqual(mock_get.call_args.kwargs['headers']['Authorization'], 'Bearer access-new')

    @patch('src.integrations.codex_api.requests.post')
    @patch('src.integrations.codex_api.requests.get')
    def test_fetch_usage_does_not_refresh_fresh_token(self, mock_get, mock_post):
        mock_get.return_value = _mock_response({
            'rate_limit': {
                'secondary_window': {'used_percent': 7, 'reset_at': 1735920000, 'limit_window_seconds': 604800},
            },
        })

        with TemporaryDirectory() as tmp:
            _write_auth(Path(tmp) / 'auth.json', last_refresh='2999-01-01T00:00:00Z')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                result = fetch_codex_usage()

        self.assertIn('seven_day', result)
        mock_post.assert_not_called()

    @patch('src.integrations.codex_api.requests.post')
    @patch('src.integrations.codex_api.requests.get')
    def test_failed_stale_token_refresh_does_not_call_usage(self, mock_get, mock_post):
        mock_post.return_value = _mock_response({'error': {'message': 'refresh expired'}}, status_code=401)

        with TemporaryDirectory() as tmp:
            _write_auth(Path(tmp) / 'auth.json', last_refresh='2000-01-01T00:00:00Z')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                result = fetch_codex_usage()

        self.assertTrue(result['auth_error'])
        self.assertTrue(result['refresh_attempted'])
        self.assertEqual(result['server_message'], 'refresh expired')
        mock_get.assert_not_called()


class TestCodexUsageMapping(unittest.TestCase):
    """Tests for mapping Codex usage responses to CCMonitor fields."""

    def test_maps_five_hour_and_seven_day_windows(self):
        result = map_codex_usage_response({
            'plan_type': 'pro',
            'rate_limit': {
                'primary_window': {'used_percent': 15, 'reset_at': 1735401600, 'limit_window_seconds': 18000},
                'secondary_window': {'used_percent': 5, 'reset_at': 1735920000, 'limit_window_seconds': 604800},
            },
            'credits': {'balance': 150.0},
        })

        self.assertEqual(result['five_hour']['utilization'], 15.0)
        self.assertEqual(result['seven_day']['utilization'], 5.0)
        self.assertIn('2024-12', result['five_hour']['resets_at'])
        self.assertEqual(result['__profile']['organization']['organization_type'], 'pro')
        self.assertNotIn('extra_usage', result)

    def test_weekly_only_maps_to_seven_day(self):
        result = map_codex_usage_response({
            'rate_limit': {
                'primary_window': {'used_percent': 64, 'reset_at': 1735920000, 'limit_window_seconds': 604800},
            },
        })

        self.assertNotIn('five_hour', result)
        self.assertEqual(result['seven_day']['utilization'], 64.0)

    def test_bad_window_values_are_skipped(self):
        result = map_codex_usage_response({
            'plan_type': 'unknown_plan',
            'rate_limit': {
                'primary_window': {'used_percent': 'bad', 'reset_at': 1735401600, 'limit_window_seconds': 18000},
                'secondary_window': {'used_percent': 5, 'reset_at': {}, 'limit_window_seconds': 604800},
            },
        })

        self.assertNotIn('five_hour', result)
        self.assertNotIn('seven_day', result)
        self.assertEqual(result['__profile']['organization']['organization_type'], 'unknown_plan')

    def test_unknown_window_seconds_are_skipped(self):
        result = map_codex_usage_response({
            'rate_limit': {
                'primary_window': {'used_percent': 10, 'reset_at': 1735401600, 'limit_window_seconds': 3600},
            },
        })

        self.assertEqual(result, {})

    def test_non_integer_window_seconds_are_skipped(self):
        result = map_codex_usage_response({
            'rate_limit': {
                'primary_window': {'used_percent': 10, 'reset_at': 1735401600, 'limit_window_seconds': 18000.5},
            },
        })

        self.assertEqual(result, {})


class TestCodexFetchErrors(unittest.TestCase):
    """Tests for Codex usage fetch error handling."""

    @patch('src.integrations.codex_api.requests.get')
    def test_unauthorized_sets_auth_error(self, mock_get):
        mock_get.return_value = _mock_response({'error': {'message': 'expired'}}, status_code=401)

        with TemporaryDirectory() as tmp:
            _write_auth(Path(tmp) / 'auth.json')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                result = fetch_codex_usage()

        self.assertTrue(result['auth_error'])
        self.assertIn('Codex', result['error'])

    @patch('src.integrations.codex_api.requests.get')
    def test_rate_limit_sets_retry_after(self, mock_get):
        mock_get.return_value = _mock_response(
            {'error': {'message': 'Rate limited. Please try again later.'}},
            status_code=429,
            headers={'Retry-After': '60'},
        )

        with TemporaryDirectory() as tmp:
            _write_auth(Path(tmp) / 'auth.json')

            with patch.dict('os.environ', {'CODEX_HOME': tmp}):
                result = fetch_codex_usage()

        self.assertTrue(result['rate_limited'])
        self.assertEqual(result['retry_after'], 60)
        self.assertEqual(result['server_message'], 'Rate limited.')


if __name__ == '__main__':
    unittest.main()
