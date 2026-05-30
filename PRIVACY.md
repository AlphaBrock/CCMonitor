# Privacy Policy

**CCMonitor** is a local desktop application that monitors your Claude or Codex API usage.

## Data Collection

This application does **not** collect, store, or transmit any personal data.

## Network Communication

In Claude mode, the application communicates only with `api.anthropic.com` to retrieve your current
usage data. In Codex mode, it communicates only with `auth.openai.com` for OAuth refresh and
`chatgpt.com` for usage data. No other network connections are made.

## Credentials

The application reads your existing OAuth token from the selected provider's local configuration:
Claude mode reads `~/.claude/.credentials.json`; Codex mode reads `%CODEX_HOME%\auth.json` or
`~\.codex\auth.json`. This token is:

- Used solely in HTTP Authorization headers to authenticate with the selected provider's usage API
- Never logged, stored elsewhere, copied, or transmitted to any third party

## Local Usage Logs

The desktop panel reads local Claude and Codex JSONL logs to estimate cost, token totals, latest
turn tokens, and top model over a rolling 30-day window. These estimates stay in memory, are never
uploaded, and may differ from provider billing.

## Local Storage

The application does not write its own state files. All usage data and local log summaries are kept in memory only and
discarded when the application closes. An optional settings file (`usage-monitor-settings.json`) is
read-only. In Codex mode, a successful OAuth refresh writes the refreshed token back to Codex's own
`auth.json`.

## Third-Party Services

The application does not integrate with any analytics, tracking, advertising, or telemetry services.

## Contact

For questions about this privacy policy, please open an issue at
https://github.com/AlphaBrock/CCMonitor/issues
