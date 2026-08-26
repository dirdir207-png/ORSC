/**
 * @file expenses.js
 * @description API layer for bills/expenses management
 * @requires utils/formatting.js (fmt function)
 * @requires state.js (expensesDataStore, currentFundingSource)
 */

/**
 * Load expenses/bills from the API
 * @param {boolean} forceRefresh - If true, bypass cache and force refresh
 */
function loadExpenses(forceRefresh = false) {
    const url = forceRefresh ? '/api/expenses?refresh=true' : '/api/expenses';
    fetch(url).then(res => res.json()).then(data => {
        if(data.error) return;
        updateAllMath(data.summary.totalReserved || 0);
        expensesDataStore = data.expenses;

        // Store the source for later use in Delete Logic
        currentFundingSource = data.summary.fundingSource || "Checking";

        const nextDate = new Date(data.summary.nextFundingDate).toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric'});
        const summaryText = `Next Funding: ${nextDate} • Estimated ${fmt(data.summary.estimatedFunding)}`;

        document.getElementById('exp-summary-text').innerText = summaryText;

        const heroHtml = `
            <div class="exp-hero-card" onclick="openScheduleManager()" style="cursor:pointer;" title="Manage funding schedule">
                <div class="exp-hero-col">
                    <span class="hero-lbl">Setting aside:</span>
                    <span class="hero-val">${fmt(data.summary.estimatedFunding)} on Payday 💰</span>
                </div>
                <div class="exp-hero-divider"></div>
                <div class="exp-hero-col right">
                    <span class="hero-lbl">Next Funding:</span>
                    <span class="hero-status">${nextDate}</span>
                </div>
                <span style="position:absolute;right:14px;top:50%;transform:translateY(-50%);color:var(--text-muted);font-size:18px;">⚙️</span>
            </div>

            <!-- Funding Schedule Manager (hidden until hero clicked) -->
            <div id="schedule-manager" style="display:none; margin-top:12px;"></div>
        `;
        document.getElementById('exp-hero-container').innerHTML = heroHtml;

        let html = `<div class="add-bill-row" onclick="openBillModal()">
            <span style="font-size:20px; line-height:1;">+</span> Add Bill
        </div>`;

        data.expenses.forEach((e, index) => {
            let pct = e.amount > 0 ? Math.min((e.reserved / e.amount) * 100, 100) : 0;
            const readyDate = e.reservedBy ? new Date(e.reservedBy).toLocaleDateString(undefined, {month:'short', day:'numeric'}) : 'Monthly';
            const estFunding = e.estimatedFunding > 0 ? `${fmt(e.estimatedFunding)} on Payday 💰` : 'Fully Funded';
            let statusBadge = e.paused ? `<span class="exp-funding-status">Paused</span>` : (e.reserved >= e.amount ? `<span class="exp-funding-status ready">Ready</span>` : '');
            html += `<div class="exp-item" onclick="openExpenseDetail(${index})"><div class="exp-header-line"><div class="exp-name">${e.name}</div>${statusBadge}</div><div class="exp-progress-container"><div class="exp-progress-bar" style="width: ${pct}%"></div></div><div class="exp-details"><span>${fmt(e.reserved)} of ${fmt(e.amount)} reserved • Ready by ${readyDate}</span><span class="exp-funding-text">${estFunding}</span></div></div>`;
        });
        document.getElementById('expenses-list').innerHTML = html;
    });
}

/**
 * Delete a bill/expense
 * @param {string} id - The bill ID
 * @param {string} name - The bill name
 * @param {number} reservedAmount - The currently reserved amount
 */
function deleteBill(id, name, reservedAmount) {
    let msg = `Are you sure you want to delete "${name}"?`;

    // Logic: Checking -> Safe-to-Spend, anything else -> displayName
    const destinationName = (currentFundingSource === "Checking") ? "Safe-to-Spend" : currentFundingSource;

    if (reservedAmount > 0) {
        msg += `\n\n${fmt(reservedAmount)} currently reserved will be returned to ${destinationName}.`;
    } else {
        msg += `\n\nThis will remove the bill and stop future funding.`;
    }

    appConfirm(msg, "Delete Expense", { confirmText: "Delete", danger: true }).then(confirmed => {
        if (!confirmed) return;

        const btn = document.querySelector('.btn-goal-delete');
        if(btn) {
            btn.innerText = "Deleting...";
            btn.disabled = true;
            btn.style.opacity = "0.7";
        }

        fetch('/api/delete-bill', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ id: id })
        })
        .then(res => res.json())
        .then(data => {
            if(data.error) {
                appAlert("Error: " + data.error, "Error");
                if(btn) {
                    btn.innerText = "Delete Expense";
                    btn.disabled = false;
                    btn.style.opacity = "1";
                }
            } else {
                closeModal();
                loadExpenses(true);
            }
        })
        .catch(err => {
            appAlert("System error occurred.", "Error");
            if(btn) btn.disabled = false;
        });
    });
}

/**
 * Funding Schedule Manager — opened by clicking the "Setting aside" hero.
 * Shows Beacon sufficiency projection + every bill's schedule with edit/delete.
 */
let _scheduleBeacon = null;

async function openScheduleManager() {
    haptic(8);
    const container = document.getElementById('schedule-manager');
    if (!container) return;
    const isOpen = container.style.display !== 'none';
    if (isOpen) { container.style.display = 'none'; return; }
    container.style.display = 'block';
    container.innerHTML = '<div style="padding:14px;text-align:center;color:var(--text-muted);font-size:13px;">Loading schedule & forecast…</div>';

    // Beacon projection (non-blocking failure)
    let banner = '';
    try {
        const res = await fetch('/api/beacon/reserve', { credentials: 'same-origin' });
        _scheduleBeacon = await res.json();
        if (_scheduleBeacon.available && _scheduleBeacon.projection) {
            const p = _scheduleBeacon.projection;
            if (p.verdict === 'shortfall') {
                banner = `<div style="background:#fdecea;color:#b71c1c;padding:10px 12px;border-radius:10px;margin-bottom:12px;font-size:13px;">
                    ⚠️ <strong>Beacon:</strong> at your current pace, <strong>${escHtml(p.first_missed.name)}</strong> (in ${p.first_missed.due_in_days} days) will fall short by about <strong>$${p.shortfall.toFixed(2)}</strong>. Consider raising the setting-aside amount.</div>`;
            } else if (p.verdict === 'covered') {
                banner = `<div style="background:#e8f5e9;color:#1b5e20;padding:10px 12px;border-radius:10px;margin-bottom:12px;font-size:13px;">
                    ✅ <strong>Beacon:</strong> your reserve is on pace to cover every upcoming bill.</div>`;
            } else {
                banner = `<div style="background:#e3f2fd;color:#0d47a1;padding:10px 12px;border-radius:10px;margin-bottom:12px;font-size:13px;">
                    ℹ️ <strong>Beacon:</strong> nothing upcoming needs funding right now.</div>`;
            }
        }
    } catch (e) { /* beacon optional */ }

    const bills = expensesDataStore || [];
    let rows = '';
    bills.forEach((e, index) => {
        const readyDate = e.reservedBy ? new Date(e.reservedBy).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—';
        const pct = e.amount > 0 ? Math.min(Math.round((e.reserved / e.amount) * 100), 100) : 0;
        rows += `
        <div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border-color);">
            <div style="flex:1;min-width:0;">
                <div style="font-weight:600;font-size:13px;">${escHtml(e.name)}${e.paused ? ' <span style="color:var(--text-muted);font-weight:400;">(paused)</span>' : ''}</div>
                <div style="font-size:12px;color:var(--text-muted);">${fmt(e.amount)} • ready by ${readyDate} • ${pct}% funded</div>
                <div style="height:4px;background:var(--border-color);border-radius:99px;margin-top:6px;overflow:hidden;"><div style="height:100%;width:${pct}%;background:var(--simple-blue);"></div></div>
            </div>
            <button class="sched-btn" onclick="editBillSchedule(${index})">Edit</button>
            <button class="sched-btn danger" onclick="deleteBillFromManager('${e.id}', '${escHtml(e.name).replace(/'/g, "\\'")}', ${e.reserved || 0})">Delete</button>
        </div>`;
    });

    container.innerHTML = `
        <div style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:14px;padding:16px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <strong style="font-size:14px;">Funding Schedule</strong>
                <button class="sched-btn" onclick="openBillModal(); document.getElementById('schedule-manager').scrollIntoView({behavior:'smooth'});">+ Add Bill</button>
            </div>
            ${banner}
            ${rows || '<div style="color:var(--text-muted);font-size:13px;">No bills yet — add your first one above.</div>'}
            <div style="margin-top:12px;font-size:12px;color:var(--text-muted);">Schedules pull from <strong>${escHtml(currentFundingSource || 'Checking')}</strong>. Editing recreates the bill with your new schedule.</div>
        </div>`;
}

function escHtml(t) {
    return String(t == null ? '' : t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function deleteBillFromManager(id, name, reserved) {
    deleteBill(id, name, reserved).then(() => setTimeout(() => {
        loadExpenses(true).then(() => openScheduleManagerRefresh());
    }, 800));
}

function openScheduleManagerRefresh() {
    const c = document.getElementById('schedule-manager');
    if (c && c.style.display !== 'none') {
        c.style.display = 'none';
        openScheduleManager();
    }
}

/** Edit = prefill modal; save performs delete + recreate */
function editBillSchedule(index) {
    const e = (expensesDataStore || [])[index];
    if (!e) return;
    window._editingBillId = e.id;
    window._editingBillName = e.name;
    openBillModal();
    document.getElementById('bill-name').value = e.name || '';
    document.getElementById('bill-amount').value = e.amount || '';
    const daySelect = document.getElementById('bill-day');
    const anchor = e.anchorDate ? new Date(e.anchorDate) : null;
    if (anchor && daySelect) daySelect.value = anchor.getDate();
    const freq = document.getElementById('bill-freq');
    if (freq && (e.frequencyKey || e.frequency)) freq.value = e.frequencyKey || e.frequency;
    const msg = document.getElementById('bill-message');
    if (msg) msg.innerHTML = '<div style="color:var(--simple-blue);margin-bottom:10px;">Editing “' + escHtml(e.name) + '” — saving will replace the existing bill.</div>';
}
