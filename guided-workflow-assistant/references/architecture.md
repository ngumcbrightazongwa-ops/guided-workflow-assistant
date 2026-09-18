# Architecture

How the pieces fit, and why they are shaped this way.

## Contents

1. The moving parts
2. What is stored, and what is not
3. The life of a run
4. The two tests on every step
5. How a step is decided to be "current"
6. Branching
7. Moving between records
8. Two audiences
9. Why a host adapter

---

## 1. The moving parts

```
                 ┌──────────────────────── server ────────────────────────┐
                 │                                                         │
  config ───────▶│  Registry ──▶ Definitions (one class per task)          │
                 │                    │ steps(context)                     │
                 │                    ▼                                    │
  workflow_runs ◀┼──▶ Manager ──▶ Context (run + user + record lookups)    │
                 │      │  start / advance / back / jump / answer / bind   │
                 │      │  state(run) → JSON for the browser               │
  workflow_events◀┼── Recorder (listens to engine events, never throws)    │
                 │      │                                                  │
                 │   Controller + routes (one set per audience)            │
                 └──────┼──────────────────────────────────────────────────┘
                        │ JSON                     ▲ the run, on every page
                 ┌──────▼──────────────────────────┴───── browser ─────────┐
                 │  Host adapter  (SPA props  |  JSON block on the page)   │
                 │      │                                                  │
                 │  Provider ── watcher (reads real controls)              │
                 │      │       spotlight (box around the field group)     │
                 │      │       navigation (only after the assistant acts) │
                 │      ├── Panel (docked column / bottom sheet / pill)    │
                 │      ├── Launcher (Ctrl/Cmd+K, search, categories)      │
                 │      └── Resume card, success screen                    │
                 └─────────────────────────────────────────────────────────┘
                        ▲
         data-workflow="…" hooks and data-workflow-entity="type:id" markers
                        on the application's real pages
```

## 2. What is stored, and what is not

**Stored** on the run (`workflow_runs`): which workflow, whose run, which record (`entity_type`, `entity_id`), the current step key, status (`active`, `paused`, `completed`, `cancelled`), timestamps, and a JSON state blob holding question **answers**, the list of steps explicitly **completed**, and any **other records** the run has passed through.

**Not stored**: the list of steps, their text, their targets. These are rebuilt from the definition on every request.

This split is deliberate. A step list stored at start time would go stale the moment a question is answered, a record changes, or the workflow is edited in a deploy. Rebuilding means a run started last week follows today's definition.

**Stored separately** (`workflow_events`): an append-only trail — started, resumed, paused, completed, cancelled, and per step completed / skipped / blocked. It keeps the run id as a plain column rather than a foreign key, so cleaning up old runs does not rewrite history. This is both the audit trail and the analytics source.

## 3. The life of a run

1. **Start.** The user picks a task in the launcher (or a "next action" on a success screen). The server checks permission, checks the record is theirs if one was given, reuses an open run for the same task and record if there is one, and pauses any other active run — **one run drives the screen at a time**.
2. **Sync.** Before the first step is chosen, the engine asks each step whether the record already satisfies it, and ticks those off. A half-finished item opens on the first thing still outstanding.
3. **Navigate.** The browser receives the run. Because the assistant just acted, it navigates to the current step's route.
4. **Bind.** The page it lands on may declare `data-workflow-entity="type:id"`. If that type belongs to this workflow and the user may use that record, the run binds to it. This is how "Add product" learns which product it just created — without any controller knowing workflows exist.
5. **Reveal.** If the step names a `reveal` control (a tab), the assistant clicks it once, so the fields exist.
6. **Watch.** The browser reads the step's fields continuously: present? filled? It draws one box around the group, ticks fields in the panel, and enables Continue when the page looks done.
7. **Advance.** Continue asks the server. The server runs the step's `completeWhen` against the real record. If it fails, the run does not move and the *requirement* comes back to be shown. If it passes, the step is marked complete and the next unfinished step becomes current.
8. **Finish.** When no unfinished step remains, the run completes and the browser shows a success screen with next actions — links, or other workflows to start.

At any point the user can pause (the run waits in "Continue your work"), cancel, collapse the panel to a pill, jump back to a revisitable step, or simply navigate away — and the run is still there when they return.

## 4. The two tests on every step

| | Browser `watch` | Server `completeWhen` |
|---|---|---|
| Runs | Continuously, against the live page | On Continue, against the database |
| Purpose | Feedback: light up Continue, tick fields | Proof: may the run move on? |
| Knows about | What is typed, even unsaved | Only what is saved |
| Format | Declarative data (travels as JSON) | Code (a closure) |

They disagree in exactly one normal situation: the user has filled the form but not saved it. The browser says yes; the server says no. The panel should then say *"That all looks right — save the page, then press Continue"*, not repeat the requirement.

They disagree in one abnormal situation: the server says yes but the page says no — typically because the form cleared itself after a successful submit. The server's verdict wins: each step carries a `satisfied` flag computed server-side, and the browser ORs it into its own check. Without this, a step that is plainly done can lock Continue forever.

A step with **no** `completeWhen` is done once walked through (the user pressed Continue on it). Use that for read-only "look at this" steps. A step with no `watch` and no fields leaves Continue enabled and lets the server decide.

## 5. How a step is decided to be "current"

1. If a current step key is stored and still exists in the rebuilt list, that is current — **even if it is already satisfied**. The user stays where they are until they press Continue. (Jumping ahead the moment a field fills is disorienting.)
2. Otherwise, the first step that is not satisfied.
3. Otherwise, the last step.

Persist the resolved current step whenever state is computed, not only on advance. Otherwise a run abandoned before its first Continue has no step recorded — and "where do people give up?" silently loses the most common answer, step one.

## 6. Branching

A question step records an answer in the run's state and is then complete. Because `steps(context)` is recomputed every time, the definition simply returns a different list when it sees a different answer:

```php
$steps = [/* … shared steps …, */ $readyQuestion];

return $context->answer('ready') === 'draft'
    ? [...$steps, $saveDraftStep]
    : [...$steps, $reviewAndPublishStep];
```

Answering again (from the checklist, if revisitable) re-routes the rest of the path. Do not store the branch; store the answer.

## 7. Moving between records

Some tasks start on one record and finish on another: an approved application becomes a contract; a completed order becomes a purchase contract. The run's own `entity` is the *primary* type; others it passes through are kept in state under `bound.<type>`. A definition lists every type it passes through in `bindableTypes()`, and asks `context->bound('type')` for any of them. The browser re-binds whenever it lands on a page showing a new record, and remembers which records it has already offered so it asks only once.

## 8. Two audiences

Staff and customers each get their own workflows, never each other's. A definition declares its `audience`. The same controller serves both, but each route group carries its audience as a route default, and the controller only admits its own people (staff through the admin routes, customers through the portal routes). On top of that:

- `relevantTo(user)` hides workflows that do not apply (no payment-receipt task for someone who paid in full).
- `owns(user, record)` is enforced on start-with-record and on every bind. For staff it is usually "yes, if your role reaches it"; for customers it is "only if it is yours", matching the exact rule the page itself uses to decide ownership.

## 9. Why a host adapter

The engine needs four things from its environment: the starting run, the current address, a way to navigate, and the API base URL. In an Inertia/SPA app those come from page props and the client router. On a server-rendered page they come from a JSON block the page prints and `window.location`. Putting those four behind a tiny interface means the same provider, panel, launcher and watcher run in both — no second copy in a different framework to keep in step. See `server-rendered-island.md`.
