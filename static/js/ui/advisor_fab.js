/**
 * @file advisor_fab.js
 * @description Meridian contextual advisor — in-context control (desktop right
 * rail, mobile full-height sheet). Via window.advisorSetOpen() the shell's
 * in-context [data-open-advisor] buttons open it; the floating trigger is a
 * discreet secondary entry point. Chat history persists across sessions via
 * localStorage. Proposals still require owner approval in Pending Actions; the
 * advisor can only propose.
 */

const ADVISOR_HISTORY_KEY = 'sc_advisor_history_v1';
let advisorFabHistory = [];
let advisorFabReady = false;
let advisorConfigured = null;

function _advisorLog() {
    return document.getElementById('advisor-fab-log');
}

function advisorLoadPersisted() {
    try {
        const raw = localStorage.getItem(ADVISOR_HISTORY_KEY);
        advisorFabHistory = raw ? JSON.parse(raw) : [];
        if (!Array.isArray(advisorFabHistory)) advisorFabHistory = [];
        if (advisorFabHistory.length > 20) advisorFabHistory = advisorFabHistory.slice(-20);
    } catch (e) {
        advisorFabHistory = [];
    }
    const log = _advisorLog();
    if (log) {
        log.innerHTML = '';
        if (advisorFabHistory.length === 0) {
            advisorBubble('assistant', "Hi! I'm your Crew copilot. Ask about balances, pockets, or spending — or tell me to move money and I'll draft a proposal for your approval.");
        } else {
            for (const m of advisorFabHistory) {
                if (m && m.content) advisorBubble(m.role, m.content, true);
            }
        }
    }
}

function advisorPersist() {
    try {
        localStorage.setItem(ADVISOR_HISTORY_KEY, JSON.stringify(advisorFabHistory.slice(-20)));
    } catch (e) { /* storage unavailable */ }
}

function advisorBubble(role, text, skipPersist) {
    const log = _advisorLog();
    if (!log || !text) return;
    const bubble = document.createElement('div');
    bubble.className = role === 'user'
        ? 'm-advisor-bubble m-advisor-bubble--user'
        : 'm-advisor-bubble m-advisor-bubble--assistant';
    bubble.textContent = text;
    log.appendChild(bubble);
    log.scrollTop = log.scrollHeight;
    if (!skipPersist && role !== undefined) {
        // persisted by caller for user/assistant real messages
    }
}

function advisorSetOpen(open) {
    const panel = document.getElementById('advisor-panel');
    if (!panel) return;
    const shell = window.MeridianShell || null;
    if (open) {
        if (!advisorFabReady) { advisorLoadPersisted(); advisorFabReady = true; }
        ensureAdvisorStatus();
        if (shell && typeof shell.openSheet === 'function') {
            // Reuse the shell's sheet primitive: it handles Escape, inert
            // background until the final close, and focus restore.
            shell.openSheet(panel, { modal: true });
        } else {
            panel.hidden = false;
            panel.setAttribute('data-open', '');
            panel.setAttribute('role', 'dialog');
            panel.setAttribute('aria-modal', 'true');
        }
        const input = document.getElementById('advisor-fab-input');
        if (input) input.focus();
        try { localStorage.setItem('sc_advisor_open', '1'); } catch (e) {}
        const log = _advisorLog();
        if (log) log.scrollTop = log.scrollHeight;
    } else {
        if (shell && typeof shell.closeSheet === 'function') {
            shell.closeSheet();
        } else {
            panel.hidden = true;
            panel.removeAttribute('data-open');
            panel.removeAttribute('role');
            panel.removeAttribute('aria-modal');
            const fab = document.getElementById('advisor-fab');
            if (fab && typeof fab.focus === 'function') fab.focus();
        }
        try { localStorage.setItem('sc_advisor_open', '0'); } catch (e) {}
    }
}

async function ensureAdvisorStatus() {
    const statusEl = document.getElementById('advisor-fab-status');
    if (advisorConfigured !== null && statusEl) {
        statusEl.textContent = advisorConfigured ? '' : 'not configured';
        return;
    }
    try {
        const response = await fetch('/api/advisor/status', { credentials: 'same-origin' });
        const data = await response.json();
        advisorConfigured = !!data.configured;
        if (statusEl) statusEl.textContent = advisorConfigured ? '' : 'not configured';
        if (!advisorConfigured) {
            advisorBubble('assistant', 'AI provider not configured yet.\nAdd OPENAI_API_KEY (or OPENROUTER_API_KEY) to your .env and restart.');
        }
    } catch (e) {
        if (statusEl) statusEl.textContent = 'offline';
    }
}

async function advisorFabSend() {
    const input = document.getElementById('advisor-fab-input');
    const sendBtn = document.getElementById('advisor-fab-send');
    const message = ((input && input.value) || '').trim();
    if (!message) return;

    input.value = '';
    advisorBubble('user', message);
    advisorFabHistory.push({ role: 'user', content: message });
    advisorBubble('assistant', 'Thinking…');

    if (sendBtn) sendBtn.disabled = true;
    try {
        const contextualNode = document.querySelector('[data-advisor-context]:not([hidden])');
        const isMeridian = document.querySelector('[data-meridian-shell]') !== null;
        const context = contextualNode
            ? {
                kind: contextualNode.dataset.advisorContext,
                object_id: contextualNode.dataset.objectId || 'current',
                evidence_ids: contextualNode.dataset.objectId
                    ? [`${contextualNode.dataset.advisorContext}:${contextualNode.dataset.objectId}`]
                    : [],
            }
            : { kind: 'forecast', object_id: 'current', evidence_ids: [] };
        const response = await fetch(isMeridian ? '/api/meridian/advisor' : '/api/advisor/chat', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(isMeridian
                ? { question: message, context }
                : { message, history: advisorFabHistory.slice(-10) }),
        });
        const data = await response.json();
        const log = _advisorLog();
        if (log.lastChild) log.lastChild.remove();

        let replyText;
        if (!response.ok) {
            replyText = data.error || 'Advisor error.';
        } else {
            replyText = isMeridian ? (data.answer || '') : (data.reply || '');
            const proposal = data.proposal || ((data.proposals || [])[0]);
            if (proposal) {
                replyText += `\n\nProposal drafted: ${proposal.summary || proposal.type}\nReview it before approval.`;
                if (typeof loadPendingActions === 'function') loadPendingActions();
                if (typeof haptic === 'function') haptic([15, 40, 15]);
            }
        }
        advisorBubble('assistant', replyText);
        advisorFabHistory.push({ role: 'assistant', content: replyText });
        if (advisorFabHistory.length > 20) advisorFabHistory = advisorFabHistory.slice(-20);
        advisorPersist();
    } catch (error) {
        const log = _advisorLog();
        if (log.lastChild) log.lastChild.remove();
        advisorBubble('assistant', 'Could not reach the advisor.');
    } finally {
        if (sendBtn) sendBtn.disabled = false;
    }
}

// Wire up on DOM ready
document.addEventListener('DOMContentLoaded', function () {
    const fab = document.getElementById('advisor-fab');
    const close = document.getElementById('advisor-close');
    const send = document.getElementById('advisor-fab-send');
    const input = document.getElementById('advisor-fab-input');

    if (fab) fab.addEventListener('click', () => {
        if (typeof haptic === 'function') haptic(8);
        advisorSetOpen(true);
    });
    if (close) close.addEventListener('click', () => advisorSetOpen(false));
    if (send) send.addEventListener('click', advisorFabSend);
    if (input) input.addEventListener('keydown', (e) => { if (e.key === 'Enter') advisorFabSend(); });

    let shouldOpen = false;
    try { shouldOpen = localStorage.getItem('sc_advisor_open') === '1'; } catch (e) {}
    if (shouldOpen) advisorSetOpen(true);
});
