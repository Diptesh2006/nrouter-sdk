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

// Guardrails, prompt templates, rate limits and budgets are configured in the
// dashboard and enforced server-side on every request. There is deliberately no
// endpoint to list or override them: a request cannot opt out of its org policy.
// Balances and spend history live at https://app.nrouter.ai — org billing data,
// not inference. Per-request cost arrives on the x-nr-request-cost header.
// ━━━ 1. Chat (org defaults auto-apply) ━━━━━━━━━━━━━━━━━━━━━━
// Cache, guardrails, and rate limits auto-apply from org config.

$client = OpenAI::factory()
    ->withApiKey($nrouterKey)
    ->withBaseUri("{$nrouterBase}/v1")
    ->make();

$response = $client->chat()->create([
    'model' => 'anthropic/claude-sonnet-4-5-20250929',
    'messages' => [['role' => 'user', 'content' => 'Hello!']],
]);
echo $response->choices[0]->message->content . "\n";

// With prompt template + variables
$withPrompt = $client->chat()->create([
    'model' => 'anthropic/claude-sonnet-4-5-20250929',
    'messages' => [['role' => 'user', 'content' => 'Q1 revenue was $4.2M...']],
    'nrouter_prompt_template_id' => 'your-summarizer-id',
    'nrouter_prompt_variables' => ['language' => 'Spanish', 'max_length' => '100'],
]);

// Guardrails are assigned per key, team or org in the dashboard and apply
// automatically — the narrowest assignment wins. There is no per-request
// override to pass here.

// Disable cache for a single request
// Cache is enabled by default. Pass nrouter_cache: false for a fresh response.
$noCacheResponse = $client->chat()->create([
    'model' => 'anthropic/claude-sonnet-4-5-20250929',
    'messages' => [['role' => 'user', 'content' => 'What is the latest news?']],
    'nrouter_cache' => false,
]);

// ━━━ 2. PII blocked by guardrail ━━━━━━━━━━━━━━━━━━━━━━━━━━

try {
    $client->chat()->create([
        'model' => 'anthropic/claude-sonnet-4-5-20250929',
        'messages' => [['role' => 'user', 'content' => 'My SSN is 123-45-6789']],
    ]);
} catch (\Exception $e) {
    echo "Guardrail blocked: {$e->getMessage()}\n";
}

