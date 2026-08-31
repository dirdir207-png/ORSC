// meridian/memory.js - Frontend memory integration for all four workspaces
// Renders memory items across Today, Plan, Activity, and Accounts

(function() {
    'use strict';

    // Memory items use these fields:
    //   - why_it_matters: required context for each memory item
    //   - evidence_url: internal record id routed through /api/meridian/evidence/
    //   - confidence: float 0-1 representing data quality
    //   - is_overdue / is_upcoming: urgency flags
    //   - required_approval: whether this action needs explicit owner approval
    // Workspaces: today, plan, activity, accounts

    const Memory = {
        init() {
            this.bindWorkspaceTriggers();
        },

        bindWorkspaceTriggers() {
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

            // Load for current workspace on init
            const currentWorkspace = document.querySelector('[data-current-workspace]');
            if (currentWorkspace) {
                this.loadForWorkspace(currentWorkspace.dataset.currentWorkspace);
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
            const container = document.querySelector(`[data-workspace="${workspace}"] [data-memory-region]`);
            if (!container) return;

            if (!data || !data.categories || data.categories.length === 0) {
                this.renderEmpty(workspace, container);
                return;
            }

            container.innerHTML = '';
            container.dataset.memoryState = 'populated';

            data.categories.forEach(category => {
                const categoryEl = this.renderCategory(category);
                container.appendChild(categoryEl);
            });
        },

        renderCategory(category) {
            const section = document.createElement('section');
            section.className = 'memory-category';
            section.dataset.memoryKind = category.kind;

            const header = document.createElement('header');
            header.className = 'memory-category-header';

            const title = document.createElement('h3');
            title.className = 'memory-category-title';
            title.textContent = category.title;

            const count = document.createElement('span');
            count.className = 'memory-category-count';
            count.textContent = category.count;
            count.setAttribute('aria-label', `${category.count} items`);

            header.appendChild(title);
            header.appendChild(count);
            section.appendChild(header);

            const list = document.createElement('ul');
            list.className = 'memory-category-list';
            list.setAttribute('role', 'list');

            category.items.forEach(item => {
                const itemEl = this.renderItem(item);
                list.appendChild(itemEl);
            });

            section.appendChild(list);
            return section;
        },

        renderItem(item) {
            const li = document.createElement('li');
            li.className = 'memory-item';
            li.dataset.memoryItemId = item.public_id;
            li.dataset.memoryKind = item.kind;

            if (item.is_overdue) {
                li.classList.add('memory-item--overdue');
            } else if (item.is_upcoming) {
                li.classList.add('memory-item--upcoming');
            }

            if (item.required_approval) {
                li.classList.add('memory-item--requires-approval');
            }

            const main = document.createElement('div');
            main.className = 'memory-item-main';

            const titleEl = document.createElement('h4');
            titleEl.className = 'memory-item-title';
            titleEl.textContent = item.title;
            main.appendChild(titleEl);

            const descEl = document.createElement('p');
            descEl.className = 'memory-item-description';
            descEl.textContent = item.description;
            main.appendChild(descEl);

            li.appendChild(main);

            const meta = document.createElement('div');
            meta.className = 'memory-item-meta';

            if (item.due_date) {
                const dueEl = document.createElement('span');
                dueEl.className = 'memory-item-due';
                const dueText = this.formatDueDate(item.due_date);
                dueEl.textContent = dueText;
                if (item.is_overdue) {
                    dueEl.setAttribute('aria-label', `Overdue, was due ${dueText}`);
                } else if (item.is_upcoming) {
                    dueEl.setAttribute('aria-label', `Due soon, ${dueText}`);
                }
                meta.appendChild(dueEl);
            }

            const confidenceEl = document.createElement('span');
            confidenceEl.className = 'memory-item-confidence';
            confidenceEl.textContent = `${Math.round(item.confidence * 100)}%`;
            confidenceEl.setAttribute('aria-label', `Confidence ${Math.round(item.confidence * 100)} percent`);
            meta.appendChild(confidenceEl);

            li.appendChild(meta);

            if (item.next_action) {
                const actionEl = document.createElement('div');
                actionEl.className = 'memory-item-action';
                actionEl.textContent = item.next_action;
                li.appendChild(actionEl);
            }

            if (item.evidence_url) {
                const evidenceEl = document.createElement('a');
                evidenceEl.className = 'memory-item-evidence';
                evidenceEl.href = `/api/meridian/evidence/${item.evidence_url}/content`;
                evidenceEl.textContent = 'View source';
                evidenceEl.setAttribute('aria-label', `View source for ${item.title}`);
                li.appendChild(evidenceEl);
            }

            return li;
        },

        formatDueDate(dueDate) {
            if (!dueDate) return '';
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const due = new Date(dueDate);
            due.setHours(0, 0, 0, 0);

            const diffDays = Math.round((due - today) / (1000 * 60 * 60 * 24));

            if (diffDays < 0) {
                return `${Math.abs(diffDays)}d overdue`;
            } else if (diffDays === 0) {
                return 'Today';
            } else if (diffDays === 1) {
                return 'Tomorrow';
            } else if (diffDays < 7) {
                return `In ${diffDays}d`;
            } else if (diffDays < 30) {
                const weeks = Math.round(diffDays / 7);
                return `In ${weeks}w`;
            } else {
                const months = Math.round(diffDays / 30);
                return `In ${months}mo`;
            }
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
            const container = document.querySelector(`[data-workspace="${workspace}"] [data-memory-region]`);
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
