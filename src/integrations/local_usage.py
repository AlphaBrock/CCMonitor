"""
-------------------------------------------------
   File Name   :     local_usage.py
   Description :     本地日志成本与Token统计
   Company     :     JohnWick
   Author      :     linjcciam1314@gmail.com
   Date        :     2026-05-29
-------------------------------------------------
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

__all__ = [
    'LocalUsageSummary', 'clear_local_usage_cache', 'local_usage_summary',
]

_MAX_LINE_BYTES = 512 * 1024
_HISTORY_DAYS = 30
_CODEX_DEFAULT_MODEL = 'gpt-5'


@dataclass(frozen=True)
class _Pricing:
    input_cost: float
    output_cost: float
    cache_read_cost: float | None = None
    cache_create_cost: float | None = None
    threshold_tokens: int | None = None
    input_cost_above_threshold: float | None = None
    output_cost_above_threshold: float | None = None
    cache_read_cost_above_threshold: float | None = None
    cache_create_cost_above_threshold: float | None = None


@dataclass(frozen=True)
class _UsageRow:
    timestamp: datetime
    model: str
    input_tokens: int
    cache_read_tokens: int
    cache_create_tokens: int
    output_tokens: int
    cost_usd: float | None
    total_tokens_override: int | None = None

    @property
    def total_tokens(self) -> int:
        if self.total_tokens_override is not None:
            return self.total_tokens_override
        return self.input_tokens + self.cache_read_tokens + self.cache_create_tokens + self.output_tokens


@dataclass(frozen=True)
class LocalUsageSummary:
    """本地日志统计摘要。"""

    today_cost_usd: float | None
    total_cost_usd: float | None
    total_tokens: int | None
    latest_tokens: int | None
    top_model: str | None


@dataclass(frozen=True)
class _CachedFile:
    mtime_ns: int
    size: int
    rows: tuple[_UsageRow, ...]


@dataclass(frozen=True)
class _UsageFile:
    source: str
    path: Path


_FILE_CACHE: dict[tuple[str, str, str], _CachedFile] = {}

_CODEX_PRICING: dict[str, _Pricing] = {
    'gpt-5': _Pricing(1.25e-6, 1e-5, cache_read_cost=1.25e-7),
    'gpt-5-codex': _Pricing(1.25e-6, 1e-5, cache_read_cost=1.25e-7),
    'gpt-5-mini': _Pricing(2.5e-7, 2e-6, cache_read_cost=2.5e-8),
    'gpt-5-nano': _Pricing(5e-8, 4e-7, cache_read_cost=5e-9),
    'gpt-5-pro': _Pricing(1.5e-5, 1.2e-4),
    'gpt-5.1': _Pricing(1.25e-6, 1e-5, cache_read_cost=1.25e-7),
    'gpt-5.1-codex': _Pricing(1.25e-6, 1e-5, cache_read_cost=1.25e-7),
    'gpt-5.1-codex-max': _Pricing(1.25e-6, 1e-5, cache_read_cost=1.25e-7),
    'gpt-5.1-codex-mini': _Pricing(2.5e-7, 2e-6, cache_read_cost=2.5e-8),
    'gpt-5.2': _Pricing(1.75e-6, 1.4e-5, cache_read_cost=1.75e-7),
    'gpt-5.2-codex': _Pricing(1.75e-6, 1.4e-5, cache_read_cost=1.75e-7),
    'gpt-5.2-pro': _Pricing(2.1e-5, 1.68e-4),
    'gpt-5.3-codex': _Pricing(1.75e-6, 1.4e-5, cache_read_cost=1.75e-7),
    'gpt-5.3-codex-spark': _Pricing(0, 0, cache_read_cost=0),
    'gpt-5.4': _Pricing(
        2.5e-6,
        1.5e-5,
        cache_read_cost=2.5e-7,
        threshold_tokens=272_000,
        input_cost_above_threshold=5e-6,
        output_cost_above_threshold=2.25e-5,
        cache_read_cost_above_threshold=5e-7,
    ),
    'gpt-5.4-mini': _Pricing(7.5e-7, 4.5e-6, cache_read_cost=7.5e-8),
    'gpt-5.4-nano': _Pricing(2e-7, 1.25e-6, cache_read_cost=2e-8),
    'gpt-5.4-pro': _Pricing(3e-5, 1.8e-4),
    'gpt-5.5': _Pricing(
        5e-6,
        3e-5,
        cache_read_cost=5e-7,
        threshold_tokens=272_000,
        input_cost_above_threshold=1e-5,
        output_cost_above_threshold=4.5e-5,
        cache_read_cost_above_threshold=1e-6,
    ),
    'gpt-5.5-pro': _Pricing(3e-5, 1.8e-4),
}

_CLAUDE_PRICING: dict[str, _Pricing] = {
    'claude-haiku-4-5': _Pricing(1e-6, 5e-6, cache_read_cost=1e-7, cache_create_cost=1.25e-6),
    'claude-opus-4-5': _Pricing(5e-6, 2.5e-5, cache_read_cost=5e-7, cache_create_cost=6.25e-6),
    'claude-opus-4-6': _Pricing(5e-6, 2.5e-5, cache_read_cost=5e-7, cache_create_cost=6.25e-6),
    'claude-opus-4-7': _Pricing(5e-6, 2.5e-5, cache_read_cost=5e-7, cache_create_cost=6.25e-6),
    'claude-opus-4-8': _Pricing(5e-6, 2.5e-5, cache_read_cost=5e-7, cache_create_cost=6.25e-6),
    'claude-sonnet-4-5': _Pricing(
        3e-6,
        1.5e-5,
        cache_read_cost=3e-7,
        cache_create_cost=3.75e-6,
        threshold_tokens=200_000,
        input_cost_above_threshold=6e-6,
        output_cost_above_threshold=2.25e-5,
        cache_read_cost_above_threshold=6e-7,
        cache_create_cost_above_threshold=7.5e-6,
    ),
    'claude-sonnet-4-6': _Pricing(
        3e-6,
        1.5e-5,
        cache_read_cost=3e-7,
        cache_create_cost=3.75e-6,
        threshold_tokens=200_000,
        input_cost_above_threshold=6e-6,
        output_cost_above_threshold=2.25e-5,
        cache_read_cost_above_threshold=6e-7,
        cache_create_cost_above_threshold=7.5e-6,
    ),
    'claude-opus-4': _Pricing(1.5e-5, 7.5e-5, cache_read_cost=1.5e-6, cache_create_cost=1.875e-5),
    'claude-opus-4-1': _Pricing(1.5e-5, 7.5e-5, cache_read_cost=1.5e-6, cache_create_cost=1.875e-5),
    'claude-sonnet-4': _Pricing(
        3e-6,
        1.5e-5,
        cache_read_cost=3e-7,
        cache_create_cost=3.75e-6,
        threshold_tokens=200_000,
        input_cost_above_threshold=6e-6,
        output_cost_above_threshold=2.25e-5,
        cache_read_cost_above_threshold=6e-7,
        cache_create_cost_above_threshold=7.5e-6,
    ),
}


def clear_local_usage_cache() -> None:
    """清空进程内文件解析缓存。"""
    _FILE_CACHE.clear()


def local_usage_summary(provider_id: str, *, now: datetime | None = None, env: dict[str, str] | None = None) -> LocalUsageSummary:
    """读取本地日志并返回30天统计摘要。"""
    current_time = now or datetime.now().astimezone()
    environment = env if env is not None else os.environ
    today = current_time.date()
    start_date = today - timedelta(days=_HISTORY_DAYS - 1)

    rows: list[_UsageRow] = []
    for usage_file in _provider_files(provider_id, environment, start_date):
        rows.extend(_cached_rows(provider_id, usage_file.source, usage_file.path))

    filtered = [row for row in rows if start_date <= row.timestamp.astimezone().date() <= today]
    if not filtered:
        return LocalUsageSummary(None, None, None, None, None)

    today_rows = [row for row in filtered if row.timestamp.astimezone().date() == today]
    total_tokens = sum(row.total_tokens for row in filtered)
    latest = max(filtered, key=lambda row: row.timestamp)
    top_model = _top_model(filtered)

    return LocalUsageSummary(
        today_cost_usd=_sum_cost(today_rows),
        total_cost_usd=_sum_cost(filtered),
        total_tokens=total_tokens if total_tokens > 0 else None,
        latest_tokens=latest.total_tokens if latest.total_tokens > 0 else None,
        top_model=top_model,
    )


def _provider_files(provider_id: str, env: dict[str, str], start_date: object) -> list[_UsageFile]:
    """返回 provider 对应的可读 JSONL 文件。"""
    roots: list[tuple[str, Path]] = []
    if provider_id == 'claude':
        roots.extend(('claude_native', root) for root in _claude_roots(env))
        roots.extend(('pi_session', root) for root in _pi_session_roots())
    elif provider_id == 'codex':
        roots.extend(('codex_native', root) for root in _codex_roots(env))

    files: list[_UsageFile] = []
    for source, root in roots:
        if not root.is_dir():
            continue
        try:
            for path in root.rglob('*.jsonl'):
                if path.is_file():
                    files.append(_UsageFile(source=source, path=path))
        except OSError:
            continue

    return files


def _claude_roots(env: dict[str, str]) -> list[Path]:
    """返回 Claude projects 根目录列表。"""
    raw = env.get('CLAUDE_CONFIG_DIR', '').strip()
    if raw:
        roots: list[Path] = []
        for part in raw.split(','):
            path_text = part.strip()
            if not path_text:
                continue
            path = Path(path_text)
            roots.append(path if path.name == 'projects' else path / 'projects')
        return roots

    home = Path.home()
    return [home / '.config' / 'claude' / 'projects', home / '.claude' / 'projects']


def _codex_roots(env: dict[str, str]) -> list[Path]:
    """返回 Codex sessions 根目录列表。"""
    codex_home = env.get('CODEX_HOME', '').strip()
    root = Path(codex_home) if codex_home else Path.home() / '.codex'
    return [root / 'sessions', root / 'archived_sessions']


def _pi_session_roots() -> list[Path]:
    """返回 pi session 根目录列表。"""
    return [Path.home() / '.pi' / 'agent' / 'sessions']


def _cached_rows(provider_id: str, source: str, path: Path) -> tuple[_UsageRow, ...]:
    """读取单个文件，未变化时复用缓存。"""
    try:
        stat = path.stat()
    except OSError:
        return ()

    cache_key = (provider_id, source, str(path))
    cached = _FILE_CACHE.get(cache_key)
    if cached is not None and cached.mtime_ns == stat.st_mtime_ns and cached.size == stat.st_size:
        return cached.rows

    rows = tuple(_parse_file(provider_id, source, path))
    _FILE_CACHE[cache_key] = _CachedFile(stat.st_mtime_ns, stat.st_size, rows)
    return rows


def _parse_file(provider_id: str, source: str, path: Path) -> list[_UsageRow]:
    """按 provider 解析一个 JSONL 文件。"""
    if source == 'pi_session':
        return _parse_pi_session_file(path, provider_id)
    if source == 'claude_native':
        return _parse_claude_file(path)
    if source == 'codex_native':
        return _parse_codex_file(path)
    return []


def _parse_claude_file(path: Path) -> list[_UsageRow]:
    """解析 Claude JSONL 文件。"""
    keyed_rows: dict[str, _UsageRow] = {}
    unkeyed_rows: list[_UsageRow] = []

    for raw in _iter_jsonl(path):
        if raw.get('type') != 'assistant':
            continue
        message = raw.get('message')
        if not isinstance(message, dict):
            continue
        usage = message.get('usage')
        if not isinstance(usage, dict):
            continue
        timestamp = _parse_timestamp(raw.get('timestamp'))
        model = message.get('model')
        if timestamp is None or not isinstance(model, str) or not model:
            continue

        input_tokens = _int_value(usage.get('input_tokens'))
        cache_create_tokens = _int_value(usage.get('cache_creation_input_tokens'))
        cache_read_tokens = _int_value(usage.get('cache_read_input_tokens'))
        output_tokens = _int_value(usage.get('output_tokens'))
        if input_tokens + cache_create_tokens + cache_read_tokens + output_tokens <= 0:
            continue

        normalized_model = _normalize_claude_model(model)
        row = _UsageRow(
            timestamp=timestamp,
            model=normalized_model,
            input_tokens=input_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_create_tokens=cache_create_tokens,
            output_tokens=output_tokens,
            cost_usd=_claude_cost(normalized_model, input_tokens, cache_read_tokens, cache_create_tokens, output_tokens),
        )

        message_id = message.get('id')
        request_id = raw.get('requestId')
        if isinstance(message_id, str) and isinstance(request_id, str):
            keyed_rows[f'{message_id}:{request_id}'] = row
        else:
            unkeyed_rows.append(row)

    return list(keyed_rows.values()) + unkeyed_rows


def _parse_pi_session_file(path: Path, provider_id: str) -> list[_UsageRow]:
    """解析 pi session JSONL 文件。"""
    rows: list[_UsageRow] = []
    current_context: tuple[str, str] | None = None

    for raw in _iter_jsonl(path):
        entry_type = raw.get('type')
        if entry_type == 'model_change':
            current_context = _pi_model_context(raw)
            continue

        if entry_type != 'message':
            continue
        message = raw.get('message')
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            continue

        identity = _pi_assistant_identity(raw, message, current_context)
        if identity is None or identity[0] != provider_id:
            continue

        timestamp = _parse_timestamp(message.get('timestamp')) or _parse_timestamp(raw.get('timestamp'))
        if timestamp is None:
            continue

        usage = message.get('usage')
        if not isinstance(usage, dict):
            continue

        row = _pi_usage_row(provider_id, identity[1], timestamp, usage)
        if row is not None:
            rows.append(row)

    return rows


def _pi_model_context(raw: dict[str, Any]) -> tuple[str, str] | None:
    """读取 pi model_change 上下文。"""
    provider_id = _pi_provider_id(_string_value(raw.get('provider')))
    if provider_id is None:
        return None

    model = _string_value(raw.get('modelId')) or _string_value(raw.get('model'))
    if model is None:
        return None

    normalized = _normalize_model_for_provider(provider_id, model)
    return (provider_id, normalized) if normalized else None


def _pi_assistant_identity(raw: dict[str, Any], message: dict[str, Any], fallback: tuple[str, str] | None) -> tuple[str, str] | None:
    """解析 pi assistant 消息的 provider 和模型。"""
    explicit_provider_text = _string_value(message.get('provider')) or _string_value(raw.get('provider'))
    explicit_provider = _pi_provider_id(explicit_provider_text)
    explicit_model = (
        _string_value(message.get('model'))
        or _string_value(raw.get('model'))
        or _string_value(message.get('modelId'))
        or _string_value(raw.get('modelId'))
    )

    if explicit_provider_text is not None and explicit_provider is None:
        return None

    if explicit_provider is not None and explicit_model is not None:
        normalized = _normalize_model_for_provider(explicit_provider, explicit_model)
        return (explicit_provider, normalized) if normalized else None

    if explicit_provider is not None and fallback is not None and fallback[0] == explicit_provider:
        return fallback

    if explicit_provider_text is None and explicit_model is not None and fallback is not None:
        normalized = _normalize_model_for_provider(fallback[0], explicit_model)
        return (fallback[0], normalized) if normalized else None

    if explicit_provider_text is None and fallback is not None:
        return fallback

    return None


def _pi_usage_row(provider_id: str, model: str, timestamp: datetime, usage: dict[str, Any]) -> _UsageRow | None:
    """把 pi usage 转换为内部统计行。"""
    input_tokens = _int_from_aliases(usage, ('input', 'inputTokens', 'input_tokens', 'promptTokens', 'prompt_tokens'))
    cache_read_tokens = _int_from_aliases(
        usage,
        ('cacheRead', 'cacheReadTokens', 'cache_read', 'cache_read_tokens', 'cacheReadInputTokens', 'cache_read_input_tokens'),
    )
    cache_create_tokens = _int_from_aliases(
        usage,
        (
            'cacheWrite', 'cacheWriteTokens', 'cache_write', 'cache_write_tokens',
            'cacheCreationTokens', 'cache_creation_tokens', 'cacheCreationInputTokens', 'cache_creation_input_tokens',
        ),
    )
    output_tokens = _int_from_aliases(usage, ('output', 'outputTokens', 'output_tokens', 'completionTokens', 'completion_tokens'))
    direct_total = _int_from_aliases(usage, ('totalTokens', 'total_tokens', 'tokenCount', 'token_count', 'tokens'))
    derived_total = input_tokens + cache_read_tokens + cache_create_tokens + output_tokens
    total_tokens = max(direct_total, derived_total)
    if total_tokens <= 0:
        return None

    cost = None
    if derived_total > 0:
        if provider_id == 'claude':
            cost = _claude_cost(model, input_tokens, cache_read_tokens, cache_create_tokens, output_tokens)
        elif provider_id == 'codex':
            cost = _codex_cost(model, input_tokens + cache_read_tokens + cache_create_tokens, cache_read_tokens, output_tokens)

    return _UsageRow(
        timestamp=timestamp,
        model=model,
        input_tokens=input_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_create_tokens=cache_create_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        total_tokens_override=total_tokens if direct_total > derived_total else None,
    )


def _parse_codex_file(path: Path) -> list[_UsageRow]:
    """解析 Codex JSONL 文件。"""
    rows: list[_UsageRow] = []
    current_model: str | None = None
    previous_total: tuple[int, int, int] | None = None

    for raw in _iter_jsonl(path):
        timestamp = _parse_timestamp(raw.get('timestamp'))
        entry_type = raw.get('type')

        if entry_type == 'turn_context':
            payload = raw.get('payload')
            if isinstance(payload, dict):
                current_model = _string_value(payload.get('model'))
                info = payload.get('info')
                if current_model is None and isinstance(info, dict):
                    current_model = _string_value(info.get('model'))
            continue

        if entry_type != 'event_msg' or timestamp is None:
            continue

        payload = raw.get('payload')
        if not isinstance(payload, dict) or payload.get('type') != 'token_count':
            continue

        info = payload.get('info')
        if not isinstance(info, dict):
            continue

        model = current_model or _string_value(info.get('model')) or _string_value(info.get('model_name'))
        model = model or _string_value(payload.get('model')) or _string_value(raw.get('model')) or _CODEX_DEFAULT_MODEL
        total_usage = info.get('total_token_usage')
        last_usage = info.get('last_token_usage')
        input_tokens = cache_read_tokens = output_tokens = 0

        if isinstance(last_usage, dict):
            input_tokens, cache_read_tokens, output_tokens = _codex_token_tuple(last_usage)
        elif isinstance(total_usage, dict):
            current_total = _codex_token_tuple(total_usage)
            if previous_total is None:
                input_tokens, cache_read_tokens, output_tokens = current_total
            else:
                input_tokens = max(0, current_total[0] - previous_total[0])
                cache_read_tokens = max(0, current_total[1] - previous_total[1])
                output_tokens = max(0, current_total[2] - previous_total[2])
        else:
            continue

        if isinstance(total_usage, dict):
            previous_total = _codex_token_tuple(total_usage)

        if input_tokens + cache_read_tokens + output_tokens <= 0:
            continue

        normalized_model = _normalize_codex_model(model)
        rows.append(_UsageRow(
            timestamp=timestamp,
            model=normalized_model,
            input_tokens=input_tokens,
            cache_read_tokens=min(cache_read_tokens, input_tokens),
            cache_create_tokens=0,
            output_tokens=output_tokens,
            cost_usd=_codex_cost(normalized_model, input_tokens, min(cache_read_tokens, input_tokens), output_tokens),
        ))

    return rows


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    """安全读取 JSONL，跳过损坏行和超长行。"""
    rows: list[dict[str, Any]] = []
    try:
        with path.open('rb') as file:
            for raw_line in file:
                line = raw_line[:_MAX_LINE_BYTES]
                if len(raw_line) > _MAX_LINE_BYTES:
                    continue
                try:
                    value = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []

    return rows


def _parse_timestamp(value: object) -> datetime | None:
    """解析日志时间戳。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            timestamp = float(value)
            if abs(timestamp) > 10_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_value(value: object) -> int:
    """读取非负整数。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _int_from_aliases(values: dict[str, Any], keys: tuple[str, ...]) -> int:
    """按别名读取第一个有效 token 数。"""
    for key in keys:
        count = _int_value(values.get(key))
        if count > 0:
            return count
    return 0


def _string_value(value: object) -> str | None:
    """读取非空字符串。"""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _pi_provider_id(value: str | None) -> str | None:
    """把 pi provider 名称映射为内部 provider。"""
    if value is None:
        return None

    provider = value.strip().lower()
    if provider == 'anthropic':
        return 'claude'
    if provider == 'openai-codex':
        return 'codex'
    return None


def _normalize_model_for_provider(provider_id: str, raw: str) -> str | None:
    """按 provider 标准化模型名。"""
    model = raw.strip()
    if not model:
        return None
    if provider_id == 'claude':
        return _normalize_claude_model(model)
    if provider_id == 'codex':
        return _normalize_codex_model(model)
    return None


def _codex_token_tuple(usage: dict[str, Any]) -> tuple[int, int, int]:
    """读取 Codex token 三元组。"""
    return (
        _int_value(usage.get('input_tokens')),
        _int_value(usage.get('cached_input_tokens') or usage.get('cache_read_input_tokens')),
        _int_value(usage.get('output_tokens')),
    )


def _sum_cost(rows: list[_UsageRow]) -> float | None:
    """汇总已知价格的成本。"""
    costs = [row.cost_usd for row in rows if row.cost_usd is not None]
    if not costs:
        return None
    return sum(costs)


def _top_model(rows: list[_UsageRow]) -> str | None:
    """返回 30 天 token 数最多的模型。"""
    totals: dict[str, int] = {}
    for row in rows:
        totals[row.model] = totals.get(row.model, 0) + row.total_tokens

    if not totals:
        return None
    return max(totals.items(), key=lambda item: item[1])[0]


def _normalize_codex_model(raw: str) -> str:
    """标准化 Codex 模型名。"""
    model = raw.strip()
    if model.startswith('openai/'):
        model = model[len('openai/'):]
    if model in _CODEX_PRICING:
        return model

    if len(model) > 11 and model[-11] == '-' and model[-10:].replace('-', '').isdigit():
        base = model[:-11]
        if base in _CODEX_PRICING:
            return base
    return model


def _normalize_claude_model(raw: str) -> str:
    """标准化 Claude 模型名。"""
    model = raw.strip()
    if model.startswith('anthropic.'):
        model = model[len('anthropic.'):]
    if '.claude-' in model:
        model = model[model.rfind('claude-'):]
    if '-v' in model:
        model = model.split('-v', 1)[0]
    if len(model) > 9 and model[-9] == '-' and model[-8:].isdigit():
        base = model[:-9]
        if base in _CLAUDE_PRICING:
            return base
    return model


def _codex_cost(model: str, input_tokens: int, cached_input_tokens: int, output_tokens: int) -> float | None:
    """计算 Codex 成本。"""
    pricing = _CODEX_PRICING.get(model)
    if pricing is None:
        return None

    cached = min(max(0, cached_input_tokens), max(0, input_tokens))
    non_cached = max(0, input_tokens - cached)
    uses_high_context = pricing.threshold_tokens is not None and input_tokens > pricing.threshold_tokens
    input_cost = pricing.input_cost_above_threshold if uses_high_context and pricing.input_cost_above_threshold is not None else pricing.input_cost
    cache_read_cost = (
        pricing.cache_read_cost_above_threshold
        if uses_high_context and pricing.cache_read_cost_above_threshold is not None
        else pricing.cache_read_cost or pricing.input_cost
    )
    output_cost = pricing.output_cost_above_threshold if uses_high_context and pricing.output_cost_above_threshold is not None else pricing.output_cost

    return non_cached * input_cost + cached * cache_read_cost + max(0, output_tokens) * output_cost


def _claude_cost(model: str, input_tokens: int, cache_read_tokens: int, cache_create_tokens: int, output_tokens: int) -> float | None:
    """计算 Claude 成本。"""
    pricing = _CLAUDE_PRICING.get(model)
    if pricing is None:
        return None

    cache_read_cost = pricing.cache_read_cost or pricing.input_cost
    cache_create_cost = pricing.cache_create_cost or pricing.input_cost
    return (
        _tiered_cost(input_tokens, pricing.input_cost, pricing.input_cost_above_threshold, pricing.threshold_tokens)
        + _tiered_cost(cache_read_tokens, cache_read_cost, pricing.cache_read_cost_above_threshold, pricing.threshold_tokens)
        + _tiered_cost(cache_create_tokens, cache_create_cost, pricing.cache_create_cost_above_threshold, pricing.threshold_tokens)
        + _tiered_cost(output_tokens, pricing.output_cost, pricing.output_cost_above_threshold, pricing.threshold_tokens)
    )


def _tiered_cost(tokens: int, base: float, above: float | None, threshold: int | None) -> float:
    """计算带上下文阈值的 token 成本。"""
    count = max(0, tokens)
    if threshold is None or above is None:
        return count * base

    below = min(count, threshold)
    over = max(count - threshold, 0)
    return below * base + over * above
