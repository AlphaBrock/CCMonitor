let els;
let translations = {};
let statusStateByProvider = {};
let textTimerId = null;
let pinRequestPending = false;
let activeView = 'all';
let lastData = { providers: [] };
const BAR_LENGTH = 20;

const TAB_ICON_ASSETS = {
    all: { path: '../../../assets/icon/application.svg', mode: 'mask' },
    codex: { path: '../../../assets/icon/openai.svg', mode: 'mask' },
    claude: { path: '../../../assets/icon/claude-color.svg', mode: 'mask' },
};

function init(config) {
    const styles = document.documentElement.style;
    for (const [key, value] of Object.entries(config.colors)) {
        styles.setProperty(`--${key.replaceAll('_', '-')}`, value);
    }

    translations = config.t;
    document.getElementById('title').textContent = translations.title;
    document.getElementById('appVersion').textContent = config.app_version;

    els = {
        header: document.getElementById('windowHeader'),
        switcher: document.getElementById('providerSwitcher'),
        cards: document.getElementById('providerCards'),
        pinBtn: document.getElementById('pinBtn'),
        closeBtn: document.getElementById('closeBtn'),
    };

    bindWindowActions();
    setPinned(Boolean(config.window?.pinned));
    updateData(config.data);

    requestAnimationFrame(() => {
        fitTextBars();
        document.body.classList.add('open');
    });
}

function bindWindowActions() {
    const stopDrag = (event) => event.stopPropagation();

    els.pinBtn.addEventListener('mousedown', stopDrag);
    els.closeBtn.addEventListener('mousedown', stopDrag);
    els.switcher.addEventListener('mousedown', stopDrag);

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

function updateData(data) {
    lastData = data || { providers: [] };
    const providers = lastData.providers || [];
    if (activeView !== 'all' && !providers.some((provider) => provider.id === activeView)) {
        activeView = 'all';
    }

    renderSwitcher(providers);
    renderProviders(providers);
    startStatusTimer();
}

function renderSwitcher(providers) {
    const buttons = [createSwitcherButton('all', translations.all || 'All', '▦')];
    for (const provider of providers) {
        buttons.push(createSwitcherButton(provider.id, provider.title, provider.icon));
    }
    els.switcher.replaceChildren(...buttons);
}

function createSwitcherButton(viewId, labelText, iconText) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'provider-tab';
    button.classList.toggle('active', activeView === viewId);
    button.dataset.view = viewId;

    const icon = document.createElement('span');
    icon.className = 'provider-tab-icon';
    const asset = TAB_ICON_ASSETS[viewId];
    if (asset?.mode === 'mask') {
        icon.classList.add('provider-tab-icon-mask');
        icon.style.setProperty('--provider-icon-url', `url("${asset.path}")`);
    } else {
        icon.textContent = iconText;
    }

    const label = document.createElement('span');
    label.textContent = labelText;

    button.append(icon, label);
    button.addEventListener('click', () => {
        activeView = viewId;
        updateData(lastData);
    });
    return button;
}

function renderProviders(providers) {
    const visibleProviders = activeView === 'all'
        ? providers
        : providers.filter((provider) => provider.id === activeView);
    els.cards.replaceChildren(...visibleProviders.map(createProviderCard));
    requestAnimationFrame(fitTextBars);
}

function createProviderCard(provider) {
    const card = document.createElement('section');
    card.className = `provider-card provider-${provider.id}`;
    card.dataset.provider = provider.id;

    const header = document.createElement('div');
    header.className = 'provider-card-head';

    const titleWrap = document.createElement('div');
    const title = document.createElement('h2');
    title.textContent = provider.title;
    const status = document.createElement('div');
    status.className = 'provider-status';
    status.dataset.providerStatus = provider.id;
    titleWrap.append(title, status);

    const plan = document.createElement('div');
    plan.className = 'provider-plan';
    plan.textContent = provider.profile?.plan || '';
    header.append(titleWrap, plan);
    card.append(header);

    if (provider.profile?.email) {
        const email = document.createElement('div');
        email.className = 'provider-email';
        email.textContent = provider.profile.email;
        card.append(email);
    }

    const usageRows = provider.usage || [];
    if (usageRows.length) {
        const usage = document.createElement('div');
        usage.className = 'usage-list';
        usage.replaceChildren(...usageRows.map(createUsageRow));
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

function createUsageRow(entry) {
    const row = document.createElement('div');
    row.className = 'usage-row';

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
    for (const node of document.querySelectorAll('[data-provider-status]')) {
        const providerId = node.dataset.providerStatus;
        const status = statusStateByProvider[providerId];
        if (!status) {
            node.textContent = '';
            node.classList.remove('error');
            continue;
        }

        if (status.text !== undefined) {
            node.textContent = status.text;
            node.classList.toggle('error', Boolean(status.isError));
            continue;
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

        node.textContent = parts.join(' · ');
        node.classList.toggle('error', Boolean(status.error));
    }
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
