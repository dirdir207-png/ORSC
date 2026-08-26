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
