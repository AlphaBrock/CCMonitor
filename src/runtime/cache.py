"""
Usage Cache
============

Thread-safe cache for API data - single source of truth for all usage
state.  All API refresh requests go through ``UsageCache.update()``,
which uses a lock to prevent concurrent calls and a cooldown to prevent
calls that are too close together (HTTP 429).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from src.integrations.api import (
    fetch_profile,
    fetch_profile_for_provider,
    fetch_usage,
    fetch_usage_for_provider,
    read_access_token,
    read_access_token_for_provider,
    refresh_auth_token,
    refresh_auth_token_for_provider,
)
from src.integrations.claude_cli import RefreshResult
from src.presentation.settings import MAX_BACKOFF, POLL_FAST, POLL_INTERVAL, USAGE_PROVIDER

__all__ = [
    'CacheSnapshot', 'DashboardCache', 'DashboardSnapshot', 'DashboardUpdateResult',
    'ProviderClient', 'UpdateResult', 'UsageCache',
]

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheSnapshot:
    """Immutable, consistent snapshot of cache state for the popup."""

    usage: dict[str, Any]
    profile: dict[str, Any] | None
    last_success_time: float | None
    refreshing: bool
    last_error: str | None
    version: int
    provider_id: str = 'claude'


@dataclass(frozen=True)
class DashboardSnapshot:
    """Immutable snapshot containing all provider cache snapshots."""

    providers: dict[str, CacheSnapshot]
    primary_provider: str
    version: int


@dataclass(frozen=True)
class UpdateResult:
    """Result of a ``UsageCache.update()`` call.

    Attributes
    ----------
    data : dict or None
        Raw API response dict, or ``None`` when the call was skipped
        (lock held or cooldown active).
    token_refresh : RefreshResult or None
        Set when a token refresh was attempted after a 401 auth error.
    """

    data: dict[str, Any] | None
    token_refresh: RefreshResult | None = None


@dataclass(frozen=True)
class DashboardUpdateResult:
    """Result of updating every provider cache."""

    primary: UpdateResult
    providers: dict[str, UpdateResult]


@dataclass(frozen=True)
class ProviderClient:
    """Provider-specific functions used by ``UsageCache``."""

    provider_id: str
    fetch_usage: Any
    fetch_profile: Any
    read_access_token: Any
    refresh_auth_token: Any


def _primary_client() -> ProviderClient:
    """Build the default client from patchable module-level functions."""
    return ProviderClient(
        provider_id=USAGE_PROVIDER,
        fetch_usage=lambda: fetch_usage(),
        fetch_profile=lambda: fetch_profile(),
        read_access_token=lambda: read_access_token(),
        refresh_auth_token=lambda: refresh_auth_token(),
    )


def _client_for_provider(provider_id: str) -> ProviderClient:
    """Build a client for an explicit provider."""
    return ProviderClient(
        provider_id=provider_id,
        fetch_usage=lambda: fetch_usage_for_provider(provider_id),
        fetch_profile=lambda: fetch_profile_for_provider(provider_id),
        read_access_token=lambda: read_access_token_for_provider(provider_id),
        refresh_auth_token=lambda: refresh_auth_token_for_provider(provider_id),
    )


class UsageCache:
    """Thread-safe cache managing API data, cooldown, and error state.

    All callers (poll loop, popup) go through ``update()`` instead
    of calling ``fetch_usage()`` directly.
    """

    def __init__(self, client: ProviderClient | None = None) -> None:
        self._client = client or _primary_client()
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._profile_lock = threading.Lock()
        self._usage: dict[str, Any] = {}
        self._profile: dict[str, Any] | None = None
        self._profile_token: str | None = None
        self._last_success_time: float | None = None
        self._refreshing = False
        self._last_error: str | None = None
        self._version = 0
        self._consecutive_errors = 0
        self._last_failed_token: str | None = None
        self._rate_limit_until: float = 0

    # Public properties

    @property
    def usage(self) -> dict[str, Any]:
        """Last successful usage data (empty dict before first success)."""
        return self._usage

    @property
    def profile(self) -> dict[str, Any] | None:
        return self._profile

    @property
    def last_success_time(self) -> float | None:
        return self._last_success_time

    @property
    def refreshing(self) -> bool:
        return self._refreshing

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def version(self) -> int:
        """Change counter - incremented on every state change."""
        return self._version

    @property
    def consecutive_errors(self) -> int:
        return self._consecutive_errors

    @property
    def rate_limit_remaining(self) -> float:
        """Seconds remaining in the rate-limit backoff window, or 0."""
        return max(self._rate_limit_until - time.time(), 0)

    @property
    def snapshot(self) -> CacheSnapshot:
        """Return a consistent snapshot for the popup to display."""
        with self._state_lock:
            return CacheSnapshot(
                usage=self._usage,
                profile=self._profile,
                last_success_time=self._last_success_time,
                refreshing=self._refreshing,
                last_error=self._last_error,
                version=self._version,
                provider_id=self._client.provider_id,
            )

    # Public methods

    def ensure_profile(self) -> None:
        """Fetch the account profile if not yet loaded, or re-fetch if the access token changed (thread-safe).

        Acquires ``_lock`` around the HTTP call to prevent concurrent
        API requests with ``update()``.
        """
        current_token = self._client.read_access_token()
        if self._profile is not None and self._profile_token == current_token:
            return

        with self._profile_lock:
            current_token = self._client.read_access_token()
            if self._profile is not None and self._profile_token == current_token:
                return
            log.info('fetch_profile started (%s)', self._client.provider_id)
            with self._lock:
                profile = self._client.fetch_profile()
            with self._state_lock:
                self._profile = profile
                self._profile_token = current_token
                self._version += 1
            log.info('fetch_profile -> %s (%s)', 'OK' if profile else 'failed', self._client.provider_id)

    def update(self) -> UpdateResult:
        """Fetch usage data with lock and cooldown protection.

        Returns
        -------
        UpdateResult
            Contains the API response dict (``data``), or ``None``
            when the call was skipped.  If a token refresh was
            attempted, ``token_refresh`` carries the outcome.
        """
        if not self._lock.acquire(blocking=False):
            log.debug('update skipped (another update in progress)')
            return UpdateResult(data=None)

        try:
            return self._update_locked()
        finally:
            self._lock.release()

    # Private helpers

    def _update_locked(self) -> UpdateResult:
        """Execute the actual update while holding ``_lock``."""
        if self._last_success_time is not None and time.time() - self._last_success_time < POLL_FAST:
            log.debug('update skipped (cooldown, %.0fs remaining)', POLL_FAST - (time.time() - self._last_success_time))
            return UpdateResult(data=None)

        if time.time() < self._rate_limit_until:
            log.debug('update skipped (rate-limit backoff, %.0fs remaining)', self._rate_limit_until - time.time())
            return UpdateResult(data=None)

        if self._last_failed_token is not None:
            if self._client.read_access_token() == self._last_failed_token:
                log.debug('update skipped (token unchanged after auth failure)')
                return UpdateResult(data=None)
            self._last_failed_token = None

        with self._state_lock:
            self._refreshing = True
            self._version += 1

        try:
            return self._fetch_and_process()
        except Exception:
            with self._state_lock:
                self._refreshing = False
                self._version += 1
            raise

    def _fetch_and_process(self) -> UpdateResult:
        """Fetch usage data and process the response."""
        token_before = self._client.read_access_token()
        log.info('fetch_usage started (%s)', self._client.provider_id)
        data = self._client.fetch_usage()

        if 'error' in data:
            self._record_error(data)

            if data.get('rate_limited'):
                retry_after = data.get('retry_after')
                if retry_after is not None and retry_after > 0:
                    delay = min(max(retry_after, POLL_INTERVAL), MAX_BACKOFF)
                else:
                    delay = min(POLL_INTERVAL * (2 ** max(self._consecutive_errors - 1, 0)), MAX_BACKOFF)
                self._rate_limit_until = time.time() + delay
                log.warning('fetch_usage -> rate limited, backoff %.0fs', delay)

            token_refresh = None
            if data.get('auth_error'):
                if data.get('refresh_attempted'):
                    log.warning('fetch_usage -> auth error, provider refresh already failed')
                    self._last_failed_token = token_before
                else:
                    log.warning('fetch_usage -> auth error, attempting token refresh')
                    token_refresh = self._try_token_refresh(token_before)
                    if token_refresh is not None and self._last_error is None:
                        # Token refresh succeeded and retry was successful
                        return UpdateResult(data=self._usage, token_refresh=token_refresh)
                    if token_refresh is None:
                        # Refresh failed or token unchanged - block this token
                        self._last_failed_token = token_before
            elif not data.get('rate_limited'):
                log.warning('fetch_usage -> error: %s', data['error'])

            with self._state_lock:
                self._refreshing = False
                self._version += 1
            return UpdateResult(data=data, token_refresh=token_refresh)

        pct_5h = (data.get('five_hour') or {}).get('utilization')
        pct_7d = (data.get('seven_day') or {}).get('utilization')
        log.info(
            'fetch_usage -> OK (%s, 5h: %s%%, 7d: %s%%)',
            self._client.provider_id,
            pct_5h if pct_5h is not None else '?',
            pct_7d if pct_7d is not None else '?',
        )
        success_data = self._record_success(data)
        return UpdateResult(data=success_data)

    def _record_error(self, data: dict[str, Any], *, count: bool = True) -> None:
        """Apply common state updates after a failed API response.

        Parameters
        ----------
        data : dict
            API response containing ``'error'`` and optional ``'server_message'``.
        count : bool
            If True (default), increment ``_consecutive_errors``.
        """
        with self._state_lock:
            if count:
                self._consecutive_errors += 1
            error = data['error']
            server_msg = data.get('server_message')
            if server_msg:
                error += f'\n{server_msg}'
            self._last_error = error

    def _record_success(self, data: dict[str, Any]) -> dict[str, Any]:
        """Apply common state updates after a successful API response."""
        # _usage is always reassigned (never mutated in place), so existing
        # CacheSnapshot references remain valid after this update.
        cleaned_data = dict(data)
        profile = cleaned_data.pop('__profile', None)
        with self._state_lock:
            self._consecutive_errors = 0
            self._last_error = None
            self._last_success_time = time.time()
            self._rate_limit_until = 0
            self._last_failed_token = None
            if isinstance(profile, dict):
                self._profile = profile
                self._profile_token = self._client.read_access_token()
            self._usage = cleaned_data
            self._refreshing = False
            self._version += 1

        return cleaned_data

    def _try_token_refresh(self, token_before: str | None) -> RefreshResult | None:
        """Attempt to refresh the OAuth token for the configured provider.

        Parameters
        ----------
        token_before : str or None
            The token that was used for the failed request.  Used to
            detect whether the refresh actually produced a new token.

        Returns
        -------
        RefreshResult or None
            The refresh outcome, or ``None`` if the CLI is not available
            or the token didn't change.
        """
        result = self._client.refresh_auth_token()
        if not result.success:
            log.info('token refresh failed: %s', result.error)
            return None

        if self._client.read_access_token() == token_before:
            log.info('token refresh succeeded but token unchanged')
            return None

        # Token changed - retry the API call
        log.info('token changed, retrying fetch_usage')
        data = self._client.fetch_usage()
        if 'error' not in data:
            log.info('retry -> OK')
            self._record_success(data)
            return result

        log.warning('retry -> error: %s', data['error'])
        # Update error message but do not increment _consecutive_errors
        # again (the caller already counted this update cycle as one error).
        self._record_error(data, count=False)

        return result


class DashboardCache:
    """Provider-aware cache for the desktop panel."""

    PROVIDER_ORDER = ('codex', 'claude')

    def __init__(self, primary_provider: str = USAGE_PROVIDER) -> None:
        self.primary_provider = primary_provider if primary_provider in self.PROVIDER_ORDER else 'claude'
        self.caches = {
            provider_id: UsageCache(_client_for_provider(provider_id))
            for provider_id in self.PROVIDER_ORDER
        }

    @property
    def primary(self) -> UsageCache:
        """Return the cache used by tray, alerts, and event commands."""
        return self.caches[self.primary_provider]

    @property
    def snapshot(self) -> DashboardSnapshot:
        """Return a consistent multi-provider snapshot."""
        provider_snapshots = {
            provider_id: cache.snapshot
            for provider_id, cache in self.caches.items()
        }
        version = sum(snapshot.version for snapshot in provider_snapshots.values())
        return DashboardSnapshot(
            providers=provider_snapshots,
            primary_provider=self.primary_provider,
            version=version,
        )

    def ensure_profiles(self) -> None:
        """Fetch profiles for all providers without letting one failure block another."""
        for cache in self.caches.values():
            try:
                cache.ensure_profile()
            except Exception:
                log.exception('provider profile refresh failed')

    def update_all(self) -> DashboardUpdateResult:
        """Refresh every provider and return the primary result separately."""
        results: dict[str, UpdateResult] = {}

        for provider_id in self._update_order():
            try:
                results[provider_id] = self.caches[provider_id].update()
            except Exception as exc:
                log.exception('provider update failed (%s)', provider_id)
                results[provider_id] = UpdateResult(data={'error': str(exc)})

        return DashboardUpdateResult(
            primary=results.get(self.primary_provider, UpdateResult(data=None)),
            providers=results,
        )

    def _update_order(self) -> list[str]:
        """Return primary provider first, then remaining providers."""
        ordered = [self.primary_provider]
        for provider_id in self.PROVIDER_ORDER:
            if provider_id not in ordered:
                ordered.append(provider_id)
        return ordered
