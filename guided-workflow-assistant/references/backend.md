# Backend: the server engine

A complete reference implementation in Laravel (PHP 8.2+). The concepts carry to any stack — see "Other stacks" at the end.

## Contents

1. Tables
2. The run model
3. `WorkflowStep`
4. `WorkflowContext`
5. `WorkflowEntities` — the record allow-list
6. `WorkflowDefinition`
7. `WorkflowManager` — the engine
8. Controller and routes
9. Sharing the active run with every page
10. Events and the recorder
11. Analytics
12. Other stacks

Namespaces below are `App\Workflows\…`; adjust to taste.

---

## 1. Tables

```php
// workflow_runs — one row per attempt at a task
Schema::create('workflow_runs', function (Blueprint $table) {
    $table->id();
    $table->string('workflow_key', 64);
    $table->foreignId('user_id')->constrained()->cascadeOnDelete();
    $table->string('entity_type', 64)->nullable();   // short word, never a class name
    $table->unsignedBigInteger('entity_id')->nullable();
    $table->string('current_step', 64)->nullable();
    $table->json('state_json')->nullable();          // answers, completed_steps, bound
    $table->string('status', 16)->default('active'); // active|paused|completed|cancelled|failed
    $table->timestamp('started_at')->nullable();
    $table->timestamp('completed_at')->nullable();
    $table->timestamps();
    $table->index(['user_id', 'status']);
    $table->index(['workflow_key', 'status']);
    $table->index(['entity_type', 'entity_id']);
});

// workflow_events — append-only trail; the audit log and the analytics source
Schema::create('workflow_events', function (Blueprint $table) {
    $table->id();
    $table->unsignedBigInteger('workflow_run_id')->nullable(); // plain column on purpose
    $table->string('workflow_key', 64);
    $table->foreignId('user_id')->nullable()->constrained()->nullOnDelete();
    $table->string('event', 32);        // started|resumed|paused|completed|cancelled|step.completed|step.skipped|step.blocked
    $table->string('step', 64)->nullable();
    $table->timestamp('created_at')->nullable();
    $table->index(['workflow_key', 'event']);
    $table->index(['created_at']);
});
```

`entity_type` stores a short word (`product`, `order`), mapped to a class through an allow-list. Never store a class name that a request could influence.

## 2. The run model

```php
class WorkflowRun extends Model
{
    public const STATUS_ACTIVE = 'active';
    public const STATUS_PAUSED = 'paused';
    public const STATUS_COMPLETED = 'completed';
    public const STATUS_CANCELLED = 'cancelled';
    public const OPEN_STATUSES = [self::STATUS_ACTIVE, self::STATUS_PAUSED];

    protected $fillable = ['workflow_key', 'user_id', 'entity_type', 'entity_id', 'current_step', 'state_json', 'status', 'started_at', 'completed_at'];
    protected $casts = ['state_json' => 'array', 'entity_id' => 'integer', 'started_at' => 'datetime', 'completed_at' => 'datetime'];

    public function user(): BelongsTo { return $this->belongsTo(User::class); }
    public function scopeOpen(Builder $q): Builder { return $q->whereIn('status', self::OPEN_STATUSES); }
    public function isOpen(): bool { return in_array($this->status, self::OPEN_STATUSES, true); }

    public function state(): array { return is_array($this->state_json) ? $this->state_json : []; }
    public function stateValue(string $key, mixed $default = null): mixed { return data_get($this->state(), $key, $default); }
    public function mergeState(array $values): void { $this->state_json = array_replace($this->state(), $values); }

    /** @return list<string> */
    public function completedSteps(): array
    {
        return array_values(array_filter((array) $this->stateValue('completed_steps', []), 'is_string'));
    }

    public function markStepComplete(string $step): void
    {
        $done = $this->completedSteps();
        if (! in_array($step, $done, true)) { $done[] = $step; }
        $this->mergeState(['completed_steps' => $done]);
    }
}
```

## 3. `WorkflowStep`

A fluent value object. `toArray()` is exactly what the browser receives.

```php
class WorkflowStep
{
    private string|Closure|null $route = null;
    private ?string $target = null;       // [data-workflow='…'] the step is about
    private ?string $reveal = null;       // clicked first (a tab) so the target exists
    private ?string $description = null;
    private ?string $tip = null;
    private string $pose = 'pointing';    // guide character pose (optional feature)
    private ?string $message = null;      // one short sentence in the guide's voice
    private ?array $watch = null;         // explicit browser check; else derived from fields
    private array $fields = [];           // [{selector, label, optional?}]
    private bool $requireAny = false;     // one field of the group is enough
    private ?Closure $completeWhen = null;
    private string $requirement = 'This step is not finished yet.';
    private ?array $question = null;      // {prompt, options:[{value,label,description?}]}
    private bool $optional = false;
    private bool $locked = false;         // cannot be stepped back past

    private function __construct(public readonly string $key, public readonly string $title) {}
    public static function make(string $key, string $title): self { return new self($key, $title); }

    public function route(string|Closure $r): self { $this->route = $r; return $this; }
    public function target(string $t): self { $this->target = $t; return $this; }
    public function reveal(string $r): self { $this->reveal = $r; return $this; }
    public function describe(string $d): self { $this->description = $d; return $this; }
    public function tip(string $t): self { $this->tip = $t; return $this; }
    public function guide(string $pose, string $message): self { $this->pose = $pose; $this->message = $message; return $this; }
    public function watch(array $rule): self { $this->watch = $rule; return $this; }
    public function fields(array $fields, bool $requireAny = false): self { $this->fields = $fields; $this->requireAny = $requireAny; return $this; }
    public function completeWhen(Closure $check, string $requirement): self { $this->completeWhen = $check; $this->requirement = $requirement; return $this; }
    public function question(string $prompt, array $options): self { $this->question = compact('prompt', 'options'); return $this; }
    public function optional(bool $o = true): self { $this->optional = $o; return $this; }
    public function locked(bool $l = true): self { $this->locked = $l; return $this; }

    public function isOptional(): bool { return $this->optional; }
    public function isLocked(): bool { return $this->locked; }
    public function isQuestion(): bool { return $this->question !== null; }
    public function requirement(): string { return $this->requirement; }

    public function resolveRoute(WorkflowContext $c): ?string
    {
        return $this->route instanceof Closure ? ($this->route)($c) : $this->route;
    }

    /** Has the user done this? A question needs an answer; a step without a test needs walking through. */
    public function isSatisfied(WorkflowContext $c): bool
    {
        if ($this->question !== null) { return $c->answer($this->key) !== null; }
        if ($this->completeWhen === null) { return $c->hasCompleted($this->key); }
        return (bool) ($this->completeWhen)($c);
    }

    public function toArray(WorkflowContext $c): array
    {
        return [
            'key' => $this->key, 'title' => $this->title,
            'description' => $this->description, 'tip' => $this->tip,
            'route' => $this->resolveRoute($c),
            'target' => $this->target, 'reveal' => $this->reveal,
            'watch' => $this->watch ?? $this->watchFromFields(),
            'fields' => $this->fields, 'require_any' => $this->requireAny,
            'question' => $this->question,
            'optional' => $this->optional, 'locked' => $this->locked,
            'requirement' => $this->requirement,
            'guide' => ['pose' => $this->pose, 'message' => $this->message],
        ];
    }

    /** A step with fields already says what to watch; do not make authors write it twice. */
    private function watchFromFields(): ?array
    {
        $required = array_values(array_filter($this->fields, fn ($f) => ! ($f['optional'] ?? false)));
        if ($required === []) { return $this->fields === [] ? null : ['type' => 'always']; }
        return ['type' => $this->requireAny ? 'any' : 'filled', 'selectors' => array_column($required, 'selector')];
    }
}
```

Watch rule vocabulary (the browser implements these): `always`, `filled {selectors}`, `any {selectors}`, `minLength {selector, value}`, `minCount {selector, value}` (e.g. at least 3 photos), `checked {selector}`.

## 4. `WorkflowContext`

What every step closure sees.

```php
class WorkflowContext
{
    private ?Model $entity = null;
    private bool $loaded = false;

    public function __construct(public readonly WorkflowRun $run, public readonly User $user) {}

    public function entity(): ?Model
    {
        if ($this->loaded) { return $this->entity; }
        $this->loaded = true;
        $class = WorkflowEntities::classFor((string) $this->run->entity_type);
        return $this->entity = ($class && $this->run->entity_id) ? $class::query()->find($this->run->entity_id) : null;
    }

    public function refresh(): void { $this->loaded = false; $this->entity = null; }

    /** Remember a record; the primary type also becomes the run's own record. */
    public function bindEntity(string $type, int $id, bool $primary = true): void
    {
        $bound = (array) $this->run->stateValue('bound', []);
        $bound[$type] = $id;
        $this->run->mergeState(['bound' => $bound]);
        if ($primary) { $this->run->forceFill(['entity_type' => $type, 'entity_id' => $id]); }
        $this->run->save();
        $this->refresh();
    }

    /** Any record the run has passed through, by type. */
    public function bound(string $type): ?Model
    {
        if ($this->run->entity_type === $type) { return $this->entity(); }
        $id = (int) $this->run->stateValue("bound.$type", 0);
        $class = $id ? WorkflowEntities::classFor($type) : null;
        return $class ? $class::query()->find($id) : null;
    }

    public function answer(string $step): ?string
    {
        $v = $this->run->stateValue("answers.$step");
        return is_string($v) && $v !== '' ? $v : null;
    }

    public function recordAnswer(string $step, string $value): void
    {
        $answers = (array) $this->run->stateValue('answers', []);
        $answers[$step] = $value;
        $this->run->mergeState(['answers' => $answers]);
        $this->run->save();
    }

    public function hasCompleted(string $step): bool { return in_array($step, $this->run->completedSteps(), true); }
}
```

## 5. `WorkflowEntities` — the record allow-list

```php
final class WorkflowEntities
{
    public const PRODUCT = 'product';
    public const ORDER = 'order';
    public const INVOICE = 'invoice';
    // …

    private const MAP = [
        self::PRODUCT => Product::class,
        self::ORDER => Order::class,
        self::INVOICE => Invoice::class,
    ];

    public static function classFor(string $type): ?string { return self::MAP[$type] ?? null; }

    /** A short label for resume cards and history. */
    public static function label(string $type, ?Model $e): ?string
    {
        return $e ? match ($type) {
            self::PRODUCT => $e->name ?: 'Untitled product',
            self::ORDER => $e->number ?: 'Order #'.$e->getKey(),
            default => '#'.$e->getKey(),
        } : null;
    }
}
```

## 6. `WorkflowDefinition`

```php
abstract class WorkflowDefinition
{
    public const AUDIENCE_STAFF = 'staff';
    public const AUDIENCE_CUSTOMER = 'customer';

    abstract public function key(): string;
    abstract public function name(): string;
    abstract public function category(): string;
    abstract public function description(): string;
    /** @return list<WorkflowStep> */
    abstract public function steps(WorkflowContext $context): array;

    public function icon(): string { return 'Workflow'; }
    public function ability(): ?string { return null; }             // staff permission
    public function audience(): string { return self::AUDIENCE_STAFF; }
    public function entityType(): ?string { return null; }
    public function bindableTypes(): array { return array_values(array_filter([$this->entityType()])); }
    public function estimatedMinutes(): string { return '3–5 min'; }
    public function popular(): bool { return false; }
    public function keywords(): array { return []; }                 // extra search words

    /** Worth offering this person at all? Hide what does not apply rather than refuse it later. */
    public function relevantTo(User $user): bool { return true; }

    /** May this person point the workflow at this record? Customers: only their own. */
    public function owns(User $user, Model $entity): bool { return true; }

    public function success(WorkflowContext $c): array
    {
        return ['title' => $this->name().' complete', 'description' => 'That task is finished.',
                'guide' => ['pose' => 'celebration', 'message' => 'Good work. What next?']];
    }

    /** @return list<array{label:string, url?:string, workflow?:string, primary?:bool}> */
    public function nextActions(WorkflowContext $c): array { return []; }

    public function onStart(WorkflowContext $c): void {}
}
```

Register definitions in config so adding a workflow is one class and one line:

```php
// config/workflows.php
return [
    'definitions' => [AddProductWorkflow::class, ReviewRefundWorkflow::class, UploadReceiptWorkflow::class],
    'categories' => ['catalogue' => 'Catalogue', 'sales' => 'Sales', 'payments' => 'Payments'],
];
```

## 7. `WorkflowManager` — the engine

The important methods, with the reasoning inline. Everything here is generic; no definition-specific code belongs in the manager.

```php
class WorkflowManager
{
    private ?array $definitions = null;
    private array $stepTitles = [];

    public function definitions(): array
    {
        return $this->definitions ??= collect(config('workflows.definitions', []))
            ->filter(fn ($c) => is_string($c) && class_exists($c))
            ->mapWithKeys(fn ($c) => [($d = app($c))->key() => $d])->all();
    }

    public function find(string $key): ?WorkflowDefinition { return $this->definitions()[$key] ?? null; }

    /** Audiences never mix; staff additionally need the workflow's permission. */
    public function allows(User $user, WorkflowDefinition $d): bool
    {
        if ($d->audience() === WorkflowDefinition::AUDIENCE_CUSTOMER) { return ! $user->isStaff(); }
        if (! $user->isStaff()) { return false; }
        return $d->ability() === null || $user->can($d->ability());
    }

    public function mayUse(User $user, WorkflowDefinition $d, string $type, int $id): bool
    {
        $class = WorkflowEntities::classFor($type);
        $record = $class ? $class::query()->find($id) : null;
        return $record !== null && $d->owns($user, $record);
    }

    public function availableTo(User $user): Collection
    {
        return collect($this->definitions())
            ->filter(fn ($d) => $this->allows($user, $d) && $d->relevantTo($user))->values();
    }

    /** The launcher's catalogue, ordered by what this person actually uses. */
    public function catalogue(User $user): array
    {
        $usage = $this->usageFor($user); // count of runs per key, last ~60 days; [] on failure
        return $this->availableTo($user)->map(fn ($d) => [
            'key' => $d->key(), 'name' => $d->name(), 'description' => $d->description(),
            'category' => $d->category(), 'icon' => $d->icon(), 'estimate' => $d->estimatedMinutes(),
            'popular' => $d->popular(), 'keywords' => $d->keywords(),
            'steps' => count($d->steps($this->blankContext($d, $user))),
            'usage' => (int) ($usage[$d->key()] ?? 0),
        ])->sortBy([fn ($a, $b) => $b['usage'] <=> $a['usage'], fn ($a, $b) => strcmp($a['name'], $b['name'])])
          ->values()->all();
    }

    public function start(User $user, string $key, ?string $type = null, ?int $id = null): WorkflowRun
    {
        $d = $this->find($key) ?? throw new RuntimeException("Unknown workflow [$key].");
        if (! $this->allows($user, $d)) { throw new RuntimeException('You do not have permission to run this workflow.'); }
        if ($type && $id && ! $this->mayUse($user, $d, $type, $id)) { throw new RuntimeException('That record is not available to you.'); }

        $existing = WorkflowRun::query()->open()->where('user_id', $user->id)->where('workflow_key', $key)
            ->when($id, fn ($q) => $q->where('entity_id', $id))->latest('id')->first();
        if ($existing) { return $this->resume($existing); }

        $this->pauseOthers($user); // one run drives the screen at a time

        $run = WorkflowRun::create(['workflow_key' => $key, 'user_id' => $user->id,
            'entity_type' => $type ?: $d->entityType(), 'entity_id' => $id,
            'state_json' => [], 'status' => WorkflowRun::STATUS_ACTIVE, 'started_at' => now()]);

        $ctx = new WorkflowContext($run, $user);
        $d->onStart($ctx);
        $this->syncCompletedSteps($d, $ctx);
        event(new WorkflowStarted($run));
        return $run->fresh();
    }

    /** Move on only if the step is genuinely done. */
    public function advance(WorkflowRun $run, User $user): array
    {
        $d = $this->find($run->workflow_key);
        $ctx = new WorkflowContext($run, $user);
        $steps = collect($d->steps($ctx))->keyBy('key');
        $current = $steps[$this->currentKey($d, $ctx)] ?? null;

        if ($current && ! $current->isOptional() && ! $current->isSatisfied($ctx)) {
            event(new WorkflowStepBlocked($run, $current->key, $current->requirement()));
            return ['moved' => false, 'reason' => $current->requirement()];
        }

        if ($current) {
            // An optional step passed without doing it is a skip — counted separately.
            $skipped = $current->isOptional() && ! $current->isSatisfied($ctx);
            $run->markStepComplete($current->key);
            $run->save();
            event(new WorkflowStepCompleted($run, $current->key, $skipped));
        }

        $ctx->refresh();                       // an answer can change the list
        $this->syncCompletedSteps($d, $ctx);
        $next = $this->firstUnfinished($d, $ctx);

        if ($next === null) { $this->complete($run); }
        else { $run->forceFill(['current_step' => $next])->save(); }

        return ['moved' => true, 'reason' => null];
    }

    public function answer(WorkflowRun $run, User $user, string $step, string $value): void
    {
        (new WorkflowContext($run, $user))->recordAnswer($step, $value);
        $run->markStepComplete($step);
        $run->save();
        // The controller then calls advance(), so the new branch takes effect.
    }

    // back(): walk to the previous step that is not locked.
    // jump(): only to a step that is revisitable (satisfied and not locked).
    // pause()/resume()/cancel()/complete(): set status (+completed_at), fire the event.

    /** The whole run as the browser needs it. */
    public function state(WorkflowRun $run, User $user): array
    {
        $d = $this->find($run->workflow_key);
        $ctx = new WorkflowContext($run, $user);
        $this->syncCompletedSteps($d, $ctx);

        $steps = $d->steps($ctx);
        $currentKey = $this->currentKey($d, $ctx);

        // Keep the stored step honest, so abandonment analytics see step one too.
        if ($currentKey && $run->current_step !== $currentKey) {
            $run->forceFill(['current_step' => $currentKey])->save();
        }

        $payload = []; $done = 0;
        foreach ($steps as $step) {
            $satisfied = $step->isSatisfied($ctx);
            $done += $satisfied ? 1 : 0;
            $payload[] = $step->toArray($ctx) + [
                'status' => $step->key === $currentKey ? 'current' : ($satisfied ? 'complete' : 'upcoming'),
                'revisitable' => $satisfied && ! $step->isLocked(),
                'satisfied' => $satisfied, // the server's verdict beats a page that cleared itself
            ];
        }

        $completed = $run->status === WorkflowRun::STATUS_COMPLETED;
        $entity = $ctx->entity();

        return [
            'id' => $run->id, 'key' => $d->key(), 'name' => $d->name(), 'icon' => $d->icon(),
            'status' => $run->status, 'current_step' => $currentKey,
            'steps' => $payload, 'total_steps' => count($steps), 'completed_steps' => $done,
            'position' => $this->positionOf($steps, $currentKey),
            'entity' => $entity ? ['type' => $run->entity_type, 'id' => $entity->getKey(),
                                   'label' => WorkflowEntities::label($run->entity_type, $entity)] : null,
            'answers' => (array) $run->stateValue('answers', []),
            'success' => $completed ? $d->success($ctx) : null,
            'next_actions' => $completed ? $this->offerable($d->nextActions($ctx), $user) : [],
        ];
    }

    /** The stored step if it still exists (even if satisfied — the user stays put), else the first gap. */
    private function currentKey(WorkflowDefinition $d, WorkflowContext $ctx): ?string
    {
        $keys = array_map(fn ($s) => $s->key, $d->steps($ctx));
        $stored = (string) $ctx->run->current_step;
        if ($stored !== '' && in_array($stored, $keys, true)) { return $stored; }
        return $this->firstUnfinished($d, $ctx) ?? (end($keys) ?: null);
    }

    /** Tick off anything the record already satisfies, so nobody redoes finished work. */
    private function syncCompletedSteps(WorkflowDefinition $d, WorkflowContext $ctx): void
    {
        $changed = false;
        foreach ($d->steps($ctx) as $step) {
            if ($step->isQuestion() || $ctx->hasCompleted($step->key)) { continue; }
            if ($step->isSatisfied($ctx)) { $ctx->run->markStepComplete($step->key); $changed = true; }
        }
        if ($changed) { $ctx->run->save(); }
    }

    /** Drop suggested next workflows this user cannot run, or that do not exist yet. */
    private function offerable(array $actions, User $user): array
    {
        return array_values(array_filter($actions, function ($a) use ($user) {
            if (empty($a['workflow'])) { return true; }
            $d = $this->find($a['workflow']);
            return $d && $this->allows($user, $d);
        }));
    }

    // firstUnfinished(), positionOf(), pauseOthers(), activeFor(), openFor(), summary(),
    // usageFor() and blankContext() are straightforward; blankContext() builds an
    // unsaved run so steps() can be counted or titled without touching the database.
}
```

## 8. Controller and routes

One controller serves both audiences. The audience comes from the route, so a customer cannot reach staff workflows by calling the admin URL, and staff cannot use the customer's.

```php
class WorkflowController extends Controller
{
    public function __construct(private readonly WorkflowManager $workflows) {}

    public function catalogue(Request $r) { $u = $this->user($r); return ['catalogue' => $this->workflows->catalogue($u), 'categories' => config('workflows.categories')]; }

    public function store(Request $r)
    {
        $u = $this->user($r);
        $data = $r->validate(['workflow' => 'required|string|max:64', 'entity_type' => 'nullable|string|max:64', 'entity_id' => 'nullable|integer|min:1']);
        if (($t = $data['entity_type'] ?? null) && ! WorkflowEntities::classFor($t)) { return response()->json(['message' => 'Unknown record type.'], 422); }
        try { $run = $this->workflows->start($u, $data['workflow'], $t, $data['entity_id'] ?? null); }
        catch (RuntimeException $e) { return response()->json(['message' => $e->getMessage()], 422); }
        return ['workflow' => $this->workflows->state($run, $u)];
    }

    public function advance(Request $r, WorkflowRun $run)
    {
        $u = $this->authorizeRun($r, $run);
        $result = $this->workflows->advance($run, $u);
        return ['workflow' => $this->workflows->state($run->fresh(), $u)] + $result;
    }

    /** Tie the run to the record the page is showing — only a record this person may use. */
    public function bind(Request $r, WorkflowRun $run)
    {
        $u = $this->authorizeRun($r, $run);
        $data = $r->validate(['entity_type' => 'required|string|max:64', 'entity_id' => 'required|integer|min:1']);
        $d = $this->workflows->find($run->workflow_key);
        $type = $data['entity_type'];

        if (! in_array($type, $d->bindableTypes(), true)) { return response()->json(['message' => 'That record does not belong to this workflow.'], 422); }
        if (! $this->workflows->mayUse($u, $d, $type, (int) $data['entity_id'])) { return response()->json(['message' => 'That record is not available to you.'], 403); }

        (new WorkflowContext($run, $u))->bindEntity($type, (int) $data['entity_id'], primary: $d->entityType() === $type);
        return ['workflow' => $this->workflows->state($run->fresh(), $u)];
    }

    // show, back, jump, answer (answer then advance), transition (pause|resume|cancel) follow the same shape.

    /** Each route group admits only its own people. */
    private function user(Request $r): User
    {
        $u = $r->user();
        abort_unless($u, 403);
        $customerSide = ($r->route()?->defaults['audience'] ?? null) === WorkflowDefinition::AUDIENCE_CUSTOMER;
        abort_unless($customerSide ? ! $u->isStaff() : $u->isStaff(), 403);
        return $u;
    }

    /** A run belongs to whoever started it, while they still hold its permission. */
    private function authorizeRun(Request $r, WorkflowRun $run): User
    {
        $u = $this->user($r);
        abort_unless($run->user_id === $u->id, 403);
        $d = $this->workflows->find($run->workflow_key);
        abort_unless($d && $this->workflows->allows($u, $d), 403);
        return $u;
    }
}
```

```php
// Staff — inside the admin group (auth + staff middleware)
Route::get('/admin/workflows/catalogue', [WorkflowController::class, 'catalogue'])->name('admin.workflows.catalogue');
Route::post('/admin/workflows', [WorkflowController::class, 'store'])->name('admin.workflows.store');
Route::get('/admin/workflows/{workflowRun}', [WorkflowController::class, 'show'])->name('admin.workflows.show');
foreach (['advance', 'back', 'jump', 'answer', 'bind', 'transition'] as $action) {
    Route::post("/admin/workflows/{workflowRun}/$action", [WorkflowController::class, $action])->name("admin.workflows.$action");
}

// Customers — inside the authenticated portal group, marked as the customer side
Route::prefix('portal/workflows')->name('portal.workflows.')->group(function () {
    $customer = fn ($route) => $route->defaults('audience', 'customer');
    $customer(Route::get('/catalogue', [WorkflowController::class, 'catalogue'])->name('catalogue'));
    $customer(Route::post('/', [WorkflowController::class, 'store'])->name('store'));
    $customer(Route::get('/{workflowRun}', [WorkflowController::class, 'show'])->name('show'));
    foreach (['advance', 'back', 'jump', 'answer', 'bind', 'transition'] as $action) {
        $customer(Route::post("/{workflowRun}/$action", [WorkflowController::class, $action])->name($action));
    }
});
```

Keep the URL shape identical on both sides (`{base}/catalogue`, `{base}`, `{base}/{id}`, `{base}/{id}/{action}`) so the browser builds every URL from one base.

## 9. Sharing the active run with every page

In an Inertia app, share it from the middleware — **under a distinctive name**:

```php
// HandleInertiaRequests::share()
'activeWorkflow' => fn () => $this->activeWorkflow($request), // NOT 'workflow'
```

```php
private function activeWorkflow(Request $request): ?array
{
    $user = $request->user();
    if (! $user?->isStaff() || ! $request->is('admin*')) { return null; }
    $m = app(WorkflowManager::class);
    $run = $m->activeFor($user);
    $d = $run ? $m->find($run->workflow_key) : null;
    return ($run && $d && $m->allows($user, $d)) ? $m->state($run, $user) : null;
}
```

A page that passes its own prop of the same name silently shadows a shared one. With the name `workflow`, two unrelated admin screens that already had a `workflow` prop rendered a blank page for everyone. See pitfalls.

For server-rendered pages, print the same state into the page as JSON instead — `server-rendered-island.md`.

## 10. Events and the recorder

Fire plain events from the manager: `WorkflowStarted`, `WorkflowResumed`, `WorkflowPaused`, `WorkflowCompleted`, `WorkflowCancelled`, `WorkflowStepCompleted($run, $step, bool $skipped)`, `WorkflowStepBlocked($run, $step, $reason)`.

A subscriber writes each to `workflow_events` — and swallows its own failures:

```php
class WorkflowEventRecorder
{
    public function subscribe(Dispatcher $events): array
    {
        return [
            WorkflowStarted::class => 'onStarted',
            WorkflowCancelled::class => 'onCancelled',          // records current_step: where they gave up
            WorkflowStepCompleted::class => 'onStepCompleted',  // step.completed or step.skipped
            WorkflowStepBlocked::class => 'onStepBlocked',      // where they got stuck
            // …
        ];
    }

    private function record(WorkflowRun $run, string $event, ?string $step = null): void
    {
        try {
            WorkflowEvent::create(['workflow_run_id' => $run->id, 'workflow_key' => $run->workflow_key,
                'user_id' => $run->user_id, 'event' => $event, 'step' => $step, 'created_at' => now()]);
        } catch (Throwable $e) {
            report($e); // analytics must never cost somebody their place in a task
        }
    }
}

// AppServiceProvider::boot()
Event::subscribe(WorkflowEventRecorder::class);
```

Test this by dropping the events table mid-test and asserting the task still runs.

## 11. Analytics

An `overview(days = 90)` returning:

- **totals**: started, completed, cancelled, open, completion rate, **median** minutes to complete (a median, so one task left open over a weekend does not skew it)
- **per workflow**, busiest first: the same figures
- **sticking points**: `step.blocked` counts grouped by workflow + step — *a step that refuses everyone is asking for something the screen does not make obvious*
- **abandoned at**: cancelled runs grouped by `current_step`
- **skipped steps**: `step.skipped` counts — an optional step everybody skips may not need to exist

Show step **titles**, not keys — look them up from the definition's default path, memoised, falling back to the key for branch-only steps. Show this only to people who manage the whole operation; everyone else sees their own history.

## 12. Other stacks

The design is framework-neutral. Map it as follows:

| Concept | Rails | Django | Node (Nest/Express) |
|---|---|---|---|
| Definition registry | classes listed in an initializer | classes listed in settings | classes in a registry module |
| `completeWhen` closure | lambda / method | callable | function |
| Route defaults for audience | `defaults: { audience: 'customer' }` | URL kwargs | router-level middleware setting `req.audience` |
| Shared active run | `helper_method` → JSON in layout, or Inertia-Rails shared data | context processor → JSON script tag | SSR props or JSON script tag |
| Event recorder | `ActiveSupport::Notifications` subscriber | signals | an event emitter listener |

Keep: short-word entity types with an allow-list, ownership on every bind, audiences via the route, steps rebuilt per request, the `satisfied` flag, persisting the current step, and a recorder that cannot throw.
