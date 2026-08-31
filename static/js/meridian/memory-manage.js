// meridian/memory-manage.js - asset/contract management via pipeline proposals
//
// Renders management forms (add/update/delete asset or contract) and surfaces
// pending memory proposals for owner approval. All mutations go through the
// action pipeline: management endpoints return 202 {"proposal": {id, state}}
// and the pending proposals are approved/executed via the existing
// /api/actions endpoints.

(function () {
    'use strict';

    const ASSET_CATEGORIES = [
        'electronics', 'furniture', 'appliance', 'vehicle', 'clothing', 'other',
    ];
    const CONTRACT_KINDS = [
        'insurance', 'subscription', 'lease', 'loan', 'service', 'other',
    ];

    const Management = {
        init() {
            document.querySelectorAll('[data-testid=add-asset]').forEach((button) => {
                button.addEventListener('click', () => this.openForm('asset', 'create'));
            });
            document.querySelectorAll('[data-testid=add-contract]').forEach((button) => {
                button.addEventListener('click', () => this.openForm('contract', 'create'));
            });
            this.loadPending();
        },

        async submit(kind, mode, payload) {
            const path = kind === 'asset' ? '/api/meridian/assets' : '/api/meridian/contracts';
            const method = mode === 'create' ? 'POST'
                : mode === 'delete' ? 'DELETE' : 'PATCH';
            const suffix = mode === 'create' ? '' : `/${payload.record_id}`;
            const response = await fetch(`${path}${suffix}`, {
                method,
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!response.ok) {
                const body = await response.json().catch(() => ({}));
                throw new Error((body.error && body.error.message) || `Request failed (${response.status})`);
            }
            return response.json();
        },

        section() {
            return document.querySelector('.memory-management')
                || document.querySelector('[data-workspace="accounts"]');
        },

        openForm(kind, mode, record) {
            const host = this.section();
            if (!host) return;

            const existing = host.querySelector('[data-testid=management-form]');
            if (existing) existing.remove();

            const isAsset = kind === 'asset';
            const form = document.createElement('form');
            form.setAttribute('data-testid', 'management-form');
            form.setAttribute('data-kind', kind);
            form.setAttribute('data-mode', mode);
            form.className = 'memory-management__form';

            const nameField = document.createElement('label');
            nameField.className = 'memory-management__field';
            const nameSpan = document.createElement('span');
            nameSpan.textContent = isAsset ? 'Asset name' : 'Contract name';
            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.name = 'name';
            nameInput.setAttribute('data-testid', isAsset ? 'asset-name' : 'contract-name');
            nameInput.required = true;
            if (record && record.title) nameInput.value = record.title;
            nameField.appendChild(nameSpan);
            nameField.appendChild(nameInput);

            const kindField = document.createElement('label');
            kindField.className = 'memory-management__field';
            const kindSpan = document.createElement('span');
            kindSpan.textContent = isAsset ? 'Category' : 'Kind';
            const kindSelect = document.createElement('select');
            kindSelect.name = isAsset ? 'category' : 'kind';
            kindSelect.setAttribute('data-testid', isAsset ? 'asset-category' : 'contract-kind');
            const options = isAsset ? ASSET_CATEGORIES : CONTRACT_KINDS;
            options.forEach((value) => {
                const option = document.createElement('option');
                option.value = value;
                option.textContent = value;
                kindSelect.appendChild(option);
            });
            kindField.appendChild(kindSpan);
            kindField.appendChild(kindSelect);

            const submit = document.createElement('button');
            submit.type = 'submit';
            submit.textContent = mode === 'delete' ? 'Delete' : 'Create proposal';
            submit.setAttribute('data-testid', isAsset ? 'submit-asset' : 'submit-contract');

            const cancel = document.createElement('button');
            cancel.type = 'button';
            cancel.textContent = 'Cancel';
            cancel.setAttribute('data-testid', 'cancel-management');
            cancel.addEventListener('click', () => form.remove());

            const status = document.createElement('p');
            status.className = 'memory-management__status';
            status.setAttribute('data-testid', 'management-status');
            status.hidden = true;

            form.appendChild(nameField);
            form.appendChild(kindField);
            form.appendChild(submit);
            form.appendChild(cancel);
            form.appendChild(status);

            form.addEventListener('submit', async (event) => {
                event.preventDefault();
                const payload = {
                    name: nameInput.value.trim(),
                };
                if (isAsset) {
                    payload.category = kindSelect.value;
                } else {
                    payload.kind = kindSelect.value;
                }
                if (mode === 'update' || mode === 'delete') {
                    payload.record_id = (record && record.recordId) || null;
                }
                try {
                    await this.submit(kind, mode, payload);
                    status.textContent = 'proposal created';
                    status.hidden = false;
                    submit.disabled = true;
                } catch (error) {
                    status.textContent = error.message;
                    status.hidden = false;
                }
            });

            host.appendChild(form);
        },

        async loadPending() {
            const container = document.querySelector('[data-testid=pending-memory-proposals]');
            if (!container) return;
            const response = await fetch('/api/actions/pending', { credentials: 'same-origin' });
            if (!response.ok) return;
            const body = await response.json();
            const memoryTypes = new Set([
                'create_asset', 'update_asset', 'delete_asset',
                'create_contract', 'update_contract', 'delete_contract',
            ]);
            const pending = (body.actions || body.pending || []).filter(
                (action) => memoryTypes.has(action.type)
            );
            if (pending.length === 0) {
                container.hidden = true;
                return;
            }
            container.hidden = false;
            container.innerHTML = '';
            pending.forEach((action) => {
                const row = document.createElement('div');
                row.className = 'pending-memory-proposal';
                row.setAttribute('data-testid', 'pending-memory-proposal');
                const label = document.createElement('span');
                label.textContent = `${action.type}: ${action.rationale || action.id}`;
                row.appendChild(label);
                const approve = document.createElement('button');
                approve.textContent = 'Approve';
                approve.setAttribute('data-testid', 'approve-proposal');
                approve.addEventListener('click', () => this.decide(action.id, 'approve', approve));
                row.appendChild(approve);
                const execute = document.createElement('button');
                execute.textContent = 'Execute';
                execute.setAttribute('data-testid', 'execute-proposal');
                execute.disabled = true;
                execute.addEventListener('click', () => this.decide(action.id, 'execute', execute));
                row.appendChild(execute);
                const status = document.createElement('span');
                status.className = 'memory-management__status';
                status.setAttribute('data-testid', 'pending-proposal-status');
                row.appendChild(status);
                container.appendChild(row);
            });
        },

        async decide(id, step, button) {
            const row = button && button.parentElement;
            const statusEl = row && row.querySelector('[data-testid=pending-proposal-status]');
            const execute = row && row.querySelector('[data-testid=execute-proposal]');
            try {
                const response = await fetch(`/api/actions/${id}/${step}`, {
                    method: 'POST', credentials: 'same-origin',
                });
                if (!response.ok) {
                    const body = await response.json().catch(() => ({}));
                    throw new Error((body.error && body.error.message) || `Request failed (${response.status})`);
                }
                if (step === 'approve') {
                    // Approval succeeds: the action is no longer PROPOSED, so do
                    // NOT re-fetch pending (it would wipe the row). Instead enable
                    // this row's Execute button in place.
                    if (execute) execute.disabled = false;
                    if (statusEl) statusEl.textContent = 'approved';
                } else if (step === 'execute') {
                    if (statusEl) statusEl.textContent = 'executed';
                    if (row) row.remove();
                    // The action is now applied; refresh the accounts memory region
                    // so the newly created/updated record shows up.
                    document.dispatchEvent(new CustomEvent('memory:refresh', {
                        detail: { workspace: 'accounts' },
                    }));
                }
            } catch (error) {
                if (statusEl) statusEl.textContent = error.message;
            }
        },
    };

    document.addEventListener('DOMContentLoaded', () => Management.init());
})();
