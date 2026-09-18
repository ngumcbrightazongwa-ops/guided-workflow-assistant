# Pitfalls

Every one of these happened in a real build and was found by a real user or a real browser session. Each is **symptom → cause → fix**. Read the whole list before you ship.

## Contents

- A. Highlighting and layout (1–6)
- B. Watching the page (7–12)
- C. Navigation and state (13–18)
- D. Server, data and security (19–26)
- E. Server-rendered pages (27–30)
- F. Process (31–34)

---

## A. Highlighting and layout

**1. One highlighted input tells the user nothing.**
*Symptom:* "It only highlights the title." Users could not tell which other fields belonged to the step.
*Cause:* each step targeted a single control.
*Fix:* steps declare `fields` (a group). The spotlight is the **union rect** of every present field; the panel lists them all and ticks each off.

**2. The panel covers the fields it points at.**
*Symptom:* "Most of the time the thing is blocking the field it's highlighting."
*Cause:* a floating panel over the page.
*Fix:* dock it in its own column and pad the page by the column's width while it is open (`docked`). On phones, a short bottom sheet (≤ 58vh), page padding underneath, and focus scrolls fields into the upper third.

**3. "Move it to the other side" does not work.**
*Symptom:* after flipping the panel to whichever side the target was not on, it covered the other half of a two-column field group.
*Cause:* groups span the form; there is no free side.
*Fix:* the same as 2. Do not retry this.

**4. The spotlight blocks the input it highlights.**
*Cause:* the dim overlay captured pointer events.
*Fix:* `pointer-events: none` on the whole spotlight layer. Draw the dim as a huge `box-shadow` spread from the ring so there is one element to position.

**5. The box is empty or in the wrong place behind a tab.**
*Cause:* controls in a hidden tab panel exist but measure 0×0; the rect union included them or fell back to (0,0).
*Fix:* filter out zero-size rects; if none remain, fall back to the step's `target`; if that is also zero, draw nothing.

**6. The guide character takes space while the user types.**
*Fix:* shrink it to an avatar while an input has focus. Do not hide the instructions.

## B. Watching the page

**7. The page freezes and fights the user's typing.**
*Cause:* a `MutationObserver` on `document` with `attributes: true, subtree: true`. Every React render — including the spotlight's own — mutated attributes, re-triggering measurement, re-rendering, forever.
*Fix:* listen to `input`, `change`, `scroll`, `resize`, `click`, `focusin` in capture phase, coalesced with `requestAnimationFrame`, plus a 400 ms interval as a backstop.

**8. Changing a dropdown does not update anything.**
*Symptom:* "Me using the drop down does not update it."
*Cause:* the watcher listened to `input` only; some selects fire only `change`. Custom selects keep their value in a hidden input.
*Fix:* listen to both; read nested `input/select/textarea` inside a hooked wrapper.

**9. The assistant does not notice what the user did.**
*Cause:* the step had only a server check, so the panel only knew after Continue.
*Fix:* every step with fields gets a browser `watch` (derived from the fields automatically), so Continue lights up and fields tick live.

**10. Continue stays locked on a step that is plainly done.**
*Cause:* after a successful submit the form cleared itself (or redirected to a blank form); the browser watch now fails even though the record is complete.
*Fix:* the server sends its own `satisfied` verdict with each step; the browser ORs it in.

**11. "Enter price" is repeated at someone who has entered the price.**
*Cause:* advance was refused because the form was not saved, and the panel echoed the server requirement.
*Fix:* when advance is refused but the page looks right, say *"That all looks right — save the page, then press Continue."*

**12. The watcher crashes on one bad selector.**
*Fix:* wrap `querySelectorAll` in try/catch and treat a malformed selector as "matches nothing".

## C. Navigation and state

**13. Walking away drags the user back.**
*Symptom:* navigate to another page mid-task → instantly returned to the step's page.
*Cause:* "have I already navigated for this step?" lived in a `useRef`. The layout (and provider) remounts on every SPA page, resetting the ref, so every load looked like a fresh step.
*Fix:* a **module-level** `navigationPending` flag, set only by actions that should move the user (start, advance, back, jump, answer, resume, "take me there"), consumed by the first navigation.

**14. The assistant keeps clicking a tab the user left.**
*Cause:* the reveal effect re-ran whenever the run object changed.
*Fix:* reveal once per `run:step:page`, remembered in a ref.

**15. The assistant clicks a tab that is already open, toggling it shut (or re-fetching).**
*Cause:* it checked `aria-selected` only; the tabs used `aria-current="page"`.
*Fix:* treat `aria-selected="true"` **or** `aria-current` of `page`/`true`/`step` as open.

**16. Enter submits the form (and publishes it).**
*Cause:* Enter-to-next only swallowed the key when there was a next field.
*Fix:* when focus is on one of the step's tracked fields, **always** `preventDefault`. Never in textareas or contenteditable. Only while the panel is open. Say so in the panel.

**17. Enter on the last empty field does nothing.**
*Cause:* the wrap-around list included the current field, so "next empty" was the field you were in.
*Fix:* order as `[...after, ...before]`, excluding the current field; if nothing is empty, focus Continue.

**18. Abandonment analytics never show step one.**
*Cause:* `current_step` was only written on advance; runs abandoned before their first Continue had none.
*Fix:* persist the resolved current step whenever `state()` is computed.

## D. Server, data and security

**19. Two unrelated pages go blank for everybody.**
*Cause:* the active run was shared to every page as the prop `workflow`. Two pages already had their own `workflow` prop (a finance "workflow status", a contract "workflow"). Page props overrode the shared one — or vice versa — and components received the wrong shape and threw.
*Fix:* a distinctive shared name (`activeWorkflow`) **and** a shape guard (`asWorkflowState`) before use. Add a regression test rendering those pages with an active run.

**20. A customer binds another customer's order.**
*Cause:* `bind` checked the record existed and was of an allowed type, not that it was theirs.
*Fix:* `owns(user, record)` on every definition, enforced on start-with-record and every bind (403). Use the page's own ownership rule.

**21. An old receipt finishes a new task.**
*Cause:* `completeWhen` checked "a receipt exists for this invoice".
*Fix:* "a receipt by this user created on/after `run.started_at`".

**22. A workflow filters a list by the wrong value and shows nothing.**
*Cause:* the step linked to `?type=part_exchange`; the stored value was `part-exchange`.
*Fix:* read enum values from the model/enum, never retype them. Audit list-filter routes with data present.

**23. A hook exists but never renders.**
*Cause:* the hook was placed in the template's empty-state branch; the step runs when the record has data, which renders the other branch.
*Fix:* hook tests render pages with realistic data in the state each step expects.

**24. A customer is offered a task that cannot apply to them.**
*Fix:* `relevantTo(user)`. And when a task *might* apply but is not ready, say so on the first step, before any typing.

**25. Analytics took a task down.**
*Cause:* the event listener threw (missing table after a partial deploy).
*Fix:* the recorder catches, reports, and returns.

**26. Staff start customer workflows (or the reverse) by calling the other side's API.**
*Fix:* audience on the definition *and* on the route group (route default); the controller admits only its side.

## E. Server-rendered pages

**27. The whole page 500s from a Blade `@json`.**
*Symptom:* `ParseError: Unclosed '['`.
*Cause:* `@json([...])` with a multi-line array literal — Blade's directive parser cannot handle it.
*Fix:* build the array in `@php` first, then `@json($state)`.

**28. The JSON can close its own script tag.**
*Cause:* user text containing `</script>` inside unescaped JSON.
*Fix:* an escaping encoder (`@json`, `JSON_HEX_TAG`, `json_script`, `json_escape`).

**29. A test asserting the API base in the page fails.**
*Cause:* `@json` escapes `/` as `\/`.
*Fix:* parse the JSON block in the test rather than string-matching.

**30. Hooks behind server-rendered tabs are "missing" in tests.**
*Cause:* the test rendered the default tab.
*Fix:* drive the tab via the framework (Livewire `call('setTab', …)`), and `reveal` the tab in the step.

## F. Process

**31. Everything passed; nothing worked.**
*Cause:* tests exercised the engine, not a person using it.
*Fix:* drive every workflow in a browser (see `testing-and-audit.md` §7) before calling it done.

**32. Dead highlights across the library.**
*Fix:* the selector audit, page by page, with tabs opened. Keep the dump current.

**33. Building a second engine for the other half of the app.**
*Fix:* a host adapter and an island. One engine.

**34. Temporary data left in the dev database after probing.**
*Fix:* create temp records in a script that deletes them in a `finally`; never leave probe data behind, and never probe production.
