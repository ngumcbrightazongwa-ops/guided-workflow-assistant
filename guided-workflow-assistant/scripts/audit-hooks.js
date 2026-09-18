/**
 * audit-hooks.js — check that workflow selectors resolve on the current page.
 *
 * Paste this whole file into the browser console on the page a workflow step
 * lives on (logged in, with realistic data), then call:
 *
 *   await auditHooks(
 *     ["[data-workflow='product-name']", "[data-workflow='product-price']"],
 *     { tabs: ["[data-workflow='product-tab-pricing']"] }
 *   );
 *
 * Or feed it one page's entry from dump-selectors output:
 *
 *   await auditHooks(Object.keys(dump["/admin/products/create"]), { tabs: [...] });
 *
 * For each selector it reports:
 *   ok       present and visible
 *   hidden   present but zero-size (behind a closed tab / collapsed section)
 *   missing  matches nothing
 *   invalid  not a valid CSS selector
 *
 * It first checks with the page as it is, then opens each tab in `tabs` in
 * turn (clicking it, waiting for the page to settle) and re-checks anything
 * not yet found visible. It reports which tab revealed each selector, which is
 * exactly what that step's `reveal` should be.
 *
 * Read-only apart from clicking the tabs you list. Nothing is submitted.
 */
(function () {
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    function check(selector) {
        let found;
        try {
            found = Array.from(document.querySelectorAll(selector));
        } catch (error) {
            return { status: 'invalid', count: 0 };
        }
        if (found.length === 0) {
            return { status: 'missing', count: 0 };
        }
        const visible = found.some((el) => {
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        });
        return { status: visible ? 'ok' : 'hidden', count: found.length };
    }

    function isOpen(control) {
        return control.getAttribute('aria-selected') === 'true'
            || ['page', 'true', 'step'].includes(control.getAttribute('aria-current') || '');
    }

    async function auditHooks(selectors, options = {}) {
        const tabs = options.tabs || [];
        const settle = options.settleMs ?? 600;
        const results = new Map(selectors.map((s) => [s, { selector: s, ...check(s), revealedBy: null }]));

        for (const tab of tabs) {
            const pending = [...results.values()].filter((r) => r.status !== 'ok' && r.status !== 'invalid');
            if (pending.length === 0) break;

            let control = null;
            try { control = document.querySelector(tab); } catch (e) { /* invalid */ }
            if (!control) {
                console.warn(`[audit] tab not found: ${tab}`);
                continue;
            }
            if (!isOpen(control)) {
                control.click();
                await sleep(settle);
            }
            for (const r of pending) {
                const again = check(r.selector);
                if (again.status === 'ok') {
                    results.set(r.selector, { ...r, ...again, revealedBy: tab });
                } else if (again.status === 'hidden' && r.status === 'missing') {
                    results.set(r.selector, { ...r, ...again });
                }
            }
        }

        const rows = [...results.values()];
        console.table(rows);
        const problems = rows.filter((r) => r.status !== 'ok');
        if (problems.length === 0) {
            console.log(`%c[audit] all ${rows.length} selectors resolve and are visible`, 'color: green');
        } else {
            console.log(`%c[audit] ${problems.length} of ${rows.length} need attention`, 'color: #b45309');
        }
        return rows;
    }

    window.auditHooks = auditHooks;
    console.log('[audit] ready: await auditHooks([selectors], { tabs: [tabSelectors] })');
})();
