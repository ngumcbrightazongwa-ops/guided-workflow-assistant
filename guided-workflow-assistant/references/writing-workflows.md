# Writing workflows

How to author a definition, add hooks to the pages it walks through, and write guidance people actually follow.

## Contents

1. Before writing: walk the task yourself
2. Anatomy of a definition, worked example
3. Choosing what a step covers
4. Hooks: `data-workflow` and `data-workflow-entity`
5. Proving a step on the server
6. Questions and branching
7. Tasks that move between records
8. Customer workflows
9. Success screens and next actions
10. Writing the words
11. Checklist for a new workflow

---

## 1. Before writing: walk the task yourself

Open the app and do the task by hand with realistic data. Write down:

- every page visited, in order, and its route
- every tab or accordion that has to be opened
- the fields that *must* be filled, the ones that are *optional*, and groups where *one of several* is enough
- what gets saved, and when (a single save at the end? a save per tab? autosave?)
- what the record looks like afterwards — this is what `completeWhen` checks
- where you hesitated. That hesitation is the tip.

Workflows written from the code instead of from the screen point at fields that are conditionally rendered, behind a tab, or on the empty-state branch of a template — and look fine in tests.

## 2. Anatomy of a definition, worked example

A staff workflow that adds a product across a multi-tab form, binds to the product once it is created, and branches on whether to publish now.

```php
class AddProductWorkflow extends WorkflowDefinition
{
    public function key(): string { return 'add-product'; }
    public function name(): string { return 'Add a Product'; }
    public function category(): string { return 'catalogue'; }
    public function description(): string { return 'Create a product listing with photos, pricing and details, then publish it or save a draft.'; }
    public function icon(): string { return 'PackagePlus'; }
    public function ability(): ?string { return 'products.create'; }
    public function entityType(): ?string { return WorkflowEntities::PRODUCT; }
    public function estimatedMinutes(): string { return '5–8 min'; }
    public function popular(): bool { return true; }
    public function keywords(): array { return ['new', 'listing', 'item', 'stock', 'create']; }

    public function steps(WorkflowContext $context): array
    {
        $product = $context->entity();

        $steps = [
            WorkflowStep::make('basics', 'The Basics')
                ->route(fn ($c) => $this->editUrl($c) ?? route('admin.products.create', absolute: false))
                ->reveal("[data-workflow='product-tab-basics']")
                ->describe('The name customers will search for, and where the product sits in the catalogue.')
                ->tip('Lead with what people search for: brand, model, size. Leave marketing words for the description.')
                ->guide('pointing', 'Start with the name and category. Everything else hangs off these.')
                ->fields([
                    ['selector' => "[data-workflow='product-name']", 'label' => 'Name'],
                    ['selector' => "[data-workflow='product-category']", 'label' => 'Category'],
                    ['selector' => "[data-workflow='product-sku']", 'label' => 'SKU', 'optional' => true],
                ])
                ->completeWhen(fn ($c) => filled($c->entity()?->name) && $c->entity()?->category_id,
                    'Give the product a name and a category, then save.'),

            WorkflowStep::make('pricing', 'Pricing')
                ->route(fn ($c) => $this->editUrl($c))
                ->reveal("[data-workflow='product-tab-pricing']")
                ->describe('Enter the selling price, or a price label such as "Call for price" if it should not show publicly.')
                ->fields([
                    ['selector' => "[data-workflow='product-price']", 'label' => 'Price'],
                    ['selector' => "[data-workflow='product-price-label']", 'label' => 'Price label'],
                ], requireAny: true)
                ->completeWhen(fn ($c) => $c->entity()?->price > 0 || filled($c->entity()?->price_label),
                    'Enter a price or a price label, then save.'),

            WorkflowStep::make('photos', 'Photos')
                ->route(fn ($c) => $this->editUrl($c))
                ->reveal("[data-workflow='product-tab-photos']")
                ->target("[data-workflow='product-photos']")
                ->describe('Add at least three photos. The first is the one shown in listings.')
                ->watch(['type' => 'minCount', 'selector' => "[data-workflow='product-photo-item']", 'value' => 3])
                ->completeWhen(fn ($c) => $c->entity()?->photos()->count() >= 3, 'Add at least three photos.'),

            WorkflowStep::make('ready', 'Ready to Publish?')
                ->question('Should this product go live now?', [
                    ['value' => 'publish', 'label' => 'Publish it now', 'description' => 'Customers can see it straight away.'],
                    ['value' => 'draft', 'label' => 'Keep it as a draft', 'description' => 'Finish it later; nobody sees it yet.'],
                ]),
        ];

        return $context->answer('ready') === 'draft'
            ? [...$steps, $this->saveDraft()]
            : [...$steps, $this->publish()];
    }

    public function nextActions(WorkflowContext $c): array
    {
        return [
            ['label' => 'View the listing', 'url' => $c->entity()?->publicUrl(), 'primary' => true],
            ['label' => 'Add another product', 'workflow' => 'add-product'],
        ];
    }

    private function editUrl(WorkflowContext $c): ?string
    {
        $p = $c->entity();
        return $p ? route('admin.products.edit', $p, absolute: false) : null;
    }

    // saveDraft(), publish() — each a step with its own completeWhen on the record's status, ->locked()
}
```

Register it in `config/workflows.php`. That is all.

## 3. Choosing what a step covers

- **One step = one visual group the user sees as a unit.** A card, a tab, a fieldset. Not one input (too tight — the box tells them nothing about the rest), not a whole page of fifteen inputs (too loose — the checklist becomes a wall).
- **Split at saves.** If the form saves per tab, a step per tab. If it saves once at the end, the steps are sections of one form and the *last* step is "Save"; earlier steps have only a browser watch, and their `completeWhen` can check the record *or* be omitted (walked-through).
- **A read-only step** ("Check the customer's documents") has a `target`, no fields, and usually no `completeWhen`. Continue is available; the step is done once walked through.
- **Put the question where the decision is made**, not at the start. Users answer better after they have seen the record.
- **Optional steps** are for things that improve the result but are not needed. Analytics counts skips; an optional step everyone skips may not need to exist.
- **Lock** steps after an irreversible action (saved, sent, published) so Back does not suggest it can be undone.

## 4. Hooks: `data-workflow` and `data-workflow-entity`

### Naming

`data-workflow="<area>-<thing>"`, lowercase kebab: `product-name`, `product-tab-pricing`, `refund-approve-button`, `customer-proof-file`. Prefix customer-side hooks (`customer-…`) so the two audiences never collide on a shared component.

Select them in steps as `[data-workflow='product-name']`. Never select by CSS class, id or DOM position — designers change those.

### Where the hook goes

| Control | Put the hook on |
|---|---|
| `<input>`, `<select>`, `<textarea>` | the element itself |
| Custom select / combobox | a wrapper that contains its hidden `<input>` (the watcher reads nested inputs) |
| Rich text editor | its wrapper (the watcher reads its hidden input, else its text) |
| Checkbox or switch | the `<input type=checkbox>`; for a styled switch with no input, the button with `aria-checked`, and use a `target` rather than a field |
| File upload | the drop zone as `target`; each uploaded item as `…-item` for `minCount` |
| A tab | the tab trigger, with `role="tab"` and `aria-selected`, or `aria-current` |
| A section to point at | the card or fieldset |

In React components that receive props, pass it through: `<PriceInput data-workflow="product-price" … />` and spread `...rest` onto the real input.

### The entity marker

A page that shows one record declares it once:

```html
<div data-workflow-entity="product:42"> … </div>
```

The type is the short word from `WorkflowEntities`, never a class name. Put it on every page a workflow might land on after creating or opening a record: edit pages, show pages, "submitted" pages. That is the whole integration — controllers never learn that workflows exist.

### Conditional markup

If a template has an empty-state branch and a normal branch, the hook must be on the branch that renders **when the step runs**. Check with real data — see `testing-and-audit.md`. This was a real bug: the hook sat in the "no applicant yet" branch, which never renders when you are reviewing an applicant.

## 5. Proving a step on the server

`completeWhen(closure, requirement)`:

- **Check the saved record, not the request.** `$c->entity()->price > 0`, not "a form was posted".
- **For actions that create evidence** (a receipt, a note, a status change), check the evidence exists **and was created on or after `$c->run->started_at`**, by this user where that matters. Otherwise an old receipt finishes a brand-new task.
- **Match the app's own rules.** If the app considers a product "publishable" via a method, call that method. Do not reimplement it.
- **Keep closures cheap.** They run on every page load (sync) and every state computation. Avoid N+1s: load what you need once via `$c->entity()` and relationships.
- **Write the requirement as the fix, not the failure.** "Add at least three photos." — not "Photos invalid."
- **When a step cannot be done yet, say so at the first step**, before the user fills anything in: "Your account is not set up for payments yet. You can send proof here once your first statement is ready."

## 6. Questions and branching

```php
WorkflowStep::make('decision', 'Your Decision')
    ->question('What would you like to do with this application?', [
        ['value' => 'approve', 'label' => 'Approve'],
        ['value' => 'more-info', 'label' => 'Ask for more information'],
        ['value' => 'decline', 'label' => 'Decline'],
    ]);
```

Then in `steps()`:

```php
return match ($context->answer('decision')) {
    'approve' => [...$shared, $setTerms, $sendApproval],
    'decline' => [...$shared, $recordReason, $sendDecline],
    'more-info' => [...$shared, $requestDocuments],
    default => [...$shared, $placeholderForTheRest], // before answering: show that more follows
};
```

- Step keys must be **unique across all branches** — the completed list is shared.
- Before the question is answered, show at least one step after it, so the progress count does not jump from "4 of 4" to "4 of 7".
- A question can also check the record and pre-fill: if the product is already published, skip the question entirely by not including it.

## 7. Tasks that move between records

```php
public function entityType(): ?string { return WorkflowEntities::APPLICATION; }
public function bindableTypes(): array { return [WorkflowEntities::APPLICATION, WorkflowEntities::CONTRACT]; }

// in a later step
->completeWhen(fn ($c) => $c->bound(WorkflowEntities::CONTRACT)?->status === 'sent', 'Send the contract to the customer.')
```

The contract page carries `data-workflow-entity="contract:17"`; the browser binds it when the user lands there. Route closures can use `$c->bound('contract')` to send the user to the right page on resume.

## 8. Customer workflows

```php
public function audience(): string { return self::AUDIENCE_CUSTOMER; }

public function relevantTo(User $user): bool
{
    // Only offer it to people it applies to.
    return Order::query()->where('user_id', $user->id)->exists();
}

public function owns(User $user, Model $entity): bool
{
    // The same rule the page uses to decide the customer may see it.
    return $entity instanceof Order && (int) $entity->user_id === (int) $user->id;
}
```

- Customer tasks are usually **short and read-heavy**: "Where is my order?", "Send a receipt", "Check my return". Three to five steps.
- Use `reveal` generously: customer pages are often tabbed.
- If the record type is ambiguous (an enquiry vs a trade-in are both "leads"), check the subtype in `owns()` too.
- Plain tone. No celebration around payments, debts, or declines.

## 9. Success screens and next actions

- Title: past tense, specific. "Product Published", "Payment Proof Sent".
- Description: what happens next and who does it. "We will check it against the payment and email you once it has been reviewed."
- Next actions: one primary (usually "view what you made"), and at most two others — often the natural *next* workflow (`'workflow' => 'approve-refund'`). The engine drops suggestions the user cannot run.

## 10. Writing the words

Write as a capable colleague sitting beside the user.

| Field | Length | Voice |
|---|---|---|
| `name` | 2–4 words, verb first | "Approve a Refund" |
| `description` (catalogue) | one sentence | what they will have at the end |
| step `title` | 1–4 words | "Pricing", "Your Decision" |
| step `describe` | 1–2 sentences | what to do here, concretely |
| `tip` | one sentence | the thing people get wrong |
| `guide` message | one short sentence | encouraging, specific, never cute |
| `requirement` | one sentence | the fix, imperative |

Good: "Enter the selling price, or a price label like 'Call for price' if it should not show publicly."
Bad: "Enter price." / "Let's make some magic happen! ✨"

Name fields in the checklist exactly as the page labels them, so users can match the two.

## 11. Checklist for a new workflow

- [ ] Walked the task by hand with real data; noted pages, tabs, saves, hesitations.
- [ ] Every selector exists on the page **in the state the step runs in** (tab open, record present, right branch).
- [ ] Hooks added with `data-workflow`, customer ones prefixed.
- [ ] `data-workflow-entity` on every page the run lands on with a record.
- [ ] `completeWhen` checks the saved record; evidence checks are time-bounded to the run.
- [ ] Requirements read as fixes.
- [ ] `ability` set (staff) or `audience`, `relevantTo` and `owns` set (customer).
- [ ] Branches have unique step keys; progress does not jump.
- [ ] Next actions point at things the user can do.
- [ ] Added to config; the library test (every definition builds, every workflow's steps serialise) passes.
- [ ] Driven end to end in a browser, including walking away mid-task and resuming.
