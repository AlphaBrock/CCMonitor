# Changelog / 更新日志

All notable changes to this project will be documented in this file.
本项目的所有重要变更都将记录在此文件中。

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.15.5] - 2026-05-22

### Added

- The detail window now opens visibly on startup at the top-right of the current taskbar screen, stays available on the desktop until hidden, can be dragged with the left mouse button, and includes a working `PIN` action that keeps it always on top and locks the window position
- Root-level `main.py` and `python -m src` now both work as source-debug entry points without building an EXE first
- Language selection submenu in the tray context menu to switch UI language manually, with auto-restart on change
- "Check for Updates" menu item that checks GitHub releases for newer versions and opens the download page when an update is available

### Changed

- The detail window now focuses on the two most frequently checked quotas (`5h` and `7d`) and renders them as full-width `█░` text bars that switch across four visible color bands inside a Monokai Pro-inspired panel theme
- Closing the detail window now hides it to the tray instead of exiting, and tray actions restore the existing window instead of creating a one-shot popup
- System language detection now uses the Windows `GetUserDefaultLocaleName` API for reliable locale identification, fixing Chinese and other non-Latin locale detection

### Removed

- The `CLAUDE CODE` section, changelog link, and popup-only installed-version list have been removed from the desktop window
- Midnight dividers and time-marker lines have been removed from the detail window bars

### Fixed

- UI language was always English on Chinese Windows systems because `locale.getlocale()` returns display names like `Chinese (Simplified)_China` that `locale.normalize()` cannot convert to ISO codes

---

### 新增

- 桌面窗口启动时在当前任务栏屏幕右上角可见打开，保持在桌面直到隐藏，支持左键拖拽定位，并包含 `PIN` 置顶按钮保持窗口在最上层并锁定位置
- 根目录 `main.py` 和 `python -m src` 均可作为源码调试入口，无需先构建 EXE
- 右键菜单新增语言切换子菜单，支持手动切换 UI 语言，切换后自动重启生效
- 右键菜单新增「检查更新」，检查 GitHub 最新版本并在有更新时打开下载页面

### 变更

- 桌面窗口聚焦于两个最常查看的配额（`5h` 和 `7d`），以全宽 `█░` 文字进度条渲染，在 Monokai Pro 风格面板中显示四种颜色档次
- 关闭桌面窗口现在隐藏到托盘而非退出，托盘操作恢复已有窗口而非创建新弹窗
- 系统语言检测改用 Windows `GetUserDefaultLocaleName` API，可靠识别中文等非拉丁语系地区

### 移除

- 移除了桌面窗口中的 `CLAUDE CODE` 部分、更新日志链接和已安装版本列表
- 移除了桌面窗口进度条中的午夜分割线和时间标记线

### 修复

- 中文 Windows 系统上 UI 语言始终显示英文，因为 `locale.getlocale()` 返回 `Chinese (Simplified)_China` 等显示名称，`locale.normalize()` 无法将其转换为 ISO 代码

[Show all code changes / 查看代码变更](https://github.com/AlphaBrock/CCMonitor/compare/1.15.5...HEAD)

## [1.15.1] - 2026-05-17

### Fixed

- Popup window now appears at the correct screen corner on high-DPI displays and on multi-monitor setups where the primary monitor is not positioned at virtual x=0; previously the popup could render oversized and overflow the screen edges at 150%/200% scaling, or land at the wrong edge when secondary monitors sat to the left of the primary (thanks to [@jnwildfire](https://github.com/jnwildfire) for the contribution)

---

### 修复

- 弹窗在高 DPI 显示器和主显示器不在虚拟 x=0 的多显示器配置上现在能正确显示在屏幕角落；此前在 150%/200% 缩放时弹窗可能过大溢出屏幕边缘，或在副显示器位于主显示器左侧时出现在错误边缘（感谢 [@jnwildfire](https://github.com/jnwildfire) 的贡献）

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.15.0...v1.15.1)

## [1.15.0] - 2026-05-01

### Added

- `on_startup_command` event - run a custom command once after the first successful API update following app start (also after using the **Restart** menu option). Receives per-quota utilization and reset timestamps as environment variables, so a command can decide what to do based on which sessions are active - for example, send a Claude Code ping when no five-hour session is running yet
- [Dim usage bars when data is stale](https://github.com/jens-duttke/usage-monitor-for-claude/discussions/28) - the usage section fades to 40% opacity when no successful update has been received for longer than the poll interval, clearly indicating that the displayed data may be outdated
- Account switch notification - switching to a different Claude account now shows an "Account Switched" notification with the new account's email address instead of a misleading "Quota Reset" notification
- Overage bar mode for tray icon bars - each entry in `icon_fields` now accepts an optional `:overage` suffix (e.g. `"five_hour:overage"`) to switch that bar to an over-budget view: the bar is empty when usage is at or below the time marker (on pace or ahead) and fills proportionally as usage climbs toward 100%, making it immediately visible how far you have overrun your expected pace
- Tray icon now distinguishes between "blocked" and "pay-as-you-go" states: a `$` replaces the `C`/percentage when any displayed quota is at 100% but your account still has paid extra-usage credits available, warning that further requests will now consume credits; a `✕` appears only when you are fully blocked (either no extra usage enabled or all credits spent). The `✕` also triggers when the bottom bar reaches 100%, not only the top bar

### Changed

- Tray icon now shows the usage percentage as soon as there is any usage; the `C` placeholder appears only while the top quota is still at 0% (previously the `C` stayed visible up to 50%)

### Fixed

- Usage bars are now always shown in red when they reach 100%, regardless of the time marker position
- Auto-refresh of the OAuth token now works for users who installed Claude Code via npm - the CLI is discovered via PATH and `%APPDATA%\npm`, not only the native Anthropic installer path (thanks to [@timyjsong](https://github.com/timyjsong) for the contribution)

---

### 新增

- `on_startup_command` 事件 - 应用启动后首次成功 API 更新时运行自定义命令（使用 **重新启动** 菜单后同样触发）。通过环境变量传递各配额的使用率和重置时间戳，命令可根据活跃会话情况决定操作
- [数据过时时淡化用量条](https://github.com/jens-duttke/usage-monitor-for-claude/discussions/28) - 当超过轮询间隔未收到成功更新时，用量部分淡化至 40% 透明度，清晰表明显示的数据可能已过时
- 账号切换通知 - 切换到不同的 Claude 账号时显示「账号已切换」通知及新账号邮箱，而非误导性的「配额重置」通知
- 托盘图标支持超支模式 - `icon_fields` 中的每个条目现在可添加 `:overage` 后缀（如 `"five_hour:overage"`），切换为超支视图
- 托盘图标区分「已用尽」和「按需付费」状态：当配额达 100% 但账户仍有付费额外用量时显示 `$`；完全被阻止时才显示 `✕`

### 变更

- 托盘图标在有任何使用时立即显示使用百分比；`C` 占位符仅在顶部配额为 0% 时显示

### 修复

- 用量条在达到 100% 时始终显示红色，不受时间标记位置影响
- 通过 npm 安装 Claude Code 的用户现在可以正常自动刷新 OAuth 令牌（感谢 [@timyjsong](https://github.com/timyjsong) 的贡献）

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.14.0...v1.15.0)

## [1.14.0] - 2026-03-27

### Added

- Verbose mode (`--verbose`) - prints system diagnostics (OS, DPI, WebView2, .NET, Python, dependencies, credentials) to the terminal, making it easy to troubleshoot startup issues without a Python installation

### Changed

- Running from source (`python -m usage_monitor_for_claude`) no longer shows log output by default - use `--verbose` to enable diagnostics

---

### 新增

- 详细模式（`--verbose`）- 在终端打印系统诊断信息（OS、DPI、WebView2、.NET、Python、依赖、凭据），方便排查启动问题

### 变更

- 从源码运行时不再默认显示日志输出 - 使用 `--verbose` 启用诊断

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.13.1...v1.14.0)

## [1.13.1] - 2026-03-27

### Fixed

- App no longer crashes when the API returns `null` instead of an object for a quota field, e.g. `five_hour: null` (thanks to [@2wplayer](https://github.com/2wplayer) for reporting [#26](https://github.com/jens-duttke/usage-monitor-for-claude/issues/26))

---

### 修复

- API 返回 `null` 而非对象（如 `five_hour: null`）时应用不再崩溃（感谢 [@2wplayer](https://github.com/2wplayer) 报告 [#26](https://github.com/jens-duttke/usage-monitor-for-claude/issues/26)）

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.13.0...v1.13.1)

## [1.13.0] - 2026-03-21

### Added

- [Show app version in popup](https://github.com/jens-duttke/usage-monitor-for-claude/discussions/20) - the popup footer now shows the app version (e.g. "1.13.0") in the bottom-right corner
- [Dynamic quota bars](https://github.com/jens-duttke/usage-monitor-for-claude/discussions/12) - the popup now automatically detects and displays all usage fields from the API response; no code change needed when Anthropic adds new quota types. Includes configurable `popup_fields` setting and per-variant alert threshold overrides
- [Configurable tray icon bars](https://github.com/jens-duttke/usage-monitor-for-claude/discussions/11) - new `icon_fields` setting lets you choose which two usage fields are shown in the tray icon (e.g. `["five_hour", "seven_day_sonnet"]`)
- [Configurable tooltip fields](https://github.com/jens-duttke/usage-monitor-for-claude/discussions/10) - new `tooltip_fields` setting lets you choose which usage fields appear in the tray tooltip (e.g. `["five_hour", "seven_day_sonnet"]`)
- Support for the `CLAUDE_CONFIG_DIR` environment variable - the app now reads credentials and settings from a custom Claude config directory when set, falling back to `~/.claude/` as before
- Event commands now receive `USAGE_MONITOR_VERSION` with the running app version, so scripts can use it without hardcoding
- Configurable `bar_divider` color for midnight dividers on weekly progress bars

### Changed

- Improved visibility of midnight dividers on weekly bars
- Time marker color default changed from solid white to slightly transparent (`#fffc`) with a subtle shadow for better contrast on colored bars

---

### 新增

- [弹窗显示应用版本](https://github.com/jens-duttke/usage-monitor-for-claude/discussions/20) - 弹窗页脚右下角显示版本号
- [动态配额条](https://github.com/jens-duttke/usage-monitor-for-claude/discussions/12) - 弹窗自动检测并显示 API 响应中的所有用量字段，Anthropic 新增配额类型时无需修改代码
- [可配置托盘图标条](https://github.com/jens-duttke/usage-monitor-for-claude/discussions/11) - 新增 `icon_fields` 设置选择显示哪两个用量字段
- [可配置工具提示字段](https://github.com/jens-duttke/usage-monitor-for-claude/discussions/10) - 新增 `tooltip_fields` 设置选择工具提示中显示的字段
- 支持 `CLAUDE_CONFIG_DIR` 环境变量 - 从自定义 Claude 配置目录读取凭据和设置
- 事件命令接收 `USAGE_MONITOR_VERSION` 环境变量
- 可配置 `bar_divider` 颜色

### 变更

- 改善了周用量条上午夜分割线的可见性
- 时间标记颜色默认值改为半透明（`#fffc`）并带阴影

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.12.0...v1.13.0)

## [1.12.0] - 2026-03-20

### Added

- "Project on GitHub" link in the tray context menu to quickly open the project repository
- Live status timer in popup - shows "Updated Xs ago" counting up every second instead of a static timestamp, with "Next update in ..." countdown after 60 seconds
- Tray tooltip now includes the server's error message (e.g. "Rate limited") alongside the HTTP error

### Fixed

- Context menu hover effect not showing on displays with DPI scaling above 100%
- Popup no longer shows an icon in the taskbar while open
- Popup appearing at the wrong position after changing DPI scaling without restarting the app

---

### 新增

- 右键菜单新增「GitHub 项目」链接
- 弹窗实时状态计时器 - 显示「X秒前更新」并每秒递增，60 秒后显示下次更新倒计时
- 托盘工具提示包含服务器错误信息

### 修复

- DPI 缩放超过 100% 时右键菜单悬停效果不显示
- 弹窗打开时不再在任务栏显示图标
- 更改 DPI 缩放后弹窗出现在错误位置

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.11.0...v1.12.0)

## [1.11.0] - 2026-03-20

### Added

- Single-instance guard - if the app is already running, a dialog shows the running version and asks whether to replace it (thanks to [@GitHubEtienne](https://github.com/GitHubEtienne) for reporting [#6](https://github.com/jens-duttke/usage-monitor-for-claude/issues/6))

### Fixed

- Popup no longer dismisses immediately or appears off-screen on displays with DPI scaling above 100% (thanks to [@GitHubEtienne](https://github.com/GitHubEtienne) for reporting [#6](https://github.com/jens-duttke/usage-monitor-for-claude/issues/6) and [@igorrr01](https://github.com/igorrr01) for testing)

---

### 新增

- 单实例保护 - 应用已运行时弹出对话框显示运行版本并询问是否替换（感谢 [@GitHubEtienne](https://github.com/GitHubEtienne) 报告 [#6](https://github.com/jens-duttke/usage-monitor-for-claude/issues/6)）

### 修复

- DPI 缩放超过 100% 时弹窗不再立即消失或出现在屏幕外（感谢 [@GitHubEtienne](https://github.com/GitHubEtienne) 报告、[@igorrr01](https://github.com/igorrr01) 测试）

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.10.0...v1.11.0)

## [1.10.0] - 2026-03-18

### Added

- New color settings `fg_link` (link text) and `bar_marker` (time-position marker on progress bars) for finer theme control

### Changed

- Context-specific titles: popup shows "Usage Monitor for Claude", tooltip shows "Claude Usage", and context menu shows "Show Claude Usage" instead of the generic "Account & Usage" everywhere
- Popup window rebuilt with HTML/CSS rendering (via Edge WebView2) replacing tkinter - smoother bar animations with CSS transitions, no flickering on updates, and more flexible layout
- Executable size reduced by more than a third (from ~20 MB to ~12.5 MB) by removing unused image codecs and bundled modules

---

### 新增

- 新增颜色设置 `fg_link`（链接文字）和 `bar_marker`（进度条时间标记）

### 变更

- 上下文特定标题：弹窗、工具提示和菜单分别显示不同标题
- 弹窗改用 HTML/CSS 渲染（通过 Edge WebView2）替代 tkinter - 更流畅的动画，无闪烁
- 可执行文件体积缩减超过三分之一（从约 20 MB 到约 12.5 MB）

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.9.0...v1.10.0)

## [1.9.0] - 2026-03-15

### Added

- Day dividers on the weekly usage bar - subtle gaps at local midnight boundaries visually group usage into day segments

### Changed

- `on_reset_command` and `on_threshold_command` now accept an array of command strings to run multiple commands per event (single strings still work)
- `on_reset_command` now fires promptly even when the computer is idle or locked, so automated workflows (e.g. resuming a Claude session) are not delayed until the user returns

---

### 新增

- 周用量条上的日分割线 - 在本地午夜边界处以细微间隙分隔各天

### 变更

- `on_reset_command` 和 `on_threshold_command` 支持字符串数组以运行多条命令
- `on_reset_command` 在电脑空闲或锁定时也能及时触发

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.8.0...v1.9.0)

## [1.8.0] - 2026-03-15

### Added

- `on_reset_command` and `on_threshold_command` settings to run shell commands when usage events occur (e.g. push notifications, agent orchestration), with event details passed as environment variables. The reset command fires on any usage drop and includes the previous utilization so your script can decide when to act
- "Restart" option in the tray context menu to reload settings without manually closing and reopening the app
- "Test event commands" submenu to fire configured event commands with sample data for quick verification

### Fixed

- Brief console window flash when checking CLI version or refreshing the authentication token

---

### 新增

- `on_reset_command` 和 `on_threshold_command` 设置，在用量事件发生时运行 Shell 命令（如推送通知、代理编排），事件详情通过环境变量传递
- 右键菜单新增「重新启动」选项，无需手动关闭重开即可重新加载设置
- 「测试事件命令」子菜单，使用示例数据快速验证已配置的事件命令

### 修复

- 检查 CLI 版本或刷新认证令牌时不再闪现控制台窗口

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.7.0...v1.8.0)

## [1.7.0] - 2026-03-14

### Added

- Ukrainian language support (thanks to [@Actpohomoc](https://github.com/Actpohomoc) for the contribution)
- Configurable alert notifications for extra usage (paid overage) via `alert_thresholds_extra_usage` setting (default: 50%, 80%, 95%)

### Changed

- Usage bars now turn red only when usage passes the time marker (usage ahead of elapsed time), instead of always at 80%
- **Breaking:** Setting `bar_fg_high` renamed to `bar_fg_warn`

---

### 新增

- 乌克兰语支持（感谢 [@Actpohomoc](https://github.com/Actpohomoc) 的贡献）
- 可配置额外用量（付费超额）提醒通知

### 变更

- 用量条仅在使用超过时间标记时才变红，而非始终在 80% 时变色
- **破坏性变更：** 设置 `bar_fg_high` 重命名为 `bar_fg_warn`

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.6.0...v1.7.0)

## [1.6.0] - 2026-03-10

### Added

- `language` setting to manually override the auto-detected UI language (e.g., `"language": "ja"`)
- Live countdown for reset times in the popup - timers now tick down between API polls instead of staying frozen

### Fixed

- Popup sections could appear in wrong order when usage data was not yet available at startup

---

### 新增

- `language` 设置，手动覆盖自动检测的 UI 语言（如 `"language": "ja"`）
- 弹窗中重置时间实时倒计时 - 在 API 轮询间隔内持续递减而非冻结

### 修复

- 启动时用量数据尚未可用时弹窗区域可能以错误顺序显示

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.5.0...v1.6.0)

## [1.5.0] - 2026-03-08

### Added

- Idle and lock detection - polling pauses when the computer is idle (default: 300 seconds of no keyboard/mouse input) or locked, and resumes immediately when activity returns. Configurable via the `idle_pause` setting (set to `0` to disable)
- Automatic token refresh - when the OAuth session expires, runs `claude update` in the background to renew the token without user intervention
- Claude Code version display in the detail popup showing installed versions for CLI, VS Code, Cursor, and Windsurf
- Notification when `claude update` installs a newer CLI version
- Clickable changelog link in the Claude Code section of the detail popup, opening the official Claude Code changelog on GitHub
- User-configurable `max_backoff` setting to cap rate-limit backoff duration (default 15 minutes)
- Terminal logging when running via `python -m usage_monitor_for_claude` - shows API calls, skip reasons, and results (silent in EXE builds)

### Changed

- Increased default polling intervals to reduce API rate-limit errors (`poll_interval`: 120 to 180 seconds, `poll_fast`: 60 to 120 seconds)
- Numeric settings (`poll_interval`, `poll_fast`, etc.) now require integer values - fractional numbers like `120.5` are no longer accepted

### Removed

- "Refresh now" context menu entry - automatic polling makes manual refresh unnecessary, and it could trigger API rate-limit errors

### Fixed

- A successful token refresh followed by a transient API error (e.g. HTTP 500) no longer permanently blocks the new token from being used
- Eliminated race condition where opening the popup could trigger a redundant API call alongside the poll loop, causing HTTP 429 rate-limit errors
- Opening the popup during an active rate-limit backoff no longer triggers an additional API call - the popup shows cached data instead
- Prevented duplicate profile fetches when multiple threads check the account profile simultaneously
- Clicking the tray icon while the popup is open no longer causes the popup to briefly close and immediately reopen
- Fixed double separator line in the popup when usage data is unavailable (e.g. API error on startup)

---

### 新增

- 空闲和锁定检测 - 电脑空闲（默认 300 秒无输入）或锁定时暂停轮询，活动恢复后立即继续。通过 `idle_pause` 设置配置
- 自动令牌刷新 - OAuth 会话过期时后台运行 `claude update` 自动续期
- 弹窗中显示 Claude Code 版本（CLI、VS Code、Cursor、Windsurf）
- `claude update` 安装新版本时显示通知
- 弹窗中可点击的更新日志链接
- 可配置 `max_backoff` 设置限制速率限制退避时长（默认 15 分钟）
- 从源码运行时终端日志输出

### 变更

- 增加默认轮询间隔以减少 API 速率限制错误（`poll_interval`：120 到 180 秒，`poll_fast`：60 到 120 秒）
- 数值设置项现在要求整数值

### 移除

- 「立即刷新」菜单项 - 自动轮询使手动刷新不再必要

### 修复

- 令牌刷新成功后遇到暂时性 API 错误不再永久阻止使用新令牌
- 消除了打开弹窗可能触发冗余 API 调用导致 HTTP 429 的竞态条件
- 速率限制退避期间打开弹窗不再触发额外 API 调用
- 防止多线程同时获取账户配置文件时的重复请求
- 点击托盘图标时弹窗不再短暂关闭后立即重新打开
- 修复无用量数据时弹窗中的双分隔线

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.4.0...v1.5.0)

## [1.4.0] - 2026-03-05

### Changed

- Rate-limit errors (HTTP 429) now use exponential backoff instead of the short error interval, preventing the app from making the problem worse by polling faster
- API error messages now include the server's error detail (e.g. "Rate limited.") when available

### Fixed

- API requests could be permanently rejected (HTTP 429) due to endpoint restrictions on the server side

---

### 变更

- 速率限制错误（HTTP 429）现使用指数退避而非短错误间隔，避免更频繁轮询加剧问题
- API 错误消息包含服务器错误详情

### 修复

- API 请求可能因服务器端限制被永久拒绝（HTTP 429）

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.3.0...v1.4.0)

## [1.3.0] - 2026-03-02

### Added

- Configurable usage alerts when quota exceeds defined thresholds (e.g., 80%, 95%), with separate settings for session and weekly quotas
- Time-aware alert mode (on by default) - suppresses notifications when usage is on track with elapsed time; `alert_time_aware_below` controls up to which threshold this applies, so high thresholds can always fire
- Extra usage section in the detail popup when extra usage is enabled on your account, with automatic currency symbol detection from the system locale (overridable via `currency_symbol` in the settings file)
- Status line in the popup showing when data was last updated and whether a refresh is in progress or failed

### Changed

- Server errors (HTTP 5xx) now show a specific "temporarily unavailable" message instead of the generic HTTP error
- Popup opens immediately with cached data instead of waiting for the API response; errors are shown in the status line while usage bars remain visible
- Popup grows away from the taskbar edge regardless of taskbar position (bottom, top, left, or right)

---

### 新增

- 可配置用量提醒，配额超过设定阈值时通知（如 80%、95%），会话和周配额可分别设置
- 时间感知提醒模式（默认开启）- 当使用进度与已过时间一致时不发通知
- 账户启用额外用量时弹窗显示额外用量部分，自动检测系统地区货币符号
- 弹窗状态行显示上次更新时间和刷新状态

### 变更

- 服务器错误（HTTP 5xx）显示「暂时不可用」而非通用 HTTP 错误
- 弹窗立即显示缓存数据而非等待 API 响应
- 弹窗在任何任务栏位置都朝远离任务栏的方向展开

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.2.0...v1.3.0)

## [1.2.0] - 2026-03-01

### Added

- Optional settings file (`usage-monitor-settings.json`) to customize polling intervals, popup colors, and icon colors

### Changed

- The code has been split into smaller, focused modules. Running from source now uses `python -m usage_monitor_for_claude`

### Fixed

- No longer sends repeated API requests after a 401 auth error; polls only re-read the credentials file until the token actually changes

---

### 新增

- 可选设置文件（`usage-monitor-settings.json`）自定义轮询间隔、弹窗颜色和图标颜色

### 变更

- 代码拆分为更小的专注模块。从源码运行改用 `python -m usage_monitor_for_claude`

### 修复

- 401 认证错误后不再重复发送 API 请求；仅在令牌实际更改后才重新请求

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.1.0...v1.2.0)

## [1.1.0] - 2026-02-28

### Added

- Tray icon supports the Windows light theme
- Session expiry detection with distinct "C!" tray icon when the Anthropic API returns HTTP 401, instead of showing a generic error
- Windows toast notification when quota resets after near-exhaustion (session >95% or weekly >98%), so users know Claude is available again without manually checking
- Adaptive polling that aligns to imminent quota resets for near-immediate feedback when quota refreshes
- Simplified Chinese (zh-CN) and Traditional Chinese (zh-TW) translations

### Changed

- Reassigned tray icon symbols for clearer meaning: "✕" for depleted quota, "!" for errors, "C!" for expired session

### Fixed

- Updated repository URL in setup instructions

---

### 新增

- 托盘图标支持 Windows 浅色主题
- 会话过期检测 - Anthropic API 返回 HTTP 401 时显示「C!」图标
- 配额在近乎耗尽后重置时弹出 Windows 通知
- 自适应轮询，在配额即将重置时加速轮询
- 简体中文（zh-CN）和繁体中文（zh-TW）翻译

### 变更

- 重新分配托盘图标符号：「✕」表示配额耗尽，「!」表示错误，「C!」表示会话过期

### 修复

- 更新了设置说明中的仓库 URL

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/compare/v1.0.0...v1.1.0)

## [1.0.0] - 2026-02-26

Initial release. / 首次发布。

### Added

- Windows system tray tool displaying live Claude.ai rate-limit usage
- Authentication via Claude Code OAuth token
- Adaptive polling intervals based on current usage levels
- Session (5h) and weekly (7d) limits shown as progress bars in tray icon and detail popup
- Dark-themed detail popup with usage breakdown
- PyInstaller build tooling (spec file + build script)
- 10-language i18n support

---

### 新增

- Windows 系统托盘工具，实时显示 Claude.ai 速率限制用量
- 通过 Claude Code OAuth 令牌认证
- 基于当前使用水平的自适应轮询间隔
- 会话（5 小时）和周（7 天）限额在托盘图标和详情弹窗中以进度条显示
- 深色主题详情弹窗
- PyInstaller 构建工具（spec 文件 + 构建脚本）
- 10 种语言国际化支持

[Show all code changes / 查看代码变更](https://github.com/jens-duttke/usage-monitor-for-claude/releases/tag/v1.0.0)
