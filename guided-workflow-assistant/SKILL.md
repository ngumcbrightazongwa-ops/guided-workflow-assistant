---
name: guided-workflow-assistant
description: Build an in-app guided workflow assistant — a task engine that walks users through real work on the real screens, not a product tour. It navigates between pages, spotlights groups of form fields, ticks them off live, refuses to move on until the server proves a step is done, skips finished work, branches on questions, survives refreshes, and records where people get stuck. Use it whenever the user wants a "workflow assistant", "guided workflow", "task wizard across pages", "step-by-step helper", "command palette of tasks", "copilot for my dashboard" or "resume where you left off", or wants an admin panel or customer portal easier to use — even if they say "product tour" or "walkthrough" but mean completing real tasks. Also use it for a second audience (customers beside staff), for server-rendered pages (Blade, Livewire, Rails, Django), or to debug an assistant that highlights the wrong thing, covers its fields, or misses what the user did.
---

# Guided Workflow Assistant

A guided workflow assistant helps someone **finish a real task** in an app: add a product, approve a refund, send a payment receipt. It is not a tour. A tour points at buttons; this drives the work — it takes the user to the right page, opens the right tab, highlights the fields that matter, watches them fill those fields in, and will not move on until the task is actually done.

This skill captures an architecture that was built, shipped, and then broken in a dozen instructive ways by real use. The architecture is the easy part. The value is in the things that go wrong when a real person drives it — read `references/pitfalls.md` before you finish, not after.

## When this is the right tool

Build this when users repeat multi-step tasks that span pages and forms, and either get them wrong or ask for help. Do not build it for a single form (a good form is better), or for pure explanation (docs are better).

## The mental model

Everything else follows from five ideas. Keep them in mind while building; most bugs come from forgetting one.

1. **The server owns the truth, the page owns the feel.** Each step has two tests. The *browser* watches the real form controls so Continue lights up the moment the page looks right. The *server* re-checks against the real record before the run moves. A step is never complete because someone pressed Next.

2. **Workflows are data the engine interprets.** One definition class per task says what the steps are, where each happens, which controls it is about, what to say, and how to prove it is done. One engine runs all of them. Never hand-write per-workflow UI.

3. **Steps are recomputed, not stored.** Every request rebuilds the step list from the run's state. That is how a workflow branches: answer a question differently and a different list comes back. Only the answers and the current position are stored.

4. **The assistant serves the user's attention; it never competes for it.** It must never cover what it points at, never move the user unless it just did something, never fight them while they type, and never change what a key does without saying so.

5. **Everything is bound to a record and to a person.** A run belongs to whoever started it, is scoped to what their role may do, and is pointed at a specific record — which, for customers, must be *their own*.

## Build order

Build in this order. Each stage is usable on its own, and each later stage leans on the one before.

1. **Engine (server)** — run persistence, step/definition/context/manager, API routes with authorization. → `references/backend.md`
2. **Engine (browser)** — a provider behind a small *host* adapter, the page watcher, spotlight, docked panel, launcher. → `references/frontend.md`
3. **Hooks on the real pages** — stable `data-workflow` attributes on the controls steps point at, and a `data-workflow-entity` marker on pages that show a record. → `references/writing-workflows.md`
4. **The first workflow**, end to end, driven in a real browser. Do not write the second until the first survives a real user. → `references/testing-and-audit.md`
5. **The rest of the library**, then a **selector audit** of every step against the real pages.
6. **Analytics** — an event trail, and the three lists that matter: where people get stuck, where they give up, what they skip. → `references/backend.md` (Analytics)
7. **Second audience / server-rendered pages** (optional) — customers beside staff, or Blade/Livewire/Rails pages via an island. → `references/server-rendered-island.md`
8. **Guide character** (optional) — a mascot with a pose system, if the product has one. → `references/guide-character.md`

## Core contracts

These shapes are the spine. The reference files show full implementations; keep to these names and the pieces fit together.

**A step** declares:

| Field | Purpose |
|---|---|
| `key`, `title` | Stable id and human name |
| `route` | Where it happens (string or closure over context) |
| `reveal` | A control to click first — a tab, an accordion — so the target exists |
| `target` | The control or section it is about, as `[data-workflow='…']` |
| `fields` | The group of inputs it covers, each `{selector, label, optional?}` |
| `requireAny` | One field of the group is enough (e.g. price *or* price label) |
| `watch` | Declarative live check for the browser (derived from `fields` if absent) |
| `completeWhen` | Server closure proving the step against the record, plus a human *requirement* |
| `question` | A fork: `{prompt, options[]}` — the answer steers later steps |
| `optional`, `locked` | Skippable; cannot be walked back past (e.g. after saving) |
| `guide` | Pose + one short sentence for the guide character (optional) |

**A definition** declares `key`, `name`, `category`, `description`, `icon`, `ability` (permission), `audience` (staff/customer), `entityType` (+ `bindableTypes` if it moves between records), `relevantTo(user)`, `owns(user, record)`, `steps(context)`, `success(context)`, `nextActions(context)`.

**The run state** sent to the browser includes each step with `status` (current / complete / upcoming), `revisitable`, and **`satisfied`** — the server's own verdict (see pitfall "a form that clears itself").

**The host** (browser) supplies `initial` run, current `url`, `visit(url)`, and API `base`. This is what lets one engine run inside an SPA *and* on server-rendered pages.

## Non-negotiables

Each of these came from a real failure. The reasoning is in `references/pitfalls.md`.

- **Name the shared state distinctively** (`activeWorkflow`, not `workflow`) and **shape-check it** before use. A page with its own prop of the same name will otherwise shadow it and blank the page.
- **Highlight the group, not one input**, and tick fields off live. One ring on one input tells the user nothing about the rest.
- **Give the panel its own column; never float it over content.** Moving it to "the other corner" fails the moment a field group spans the form. The page reflows beside it. On phones, reserve space under the sheet and scroll fields into the upper third.
- **Only navigate when the assistant just acted.** Pages remount; memory of "already navigated" must live outside component state, or walking away drags the user back.
- **Never run a MutationObserver over the whole document's attributes.** It fires on your own renders and fights the user's typing. Use real input events plus a slow interval.
- **Open a tab once per step**, and treat `aria-current` as well as `aria-selected` as "already open".
- **When the page is right but the record is not, say "save, then continue"** — do not repeat the requirement to someone who has already met it.
- **Ship the server's `satisfied` verdict with each step** and let it unlock Continue. Forms clear after submit.
- **Check ownership on every bind, not just existence.** Otherwise guessing an ID binds someone else's record.
- **Count only evidence created after the run started.** An old receipt must not finish a new task.
- **Recording analytics must never break a task.** Swallow and report.
- **Audit every selector against real pages with real data**, including tab-gated and conditional branches. Tests with toy data miss the branch where the hook actually lives.

## Accessibility and tone

- The panel is a labelled region; progress is announced through a polite live region; Escape collapses rather than cancels; focus is returned when overlays close.
- The spotlight is click-through — it dims but never blocks the control being highlighted.
- Respect `prefers-reduced-motion` on every transition.
- If Enter moves between a step's fields, scope it tightly (only that step's tracked fields, never textareas, only while the panel is open), swallow it consistently so it never submits by surprise, and **say so in the panel**.
- Write guidance as an experienced colleague would: short, specific, practical. "Enter the selling price, or a price label like 'Call for price' if it should not show publicly" — not "Enter price." No celebration around money or credit decisions.

## Definition of done

The assistant is done when, in a real browser, a real user can: start a task from the launcher; be taken to the page; see the group highlighted and *not covered*; fill fields and watch them tick; press Continue and be refused with a useful reason when something is missing; save and move on; walk away to another page and *not* be dragged back; come back later and resume at the same step; answer a branching question and see the path change; finish and land on a success screen with sensible next actions. And an audit has confirmed every step's selectors resolve on its real page.

Read `references/testing-and-audit.md` for how to prove each of those.

## Reference files

| File | Read it when |
|---|---|
| `references/architecture.md` | Before starting — the moving parts and how data flows |
| `references/backend.md` | Building the server engine, API, authorization, analytics (Laravel reference implementation; notes for other stacks) |
| `references/frontend.md` | Building the provider, watcher, spotlight, panel, launcher (React reference implementation) |
| `references/writing-workflows.md` | Authoring a workflow and adding hooks to pages |
| `references/server-rendered-island.md` | Adding the assistant to Blade/Livewire/Rails/Django pages or a second audience |
| `references/testing-and-audit.md` | Testing, the selector audit, and driving it in a browser |
| `references/pitfalls.md` | **Before shipping.** Every real failure: symptom → cause → fix |
| `references/guide-character.md` | Adding a mascot with poses and crops (optional) |

## Scripts

- `scripts/audit-hooks.js` — paste into the browser console on a page to check a list of `data-workflow` selectors, including ones behind tabs.
- `scripts/dump-selectors.php` — a Laravel script that lists every selector every step points at, grouped by page; the input to the audit.
- `scripts/build-crops.py` — cut full-body character art into avatar/closeup/chest/half/full WebP crops (optional; needs Pillow).

---

Created by **Aneta Prime** · by [@ngumcbrightazongwa-ops](https://github.com/ngumcbrightazongwa-ops). MIT licence.
