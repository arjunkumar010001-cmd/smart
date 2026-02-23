/**
 * ============================================================
 *  SHARED UTILITIES — Smart Hiring System
 * ============================================================
 *  Single source of truth for:
 *    - XSS-safe HTML escaping  (one function, no duplicates)
 *    - Accessible modal system (focus-trap, ESC, ARIA)
 *    - Common UI helpers       (status badges, formatters)
 *
 *  Loaded BEFORE app.js, company.js, candidate.js.
 *  Everything is exposed on `window` so legacy inline
 *  `onclick` / `onchange` handlers still work.
 * ============================================================
 */

(function (window, document) {
    'use strict';

    // =================================================================
    //  1.  XSS-SAFE HTML ESCAPING  — THE ONLY ESCAPE FUNCTION
    // =================================================================

    /**
     * Escape a value for safe insertion into HTML.
     * Handles null, undefined, numbers, booleans — always returns a string.
     *
     * @param {*} text - Value to escape
     * @returns {string} HTML-entity-escaped string
     */
    function escapeHtml(text) {
        if (text === null || text === undefined) return '';
        const s = String(text);
        if (s === '') return '';
        const div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    // Short alias used in template literals
    const esc = escapeHtml;

    // =================================================================
    //  2.  ACCESSIBLE MODAL SYSTEM
    // =================================================================

    // Track currently-open modals for stack management
    const _modalStack = [];

    /**
     * Create and display an accessible modal dialog.
     *
     * Features:
     *   - `role="dialog"` + `aria-modal="true"` + `aria-labelledby`
     *   - Focus trap (Tab / Shift+Tab cycle inside modal)
     *   - ESC key closes the top-most modal
     *   - Backdrop click closes (optional)
     *   - Returns focus to the element that triggered the modal
     *
     * @param {Object} opts
     * @param {string}   opts.title        - Modal title text
     * @param {string}   opts.body         - innerHTML for the modal body
     * @param {string}  [opts.footer]      - innerHTML for the modal footer (optional)
     * @param {string}  [opts.headerStyle] - inline CSS for the header (optional)
     * @param {string}  [opts.maxWidth]    - e.g. '1000px' (default '640px')
     * @param {boolean} [opts.closeOnBackdrop=true] - close when clicking backdrop
     * @param {Function}[opts.onClose]     - callback fired when modal is closed
     * @returns {HTMLElement} The modal overlay element
     */
    function createModal(opts) {
        const {
            title = '',
            body = '',
            footer = '',
            headerStyle = '',
            maxWidth = '640px',
            closeOnBackdrop = true,
            onClose = null
        } = opts;

        // Remember which element had focus so we can restore it
        const previouslyFocused = document.activeElement;

        // Build the modal DOM
        const overlay = document.createElement('div');
        overlay.className = 'modal show';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-labelledby', 'sh-modal-title');
        overlay.tabIndex = -1; // allow programmatic focus

        const titleId = 'sh-modal-title-' + Date.now();

        overlay.innerHTML = `
            <div class="modal-content" style="max-width: ${esc(maxWidth)}; max-height: 90vh;">
                <div class="modal-header" style="${headerStyle}">
                    <h3 class="modal-title" id="${titleId}">${title}</h3>
                    <button class="modal-close" aria-label="Close dialog">&times;</button>
                </div>
                <div class="modal-body" style="overflow-y: auto; max-height: calc(90vh - 140px);">
                    ${body}
                </div>
                ${footer ? `<div class="modal-footer">${footer}</div>` : ''}
            </div>
        `;

        overlay.setAttribute('aria-labelledby', titleId);

        // --- Close handler ---
        function closeModal() {
            overlay.classList.remove('show');
            overlay.classList.add('closing');
            setTimeout(() => {
                if (overlay.parentElement) overlay.parentElement.removeChild(overlay);
            }, 200);

            // Remove from stack
            const idx = _modalStack.indexOf(overlay);
            if (idx !== -1) _modalStack.splice(idx, 1);

            // Restore focus
            if (previouslyFocused && previouslyFocused.focus) {
                previouslyFocused.focus();
            }

            // Clean up listeners
            document.removeEventListener('keydown', keyHandler);

            if (typeof onClose === 'function') onClose();
        }

        // Close button
        overlay.querySelector('.modal-close').addEventListener('click', closeModal);

        // Backdrop click
        if (closeOnBackdrop) {
            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) closeModal();
            });
        }

        // --- ESC key handler ---
        function keyHandler(e) {
            if (e.key === 'Escape') {
                // Only close the top-most modal
                if (_modalStack[_modalStack.length - 1] === overlay) {
                    e.preventDefault();
                    closeModal();
                }
            }

            // Focus trap (Tab / Shift+Tab)
            if (e.key === 'Tab') {
                const focusable = overlay.querySelectorAll(
                    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
                );
                if (focusable.length === 0) return;

                const first = focusable[0];
                const last = focusable[focusable.length - 1];

                if (e.shiftKey) {
                    if (document.activeElement === first) {
                        e.preventDefault();
                        last.focus();
                    }
                } else {
                    if (document.activeElement === last) {
                        e.preventDefault();
                        first.focus();
                    }
                }
            }
        }
        document.addEventListener('keydown', keyHandler);

        // --- Mount & focus ---
        document.body.appendChild(overlay);
        _modalStack.push(overlay);

        // Move focus into modal
        const firstFocusable = overlay.querySelector(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (firstFocusable) {
            firstFocusable.focus();
        } else {
            overlay.focus();
        }

        // Expose the close function on the element for external use
        overlay._close = closeModal;

        return overlay;
    }

    /**
     * Close the top-most modal (useful from inline onclick handlers).
     */
    function closeTopModal() {
        const top = _modalStack[_modalStack.length - 1];
        if (top && top._close) top._close();
    }

    /**
     * Quick error modal — replaces the ad-hoc error modal patterns
     * scattered across the codebase.
     */
    function showErrorModal(message) {
        return createModal({
            title: 'Error',
            body: `<div class="alert alert-error">${esc(message)}</div>`,
            footer: '<button class="btn btn-secondary" onclick="closeTopModal()">Close</button>'
        });
    }

    // =================================================================
    //  3.  STATUS HELPERS
    // =================================================================

    const STATUS_MAP = {
        submitted: 'pending', applied: 'pending', review: 'pending',
        under_review: 'pending', pending: 'pending',
        shortlisted: 'shortlisted', interviewed: 'interviewed',
        hired: 'hired', rejected: 'rejected'
    };

    function normalizeStatus(status) {
        const s = (status || 'pending').toLowerCase().trim();
        return STATUS_MAP[s] || 'pending';
    }

    const STATUS_COLORS = {
        pending:      { bg: '#fef9c3', text: '#92400e', border: '#fbbf24' },
        shortlisted:  { bg: '#dbeafe', text: '#1e40af', border: '#3b82f6' },
        interviewed:  { bg: '#ede9fe', text: '#5b21b6', border: '#8b5cf6' },
        hired:        { bg: '#d1fae5', text: '#065f46', border: '#10b981' },
        rejected:     { bg: '#fee2e2', text: '#991b1b', border: '#ef4444' }
    };

    const STATUS_ICONS = {
        pending: '🟡', shortlisted: '💛', interviewed: '🟣',
        hired: '💚', rejected: '❌'
    };

    function getStatusColor(status) {
        return STATUS_COLORS[normalizeStatus(status)] || STATUS_COLORS.pending;
    }

    function getStatusIcon(status) {
        return STATUS_ICONS[normalizeStatus(status)] || '⚪';
    }

    function getScoreClass(score) {
        if (score >= 80) return 'score-high';
        if (score >= 60) return 'score-medium';
        return 'score-low';
    }

    // =================================================================
    //  4.  FORMATTERS
    // =================================================================

    /**
     * Anonymize an ID for blind-mode display.
     * e.g. "507f1f77bcf86cd799439011" → "SH-439011"
     */
    function anonymizeId(id) {
        return 'SH-' + (id || '000000').slice(-6).toUpperCase();
    }

    /**
     * Format bytes into human-readable size string.
     */
    function formatFileSize(bytes) {
        if (!bytes || bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    /**
     * Format an ISO date string or Date object into short readable form.
     */
    function formatDate(dateStr) {
        if (!dateStr) return 'N/A';
        try {
            const d = new Date(dateStr);
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch {
            return String(dateStr);
        }
    }

    // =================================================================
    //  5.  GLOBAL EXPORTS
    // =================================================================
    //  Exposed on `window` so that:
    //   - Legacy inline onclick/onchange handlers keep working
    //   - company.js, candidate.js, app.js can reference them directly
    //   - Future ES-module migration only needs to change imports

    window.escapeHtml       = escapeHtml;
    window.esc              = esc;
    window.createModal      = createModal;
    window.closeTopModal    = closeTopModal;
    window.showErrorModal   = showErrorModal;
    window.normalizeStatus  = normalizeStatus;
    window.getStatusColor   = getStatusColor;
    window.getStatusIcon    = getStatusIcon;
    window.getScoreClass    = getScoreClass;
    window.anonymizeId      = anonymizeId;
    window.formatFileSize   = formatFileSize;
    window.formatDate       = formatDate;

    console.log('✅ shared-utils.js loaded — unified escape, modal, helpers');

})(window, document);
