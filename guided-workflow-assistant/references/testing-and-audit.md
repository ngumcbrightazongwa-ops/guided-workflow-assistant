# Testing, auditing and driving it for real

Three layers, each catching what the one before misses:

1. **Automated tests** — the engine's rules, authorization, and every definition.
2. **The selector audit** — every hook every step points at, checked against real pages with real data.
3. **Driving it in a browser** — as a real user would, including walking away.

Most of the bugs in `pitfalls.md` passed layer 1. Several passed layer 2. Only layer 3 found them.

## Contents

1. Engine tests
2. Library tests (every definition)
3. Authorization and ownership tests
4. Hook tests against rendered pages
5. The selector audit
6. Driving it in a browser
7. The browser script: what to try
8. Regression tests for fixed bugs

---

## 1. Engine tests

Cover each rule once, on a tiny test definition registered only in the test:

- starting creates an active run; starting again resumes the same run (same task + record)
- starting a second task pauses the first — one active run per user
- `advance` refuses an unsatisfied required step, returns the requirement, and records `step.blocked`
- `advance` on an optional unsatisfied step moves on and records `step.skipped`
- sync: a record that already satisfies steps 1–2 opens on step 3
- the current step is persisted by `state()`, before any advance
- answering a question changes the step list; answering again re-routes
- `back` will not cross a locked step; `jump` only to revisitable steps
- completing the last step sets `completed`, `completed_at`, and returns `success` + `next_actions`
- `next_actions` naming a workflow the user may not run are dropped
- the event recorder still lets the task run when its table is missing (drop the table in the test)

## 2. Library tests (every definition)

One sweep over every registered definition, run as a user on the right side:

```php
foreach ($manager->definitions() as $key => $definition) {
    $runner = $definition->audience() === WorkflowDefinition::AUDIENCE_CUSTOMER ? $customer : $admin;
    $run = $manager->start($runner, $key);
    $state = $manager->state($run, $runner);

    $this->assertNotEmpty($state['steps'], "[$key] has no steps.");
    $this->assertNotNull($state['current_step'], "[$key] opens on nothing.");

    foreach ($state['steps'] as $step) {
        $this->assertNotSame('', trim($step['title']), "[$key] has an unnamed step.");
        // A step either asks something or points at something.
        $this->assertTrue($step['question'] !== null || $step['target'] !== null || $step['fields'] !== [],
            "[$key::{$step['key']}] neither asks nor points at anything.");
    }
    $manager->cancel($run);
}
```

Also: step keys unique per definition across every branch (answer each option and collect keys); every `nextActions` workflow key exists; each role's catalogue contains what it should and nothing it should not.

## 3. Authorization and ownership tests

For each audience boundary and each customer definition:

- a customer calling the staff routes → 403; staff calling the customer routes → 403
- a customer's catalogue contains only customer workflows; staff only staff (and only what their role permits)
- `relevantTo`: a customer with nothing applicable is offered nothing, and the island/launcher button does not render
- start with **another customer's record ID** → refused
- bind a run to **another customer's record ID** → 403, and the run's entity is unchanged
- bind a record of a type not in `bindableTypes()` → 422
- a record of the right table but wrong subtype (an enquiry where a trade-in is expected) → refused
- evidence created **before** the run started does not complete the step; evidence after does
- a run belongs to its starter: another user of the same audience gets 403 on every run action

## 4. Hook tests against rendered pages

Render each page a step lives on **with realistic data**, in the state the step runs in, and assert the hooks are present.

```php
$html = $this->actingAs($customer)->get(route('portal.financing'))->assertOk()->getContent();
foreach (['customer-schedule', 'customer-proof-form', 'customer-proof-amount', 'customer-proof-file'] as $hook) {
    $this->assertStringContainsString("data-workflow=\"$hook\"", $html, "Missing hook [$hook].");
}
$this->assertStringContainsString('data-workflow-entity="invoice:'.$invoice->id.'"', $html);
```

- **Tab-gated content**: drive the tab through the framework, not just the default render. With Livewire: `Livewire::actingAs($u)->test(OrderShowPage::class, ['order' => $o])->call('setTab', 'payment')->assertSeeHtml('data-workflow="customer-order-payment"')`.
- **Conditional branches**: create the data that puts the page in the branch the step expects (an application *with* an applicant, an order *with* a shipment).
- **SPA pages**: assert the Inertia props render the component that carries the hook, or better, cover them in the browser audit (§5) — server tests cannot see React markup.
- **Shared-prop collisions**: for every page component that receives its own props, assert the page still renders with an active run (§8).
- **Island JSON**: parse it, don't string-match it — `@json` escapes slashes, so `"/portal/workflows"` appears as `"\/portal\/workflows"`.

## 5. The selector audit

The single most valuable check. A selector that matches nothing is a dead highlight — the exact complaint users make first.

**Step 1 — dump every selector, grouped by page.** `scripts/dump-selectors.php` builds each definition with a blank unsaved run and prints:

```json
{
  "/admin/products/create": {
    "[data-workflow='product-name']": "add-product::basics",
    "[data-workflow='product-tab-pricing']": "add-product::pricing"
  },
  "(no route)": { … }
}
```

Routes that depend on a record come out as `(no route)` from a blank run; audit those on a real record's page.

**Step 2 — check each page in a browser** with realistic data. Open the page (logged in as the right kind of user), paste `scripts/audit-hooks.js` into the console with that page's selector list and any tabs to open:

```js
auditHooks(
  ["[data-workflow='product-name']", "[data-workflow='product-price']"],
  { tabs: ["[data-workflow='product-tab-pricing']"] }
);
```

It reports each selector as `ok` (present and visible), `hidden` (present, zero size — behind a closed tab or collapsed section), or `missing`, opening tabs one at a time.

**Step 3 — fix every `missing`.** Every `hidden` must have a `reveal` on its step, or be a field the user opens themselves (and the step should say so).

**Step 4 — keep the dump in the repo or CI**, and re-run it when pages change. A renamed hook fails nothing else.

## 6. Driving it in a browser

Use a real browser — an automation tool (Playwright, a browser MCP, Claude's browser pane) or by hand — on the dev server, logged in as a real user of each audience.

**Do not type passwords into login forms with an automation agent.** Ask the human to log in, then drive from there.

Things only a browser shows:

- the panel covering the highlighted fields at some viewport width
- the spotlight box in the wrong place after a scroll, a tab switch, or an image loading
- a step that never ticks because the control is custom (a styled select, an uploader)
- Continue locked on a step the server already considers done
- the page dragging the user back after they navigated away
- Enter submitting the form instead of moving on
- a tab being clicked over and over
- typing lag from an observer loop

Check at **desktop (≥1280px), laptop (~1024px), and phone (375px)** widths. Check dark mode if the app has one — the dim and ring must stay visible.

## 7. The browser script: what to try

For each workflow, once:

1. Open the launcher with the keyboard (Ctrl/Cmd+K), search with two words, start with Enter.
2. Confirm you are taken to the page, the tab is opened, and the **whole group** is boxed — not one input — and **not under the panel**.
3. Fill fields one by one; each ticks in the panel as you go. Change a `<select>` with the mouse; it ticks.
4. Press Enter in a field: focus moves to the next empty one; on the last, focus lands on Continue. The form does not submit.
5. Press Continue before saving: refused, with "save the page, then press Continue".
6. Save; press Continue; you move on.
7. Mid-task, navigate somewhere else yourself. You are **not** dragged back. The collapsed pill or checklist brings you back.
8. Reload. The same step is current.
9. Pause; the dashboard shows it under "Continue your work"; resume puts you back on the same step.
10. On a question step, answer; the remaining steps change. Revisit and answer differently; they change again.
11. Finish; the success screen shows sensible next actions; a "start another workflow" action works.
12. Phone width: the sheet leaves the field visible above it; the field scrolls into the upper third on focus.
13. Escape collapses, never cancels.
14. For customer workflows: try a URL/ID belonging to someone else and confirm nothing binds.

Record which steps you had to fight. Every one is either a pitfall or a missing tip.

## 8. Regression tests for fixed bugs

Every real bug fixed deserves a test that would have failed before:

- **Shared-prop collision**: render every page that has a prop named like your shared state, with an active run, and assert it renders its own data.
- **Current step persisted**: start a run, call `state()` only, assert `current_step` is stored.
- **Server satisfied flag**: a step whose record is done but whose page is blank serialises `satisfied: true`.
- **Ownership on bind**: covered in §3.
- **Evidence timing**: covered in §3.
- **Hooks on the right branch**: render with the data that selects that branch (§4).
- **Recorder failure**: drop the events table and complete a task.
