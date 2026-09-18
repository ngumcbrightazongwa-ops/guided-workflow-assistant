# Server-rendered pages and a second audience

How to run the same assistant on pages that are not part of your SPA — Blade, Livewire, Rails ERB/Hotwire, Django templates, PHP — and how to add a second audience (customers beside staff) without the two ever mixing.

## Contents

1. Why an island, not a rewrite
2. The page contract
3. Building the state on the server
4. The island entry
5. Talking to the rest of the page
6. Docking a server-rendered layout
7. Livewire, Turbo and partial page updates
8. The second audience, end to end
9. Other stacks

---

## 1. Why an island, not a rewrite

The tempting move on a Blade/Alpine or Hotwire page is to rebuild the assistant in that page's own idiom. Don't. The provider, watcher, spotlight, Enter handling and panel together hold dozens of hard-won fixes (see `pitfalls.md`). A second copy drifts from the first within a month, and every fix has to land twice.

Mount the same React engine as an island instead. The only thing that differs is the **host**: where the starting run comes from, what the current URL is, how to navigate, and the API base. On a server-rendered page:

| Host field | Source |
|---|---|
| `initial` | a JSON block the page prints |
| `url` | `window.location.pathname + search` (constant while mounted — every move is a full load) |
| `visit` | `window.location.assign(url)` |
| `base` | printed in the same JSON block |

## 2. The page contract

The layout renders, only for people who have workflows:

```html
<div id="workflow-root"></div>
<script type="application/json" id="workflow-state">{"activeWorkflow":…,"openWorkflows":[…],"base":"/portal/workflows"}</script>
<script type="module" src="/build/customer-workflows.js"></script>
```

and optionally:

- `<div id="workflow-resume-slot"></div>` where a "Continue your work" card should appear (e.g. the dashboard home)
- a header button that dispatches `window.dispatchEvent(new CustomEvent('workflow:open-launcher'))`
- `<main id="main">` whose padding reacts to `data-workflow-docked="true"`
- `<meta name="csrf-token" content="…">` (the provider's `post()` reads it)

**Escape the JSON.** It contains user-supplied text (names, record labels). The JSON must not be able to contain `</script>`. Laravel's `@json` escapes `<`, `>` and `/`; `json_encode` needs `JSON_HEX_TAG`; Rails `json_escape`/`to_json` in ERB escapes `<`, `>` and `&`; Django's `json_script` filter does it for you.

## 3. Building the state on the server

One helper, computed once per request (the header and the island both ask it):

```php
final class CustomerWorkflowView
{
    private static array $cache = [];

    public static function for(?User $user): array
    {
        $empty = ['available' => false, 'activeWorkflow' => null, 'openWorkflows' => [], 'base' => ''];
        if (! $user || $user->isStaff()) { return $empty; }   // staff use the admin, never these
        if (isset(self::$cache[$user->id])) { return self::$cache[$user->id]; }

        try {
            $m = app(WorkflowManager::class);
            $active = $m->activeFor($user);
            $def = $active ? $m->find($active->workflow_key) : null;
            $open = $m->openFor($user, 3)
                ->filter(fn ($r) => ($d = $m->find($r->workflow_key)) && $m->allows($user, $d))
                ->map(fn ($r) => $m->summary($r, $user))->values()->all();

            return self::$cache[$user->id] = [
                'available' => $m->availableTo($user)->isNotEmpty() || $open !== [],
                'activeWorkflow' => $active && $def && $m->allows($user, $def) ? $m->state($active, $user) : null,
                'openWorkflows' => $open,
                'base' => route('portal.workflows.store', absolute: false),
            ];
        } catch (Throwable $e) {
            report($e);               // the page must render whether or not the assistant can
            return self::$cache[$user->id] = $empty;
        }
    }

    public static function flush(): void { self::$cache = []; } // for tests
}
```

On a long-running server (Octane, Swoole, RoadRunner) a static cache outlives the request — bind a request-scoped instance in the container instead.

The Blade component:

```blade
@php
    $view = \App\Workflows\CustomerWorkflowView::for(auth()->user());
    // Build the array first: @json cannot parse a multi-line array literal.
    $islandState = ['activeWorkflow' => $view['activeWorkflow'], 'openWorkflows' => $view['openWorkflows'], 'base' => $view['base']];
@endphp

@if($view['available'])
    <div id="workflow-root"></div>
    <script type="application/json" id="workflow-state">@json($islandState)</script>
    @vite('resources/js/customer-workflows.tsx')
@endif
```

## 4. The island entry

```tsx
interface IslandState { activeWorkflow: unknown; openWorkflows: WorkflowSummary[]; base: string }

function readState(): IslandState | null {
    const el = document.getElementById('workflow-state');
    if (!el?.textContent) return null;
    try { return JSON.parse(el.textContent); } catch { return null; }
}

function CustomerWorkflows({ state }: { state: IslandState }) {
    // Every page is a fresh load, so the host never changes while mounted.
    const [host] = useState<WorkflowHost>(() => ({
        initial: asWorkflowState(state.activeWorkflow),
        url: window.location.pathname + window.location.search,
        visit: (url) => window.location.assign(url),
        base: state.base,
    }));

    return (
        <WorkflowProvider host={host}>
            <PageBridge openWorkflows={state.openWorkflows} />
            <WorkflowAssistant />
            <WorkflowLauncher />
        </WorkflowProvider>
    );
}

const root = document.getElementById('workflow-root');
const state = readState();
if (root && state) createRoot(root).render(<CustomerWorkflows state={state} />);
```

Add the entry to your bundler (`vite.config` `input`, or a separate webpack entry). Keep its imports to the workflow components — do not drag the whole SPA in.

**Styling.** The island's components use the SPA's CSS utilities. Make sure the server-rendered layout loads a stylesheet that includes them — with Tailwind, add the component paths to the `content`/`@source` of the stylesheet the server layout uses, or import the SPA stylesheet in the island entry.

## 5. Talking to the rest of the page

The island cannot be called directly by server-rendered markup, so use DOM events and slots:

```tsx
function PageBridge({ openWorkflows }: { openWorkflows: WorkflowSummary[] }) {
    const { setLauncherOpen, docked } = useWorkflow();
    const [slot, setSlot] = useState<HTMLElement | null>(null);

    // A server-rendered button asks for the launcher by event.
    useEffect(() => {
        const open = () => setLauncherOpen(true);
        window.addEventListener('workflow:open-launcher', open);
        return () => window.removeEventListener('workflow:open-launcher', open);
    }, [setLauncherOpen]);

    // Tell the layout the panel is open, so it makes room.
    useEffect(() => {
        const main = document.getElementById('main');
        if (!main) return;
        main.dataset.workflowDocked = docked ? 'true' : 'false';
        return () => { delete main.dataset.workflowDocked; };
    }, [docked]);

    // Draw the resume card into a slot the page left for it — the same component the SPA uses.
    useEffect(() => setSlot(document.getElementById('workflow-resume-slot')), []);
    return slot ? createPortal(<WorkflowResumeCard runs={openWorkflows} />, slot) : null;
}
```

Show the header button only when `available` is true, on both desktop and mobile headers.

## 6. Docking a server-rendered layout

React cannot set classes on server-rendered `<main>`, but a data attribute can drive them. With Tailwind:

```html
<main id="main"
  class="transition-[padding] duration-200 motion-reduce:transition-none
         data-[workflow-docked=true]:pb-[62vh]
         lg:data-[workflow-docked=true]:pb-10
         lg:data-[workflow-docked=true]:pr-[364px]
         xl:data-[workflow-docked=true]:pr-[420px]">
```

Without Tailwind: `main[data-workflow-docked="true"] { padding-right: 364px }` inside the matching media query.

## 7. Livewire, Turbo and partial page updates

- **Tabs rendered by the server** (Livewire `wire:click="setTab('payment')"`, Turbo Frames): the tab button is the `reveal` control. After the click, the fields arrive a moment later; the 400 ms tick picks them up. Make sure the active tab carries `aria-selected="true"` or `aria-current="page"`, or the assistant will keep clicking it.
- **Morphing** (Livewire, Turbo 8 morph, htmx): `data-workflow` attributes survive a morph as long as they are in the server template. Never add them from JavaScript.
- **The island itself must not be morphed away.** Put `<x-workflow-island />` outside any Livewire component / Turbo Frame, directly in the layout; with Livewire add `wire:ignore` on the root if it sits inside one; with Turbo Drive, mark the root `data-turbo-permanent` or re-mount on `turbo:load`.
- **Turbo Drive navigation** is not a full load: listen for `turbo:load` and re-read the state (or render the JSON inside the page so each visit carries a fresh copy, and re-mount).
- **Test tab-gated hooks through the server framework** (e.g. Livewire's test API calling `setTab`), not only by rendering the default tab — see `testing-and-audit.md`.

## 8. The second audience, end to end

1. **Definitions declare it**: `audience(): 'customer'`. The catalogue, start, and every run action check `allows()`: customers get customer workflows only, staff get staff workflows only (plus permissions).
2. **Routes declare it**: a second route group under the customer area, every route with `->defaults('audience', 'customer')`. The controller admits only its own people through each group. A staff user calling the portal routes gets 403, and vice versa.
3. **Records are owned**: every customer definition implements `owns(user, record)` with the page's own ownership rule; the manager checks it on start-with-record and on every bind (403 on failure). Test it by binding another customer's record ID.
4. **Offer only what applies**: `relevantTo(user)` hides workflows that cannot apply ("send a payment receipt" for someone with no financing).
5. **Evidence is time-bounded** to the run's start.
6. **Hooks are namespaced**: `customer-…`, so a component used on both sides cannot satisfy the wrong audience's step.
7. **Shared layout prop**: the SPA's shared `activeWorkflow` must not be computed for customers on SPA pages meant for staff, and vice versa — gate it by both the user's kind and the request path.

## 9. Other stacks

- **Rails**: a helper builds the state; `<%= json_escape(state.to_json) %>` inside `<script type="application/json">`; mount with `jsbundling`/`vite_ruby`. Turbo notes above.
- **Django**: `{{ state|json_script:"workflow-state" }}` produces the whole script tag, escaped; mount with `django-vite` or a static bundle. CSRF from the `csrftoken` cookie — adapt `post()` to read it.
- **Plain PHP / other**: same three elements (root, JSON, bundle). Anything that can print JSON and serve a JS file can host the island.
