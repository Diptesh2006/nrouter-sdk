<?php
// nRouter — PHP
// openai-php/client + guardrails + prompt templates + cost tracking.
//
// composer require openai-php/client

require 'vendor/autoload.php';

$nrouterBase = 'https://api.nrouter.ai';
$nrouterKey = getenv('NROUTER_API_KEY');

// Helper to call nRouter APIs
function nrouterGet(string $path): array {
    global $nrouterBase, $nrouterKey;
    $opts = ['http' => ['method' => 'GET', 'header' => "Authorization: Bearer {$nrouterKey}\r\n"]];
    $body = file_get_contents($nrouterBase . $path, false, stream_context_create($opts));
    return json_decode($body, true) ?: [];
}

// ━━━ 1. See guardrails + prompts + balance ━━━━━━━━━━━━━━━━━

$guardrails = nrouterGet('/nrouter/guardrail/list');
echo "Guardrails:\n";
foreach ($guardrails['data'] ?? [] as $g) {
    if ($g['enabled'] ?? false) {
        echo "  • {$g['guardrail_name']} ({$g['provider']})\n";
    }
}

$prompts = nrouterGet('/nrouter/prompt/list');
echo "Prompts:\n";
foreach ($prompts['data'] ?? [] as $p) {
    echo "  • {$p['name']} (v{$p['active_version_number']})\n";
}

$balance = nrouterGet('/api/credits/balance');
echo "Credits: \${$balance['available']}\n";

// ━━━ 2. Chat (org defaults auto-apply) ━━━━━━━━━━━━━━━━━━━━━━
// Cache, guardrails, and rate limits auto-apply from org config.

$client = OpenAI::factory()
    ->withApiKey($nrouterKey)
    ->withBaseUri("{$nrouterBase}/v1")
    ->make();

$response = $client->chat()->create([
    'model' => 'claude-sonnet-4-20250514',
    'messages' => [['role' => 'user', 'content' => 'Hello!']],
]);
echo $response->choices[0]->message->content . "\n";

// With prompt template + variables
$withPrompt = $client->chat()->create([
    'model' => 'gpt-4o',
    'messages' => [['role' => 'user', 'content' => 'Q1 revenue was $4.2M...']],
    'nrouter_prompt_template_id' => 'your-summarizer-id',
    'nrouter_prompt_variables' => ['language' => 'Spanish', 'max_length' => '100'],
]);

// Per-request guardrail selection
// By default, ALL org-enabled guardrails apply automatically.
// Pass nrouter_guardrail_ids to run only specific guardrails on this request.
$withGuardrails = $client->chat()->create([
    'model' => 'gpt-4o',
    'messages' => [['role' => 'user', 'content' => 'Summarize Q1 earnings...']],
    'nrouter_guardrail_ids' => ['guardrail-uuid-1', 'guardrail-uuid-2'],
]);

// Disable cache for a single request
// Cache is enabled by default. Pass nrouter_cache: false for a fresh response.
$noCacheResponse = $client->chat()->create([
    'model' => 'gpt-4o',
    'messages' => [['role' => 'user', 'content' => 'What is the latest news?']],
    'nrouter_cache' => false,
]);

// ━━━ 3. PII blocked by guardrail ━━━━━━━━━━━━━━━━━━━━━━━━━━

try {
    $client->chat()->create([
        'model' => 'gpt-4o',
        'messages' => [['role' => 'user', 'content' => 'My SSN is 123-45-6789']],
    ]);
} catch (\Exception $e) {
    echo "Guardrail blocked: {$e->getMessage()}\n";
}

// ━━━ 4. Check spend ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

$newBalance = nrouterGet('/api/credits/balance');
$spent = $balance['available'] - $newBalance['available'];
echo "Spent: \$" . number_format($spent, 4) . "\n";
