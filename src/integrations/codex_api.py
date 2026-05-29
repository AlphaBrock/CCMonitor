"""
-------------------------------------------------
   File Name   :     codex_api.py
   Description :     Codex OAuth用量接口
   Company     :     JohnWick
   Author      :     linjcciam1314@gmail.com
   Date        :     2026-05-29
-------------------------------------------------
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.integrations.claude_cli import RefreshResult
from src.presentation.i18n import ACTIVE_LANG, T

__all__ = [
    'CODEX_AUTH_URL', 'CODEX_CLIENT_ID', 'CODEX_REFRESH_INTERVAL_SECONDS', 'CODEX_USAGE_URL', 'CODEX_USER_AGENT',
    'CodexCredentials', 'CodexCredentialsError',
    'api_headers', 'codex_auth_path', 'fetch_codex_profile', 'fetch_codex_usage',
    'map_codex_usage_response', 'read_codex_access_token', 'read_codex_credentials', 'refresh_codex_token',
]

CODEX_AUTH_URL = 'https://auth.openai.com/oauth/token'
CODEX_USAGE_URL = 'https://chatgpt.com/backend-api/wham/usage'
CODEX_CLIENT_ID = 'app_EMoamEEZ73f0CkXaXp7hrann'
CODEX_USER_AGENT = 'codex-cli'
CODEX_REFRESH_INTERVAL_SECONDS = 8 * 24 * 3600
CODEX_REFRESH_HEADERS = {'Content-Type': 'application/json'}
CODEX_USAGE_HEADERS = {'User-Agent': CODEX_USER_AGENT}
_CODEX_REFRESH_SCOPE = 'openid profile email'
_WINDOW_FIELD_BY_SECONDS = {
    18_000: 'five_hour',
    604_800: 'seven_day',
}
_PROFILE_KEY = '__profile'


class CodexCredentialsError(Exception):
    """Codex凭据读取失败。"""

    def __init__(self, message: str, *, server_message: str = '') -> None:
        super().__init__(message)
        self.message = message
        self.server_message = server_message


@dataclass(frozen=True)
class CodexCredentials:
    """Codex OAuth凭据。"""

    access_token: str
    refresh_token: str
    account_id: str
    id_token: str
    last_refresh: datetime | None
    path: Path

    def needs_refresh(self, now: datetime | None = None) -> bool:
        """判断访问令牌是否需要刷新。"""
        if self.last_refresh is None:
            return True

        current_time = now or datetime.now(timezone.utc)
        return (current_time - self.last_refresh).total_seconds() > CODEX_REFRESH_INTERVAL_SECONDS


def codex_auth_path(env: dict[str, str] | None = None) -> Path:
    """返回Codex auth.json路径。"""
    environment = env if env is not None else os.environ
    codex_home = environment.get('CODEX_HOME', '')
    if codex_home:
        return Path(codex_home) / 'auth.json'
    return Path.home() / '.codex' / 'auth.json'


def read_codex_credentials() -> CodexCredentials:
    """读取Codex OAuth凭据。"""
    path = codex_auth_path()
    if not path.is_file():
        raise CodexCredentialsError(_codex_no_token_message(), server_message=str(path))

    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise CodexCredentialsError(_codex_no_token_message(), server_message=f'Invalid Codex auth.json: {exc}') from exc
    except OSError as exc:
        raise CodexCredentialsError(_codex_no_token_message(), server_message=f'Cannot read Codex auth.json: {exc}') from exc

    if not isinstance(raw, dict):
        raise CodexCredentialsError(_codex_no_token_message(), server_message='Codex auth.json must be a JSON object.')

    api_key = raw.get('OPENAI_API_KEY')
    if isinstance(api_key, str) and api_key:
        raise CodexCredentialsError(_codex_no_token_message(), server_message='OPENAI_API_KEY cannot access Codex OAuth usage.')

    tokens = raw.get('tokens')
    if not isinstance(tokens, dict):
        raise CodexCredentialsError(_codex_no_token_message(), server_message='Codex auth.json has no OAuth tokens.')

    access_token = tokens.get('access_token')
    refresh_token = tokens.get('refresh_token')
    account_id = tokens.get('account_id')
    id_token = tokens.get('id_token') or ''
    if not isinstance(access_token, str) or not access_token:
        raise CodexCredentialsError(_codex_no_token_message(), server_message='Codex access_token is missing.')
    if not isinstance(refresh_token, str) or not refresh_token:
        raise CodexCredentialsError(_codex_no_token_message(), server_message='Codex refresh_token is missing.')
    if not isinstance(account_id, str) or not account_id:
        raise CodexCredentialsError(_codex_no_token_message(), server_message='Codex account_id is missing.')
    if not isinstance(id_token, str):
        id_token = ''

    return CodexCredentials(
        access_token=access_token,
        refresh_token=refresh_token,
        account_id=account_id,
        id_token=id_token,
        last_refresh=_parse_last_refresh(raw.get('last_refresh')),
        path=path,
    )


def read_codex_access_token() -> str | None:
    """读取当前Codex访问令牌。"""
    try:
        return read_codex_credentials().access_token
    except CodexCredentialsError:
        return None


def api_headers() -> dict[str, str] | None:
    """返回Codex usage API请求头。"""
    try:
        credentials = read_codex_credentials()
    except CodexCredentialsError:
        return None

    return _usage_headers(credentials)


def fetch_codex_usage() -> dict[str, Any]:
    """获取并映射Codex用量。"""
    try:
        credentials = read_codex_credentials()
    except CodexCredentialsError as exc:
        return _credentials_error_response(exc)

    if credentials.needs_refresh():
        refresh_result = refresh_codex_token()
        if not refresh_result.success:
            return {
                'error': _codex_auth_expired_message(),
                'auth_error': True,
                'refresh_attempted': True,
                'server_message': refresh_result.error,
            }
        try:
            credentials = read_codex_credentials()
        except CodexCredentialsError as exc:
            return _credentials_error_response(exc)

    try:
        response = requests.get(CODEX_USAGE_URL, headers=_usage_headers(credentials), timeout=10)
        response.raise_for_status()
        raw = response.json()
    except requests.ConnectionError:
        return {'error': _codex_connection_error()}
    except requests.HTTPError as exc:
        return _http_error_response(exc.response)
    except Exception:
        return {'error': _codex_connection_error()}

    if not isinstance(raw, dict):
        return {'error': _codex_connection_error(), 'server_message': 'Invalid Codex usage response.'}

    return map_codex_usage_response(raw)


def fetch_codex_profile() -> dict[str, Any] | None:
    """Codex资料随usage响应返回，独立profile接口为空。"""
    return None


def refresh_codex_token() -> RefreshResult:
    """刷新Codex OAuth令牌并写回auth.json。"""
    try:
        credentials = read_codex_credentials()
    except CodexCredentialsError as exc:
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error=_join_error(exc.message, exc.server_message))

    body = {
        'client_id': CODEX_CLIENT_ID,
        'grant_type': 'refresh_token',
        'refresh_token': credentials.refresh_token,
        'scope': _CODEX_REFRESH_SCOPE,
    }

    try:
        response = requests.post(CODEX_AUTH_URL, headers=CODEX_REFRESH_HEADERS, json=body, timeout=10)
        response.raise_for_status()
        raw = response.json()
    except requests.ConnectionError:
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error=_codex_connection_error())
    except requests.HTTPError as exc:
        message = _extract_server_message(exc.response) or _codex_auth_expired_message()
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error=message)
    except Exception as exc:
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error=str(exc)[:200] or T['connection_error'])

    if not isinstance(raw, dict):
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error='Invalid Codex token refresh response.')

    access_token = raw.get('access_token')
    refresh_token = raw.get('refresh_token')
    id_token = raw.get('id_token')
    if not isinstance(access_token, str) or not access_token:
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error='Codex token refresh response has no access_token.')
    if not isinstance(refresh_token, str) or not refresh_token:
        refresh_token = credentials.refresh_token
    if not isinstance(id_token, str):
        id_token = credentials.id_token

    try:
        _save_refreshed_credentials(credentials, access_token=access_token, refresh_token=refresh_token, id_token=id_token)
    except (OSError, json.JSONDecodeError) as exc:
        return RefreshResult(success=False, updated=False, old_version='', new_version='', error=f'Cannot save Codex auth.json: {exc}')

    return RefreshResult(success=True, updated=False, old_version='', new_version='', error='')


def map_codex_usage_response(raw: dict[str, Any]) -> dict[str, Any]:
    """把Codex wham/usage响应映射成CCMonitor用量结构。"""
    result: dict[str, Any] = {}
    rate_limit = raw.get('rate_limit')
    if isinstance(rate_limit, dict):
        for window_key in ('primary_window', 'secondary_window'):
            window = rate_limit.get(window_key)
            mapped_window = _map_window(window)
            if mapped_window is None or not isinstance(window, dict):
                continue

            window_seconds = _number_value(window.get('limit_window_seconds'))
            field = _WINDOW_FIELD_BY_SECONDS.get(int(window_seconds)) if window_seconds is not None and window_seconds.is_integer() else None
            if field and field not in result:
                result[field] = mapped_window

    profile = _profile_from_response(raw)
    if profile is not None:
        result[_PROFILE_KEY] = profile

    return result


def _parse_last_refresh(value: object) -> datetime | None:
    """解析Codex last_refresh时间。"""
    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    """格式化UTC时间。"""
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _usage_headers(credentials: CodexCredentials) -> dict[str, str]:
    """构造Codex usage API请求头。"""
    headers = dict(CODEX_USAGE_HEADERS)
    headers['Authorization'] = f'Bearer {credentials.access_token}'
    headers['ChatGPT-Account-Id'] = credentials.account_id
    return headers


def _save_refreshed_credentials(credentials: CodexCredentials, *, access_token: str, refresh_token: str, id_token: str) -> None:
    """保存刷新后的Codex OAuth令牌。"""
    raw = json.loads(credentials.path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict):
        raw = {}

    tokens = raw.get('tokens') if isinstance(raw.get('tokens'), dict) else {}
    tokens = dict(tokens)
    tokens['access_token'] = access_token
    tokens['refresh_token'] = refresh_token
    tokens['account_id'] = credentials.account_id
    if id_token:
        tokens['id_token'] = id_token
    raw['tokens'] = tokens
    raw['last_refresh'] = _format_utc(datetime.now(timezone.utc))

    credentials.path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def _credentials_error_response(exc: CodexCredentialsError) -> dict[str, Any]:
    """转换Codex凭据错误为UI可展示响应。"""
    response: dict[str, Any] = {'error': exc.message}
    if exc.server_message:
        response['server_message'] = exc.server_message
    return response


def _http_error_response(response: requests.Response | None) -> dict[str, Any]:
    """转换Codex HTTP错误为统一响应。"""
    code = response.status_code if response is not None else 0
    server_message = _extract_server_message(response)
    extra: dict[str, Any] = {}
    if server_message:
        extra['server_message'] = server_message

    if code in (401, 403):
        return {**extra, 'error': _codex_auth_expired_message(), 'auth_error': True}
    if code == 429:
        retry = _parse_retry_after(response)
        if retry is not None:
            extra['retry_after'] = retry
        return {**extra, 'error': T['http_error'].format(code=429), 'rate_limited': True}
    if 500 <= code < 600:
        return {**extra, 'error': _codex_server_error(code)}
    return {**extra, 'error': T['http_error'].format(code=code or '?')}


def _extract_server_message(response: requests.Response | None) -> str | None:
    """提取服务端错误消息。"""
    if response is None:
        return None

    try:
        raw = response.json()
    except Exception:
        return None

    if not isinstance(raw, dict):
        return None

    message = None
    error = raw.get('error')
    if isinstance(error, dict):
        message = error.get('message') or error.get('code')
    elif isinstance(error, str):
        message = error
    if isinstance(message, str):
        return message.removesuffix(' Please try again later.').removesuffix(' Please try again later').strip() or None
    return None


def _parse_retry_after(response: requests.Response | None) -> int | None:
    """解析Retry-After秒数。"""
    if response is None:
        return None

    raw = response.headers.get('Retry-After')
    if raw is None:
        return None

    try:
        return max(int(raw), 0)
    except (TypeError, ValueError):
        return None


def _map_window(value: object) -> dict[str, Any] | None:
    """映射单个Codex限流窗口。"""
    if not isinstance(value, dict):
        return None

    used_percent = _number_value(value.get('used_percent'))
    reset_at = _number_value(value.get('reset_at'))
    limit_window_seconds = _number_value(value.get('limit_window_seconds'))
    if used_percent is None or reset_at is None or limit_window_seconds is None:
        return None

    try:
        reset_time = datetime.fromtimestamp(float(reset_at), timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return None

    return {
        'utilization': float(used_percent),
        'resets_at': reset_time,
    }


def _number_value(value: object) -> float | None:
    """读取数字值，排除布尔值。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _profile_from_response(raw: dict[str, Any]) -> dict[str, Any] | None:
    """从Codex响应中提取可选资料。"""
    account: dict[str, Any] = {}
    organization: dict[str, Any] = {}

    email = raw.get('email')
    if isinstance(email, str) and email:
        account['email'] = email

    plan_type = raw.get('plan_type')
    if isinstance(plan_type, str) and plan_type:
        organization['organization_type'] = plan_type

    if not account and not organization:
        return None

    return {'account': account, 'organization': organization}


def _codex_no_token_message() -> str:
    """返回Codex未登录提示。"""
    if ACTIVE_LANG.startswith('zh'):
        return '未找到 Codex OAuth 令牌。请先运行 codex 登录。'
    return 'No Codex OAuth token. Run codex to log in first.'


def _codex_connection_error() -> str:
    """返回Codex连接错误提示。"""
    if ACTIVE_LANG.startswith('zh'):
        return '无法连接 Codex 用量接口。'
    return 'Could not connect to Codex usage API.'


def _codex_server_error(code: int) -> str:
    """返回Codex服务端错误提示。"""
    if ACTIVE_LANG.startswith('zh'):
        return f'Codex 用量接口暂时不可用（HTTP {code}）。'
    return f'Codex usage API temporarily unavailable (HTTP {code}).'


def _codex_auth_expired_message() -> str:
    """返回Codex会话过期提示。"""
    if ACTIVE_LANG.startswith('zh'):
        return 'Codex 会话已过期。请重新运行 codex 登录。'
    return 'Codex session expired. Run codex to log in again.'


def _join_error(message: str, server_message: str) -> str:
    """合并错误消息。"""
    if server_message:
        return f'{message}\n{server_message}'
    return message
