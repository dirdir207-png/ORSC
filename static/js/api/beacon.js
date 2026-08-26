/**
 * @file beacon.js
 * @description Beacon budget forecast card on the dashboard
 */

async function loadBeaconForecast() {
    const card = document.getElementById('beacon-card');
    if (!card) return;
    const body = document.getElementById('beacon-body');
    try {
        const response = await fetch('/api/beacon/forecast', { credentials: 'same-origin' });
        const data = await response.json();
        if (!data.available) {
            body.innerHTML = `<div style="font-size:13px;color:var(--text-muted);">📡 ${data.reason} (${data.points} points so far — check back in a few days).</div>`;
            return;
        }
        const burn = data.daily_burn;
        const burnLabel = burn < 0
            ? `Burning about <strong>$${Math.abs(burn).toFixed(2)}/day</strong>`
            : `Growing about <strong>$${burn.toFixed(2)}/day</strong>`;
        const runway = data.runway_days !== null && data.runway_days !== undefined
            ? `<div style="margin-top:6px;">⏳ At this pace, funds last <strong>${data.runway_days} days</strong>.</div>`
            : '';
        const trend = burn < 0 ? '📉' : '📈';
        body.innerHTML = `
            <div style="display:flex;gap:18px;flex-wrap:wrap;font-size:13px;">
                <div><span style="color:var(--text-muted);">Now</span><br><strong style="font-size:16px;">$${data.current_balance.toFixed(2)}</strong></div>
                <div><span style="color:var(--text-muted);">In ${data.horizon_days} days</span><br><strong style="font-size:16px;color:${data.projected_end < data.current_balance ? '#c0392b' : '#27ae60'};">$${data.projected_end.toFixed(2)}</strong></div>
                <div><span style="color:var(--text-muted);">${trend} Pace</span><br>${burnLabel}</div>
            </div>
            ${runway}
            <div style="margin-top:8px;font-size:12px;color:var(--text-muted);">Projection from the last 14 days of activity. Not advice — just math.</div>`;
    } catch (error) {
        body.innerHTML = '<div style="font-size:13px;color:var(--text-muted);">Could not load forecast.</div>';
    }
}

if (document.getElementById('beacon-card')) loadBeaconForecast();

async function loadSidebarWidgets() {
    const mini = document.getElementById('beacon-mini');
    const bills = document.getElementById('upcoming-bills-mini');
    if (mini) {
        try {
            const r = await fetch('/api/beacon/reserve', { credentials: 'same-origin' });
            const d = await r.json();
            if (d.available && d.projection) {
                const p = d.projection;
                if (p.verdict === 'shortfall') {
                    mini.innerHTML = `<span style="color:var(--alert-red,#c0392b);font-weight:600;">⚠ Shortfall ahead</span><br>${p.first_missed.name} in ${p.first_missed.due_in_days}d — short $${p.shortfall.toFixed(2)}`;
                } else if (p.verdict === 'covered') {
                    mini.innerHTML = `<span style="color:var(--success-green,#1b5e20);font-weight:600;">✓ Bills covered</span><br>Reserve on pace for all upcoming bills.`;
                } else {
                    mini.innerHTML = 'Nothing needs funding right now.';
                }
            } else {
                mini.textContent = 'Collecting data…';
            }
        } catch (e) { mini.textContent = 'Unavailable'; }
    }
    if (bills) {
        try {
            const r = await fetch('/api/expenses', { credentials: 'same-origin' });
            const d = await r.json();
            const items = (d.expenses || []).filter(e => !e.paused && (e.reserved || 0) < (e.amount || 0))
                .sort((a, b) => new Date(a.reservedBy || '9999') - new Date(b.reservedBy || '9999'))
                .slice(0, 4);
            bills.innerHTML = items.length ? items.map(e => {
                const when = e.reservedBy ? new Date(e.reservedBy).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—';
                return `<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border-color-light);">
                    <span>${e.name}</span><span style="font-weight:600;">${when}</span></div>`;
            }).join('') : 'All bills fully funded 🎉';
        } catch (e) { bills.textContent = 'Unavailable'; }
    }
}
if (document.getElementById('beacon-mini')) loadSidebarWidgets();
