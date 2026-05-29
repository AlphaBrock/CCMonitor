"""
API Client
===========

Reads usage-provider OAuth credentials and communicates with the
provider APIs.  This is the only module that handles credentials.

Network communication is limited to ``api.anthropic.com``,
``auth.openai.com``, and ``chatgpt.com``.
Credentials used only in HTTP Authorization headers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from src.integrations.codex_api import (
    api_headers as codex_api_headers,
    fetch_codex_profile,
    fetch_codex_usage,
    read_codex_access_token,
    refresh_codex_token,
)
from src.integrations.claude_cli import RefreshResult
from src.presentation.i18n import T
from src.presentation.settings import USAGE_PROVIDER

__all__ = [
    'API_URL_USAGE', 'API_URL_PROFILE', 'CLAUDE_CONFIG_DIR', 'CLAUDE_CREDENTIALS',
    'api_headers', 'api_headers_for_provider', 'auth_warning_text',
    'fetch_claude_profile', 'fetch_claude_usage', 'fetch_profile', 'fetch_usage',
    'fetch_profile_for_provider', 'fetch_usage_for_provider',
    'read_access_token', 'read_access_token_for_provider', 'read_claude_access_token',
    'refresh_auth_token', 'refresh_auth_token_for_provider',
]

# API endpoints & credentials
API_URL_USAGE = 'https://api.anthropic.com/api/oauth/usage'
API_URL_PROFILE = 'https://api.anthropic.com/api/oauth/profile'
CLAUDE_CONFIG_DIR = Path(os.environ.get('CLAUDE_CONFIG_DIR', '')) if os.environ.get('CLAUDE_CONFIG_DIR') else Path.home() / '.claude'
CLAUDE_CREDENTIALS = CLAUDE_CONFIG_DIR / '.credentials.json'
_FALLBACK_USER_AGENT = 'claude-code/2.1.85'


def read_access_token() -> str | None:
    """Read the current access token for the configured usage provider."""
    return read_access_token_for_provider(USAGE_PROVIDER)


def read_access_token_for_provider(provider: str) -> str | None:
    """Read the current access token for a specific provider."""
    if provider == 'codex':
        return read_codex_access_token()
    if provider == 'claude':
        return read_claude_access_token()
    return None


def read_claude_access_token() -> str | None:
    """Read the current access token from the Claude credentials file."""
    if not CLAUDE_CREDENTIALS.exists():
        return None

    try:
        creds = json.loads(CLAUDE_CREDENTIALS.read_text())
        return creds.get('claudeAiOauth', {}).get('accessToken') or None
    except (json.JSONDecodeError, KeyError):
        return None


def api_headers() -> dict[str, str] | None:
    """Return auth headers for the configured usage provider, or None."""
    return api_headers_for_provider(USAGE_PROVIDER)


def api_headers_for_provider(provider: str) -> dict[str, str] | None:
    """Return auth headers for a specific provider, or None."""
    if provider == 'codex':
        return codex_api_headers()
    if provider == 'claude':
        return claude_api_headers()
    return None


def claude_api_headers() -> dict[str, str] | None:
    """Return auth headers for the Anthropic OAuth API, or None."""
    token = read_claude_access_token()
    if not token:
        return None

    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'User-Agent': _user_agent(),
        'anthropic-beta': 'oauth-2025-04-20',
    }


def fetch_usage() -> dict[str, Any]:
    """Fetch usage data from the configured usage provider."""
    if USAGE_PROVIDER == 'codex':
        return fetch_codex_usage()

    headers = api_headers()
    return _fetch_claude_usage_with_headers(headers)


def fetch_usage_for_provider(provider: str) -> dict[str, Any]:
    """Fetch usage data from a specific provider."""
    if provider == 'codex':
        return fetch_codex_usage()
    if provider == 'claude':
        return fetch_claude_usage()
    return {'error': T['http_error'].format(code='?')}


def fetch_claude_usage() -> dict[str, Any]:
    """Fetch Claude usage data directly from the Anthropic OAuth API."""
    return _fetch_claude_usage_with_headers(claude_api_headers())


def _fetch_claude_usage_with_headers(headers: dict[str, str] | None) -> dict[str, Any]:
    """Fetch Claude usage data with precomputed headers."""
    if not headers:
        return {'error': T['no_token']}

    try:
        resp = requests.get(API_URL_USAGE, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        return {'error': T['connection_error']}
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 0
        server_msg = _extract_server_message(e.response)
        extra: dict[str, Any] = {}
        if server_msg:
            extra['server_message'] = server_msg

        if code == 401:
            return {**extra, 'error': T['auth_expired'], 'auth_error': True}
        if code == 429:
            retry = _parse_retry_after(e.response)
            if retry is not None:
                extra['retry_after'] = retry
            return {**extra, 'error': T['http_error'].format(code=429), 'rate_limited': True}
        if 500 <= code < 600:
            return {**extra, 'error': T['server_error'].format(code=code)}
        return {**extra, 'error': T['http_error'].format(code=code or '?')}
    except Exception:
        return {'error': T['connection_error']}


def fetch_profile() -> dict[str, Any] | None:
    """Fetch account profile from the configured usage provider."""
    if USAGE_PROVIDER == 'codex':
        return fetch_codex_profile()

    headers = api_headers()
    return _fetch_claude_profile_with_headers(headers)


def fetch_profile_for_provider(provider: str) -> dict[str, Any] | None:
    """Fetch account profile from a specific provider."""
    if provider == 'codex':
        return fetch_codex_profile()
    if provider == 'claude':
        return fetch_claude_profile()
    return None


def fetch_claude_profile() -> dict[str, Any] | None:
    """Fetch Claude account profile directly from the Anthropic OAuth API."""
    return _fetch_claude_profile_with_headers(claude_api_headers())


def _fetch_claude_profile_with_headers(headers: dict[str, str] | None) -> dict[str, Any] | None:
    """Fetch Claude profile with precomputed headers."""
    if not headers:
        return None

    try:
        resp = requests.get(API_URL_PROFILE, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def refresh_auth_token() -> RefreshResult:
    """Refresh the OAuth token for the configured usage provider."""
    return refresh_auth_token_for_provider(USAGE_PROVIDER)


def refresh_auth_token_for_provider(provider: str) -> RefreshResult:
    """Refresh the OAuth token for a specific provider."""
    if provider == 'codex':
        return refresh_codex_token()

    from src.integrations.claude_cli import refresh_token

    return refresh_token()


def auth_warning_text() -> tuple[str, str]:
    """Return the startup no-token notification body and title."""
    if USAGE_PROVIDER == 'codex':
        return (
            '未找到 Codex OAuth 令牌。\n请先运行 codex 登录。'
            if _is_chinese_locale()
            else 'No Codex OAuth token found.\nRun codex to log in first.',
            _provider_popup_title(),
        )

    return f"{T['warn_no_token']}\n{T['warn_login']}", T['popup_title']


# Helpers


def _provider_popup_title() -> str:
    """Return popup title for the configured usage provider."""
    if USAGE_PROVIDER == 'codex':
        return 'Codex 用量' if _is_chinese_locale() else 'Codex Usage'
    return T['popup_title']


def _is_chinese_locale() -> bool:
    """Return whether the active UI locale is Chinese."""
    from src.presentation.i18n import ACTIVE_LANG

    return ACTIVE_LANG.startswith('zh')


def _user_agent() -> str:
    """Return the User-Agent string with the installed Claude Code version."""
    from src.integrations.claude_cli import CLAUDE_CLI_PATH, cli_version

    version = cli_version(CLAUDE_CLI_PATH)
    return f'claude-code/{version}' if version else _FALLBACK_USER_AGENT


def _extract_server_message(response: requests.Response | None) -> str | None:
    """Extract ``error.message`` from a JSON error response body.

    Strips the trailing "Please try again later." suffix that the API
    appends to some error messages - the app retries automatically, so
    the advice would be misleading.
    """
    if response is None:
        return None
    try:
        msg = response.json().get('error', {}).get('message') or None
        if msg:
            msg = msg.removesuffix(' Please try again later.').removesuffix(' Please try again later').strip()
        return msg or None
    except Exception:
        return None


def _parse_retry_after(response: requests.Response | None) -> int | None:
    """Parse the ``Retry-After`` header as an integer number of seconds."""
    if response is None:
        return None
    raw = response.headers.get('Retry-After')
    if raw is None:
        return None
    try:
        return max(int(raw), 0)
    except (ValueError, TypeError):
        return None
