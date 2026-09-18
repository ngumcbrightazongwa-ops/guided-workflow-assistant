<?php

/**
 * dump-selectors.php — every selector every workflow step points at, by page.
 *
 * Run from the Laravel project root:
 *
 *   php dump-selectors.php                 # staff workflows, as the first admin
 *   php dump-selectors.php --user=12       # as a specific user (e.g. a customer)
 *   php dump-selectors.php > selectors.json
 *
 * Each definition is built against a blank, UNSAVED run, so nothing is written
 * to the database. Steps whose route needs a record come out under "(no route)"
 * — audit those on a real record's page. Branches that only appear after a
 * question is answered are included by trying each answer.
 *
 * Adjust the class names below if your engine lives somewhere else.
 */

use App\Models\User;
use App\Models\WorkflowRun;
use App\Workflows\WorkflowContext;
use App\Workflows\WorkflowManager;

require __DIR__.'/vendor/autoload.php';
$app = require_once __DIR__.'/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();

$userId = null;
foreach ($argv as $arg) {
    if (str_starts_with($arg, '--user=')) {
        $userId = (int) substr($arg, 7);
    }
}

$user = $userId
    ? User::query()->findOrFail($userId)
    : User::query()->where('is_admin', true)->firstOrFail(); // adjust to however you mark admins

$manager = app(WorkflowManager::class);
$byPage = [];

/** Collect a definition's selectors for one set of answers, returning any questions it asks. */
$collect = function ($key, $definition, array $answers) use ($user, &$byPage): array {
    $run = new WorkflowRun([
        'workflow_key' => $key,
        'user_id' => $user->getKey(),
        'state_json' => ['answers' => $answers],
        'status' => 'active',
    ]);
    $context = new WorkflowContext($run, $user);
    $questions = [];

    foreach ($definition->steps($context) as $step) {
        $data = $step->toArray($context);
        $route = $data['route'] ?? null;
        $route = $route ? (parse_url($route, PHP_URL_PATH) ?: $route) : '(no route)';

        $selectors = array_values(array_filter([
            $data['target'] ?? null,
            $data['reveal'] ?? null,
            ...array_map(static fn (array $f) => $f['selector'], $data['fields'] ?? []),
        ]));

        foreach ($selectors as $selector) {
            $byPage[$route][$selector][] = $key.'::'.$data['key'];
        }

        if (! empty($data['question']['options']) && ! array_key_exists($data['key'], $answers)) {
            $questions[$data['key']] = array_column($data['question']['options'], 'value');
        }
    }

    return $questions;
};

foreach ($manager->definitions() as $key => $definition) {
    if (! $manager->allows($user, $definition)) {
        continue;
    }

    // Walk every branch: answer each question each possible way (breadth-first, bounded).
    $queue = [[]];
    $seen = 0;
    while ($queue && $seen++ < 64) {
        $answers = array_shift($queue);
        foreach ($collect($key, $definition, $answers) as $step => $values) {
            foreach ($values as $value) {
                $queue[] = $answers + [$step => $value];
            }
            break; // one unanswered question at a time
        }
    }
}

ksort($byPage);

echo json_encode(array_map(
    static fn (array $selectors) => array_map(
        static fn (array $steps) => implode(', ', array_values(array_unique($steps))),
        $selectors,
    ),
    $byPage,
), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES).PHP_EOL;
