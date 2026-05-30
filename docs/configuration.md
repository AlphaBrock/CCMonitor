# Configuration

All settings work out of the box - no configuration file is needed. To customize behavior, create a file called `usage-monitor-settings.json` with only the keys you want to change:

```json
{
  "usage_provider": "claude",
  "poll_interval": 180,
  "bar_fg": "#4a9eff",
  "bar_fg_mid": "#65c18c",
  "bar_fg_warn": "#ff9f43",
  "bar_fg_danger": "#ff5d5d"
}
```

The app searches for this file in these locations (first match wins):

1. **Next to the EXE** (or project root when running from source)
2. **`$CLAUDE_CONFIG_DIR/usage-monitor-settings.json`** (only if `CLAUDE_CONFIG_DIR` is set and differs from `~/.claude/`)
3. **`~/.claude/usage-monitor-settings.json`**

The app never creates or modifies this file. To start, create an empty file and add keys as needed. Settings are read at startup - after editing the file, use the **Restart** option in the tray context menu to apply changes.

## Usage provider

Choose the primary provider used by alerts, reset detection, event commands, and the tray icon bars when `tray_provider` is `"auto"`. The desktop window still attempts to show both Claude and Codex in its All view.

| Key | Default | Description |
|-----|---------|-------------|
| `usage_provider` | `"claude"` | Primary provider for alerts, reset detection, event commands, and Auto tray icon bars. Valid values: `"claude"` or `"codex"` |

Claude data reads Claude Code OAuth credentials from `~/.claude/.credentials.json` (or `CLAUDE_CONFIG_DIR`). Codex data reads ChatGPT/Codex OAuth credentials from `%CODEX_HOME%\auth.json` when `CODEX_HOME` is set, otherwise `~\.codex\auth.json`.

```json
{
    "usage_provider": "codex"
}
```

Codex uses direct OAuth only. `OPENAI_API_KEY` cannot query ChatGPT/Codex usage and is intentionally ignored for this provider. Setting `usage_provider` to `codex` does not hide Claude from the desktop window; it only makes Codex the primary provider for alerts, reset detection, event commands, and Auto tray icon bars.

## Tray provider

Choose which provider appears in the tray icon, hover tooltip, and desktop panel provider filter. This is separate from `usage_provider`, which remains the primary provider for alerts and automation.

| Key | Default | Description |
|-----|---------|-------------|
| `tray_provider` | `"auto"` | Tray and desktop panel provider selector. Valid values: `"auto"`, `"claude"`, or `"codex"` |

In `"auto"` mode, the tray hover tooltip shows Codex and Claude in that order, and the desktop panel shows both providers. The tray icon still uses the primary `usage_provider` for its two progress bars because a two-bar icon cannot clearly show both providers' session and weekly quotas at the same time. Changing the Provider submenu or the provider icons in the desktop panel Details view writes this setting and immediately updates any open desktop panel.

```json
{
    "tray_provider": "codex"
}
```

## Local usage estimates

The desktop window shows local cost and token estimates for each provider. These values are read from local JSONL logs and are never uploaded.

| Provider | Local files |
|----------|-------------|
| Claude | `$CLAUDE_CONFIG_DIR/projects/**/*.jsonl`, `~/.config/claude/projects/**/*.jsonl`, `~/.claude/projects/**/*.jsonl`, and `~/.pi/agent/sessions/**/*.jsonl` |
| Codex | `%CODEX_HOME%\sessions/**/*.jsonl`, `%CODEX_HOME%\archived_sessions/**/*.jsonl`, or the same paths under `~\.codex` |

The estimate window is a rolling 30 days including today. Known models use a bundled static USD price table; unknown models still count tokens but do not contribute to cost. The app keeps only an in-memory file parse cache keyed by path, size, and modification time, and it does not write a persistent local-usage cache.

## Alert thresholds

Configure usage percentage thresholds that trigger Windows notifications. Session and weekly quotas have separate thresholds since their time horizons differ significantly. Set to an empty array `[]` to disable alerts for a specific quota type.

| Key | Default | Description |
|-----|---------|-------------|
| `alert_thresholds_five_hour` | `[50, 80, 95]` | Thresholds (%) for Session (5hr) |
| `alert_thresholds_seven_day` | `[95]` | Thresholds (%) for Weekly quotas (7 day and all variants) |
| `alert_thresholds_extra_usage` | `[50, 80, 95]` | Thresholds (%) for Extra Usage (paid overage) |
| `alert_time_aware` | `true` | Only alert when usage outpaces elapsed time |
| `alert_time_aware_below` | `90` | Time-aware check applies only to thresholds below this value; thresholds at or above always fire |

Threshold lookup uses a fallback chain: exact match (e.g. `alert_thresholds_seven_day_opus`), then base period (e.g. `alert_thresholds_seven_day`), then no alerts. This lets you configure stricter thresholds per variant when needed:

```json
{
    "alert_thresholds_seven_day_opus": [50, 80, 95]
}
```

## Tooltip fields

The tray tooltip shows a quick usage summary when you hover over the icon. By default, it displays the session (5h) and weekly (7d) quotas. Use `tooltip_fields` to choose which usage fields appear in the tooltip.

| Key | Default | Description |
|-----|---------|-------------|
| `tooltip_fields` | `["five_hour", "seven_day"]` | Which usage fields to show in the tray tooltip, in order |

Must be an array of non-empty strings. Duplicates are silently removed. An empty array `[]` is valid (tooltip shows only the title, no usage fields). Unknown field names are accepted - if a field is `null` or missing from the API response, it is simply skipped.

**Known field names:** `five_hour`, `seven_day`, `seven_day_sonnet`, `seven_day_opus`, `seven_day_cowork`, `seven_day_oauth_apps`

**Example** - show session and Sonnet quota in the tooltip:

```json
{
    "tooltip_fields": ["five_hour", "seven_day_sonnet"]
}
```

## Popup fields

The desktop window now always shows exactly two quota rows per provider: `five_hour` and `seven_day`. The `popup_fields` setting is still accepted for backward compatibility, but it no longer changes what the window displays.

| Key | Default | Description |
|-----|---------|-------------|
| `popup_fields` | `["*"]` | Deprecated. Accepted for backward compatibility, but ignored by the desktop window |

Must still be an array of non-empty strings. `"*"` may appear at most once. Duplicates are silently removed so existing settings files continue to validate cleanly.

```json
{
    "popup_fields": ["five_hour", "seven_day_sonnet", "*"]
}
```

## Tray icon bars

The tray icon displays two small progress bars. By default, these show the session (5h) and weekly (7d) quotas. Use `icon_fields` to choose which two API fields are displayed.

| Key | Default | Description |
|-----|---------|-------------|
| `icon_fields` | `["five_hour", "seven_day"]` | Which two usage fields to show as icon bars. The first entry is the top bar (also determines the icon text), the second is the bottom bar |

Must be an array of exactly 2 non-empty strings. Unknown field names are accepted - if a field is `null` or missing from the API response, the bar shows 0%.

**Known field names:** `five_hour`, `seven_day`, `seven_day_sonnet`, `seven_day_opus`, `seven_day_cowork`, `seven_day_oauth_apps`

Each entry can optionally include a display mode suffix using colon syntax: `"field_name:mode"`.

**Available bar display modes:**

| Mode | Description |
|------|-------------|
| `utilization` | *(default)* Fills left-to-right proportional to current usage |
| `overage` | Shows how far usage has entered the over-budget zone: empty when usage is at or below the time marker (on pace or ahead), half-filled when usage is halfway between the time marker and 100%, full when usage reaches 100% |

**Example** - show session in overage mode and weekly in default mode:

```json
{
    "icon_fields": ["five_hour:overage", "seven_day"]
}
```

**Example** - show session and Sonnet quota (default utilization mode):

```json
{
    "icon_fields": ["five_hour", "seven_day_sonnet"]
}
```

## Event commands

Run a shell command when a usage event occurs. See [Event Commands](event-commands.md) for examples and available environment variables.

| Key | Default | Description |
|-----|---------|-------------|
| `on_reset_command` | *(none)* | Shell command (or array of commands) to run when a quota resets (usage drops) |
| `on_startup_command` | *(none)* | Shell command (or array of commands) to run once after the first successful API update following app start |
| `on_threshold_command` | *(none)* | Shell command (or array of commands) to run when usage crosses a configured alert threshold |

## Polling intervals

| Key | Default | Description |
|-----|---------|-------------|
| `poll_interval` | `180` | Seconds between API updates |
| `poll_fast` | `120` | Seconds when usage is actively increasing |
| `poll_fast_extra` | `2` | Extra fast polls after usage stops increasing |
| `poll_error` | `30` | Seconds after a transient error (5xx, network). Rate-limit errors (429) use exponential backoff instead |
| `max_backoff` | `900` | Maximum backoff in seconds for rate-limit errors (15 min) |
| `idle_pause` | `300` | Seconds of inactivity before polling pauses (0 = disable). Polling also pauses when the workstation is locked |

## Language

| Key | Default | Description |
|-----|---------|-------------|
| `language` | *(auto-detected)* | Override the UI language with a language code. Available: `de`, `en`, `es`, `fr`, `hi`, `id`, `it`, `ja`, `ko`, `pt-BR`, `uk`, `zh-CN`, `zh-TW` |

## Currency

The Anthropic API does not include currency information, so the app detects the currency symbol from your Windows locale settings. If your Windows locale currency differs from the currency Anthropic bills you in, you can override just the symbol here. Number formatting (decimal separator, symbol position) always follows your system locale.

| Key | Default | Description |
|-----|---------|-------------|
| `currency_symbol` | *(auto-detected)* | Override the auto-detected currency symbol (e.g., `"$"`, `"€"`, `"¥"`) |

## Tray icon colors

Override individual channels as RGBA arrays `[R, G, B, A]` (0-255). Unspecified keys keep their defaults.

| Key | Default | Description |
|-----|---------|-------------|
| `icon_light` | `{"fg": [255,255,255,255], "fg_half": [255,255,255,80], "fg_dim": [255,255,255,140]}` | Light icons for dark taskbar |
| `icon_dark` | `{"fg": [0,0,0,255], "fg_half": [0,0,0,80], "fg_dim": [0,0,0,140]}` | Dark icons for light taskbar |

## Popup colors

| Key | Default | Description |
|-----|---------|-------------|
| `bg` | `"#1e1e1e"` | Background |
| `fg` | `"#cccccc"` | Text |
| `fg_dim` | `"#888888"` | Dimmed text (labels, reset times) |
| `fg_heading` | `"#ffffff"` | Section headings |
| `fg_link` | `"#4a9eff"` | Accent text |
| `bar_bg` | `"#333333"` | Progress bar background |
| `bar_fg` | `"#4a9eff"` | Text bar color for `0-49%` |
| `bar_fg_mid` | `"#65c18c"` | Text bar color for `50-79%` |
| `bar_fg_warn` | `"#ff9f43"` | Text bar color for `80-99%` |
| `bar_fg_danger` | `"#ff3b30"` | Text bar color for `100%+` and status errors |
| `bar_divider` | `"#000c"` | Legacy key kept for compatibility; no longer used by the desktop window |
| `bar_marker` | `"#fffc"` | Legacy key kept for compatibility; no longer used by the desktop window |
