let els;
let translations = {};
let statusState = {};
let textTimerId = null;
let pinRequestPending = false;
const BAR_LENGTH = 20;

function init(config) {
    const styles = document.documentElement.style;
    for (const [key, value] of Object.entries(config.colors)) {
        styles.setProperty(`--${key.replaceAll('_', '-')}`, value);
    }

    translations = config.t;
    document.getElementById('title').textContent = translations.title;
    document.getElementById('headingAccount').textContent = translations.account;
    document.getElementById('labelEmail').textContent = translations.email;
    document.getElementById('labelPlan').textContent = translations.plan;
    document.getElementById('headingUsage').textContent = translations.usage;
    document.getElementById('headingExtraUsage').textContent = translations.extra_usage;
    document.getElementById('appVersion').textContent = config.app_version;

    els = {
        header: document.getElementById('windowHeader'),
        accountSection: document.getElementById('accountSection'),
        emailRow: document.getElementById('emailRow'),
        emailValue: document.getElementById('emailValue'),
        planRow: document.getElementById('planRow'),
        planValue: document.getElementById('planValue'),
        usageSection: document.getElementById('usageSection'),
        usageRows: document.getElementById('usageRows'),
        extraSection: document.getElementById('extraSection'),
        extraRow: document.getElementById('extraRow'),
        statusSection: document.getElementById('statusSection'),
        statusText: document.getElementById('statusText'),
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
    const hasProfile = Boolean(data.profile);
    els.accountSection.classList.toggle('visible', hasProfile);
    if (hasProfile) {
        els.emailValue.textContent = data.profile.email;
        els.emailRow.style.display = data.profile.email ? '' : 'none';
        els.planValue.textContent = data.profile.plan;
        els.planRow.style.display = data.profile.plan ? '' : 'none';
    }

    const hasUsage = Boolean(data.usage?.length);
    els.usageSection.classList.toggle('visible', hasUsage);
    if (hasUsage) {
        els.usageRows.replaceChildren(...data.usage.map(createUsageRow));
    } else {
        els.usageRows.replaceChildren();
    }

    const hasExtra = Boolean(data.extra);
    els.extraSection.classList.toggle('visible', hasExtra);
    if (hasExtra) {
        els.extraRow.replaceChildren(createUsageRow({
            label: translations.extra_usage,
            pct_text: data.extra.pct_text,
            tone: data.extra.tone,
            bar_text: data.extra.bar_text,
            reset_text: data.extra.spent_text,
        }));
    } else {
        els.extraRow.replaceChildren();
    }

    requestAnimationFrame(fitTextBars);
    updateStatus(data.status);
}

function createUsageRow(entry) {
    const row = document.createElement('div');
    row.className = 'usage-row';

    const head = document.createElement('div');
    head.className = 'usage-head';

    const label = document.createElement('span');
    label.className = 'usage-label';
    label.textContent = entry.label;

    const percent = document.createElement('span');
    percent.className = `usage-pct tone-${entry.tone}`;
    percent.textContent = entry.pct_text;

    const bar = createTextBar(entry.bar_text, entry.tone);

    head.append(label, percent);
    row.append(head, bar);

    if (entry.reset_text) {
        const reset = document.createElement('div');
        reset.className = 'reset-text';
        reset.textContent = entry.reset_text;
        row.append(reset);
    }

    return row;
}

function createTextBar(barText, tone) {
    const bar = document.createElement('div');
    bar.className = `text-bar tone-${tone}`;
    const inner = document.createElement('div');
    inner.className = 'text-bar-inner';

    const normalizedBar = (barText || '').padEnd(BAR_LENGTH, '░').slice(0, BAR_LENGTH);

    const track = document.createElement('span');
    track.className = 'text-bar-track';
    track.textContent = '░'.repeat(BAR_LENGTH);

    const fill = document.createElement('span');
    fill.className = 'text-bar-fill';
    fill.textContent = normalizedBar.replaceAll('░', ' ');

    inner.append(track, fill);
    bar.append(inner);

    return bar;
}

function fitTextBars() {
    for (const bar of document.querySelectorAll('.text-bar')) {
        const inner = bar.querySelector('.text-bar-inner');
        const track = bar.querySelector('.text-bar-track');
        const fill = bar.querySelector('.text-bar-fill');
        if (!inner || !track || !fill) {
            continue;
        }

        track.style.transform = 'translateY(-50%)';
        fill.style.transform = 'translateY(-50%)';

        const naturalWidth = track.scrollWidth;
        const availableWidth = inner.clientWidth;
        if (!naturalWidth || !availableWidth) {
            continue;
        }

        const scale = availableWidth / naturalWidth;
        const transform = `translateY(-50%) scaleX(${scale})`;
        track.style.transform = transform;
        fill.style.transform = transform;
    }
}

function updateStatus(status) {
    if (textTimerId) {
        clearInterval(textTimerId);
        textTimerId = null;
    }

    if (!status) {
        els.statusSection.classList.remove('visible');
        return;
    }

    els.statusSection.classList.add('visible');

    if (status.last_success_time !== undefined) {
        statusState = {
            lastSuccessTime: status.last_success_time,
            nextPollTime: status.next_poll_time,
            refreshing: status.refreshing,
            error: status.error,
        };
        els.statusSection.classList.toggle('error', Boolean(status.error));
        tickStatusText();
        textTimerId = setInterval(tickStatusText, 1000);
        return;
    }

    statusState = {};
    els.statusText.textContent = status.text || '';
    els.statusSection.classList.toggle('error', Boolean(status.is_error));
}

function tickStatusText() {
    if (!statusState.lastSuccessTime) {
        return;
    }

    const now = Date.now() / 1000;
    const secondsAgo = Math.max(0, Math.floor(now - statusState.lastSuccessTime));
    const isStale = Boolean(statusState.nextPollTime) && now > statusState.nextPollTime + 30;
    els.usageSection.classList.toggle('stale', isStale);
    els.extraSection.classList.toggle('stale', isStale);

    const parts = [formatDuration(secondsAgo)];

    if (statusState.refreshing) {
        parts.push(translations.status_refreshing);
    } else if (statusState.error) {
        parts.push(statusState.error);
    } else if (secondsAgo >= 60 && statusState.nextPollTime) {
        const secondsUntil = Math.max(0, Math.floor(statusState.nextPollTime - now));
        if (secondsUntil > 0) {
            parts.push(
                translations.status_next_update.replace('{duration}', formatCountdown(secondsUntil)),
            );
        }
    }

    els.statusText.textContent = parts.join(' · ');
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
