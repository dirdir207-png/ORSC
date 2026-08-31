// meridian/memory.js - Frontend memory integration for all four workspaces
// Renders memory items across Today, Plan, Activity, and Accounts
//
// Each workspace exposes a render hook element `[data-memory-<workspace>]`
// (see the meridian partials). The memory endpoints (Task 3) return a
// per-workspace contract: {"workspace", "items"} where each item uses the
// Task 2 field contract (kind, title, why_it_matters, amount, confidence,
// urgency, evidence[]).

(function() {
    'use strict';

    const Memory = {
        init() {
            this.bindWorkspaceTriggers();
        },

        bindWorkspaceTriggers() {
            // Listen for workspace changes (shell dispatches `meridian:workspacechange`);
            // keep the legacy `workspace:changed` and `memory:refresh` events too.
            document.addEventListener('meridian:workspacechange', (event) => {
                if (event.detail && event.detail.workspace) {
                    this.loadForWorkspace(event.detail.workspace);
                }
            });

            // Listen for workspace changes
            document.addEventListener('workspace:changed', (event) => {
                if (event.detail && event.detail.workspace) {
                    this.loadForWorkspace(event.detail.workspace);
                }
            });

            // Listen for memory refresh requests
            document.addEventListener('memory:refresh', (event) => {
                if (event.detail && event.detail.workspace) {
                    this.loadForWorkspace(event.detail.workspace);
                }
            });

            // Load for current workspace on init: prefer an explicit
            // [data-current-workspace] marker, else the ?workspace= URL param,
            // else the first visible workspace section.
            const currentWorkspace = document.querySelector('[data-current-workspace]');
            if (currentWorkspace) {
                this.loadForWorkspace(currentWorkspace.dataset.currentWorkspace);
                return;
            }
            const fromUrl = new URLSearchParams(window.location.search).get('workspace');
            if (fromUrl && document.querySelector(`[data-workspace="${fromUrl}"]`)) {
                this.loadForWorkspace(fromUrl);
                return;
            }
            const visible = document.querySelector('[data-workspace-section]:not([hidden])');
            if (visible && visible.dataset.workspaceSection) {
                this.loadForWorkspace(visible.dataset.workspaceSection);
            }
        },

        async loadForWorkspace(workspace) {
            try {
                const response = await fetch(`/api/meridian/memory/${workspace}`, {
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json',
                    }
                });

                if (!response.ok) {
                    this.renderError(workspace, `Unable to load memory (${response.status})`);
                    return;
                }

                const data = await response.json();
                this.render(workspace, data);
            } catch (error) {
                console.error('Memory load error:', error);
                this.renderError(workspace, 'Unable to load memory right now');
            }
        },

        render(workspace, data) {
            const container = document.querySelector(`[data-workspace="${workspace}"] [data-memory-${workspace}]`);
            if (!container) return;
            if (!data || !data.items || data.items.length === 0) {
                this.renderEmpty(workspace, container);
                return;
            }
            container.innerHTML = '';
            const list = document.createElement('ul');
            list.className = 'memory-items';
            list.setAttribute('aria-label', `${workspace} memory items`);
            data.items.forEach(item => list.appendChild(this.renderItem(workspace, item)));
            container.appendChild(list);
        },

        renderItem(workspace, item) {
            const li = document.createElement('li');
            li.className = `memory-item memory-item--${item.urgency || 'scheduled'}`;
            li.setAttribute('data-memory-kind', item.kind);

            const title = document.createElement('strong');
            title.textContent = item.title || item.kind;
            li.appendChild(title);

            if (item.why_it_matters) {
                const why = document.createElement('p');
                why.className = 'memory-item__why';
                why.textContent = item.why_it_matters;
                li.appendChild(why);
            }
            if (item.amount !== null && item.amount !== undefined) {
                const amount = document.createElement('span');
                amount.className = 'memory-item__amount';
                amount.textContent = new Intl.NumberFormat('en-US', {
                    style: 'currency', currency: 'USD',
                }).format(item.amount);
                li.appendChild(amount);
            }
            if (item.confidence !== null && item.confidence !== undefined) {
                const confidence = document.createElement('span');
                confidence.className = 'memory-item__confidence';
                confidence.textContent = `${Math.round(item.confidence * 100)}% confidence`;
                li.appendChild(confidence);
            }
            if (Array.isArray(item.evidence) && item.evidence.length > 0) {
                const links = document.createElement('ul');
                links.className = 'memory-item__evidence';
                item.evidence.forEach(entry => {
                    const link = document.createElement('li');
                    const anchor = document.createElement('a');
                    anchor.href = `/api/meridian/evidence/${entry.id}/content`;
                    anchor.textContent = entry.span || 'evidence';
                    anchor.setAttribute('target', '_blank');
                    anchor.setAttribute('rel', 'noopener');
                    link.appendChild(anchor);
                    links.appendChild(link);
                });
                li.appendChild(links);
            }
            if (workspace === 'accounts' && (item.kind === 'asset' || item.kind === 'contract')) {
                this.appendRecordControls(li, item);
            }
            return li;
        },

        appendRecordControls(li, item) {
            // Per-record edit/delete entry points for the Accounts workspace.
            // The management forms are owned by memory-manage.js, exposed as
            // window.MeridianManagement.
            const isAsset = item.kind === 'asset';
            const kind = isAsset ? 'asset' : 'contract';
            const actions = document.createElement('div');
            actions.className = 'memory-item__actions';

            const edit = document.createElement('button');
            edit.type = 'button';
            edit.textContent = 'Edit';
            edit.setAttribute('data-testid', isAsset ? 'edit-asset' : 'edit-contract');
            edit.addEventListener('click', () => {
                window.MeridianManagement.openForm(kind, 'update', item);
            });
            actions.appendChild(edit);

            const remove = document.createElement('button');
            remove.type = 'button';
            remove.textContent = 'Delete';
            remove.setAttribute('data-testid', isAsset ? 'delete-asset' : 'delete-contract');
            remove.addEventListener('click', () => {
                window.MeridianManagement.openForm(kind, 'delete', item);
            });
            actions.appendChild(remove);

            li.appendChild(actions);
        },

        renderEmpty(workspace, container) {
            container.innerHTML = '';
            container.dataset.memoryState = 'empty';

            const empty = document.createElement('div');
            empty.className = 'memory-empty';
            empty.setAttribute('role', 'status');

            const headline = document.createElement('p');
            headline.className = 'memory-empty-headline';
            headline.textContent = 'No memory items yet';
            empty.appendChild(headline);

            const detail = document.createElement('p');
            detail.className = 'memory-empty-detail';
            detail.textContent = this.getEmptyMessage(workspace);
            empty.appendChild(detail);

            container.appendChild(empty);
        },

        getEmptyMessage(workspace) {
            const messages = {
                today: 'Contract and asset reminders will appear here when they need attention.',
                plan: 'Financial obligations and reserves will appear here when you connect accounts.',
                activity: 'Recent evidence and document activity will appear here.',
                accounts: 'Tracked assets and contracts will appear here when you add them.'
            };
            return messages[workspace] || '';
        },

        renderError(workspace, message) {
            const container = document.querySelector(`[data-workspace="${workspace}"] [data-memory-${workspace}]`);
            if (!container) return;

            container.innerHTML = '';
            container.dataset.memoryState = 'error';

            const error = document.createElement('div');
            error.className = 'memory-error';
            error.setAttribute('role', 'alert');

            const text = document.createElement('p');
            text.className = 'memory-error-text';
            text.textContent = message;
            error.appendChild(text);

            const retry = document.createElement('button');
            retry.type = 'button';
            retry.className = 'memory-error-retry';
            retry.textContent = 'Try again';
            retry.addEventListener('click', () => this.loadForWorkspace(workspace));
            error.appendChild(retry);

            container.appendChild(error);
        }
    };

    // Auto-init when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => Memory.init());
    } else {
        Memory.init();
    }

    // Expose to window for testing and external triggers
    window.MeridianMemory = Memory;
})();
