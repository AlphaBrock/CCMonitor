let els;
let translations = {};
let statusStateByProvider = {};
let textTimerId = null;
let pinRequestPending = false;
let activeView = 'all';
let activeMode = 'brief';
let lastData = { providers: [] };
const BAR_LENGTH = 20;

const PROVIDER_ICON_ASSETS = {
    all: { path: '../../../assets/icon/application.svg', mode: 'mask' },
    codex: { path: '../../../assets/icon/openai.svg', mode: 'mask' },
    claude: { path: '../../../assets/icon/claude-color.svg', mode: 'mask' },
};

function init(config) {
    const styles = document.documentElement.style;
    for (const [key, value] of Object.entries(config.colors)) {
        styles.setProperty(`--${key.replaceAll('_', '-')}`, value);
    }

    translations = config.t || {};
    document.getElementById('title').textContent = translations.title;
    document.getElementById('appVersion').textContent = config.app_version;

    els = {
        header: document.getElementById('windowHeader'),
        cards: document.getElementById('providerCards'),
        footerStatus: document.getElementById('footerStatus'),
        pinBtn: document.getElementById('pinBtn'),
        detailsBtn: document.getElementById('detailsBtn'),
        closeBtn: document.getElementById('closeBtn'),
    };

    bindWindowActions();
    setPinned(Boolean(config.window?.pinned));
    setDetailsMode(false, false);
    updateData(config.data);

    requestAnimationFrame(() => {
        fitTextBars();
        document.body.classList.add('open');
    });
}

function bindWindowActions() {
    const stopDrag = (event) => event.stopPropagation();

    els.pinBtn.addEventListener('mousedown', stopDrag);
    els.detailsBtn.addEventListener('mousedown', stopDrag);
    els.closeBtn.addEventListener('mousedown', stopDrag);

    els.pinBtn.addEventListener('click', async () => {
        if (pinRequestPending) {
            return;
        }

        if (!window.pywebview?.api?.toggle_pin) {
            setPinned(!els.pinBtn.classList.contains('pinned'));
            return;
        }

        pinRequestPending = true;
        try {
            const result = await pywebview.api.toggle_pin();
            setPinned(Boolean(result?.pinned));
        } catch {
            setPinned(!els.pinBtn.classList.contains('pinned'));
        } finally {
            pinRequestPending = false;
        }
    });

    els.detailsBtn.addEventListener('click', () => {
        setDetailsMode(activeMode !== 'details');
    });

    els.closeBtn.addEventListener('click', () => {
        window.pywebview?.api?.hide_window?.();
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            window.pywebview?.api?.hide_window?.();
        }
    });
}

function setPinned(pinned) {
    els.pinBtn.classList.toggle('pinned', pinned);
    els.pinBtn.setAttribute('aria-pressed', pinned ? 'true' : 'false');
    els.pinBtn.dataset.tooltip = pinned ? (translations.pin_on || 'Pinned in place') : (translations.pin_off || 'Always on top disabled');
    els.header.classList.toggle('locked', pinned);
    els.header.classList.toggle('pywebview-drag-region', !pinned);
}

function setDetailsMode(showDetails, shouldRender = true) {
    activeMode = showDetails ? 'details' : 'brief';
    els.detailsBtn.classList.toggle('active', showDetails);
    els.detailsBtn.setAttribute('aria-pressed', showDetails ? 'true' : 'false');
    els.detailsBtn.dataset.tooltip = showDetails ? (translations.view_brief || 'Brief') : (translations.view_details || 'Details');

    if (shouldRender) {
        renderProviders(lastData.providers || []);
        tickStatusText();
    }
}

function updateData(data) {
    lastData = data || { providers: [] };
    if (lastData.provider_view) {
        activeView = normalizeProviderView(lastData.provider_view);
    }

    renderProviders(lastData.providers || []);
    startStatusTimer();
}

function normalizeProviderView(viewId) {
    return ['all', 'codex', 'claude'].includes(viewId) ? viewId : 'all';
}

function syncProviderView(viewId) {
    activeView = normalizeProviderView(viewId);
    renderProviders(lastData.providers || []);
    tickStatusText();
}

function visibleProviders(providers) {
    if (activeView === 'all') {
        return providers;
    }
    return providers.filter((provider) => provider.id === activeView);
}

function renderProviders(providers) {
    statusStateByProvider = {};
    const visible = visibleProviders(providers);

    if (activeMode === 'details') {
        els.cards.replaceChildren(createDetailsSwitcher(providers), ...visible.map(createProviderCard));
    } else {
        els.cards.replaceChildren(...createSummaryNodes(visible));
    }

    requestAnimationFrame(fitTextBars);
}

function createSummaryNodes(providers) {
    const head = document.createElement('div');
    head.className = 'summary-card-head';
    const title = document.createElement('h2');
    const sessionProvider = providers.find((provider) => provider.session_usage);
    title.textContent = sessionProvider?.session_usage?.label || 'Session (5h)';
    const scope = document.createElement('span');
    scope.className = 'summary-scope';
    scope.textContent = providers.length ? providers.map((provider) => provider.title).join(' + ') : translations.status_refreshing;
    head.append(title, scope);

    const rows = document.createElement('div');
    rows.className = 'summary-provider-list';
    if (providers.length) {
        rows.replaceChildren(...providers.map(createSummaryProviderRow));
    } else {
        const empty = document.createElement('div');
        empty.className = 'brief-empty';
        empty.textContent = translations.session_unavailable || 'Session unavailable';
        rows.append(empty);
    }

    return [head, rows];
}

function createSummaryProviderRow(provider) {
    const row = document.createElement('div');
    row.className = `summary-provider-row provider-${provider.id}`;
    row.dataset.provider = provider.id;

    const head = document.createElement('div');
    head.className = 'summary-provider-head';

    const identity = document.createElement('div');
    identity.className = 'summary-provider-title';
    const icon = createProviderIcon(provider.id, provider.icon, 'summary-provider-icon');
    const name = document.createElement('span');
    name.textContent = provider.title;
    identity.append(icon, name);

    const status = document.createElement('span');
    status.className = 'summary-provider-status';
    status.dataset.providerStatus = provider.id;
    head.append(identity, status);
    row.append(head);

    const accountRow = createProviderAccountRow(provider);
    if (accountRow) {
        accountRow.classList.add('summary-account-row');
        row.append(accountRow);
    }

    if (provider.session_usage) {
        row.append(createUsageRow(provider.session_usage, { compact: true }));
    } else {
        const empty = document.createElement('div');
        empty.className = 'brief-empty';
        empty.textContent = translations.session_unavailable || 'Session unavailable';
        row.append(empty);
    }

    setProviderStatusState(provider.id, provider.status);
    return row;
}

function createDetailsSwitcher(providers) {
    const switcher = document.createElement('nav');
    switcher.className = 'provider-switcher';
    switcher.setAttribute('aria-label', 'Provider view');

    const buttons = [createSwitcherButton('all', translations.all || 'All', '')];
    for (const provider of providers) {
        buttons.push(createSwitcherButton(provider.id, provider.title, provider.icon));
    }
    switcher.replaceChildren(...buttons);
    return switcher;
}

function createSwitcherButton(viewId, labelText, iconText) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'provider-tab';
    button.classList.toggle('active', activeView === viewId);
    button.dataset.view = viewId;

    const icon = createProviderIcon(viewId, iconText, 'provider-tab-icon');
    const label = document.createElement('span');
    label.textContent = labelText;

    button.append(icon, label);
    button.addEventListener('click', () => selectProviderView(viewId));
    return button;
}

async function selectProviderView(viewId) {
    const nextView = normalizeProviderView(viewId);
    syncProviderView(nextView);

    if (!window.pywebview?.api?.set_provider_view) {
        return;
    }

    try {
        const result = await pywebview.api.set_provider_view(nextView);
        const syncedView = (typeof result === 'string' ? result : result?.provider_view) || nextView;
        syncProviderView(syncedView);
    } catch {
        syncProviderView(nextView);
    }
}

function createProviderIcon(providerId, fallbackText, className) {
    const icon = document.createElement('span');
    icon.className = className;
    const asset = PROVIDER_ICON_ASSETS[providerId];
    if (asset?.mode === 'mask') {
        icon.classList.add('provider-icon-mask');
        icon.style.setProperty('--provider-icon-url', `url("${asset.path}")`);
    } else if (fallbackText) {
        icon.textContent = fallbackText;
    } else {
        icon.classList.add('provider-icon-empty');
    }
    return icon;
}

function createProviderHeader(provider) {
    const header = document.createElement('div');
    header.className = 'provider-card-head';

    const titleRow = document.createElement('div');
    titleRow.className = 'provider-title-row';
    const titleIcon = createProviderIcon(provider.id, provider.icon, 'provider-card-icon');
    const title = document.createElement('h2');
    title.textContent = provider.title;
    titleRow.append(titleIcon, title);

    const status = document.createElement('div');
    status.className = 'provider-status';
    status.dataset.providerStatus = provider.id;

    header.append(titleRow, status);
    return header;
}

function createProviderAccountRow(provider) {
    const emailText = provider.profile?.email || '';
    const planText = provider.profile?.plan || '';
    if (!emailText && !planText) {
        return null;
    }

    const row = document.createElement('div');
    row.className = 'provider-account-row';

    const email = document.createElement('span');
    email.className = 'provider-account-email';
    email.textContent = emailText;

    const plan = document.createElement('span');
    plan.className = 'provider-account-plan';
    plan.textContent = planText;

    row.append(email, plan);
    return row;
}

function createProviderCard(provider) {
    const card = document.createElement('section');
    card.className = `provider-card provider-${provider.id}`;
    card.dataset.provider = provider.id;

    card.append(createProviderHeader(provider));

    const accountRow = createProviderAccountRow(provider);
    if (accountRow) {
        card.append(accountRow);
    }

    const usageRows = provider.usage || [];
    if (usageRows.length) {
        const usage = document.createElement('div');
        usage.className = 'usage-list';
        usage.replaceChildren(...usageRows.map((row) => createUsageRow(row)));
        card.append(usage);
    }

    if (provider.extra) {
        const extra = document.createElement('div');
        extra.className = 'extra-block';
        const extraTitle = document.createElement('div');
        extraTitle.className = 'block-title';
        extraTitle.textContent = translations.extra_usage;
        extra.append(
            extraTitle,
            createUsageRow({
                label: translations.extra_usage,
                pct_text: provider.extra.pct_text,
                tone: provider.extra.tone,
                bar_text: provider.extra.bar_text,
                reset_text: provider.extra.spent_text,
            }),
        );
        card.append(extra);
    }

    card.append(createMetricsBlock(provider.metrics));
    setProviderStatusState(provider.id, provider.status);
    return card;
}

function createUsageRow(entry, options = {}) {
    const row = document.createElement('div');
    row.className = options.compact ? 'usage-row usage-row-compact' : 'usage-row';

    const label = document.createElement('div');
    label.className = 'usage-label';
    label.textContent = entry.label;

    const bar = createTextBar(entry.bar_text, entry.tone);

    const foot = document.createElement('div');
    foot.className = 'usage-foot';

    const percent = document.createElement('span');
    percent.className = `usage-pct tone-${entry.tone}`;
    percent.textContent = `${entry.pct_text} used`;
    foot.append(percent);

    if (entry.reset_text) {
        const reset = document.createElement('span');
        reset.className = 'reset-text';
        reset.textContent = entry.reset_text;
        foot.append(reset);
    }

    row.append(label, bar, foot);
    return row;
}

function createTextBar(barText, tone) {
    const bar = document.createElement('div');
    bar.className = `text-bar tone-${tone}`;
    const glyphs = document.createElement('span');
    glyphs.className = 'text-bar-glyphs';
    glyphs.textContent = (barText || '').padEnd(BAR_LENGTH, '░').slice(0, BAR_LENGTH);
    bar.append(glyphs);
    return bar;
}

function createMetricsBlock(metrics) {
    const block = document.createElement('div');
    block.className = 'metrics-block';

    const title = document.createElement('div');
    title.className = 'block-title';
    title.textContent = translations.local_metrics;

    const grid = document.createElement('div');
    grid.className = 'metrics-grid';
    for (const item of metrics?.items || []) {
        const cell = document.createElement('div');
        cell.className = 'metric-cell';
        const label = document.createElement('div');
        label.className = 'metric-label';
        label.textContent = item.label;
        const value = document.createElement('div');
        value.className = 'metric-value';
        value.textContent = item.value;
        cell.append(label, value);
        grid.append(cell);
    }

    const note = document.createElement('div');
    note.className = 'metrics-note';
    note.textContent = metrics?.note || '';

    block.append(title, grid, note);
    return block;
}

function setProviderStatusState(providerId, status) {
    if (!status) {
        statusStateByProvider[providerId] = null;
        return;
    }

    if (status.last_success_time !== undefined) {
        statusStateByProvider[providerId] = {
            lastSuccessTime: status.last_success_time,
            nextPollTime: status.next_poll_time,
            refreshing: status.refreshing,
            error: status.error,
        };
        return;
    }

    statusStateByProvider[providerId] = {
        text: status.text || '',
        isError: Boolean(status.is_error),
    };
}

function startStatusTimer() {
    if (textTimerId) {
        clearInterval(textTimerId);
    }
    tickStatusText();
    textTimerId = setInterval(tickStatusText, 1000);
}

function tickStatusText() {
    els.footerStatus.textContent = '';
    els.footerStatus.classList.remove('error');

    for (const node of document.querySelectorAll('[data-provider-status]')) {
        const provider = (lastData.providers || []).find((item) => item.id === node.dataset.providerStatus);
        if (!provider) {
            node.textContent = '';
            node.classList.remove('error');
            continue;
        }

        const status = formatProviderStatus(provider);
        node.textContent = status.text;
        node.classList.toggle('error', status.isError);
    }
}

function formatProviderStatus(provider) {
    const status = statusStateByProvider[provider.id];
    if (!status) {
        return { text: translations.status_refreshing || '', isError: false };
    }

    if (status.text !== undefined) {
        return {
            text: status.text,
            isError: Boolean(status.isError),
        };
    }

    const now = Date.now() / 1000;
    const secondsAgo = Math.max(0, Math.floor(now - status.lastSuccessTime));
    const parts = [formatDuration(secondsAgo)];
    if (status.refreshing) {
        parts.push(translations.status_refreshing);
    } else if (status.error) {
        parts.push(status.error);
    } else if (secondsAgo >= 60 && status.nextPollTime) {
        const secondsUntil = Math.max(0, Math.floor(status.nextPollTime - now));
        if (secondsUntil > 0) {
            parts.push(translations.status_next_update.replace('{duration}', formatCountdown(secondsUntil)));
        }
    }

    return {
        text: parts.filter(Boolean).join(' · '),
        isError: Boolean(status.error),
    };
}

function fitTextBars() {
    for (const bar of document.querySelectorAll('.text-bar')) {
        const glyphs = bar.querySelector('.text-bar-glyphs');
        if (!glyphs) {
            continue;
        }

        glyphs.style.transform = 'scaleX(1)';
        const naturalWidth = glyphs.scrollWidth;
        const availableWidth = bar.clientWidth;
        if (!naturalWidth || !availableWidth) {
            continue;
        }

        glyphs.style.transform = `scaleX(${availableWidth / naturalWidth})`;
    }
}

function formatDuration(totalSeconds) {
    if (totalSeconds < 60) {
        return translations.status_updated_s.replace('{s}', totalSeconds);
    }

    const totalMinutes = Math.floor(totalSeconds / 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;

    if (hours > 0) {
        return translations.status_updated.replace(
            '{duration}',
            translations.duration_hm.replace('{h}', hours).replace('{m}', minutes),
        );
    }

    return translations.status_updated.replace(
        '{duration}',
        translations.duration_m.replace('{m}', totalMinutes),
    );
}

function formatCountdown(totalSeconds) {
    if (totalSeconds < 60) {
        return translations.duration_s.replace('{s}', totalSeconds);
    }

    const totalMinutes = Math.ceil(totalSeconds / 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;

    if (hours > 0) {
        return translations.duration_hm.replace('{h}', hours).replace('{m}', minutes);
    }

    return translations.duration_m.replace('{m}', totalMinutes);
}

new ResizeObserver(() => {
    fitTextBars();
    const height = document.body.scrollHeight;
    window.pywebview?.api?.report_height?.(height);
}).observe(document.body);
