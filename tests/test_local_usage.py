"""
Local Usage Tests
=================

Tests for local Claude/Codex JSONL cost and token summaries.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.integrations.local_usage import clear_local_usage_cache, local_usage_summary


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write JSONL rows for scanner tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n', encoding='utf-8')


class TestClaudeLocalUsage(unittest.TestCase):
    """Tests for Claude local log scanning."""

    def setUp(self):
        clear_local_usage_cache()
        self.now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        clear_local_usage_cache()

    def test_claude_streaming_rows_are_deduplicated(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_jsonl(root / 'projects' / 'p' / 'session.jsonl', [
                {
                    'type': 'assistant',
                    'timestamp': '2026-05-29T01:00:00Z',
                    'requestId': 'req-1',
                    'message': {
                        'id': 'msg-1',
                        'model': 'claude-opus-4-6',
                        'usage': {'input_tokens': 50, 'cache_creation_input_tokens': 10, 'cache_read_input_tokens': 5, 'output_tokens': 20},
                    },
                },
                {
                    'type': 'assistant',
                    'timestamp': '2026-05-29T01:00:05Z',
                    'requestId': 'req-1',
                    'message': {
                        'id': 'msg-1',
                        'model': 'claude-opus-4-6',
                        'usage': {'input_tokens': 100, 'cache_creation_input_tokens': 20, 'cache_read_input_tokens': 10, 'output_tokens': 30},
                    },
                },
            ])

            summary = local_usage_summary('claude', now=self.now, env={'CLAUDE_CONFIG_DIR': str(root)})

        self.assertEqual(summary.total_tokens, 160)
        self.assertEqual(summary.latest_tokens, 160)
        self.assertEqual(summary.top_model, 'claude-opus-4-6')
        self.assertIsNotNone(summary.total_cost_usd)

    def test_unknown_claude_model_counts_tokens_without_cost(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_jsonl(root / 'projects' / 'p' / 'session.jsonl', [
                {
                    'type': 'assistant',
                    'timestamp': '2026-05-29T01:00:00Z',
                    'message': {
                        'model': 'claude-unknown',
                        'usage': {'input_tokens': 100, 'output_tokens': 20},
                    },
                },
            ])

            summary = local_usage_summary('claude', now=self.now, env={'CLAUDE_CONFIG_DIR': str(root)})

        self.assertEqual(summary.total_tokens, 120)
        self.assertIsNone(summary.total_cost_usd)
        self.assertIsNone(summary.today_cost_usd)

    def test_pi_anthropic_assistant_message_counts_for_claude_today(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_jsonl(root / '.pi' / 'agent' / 'sessions' / 'session.jsonl', [
                {'type': 'model_change', 'provider': 'anthropic', 'modelId': 'claude-opus-4-8'},
                {
                    'type': 'message',
                    'timestamp': '2026-05-29T03:00:00Z',
                    'message': {
                        'role': 'assistant',
                        'usage': {'inputTokens': 100, 'outputTokens': 20},
                    },
                },
            ])

            with patch('src.integrations.local_usage.Path.home', return_value=root):
                summary = local_usage_summary('claude', now=self.now, env={'CLAUDE_CONFIG_DIR': str(root / 'missing')})

        self.assertEqual(summary.total_tokens, 120)
        self.assertEqual(summary.latest_tokens, 120)
        self.assertEqual(summary.top_model, 'claude-opus-4-8')
        self.assertIsNotNone(summary.today_cost_usd)

    def test_pi_model_change_context_is_used_as_message_fallback(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_jsonl(root / '.pi' / 'agent' / 'sessions' / 'session.jsonl', [
                {'type': 'model_change', 'provider': 'anthropic', 'modelId': 'anthropic.claude-sonnet-4-5'},
                {
                    'type': 'message',
                    'timestamp': 1_780_012_800_000,
                    'message': {
                        'role': 'assistant',
                        'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
                    },
                },
            ])

            with patch('src.integrations.local_usage.Path.home', return_value=root):
                summary = local_usage_summary('claude', now=self.now, env={'CLAUDE_CONFIG_DIR': str(root / 'missing')})

        self.assertEqual(summary.total_tokens, 15)
        self.assertEqual(summary.top_model, 'claude-sonnet-4-5')

    def test_pi_openai_codex_message_is_not_counted_for_claude(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_jsonl(root / '.pi' / 'agent' / 'sessions' / 'session.jsonl', [
                {'type': 'model_change', 'provider': 'openai-codex', 'modelId': 'gpt-5.5'},
                {
                    'type': 'message',
                    'timestamp': '2026-05-29T03:00:00Z',
                    'message': {
                        'role': 'assistant',
                        'usage': {'inputTokens': 100, 'outputTokens': 20},
                    },
                },
            ])

            with patch('src.integrations.local_usage.Path.home', return_value=root):
                summary = local_usage_summary('claude', now=self.now, env={'CLAUDE_CONFIG_DIR': str(root / 'missing')})

        self.assertIsNone(summary.total_tokens)
        self.assertIsNone(summary.top_model)

    def test_pi_total_only_usage_counts_tokens_without_cost(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_jsonl(root / '.pi' / 'agent' / 'sessions' / 'session.jsonl', [
                {
                    'type': 'message',
                    'timestamp': '2026-05-29T03:00:00Z',
                    'message': {
                        'role': 'assistant',
                        'provider': 'anthropic',
                        'model': 'claude-opus-4-8',
                        'usage': {'totalTokens': 777},
                    },
                },
            ])

            with patch('src.integrations.local_usage.Path.home', return_value=root):
                summary = local_usage_summary('claude', now=self.now, env={'CLAUDE_CONFIG_DIR': str(root / 'missing')})

        self.assertEqual(summary.total_tokens, 777)
        self.assertEqual(summary.latest_tokens, 777)
        self.assertIsNone(summary.total_cost_usd)
        self.assertIsNone(summary.today_cost_usd)


class TestCodexLocalUsage(unittest.TestCase):
    """Tests for Codex local log scanning."""

    def setUp(self):
        clear_local_usage_cache()
        self.now = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        clear_local_usage_cache()

    def test_codex_token_count_uses_turn_context_model(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_jsonl(root / 'sessions' / '2026' / '05' / '29' / 'session.jsonl', [
                {
                    'type': 'turn_context',
                    'timestamp': '2026-05-29T01:00:00Z',
                    'payload': {'model': 'gpt-5.5'},
                },
                {
                    'type': 'event_msg',
                    'timestamp': '2026-05-29T01:01:00Z',
                    'payload': {
                        'type': 'token_count',
                        'info': {
                            'model': 'gpt-5-mini',
                            'last_token_usage': {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 30},
                        },
                    },
                },
            ])

            summary = local_usage_summary('codex', now=self.now, env={'CODEX_HOME': str(root)})

        self.assertEqual(summary.total_tokens, 150)
        self.assertEqual(summary.latest_tokens, 150)
        self.assertEqual(summary.top_model, 'gpt-5.5')
        self.assertIsNotNone(summary.total_cost_usd)

    def test_codex_total_usage_falls_back_to_delta(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_jsonl(root / 'sessions' / '2026' / '05' / '29' / 'session.jsonl', [
                {
                    'type': 'event_msg',
                    'timestamp': '2026-05-29T01:00:00Z',
                    'payload': {
                        'type': 'token_count',
                        'info': {'total_token_usage': {'input_tokens': 100, 'cached_input_tokens': 10, 'output_tokens': 20}},
                    },
                },
                {
                    'type': 'event_msg',
                    'timestamp': '2026-05-29T01:10:00Z',
                    'payload': {
                        'type': 'token_count',
                        'info': {'total_token_usage': {'input_tokens': 150, 'cached_input_tokens': 20, 'output_tokens': 30}},
                    },
                },
            ])

            summary = local_usage_summary('codex', now=self.now, env={'CODEX_HOME': str(root)})

        self.assertEqual(summary.total_tokens, 200)
        self.assertEqual(summary.latest_tokens, 70)

    def test_bad_jsonl_does_not_crash(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'sessions' / '2026' / '05' / '29' / 'bad.jsonl'
            path.parent.mkdir(parents=True)
            path.write_text('{bad json}\n', encoding='utf-8')

            summary = local_usage_summary('codex', now=self.now, env={'CODEX_HOME': str(root)})

        self.assertIsNone(summary.total_tokens)
        self.assertIsNone(summary.top_model)


if __name__ == '__main__':
    unittest.main()
