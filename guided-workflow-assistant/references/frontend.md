# Frontend: the browser engine

A React + TypeScript reference implementation. It is written against a small *host* interface, so the same code runs inside an SPA (Inertia, Next, Remix, a plain React router) and as an island on server-rendered pages.

## Contents

1. Types
2. The host adapter
3. The watcher (`watch.ts`)
4. The provider — state, effects, actions
5. The spotlight
6. The panel — docked, never covering
7. Making room: docking the page
8. Enter moves to the next field
9. The launcher
10. Resume card and success screen
11. Accessibility checklist
12. Other frameworks

---

## 1. Types

These mirror `WorkflowManager::state()` exactly.

```ts
export type WorkflowWatch =
    | { type: 'always' }
    | { type: 'filled'; selectors: string[] }
    | { type: 'any'; selectors: string[] }
    | { type: 'minLength'; selector: string; value: number }
    | { type: 'minCount'; selector: string; value: number }
    | { type: 'checked'; selector: string };

export interface WorkflowField { selector: string; label: string; optional?: boolean }

export interface WorkflowStepState {
    key: string; title: string; description: string | null; tip: string | null;
    route: string | null; target: string | null; reveal: string | null;
    watch: WorkflowWatch | null; fields: WorkflowField[]; require_any: boolean;
    question: { prompt: string; options: { value: string; label: string; description?: string }[] } | null;
    optional: boolean; locked: boolean; requirement: string;
    guide: { pose: string; message: string | null };
    status: 'current' | 'complete' | 'upcoming';
    revisitable: boolean;
    satisfied: boolean; // the server's verdict
}

export interface WorkflowState {
    id: number; key: string; name: string; icon: string;
    status: 'active' | 'paused' | 'completed' | 'cancelled';
    current_step: string | null; steps: WorkflowStepState[];
    total_steps: number; completed_steps: number; position: number;
    entity: { type: string; id: number; label: string | null } | null;
    answers: Record<string, string>;
    success: { title: string; description: string; guide: { pose: string; message: string } } | null;
    next_actions: { label: string; url?: string; workflow?: string; primary?: boolean }[];
}

export interface WorkflowCatalogueEntry {
    key: string; name: string; description: string; category: string; icon: string;
    estimate: string; popular: boolean; keywords: string[]; steps: number; usage: number;
}
```

## 2. The host adapter

```ts
export interface WorkflowHost {
    /** The run the server says is driving the screen, fresh on every page. */
    initial: WorkflowState | null;
    /** The current address. Effects that read the page key off this, so it must change when the page does. */
    url: string;
    /** Go somewhere: a client-side visit in an SPA, a real load elsewhere. */
    visit: (url: string) => void;
    /** Where the API lives: "/admin/workflows", "/portal/workflows". */
    base: string;
}

export type RunAction = 'advance' | 'back' | 'jump' | 'answer' | 'bind' | 'transition';

export const endpoints = {
    catalogue: (h: WorkflowHost) => `${h.base}/catalogue`,
    store: (h: WorkflowHost) => h.base,
    run: (h: WorkflowHost, id: number, action?: RunAction) => (action ? `${h.base}/${id}/${action}` : `${h.base}/${id}`),
};

/** Shape-check whatever arrived under the shared name; a mix-up leaves the assistant out instead of taking the page down. */
export function asWorkflowState(value: unknown): WorkflowState | null {
    const c = value as WorkflowState | null;
    return c && Array.isArray(c.steps) && typeof c.id === 'number' ? c : null;
}
```

An Inertia host:

```ts
export function useInertiaHost(): WorkflowHost {
    const page = usePage();
    const shared = (page.props as { activeWorkflow?: unknown }).activeWorkflow;
    return useMemo(() => ({
        initial: asWorkflowState(shared),
        url: page.url,
        visit: (url: string) => router.visit(url, { preserveScroll: false }),
        base: '/admin/workflows',
    }), [shared, page.url]);
}
```

For a Next/React Router app: `initial` from a query/loader on each navigation, `url` from the router's location, `visit` from the router's `navigate`. For an island see `server-rendered-island.md`.

## 3. The watcher (`watch.ts`)

Watch rules arrive as data. The watcher reads the real DOM.

```ts
function matches(selector: string): Element[] {
    try { return Array.from(document.querySelectorAll(selector)); } catch { return []; } // a malformed selector is not a crash
}

export function findControl(selector: string): HTMLElement | null {
    return (matches(selector)[0] as HTMLElement | undefined) ?? null;
}

/** What the user has actually typed or chosen, for any kind of control. */
function valueOf(el: Element): string {
    if (el instanceof HTMLInputElement) {
        return el.type === 'checkbox' || el.type === 'radio' ? (el.checked ? 'on' : '') : el.value.trim();
    }
    if (el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) { return el.value.trim(); }
    // A wrapper (rich text editor, custom select): its own hidden input, or its text.
    const nested = el.querySelector('input, select, textarea');
    return nested ? valueOf(nested) : (el.textContent ?? '').trim();
}

const filled = (s: string) => matches(s).some((el) => valueOf(el) !== '');

export function evaluateWatch(w: WorkflowWatch | null): boolean {
    if (!w) return false;
    switch (w.type) {
        case 'always': return true;
        case 'filled': return w.selectors.length > 0 && w.selectors.every(filled);
        case 'any': return w.selectors.some(filled);
        case 'minLength': { const el = matches(w.selector)[0]; return el ? valueOf(el).length >= w.value : false; }
        case 'minCount': return matches(w.selector).length >= w.value;
        case 'checked': { const el = matches(w.selector)[0]; return el instanceof HTMLInputElement && el.checked; }
    }
}

/** Nothing on the page to watch: Continue stays available and the server decides. */
export const watchIsAdvisory = (w: WorkflowWatch | null) => w === null || w.type === 'always';

export interface FieldState extends WorkflowField { present: boolean; done: boolean }

export function readFields(fields: WorkflowField[]): FieldState[] {
    return fields.map((f) => { const el = findControl(f.selector); return { ...f, present: el !== null, done: el !== null && valueOf(el) !== '' }; });
}

export function firstEmptyField(fields: FieldState[]): FieldState | null {
    return fields.find((f) => f.present && !f.done && !f.optional) ?? fields.find((f) => f.present && !f.done) ?? null;
}

/** One box around every control of the group that is actually visible. */
export function boundsOf(selectors: string[]): DOMRect | null {
    const rects = selectors.map(findControl).filter((el): el is HTMLElement => el !== null)
        .map((el) => el.getBoundingClientRect())
        .filter((r) => r.width > 0 && r.height > 0); // inside a closed tab panel = nothing
    if (rects.length === 0) return null;
    const top = Math.min(...rects.map((r) => r.top)), left = Math.min(...rects.map((r) => r.left));
    const right = Math.max(...rects.map((r) => r.right)), bottom = Math.max(...rects.map((r) => r.bottom));
    return new DOMRect(left, top, right - left, bottom - top);
}
```

**Custom controls.** Put the `data-workflow` hook on the element whose value matters. For a custom select that renders a button and a hidden `<input name>`, put it on a wrapper containing the hidden input — `valueOf` finds nested inputs. For a file uploader, use `minCount` on the thumbnails it renders (`[data-workflow='photo-item']`).

## 4. The provider

The whole file is ~650 lines; these are the parts that matter, in order. Build it as a context provider exposing:

```ts
interface WorkflowContextValue {
    workflow: WorkflowState | null; step: WorkflowStepState | null;
    satisfied: boolean;            // page says done (OR server says done)
    fields: FieldState[];          // ticked off live
    spotlight: DOMRect | null;
    docked: boolean;               // panel open → page must make room
    busy: boolean; blockedReason: string | null;
    collapsed: boolean; setCollapsed(v: boolean): void;
    launcherOpen: boolean; setLauncherOpen(v: boolean): void;
    catalogue: WorkflowCatalogueEntry[] | null; categories: Record<string, string>;
    start(key: string, entity?: { type: string; id: number }): Promise<void>;
    resumeRun(id: number): Promise<void>;
    advance(): Promise<void>; back(): Promise<void>; jump(step: string): Promise<void>;
    answer(step: string, value: string): Promise<void>;
    pause(): Promise<void>; cancel(): Promise<void>; finish(): void;
    focusTarget(): void; focusField(selector: string): void; visit(url: string): void;
}
```

### 4.1 Navigation lives at module scope

```ts
/**
 * Pages remount their layout (and this provider) on every navigation, so a ref
 * cannot remember across one. A module variable can. The assistant moves the
 * user only when it has just done something — never merely because a page loaded.
 */
let navigationPending = false;
const requestNavigation = () => { navigationPending = true; };
```

Every action that should move the user (`start`, `advance`, `back`, `jump`, `answer`, `resumeRun`, `focusTarget` when off-page) calls `requestNavigation()` before posting. The effect:

```ts
useEffect(() => {
    if (!workflow || workflow.status !== 'active' || !step?.route) return;
    const marker = `${workflow.id}:${step.key}`;
    if (navigatedFor.current === marker || !navigationPending) return;
    navigatedFor.current = marker;
    navigationPending = false;
    if (pathOf(step.route) !== window.location.pathname) hostRef.current.visit(step.route);
}, [workflow, step]);
```

### 4.2 Keep the host in a ref

```ts
const hostRef = useRef(host);
hostRef.current = host; // callbacks never hold a host from a page already left
```

### 4.3 Fresh state on every page

```ts
useEffect(() => { setWorkflow(host.initial); setBlockedReason(null); }, [host.initial]);
```

The server re-syncs the run on every page load, so its copy is always fresher than yours.

### 4.4 Binding to the record on the page

```ts
useEffect(() => {
    if (!workflow || workflow.status !== 'active') return;
    const marker = document.querySelector<HTMLElement>('[data-workflow-entity]')?.dataset.workflowEntity ?? '';
    const [type, id] = marker.split(':');
    if (!type || !id) return;
    const attempt = `${workflow.id}:${marker}`;
    if (boundMarkers.current.has(attempt)) return;  // offered once, accepted or refused
    boundMarkers.current.add(attempt);
    let cancelled = false;
    post(endpoints.run(hostRef.current, workflow.id, 'bind'), { entity_type: type, entity_id: Number(id) })
        .then((r) => { if (!cancelled && r.workflow) setWorkflow(r.workflow); })
        .catch(() => { /* this page shows something the run is not about — leave it */ });
    return () => { cancelled = true; };
}, [workflow, host.url]);
```

Clear `boundMarkers` in `start()`.

### 4.5 Revealing a tab — once per step per page

```ts
useEffect(() => {
    if (!step?.reveal || workflow?.status !== 'active') return;
    const marker = `${workflow.id}:${step.key}:${host.url}`;
    if (revealedFor.current === marker) return;
    revealedFor.current = marker;
    const t = window.setTimeout(() => {
        const control = document.querySelector<HTMLElement>(step.reveal!);
        const open = control?.getAttribute('aria-selected') === 'true'
            || ['page', 'true', 'step'].includes(control?.getAttribute('aria-current') ?? '');
        if (control && !open) control.click();
    }, 120);
    return () => window.clearTimeout(t);
}, [step, workflow, host.url]);
```

### 4.6 Watching the page — events plus a slow tick

```ts
useEffect(() => {
    if (!workflow || workflow.status !== 'active' || !step) { setSpotlight(null); setSatisfied(false); setFields([]); return; }
    let frame = 0;
    const measure = () => {
        const read = readFields(step.fields);
        setFields(read);
        const onScreen = read.filter((f) => f.present).map((f) => f.selector);
        const bounds = onScreen.length ? boundsOf(onScreen) : null;
        const t = step.target ? findControl(step.target)?.getBoundingClientRect() : null;
        setSpotlight(bounds ?? (t && t.width > 0 && t.height > 0 ? t : null));
        // The server's verdict is ORed in: a form that cleared itself after saving must not lock Continue.
        setSatisfied(step.status === 'complete' || step.satisfied || step.optional || evaluateWatch(step.watch));
    };
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    measure();
    const events = ['input', 'change', 'scroll', 'resize', 'click', 'focusin'] as const;
    events.forEach((e) => window.addEventListener(e, schedule, true));  // capture: catches everything
    const tick = window.setInterval(schedule, 400);                     // uploads, panels opening
    return () => { cancelAnimationFrame(frame); clearInterval(tick); events.forEach((e) => window.removeEventListener(e, schedule, true)); };
}, [workflow, step, host.url]);
```

**Do not** replace this with a `MutationObserver` on `document` with `attributes: true, subtree: true`. Your own spotlight re-render mutates attributes, which triggers the observer, which re-renders… and the page fights the user's typing.

### 4.7 Actions

```ts
const run = useCallback(async (action: () => Promise<{ workflow?: WorkflowState; reason?: string | null }>) => {
    setBusy(true); setBlockedReason(null);
    try {
        const r = await action();
        if (r.workflow) setWorkflow(r.workflow);
        if (r.reason) setBlockedReason(r.reason);   // advance refused: show why
    } catch (e) {
        setBlockedReason(e instanceof Error ? e.message : 'Something went wrong.');
    } finally { setBusy(false); }
}, []);
```

`post()` sends JSON with the CSRF token and `credentials: 'same-origin'`, and throws the server's `message` on a non-2xx response. `pause`/`cancel` set `workflow` to `null` afterwards; `finish` just clears the success screen.

### 4.8 Focusing — upper third, never under the panel

```ts
const reveal = useCallback((el: HTMLElement | null) => {
    if (!el) return;
    const rect = el.getBoundingClientRect();
    // Phone: the sheet owns the bottom — aim high. Desktop: aim for the upper middle.
    const wanted = window.innerHeight * (window.innerWidth < 1024 ? 0.28 : 0.4);
    if (Math.abs(rect.top - wanted) > 80) window.scrollBy({ top: rect.top - wanted, behavior: 'smooth' });
    el.focus?.({ preventScroll: true });
}, []);

const focusTarget = useCallback(() => {
    if (step?.route && pathOf(step.route) !== window.location.pathname) {
        requestNavigation(); navigatedFor.current = null; hostRef.current.visit(step.route); return;
    }
    const gap = firstEmptyField(fields);
    const selector = gap?.selector ?? step?.fields[0]?.selector ?? step?.target;
    reveal(selector ? findControl(selector) : null);
}, [fields, step, reveal]);
```

### 4.9 Collapsed state is a per-browser convenience

Store it in `localStorage` inside `try/catch` — private windows throw. It is not part of the run.

## 5. The spotlight

One fixed element, click-through, with the dim drawn as a huge box-shadow spread:

```tsx
export function WorkflowSpotlight({ rect, visible }: { rect: DOMRect | null; visible: boolean }) {
    if (!visible || !rect || rect.width === 0 || rect.height === 0) return null;
    const P = 8;
    return (
        <div className="pointer-events-none fixed inset-0 z-[55]" aria-hidden="true">
            <div
                className="absolute rounded-lg ring-2 ring-primary transition-[top,left,width,height] duration-200 motion-reduce:transition-none"
                style={{ top: rect.top - P, left: rect.left - P, width: rect.width + P * 2, height: rect.height + P * 2,
                         boxShadow: '0 0 0 9999px rgba(8, 20, 45, 0.45)' }}
            />
        </div>
    );
}
```

`pointer-events-none` on the whole layer is essential: the user must be able to click and type inside the ring. Hide it on question steps and success screens. Keep its z-index below the panel's.

## 6. The panel — docked, never covering

Structure, top to bottom:

1. **Header**: workflow name; "Step 3 of 7 · <record label>"; collapse, pause, cancel buttons (each with `aria-label`).
2. **Progress bar** (`role="progressbar"`) and an `sr-only` `aria-live="polite"` line: "Step 3 of 7: Pricing".
3. **Scrolling body**:
   - guide character + one-sentence message (optional; shrink it to an avatar while an input has focus)
   - step title, description, tip
   - **field checklist**: one row per field, a tick when done, "Optional" tag, each row a button that focuses that field (disabled if not present)
   - a question (buttons for options) *or* "Take me to the next one (N left)" / "Show me where"
   - "Press Enter to jump to the next one" when the step has 2+ fields
   - "All steps" checklist (collapsible on phones), revisitable steps clickable
4. **Blocked message** (`role="alert"`), outside the scroll area: if the page looks right (`satisfied`) say *"That all looks right — save the page, then press Continue."*; otherwise the server's reason.
5. **Footer**: Back, and Continue (`data-workflow-continue`, disabled while `busy || !satisfied`; label "Finish" on the last step; "Checking…" while busy).
6. When not satisfied, the step's `requirement` in small text under the footer.

`remaining` counts present, required, not-done fields — but returns 0 once any field is done on a `require_any` step, so it does not nag for the alternative.

Positioning (Tailwind shown):

```
phone:   fixed inset-x-0 bottom-0 max-h-[58vh] rounded-t-2xl pb-[env(safe-area-inset-bottom)]
desktop: lg:inset-x-auto lg:right-5 lg:top-[76px] lg:bottom-5 lg:w-[336px] xl:w-[392px] lg:rounded-2xl
```

Collapsed: a pill in the corner showing name and `position/total`. Escape collapses (unless another dialog is open) — it never cancels.

## 7. Making room: docking the page

The panel is fixed; the **page** gets padding equal to the panel's column so nothing is ever underneath it:

```tsx
function AdminMain({ children }: { children: ReactNode }) {
    const { docked } = useWorkflow();
    return (
        <main className={cn('transition-[padding] duration-200 motion-reduce:transition-none',
            docked && 'pb-[62vh] lg:pb-0 lg:pr-[364px] xl:pr-[420px]')}>
            {children}
        </main>
    );
}
```

`docked = workflow?.status === 'active' && !collapsed`. On phones the bottom padding lets the last fields scroll above the sheet; `reveal()` aims at the upper third for the same reason.

The rejected alternatives, so you do not retry them: floating the panel over the page (covers fields), flipping it to whichever side the target is not on (fails as soon as a field group spans the form), auto-hiding it while typing (users lose their instructions).

## 8. Enter moves to the next field

```ts
useEffect(() => {
    if (!workflow || workflow.status !== 'active' || collapsed || fields.length < 2 || step?.question) return;
    const onKey = (e: KeyboardEvent) => {
        if (e.key !== 'Enter' || e.shiftKey || e.metaKey || e.ctrlKey || e.altKey) return;
        const active = document.activeElement as HTMLElement | null;
        if (!active || active instanceof HTMLTextAreaElement || active.isContentEditable) return; // newlines stay newlines
        const here = fields.findIndex((f) => findControl(f.selector) === active);
        if (here === -1) return;                 // not one of this step's fields: hands off
        e.preventDefault();                      // ALWAYS swallow: Enter submits forms, sometimes publishing them
        const order = [...fields.slice(here + 1), ...fields.slice(0, here)]; // wrap, excluding the current field
        const next = order.find((f) => f.present && !f.done);
        if (next) { reveal(findControl(next.selector)); return; }
        const carryOn = document.querySelector<HTMLButtonElement>('[data-workflow-continue]');
        if (carryOn && !carryOn.disabled) carryOn.focus();  // all filled: offer the button, not the form
    };
    window.addEventListener('keydown', onKey, true);  // capture, before the form sees it
    return () => window.removeEventListener('keydown', onKey, true);
}, [workflow, step, fields, collapsed, reveal]);
```

If a field is a combobox or an autocomplete that uses Enter to choose, exclude it (check `aria-expanded="true"` on the active element and return early).

## 9. The launcher

A modal command palette:

- Opened by a header button and Ctrl/Cmd+K (toggle). Fetch the catalogue the first time it opens, then keep it.
- Search box focused on open; focus returned to the previous element on close; page scroll locked while open.
- Matching: every word typed must appear somewhere in name + description + category + keywords.
- With nothing typed: a top block "You use these most" (entries with `usage > 0`, up to 4), falling back to "Popular workflows" (curated `popular`) for new users; then everything else grouped by category in config order.
- Arrow keys move through the flat list; Enter starts; Escape closes.
- Each row: icon, name, description, estimate, step count.
- An empty state that says what the user *can* do, not "No results".

## 10. Resume card and success screen

**Resume card** ("Continue your work") on the dashboard: open runs for this user, each with name, record label, "Step 3 of 7", a progress bar, and a Continue button that calls `resumeRun(id)`. The server pauses whichever run was active.

**Success screen**: replaces the panel when `status === 'completed'`. Title and description from the definition, the guide in a celebration pose (subdued for money or credit decisions), and `next_actions` as buttons: a `url` is visited through the host (use a plain `<a>` plus `visit` so it works on both hosts); a `workflow` calls `start(key)`. A close button calls `finish()`.

## 11. Accessibility checklist

- Panel: `role="region"` + `aria-label`; live region for step changes; every icon button labelled.
- Launcher: `role="dialog"` + `aria-modal`, focus trapped and returned, results as a listbox with `aria-activedescendant` or roving focus.
- Spotlight `aria-hidden`, click-through.
- Every transition guarded by `motion-reduce:`/`prefers-reduced-motion`.
- Keyboard: Ctrl/Cmd+K, Escape collapses, Enter-to-next announced in the panel, Continue reachable by Tab.
- Tap targets ≥ 40px on the phone sheet.

## 12. Other frameworks

The provider is plain state + effects; porting is mechanical.

- **Vue**: a composable with `ref`s and `watch`/`onMounted`; the module-level `navigationPending` stays a module variable.
- **Svelte**: a store; effects become `$:` blocks or `onMount`.
- **Alpine / no framework**: possible, but you will now maintain two engines if the rest of the app is React. Prefer mounting the React engine as an island (`server-rendered-island.md`).
