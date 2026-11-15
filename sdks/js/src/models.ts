// Model discovery for nRouter, extracted from the client so the transport and
// the discovery logic can be reasoned about (and tested) separately.
//
// Everything here is built on ONE decision, and it is load-bearing: discovery
// goes through the inherited vendor client's own request pipeline, and reads
// the RAW response body rather than the vendor SDK's parsed page object. The
// two halves of that decision are documented on `RawRequester` and on `list()`
// respectively; neither is an implementation detail to be "cleaned up".

/**
 * One model as the gateway describes it.
 *
 * The index signature is deliberate: the gateway may add descriptive fields
 * (context window, modality, provider attribution) and a closed type would
 * discard them silently, leaving a caller unable to read a field they can see
 * in the JSON. Only `id` is guaranteed — it is the only field the wire format
 * requires and the only one this SDK depends on.
 */
export type NRouterModel = {
  id: string;
  object?: string;
  owned_by?: string;
  [key: string]: unknown;
};

/** The `/models` envelope: `data` plus whatever else the gateway sends. */
export type NRouterModelList = {
  data: NRouterModel[];
  object?: string;
  [key: string]: unknown;
};

/**
 * Gateway-level capabilities returned by `GET /capabilities`.
 */
export type NRouterCapabilities = {
  gateway: string;
  providers: string[];
  models: string[];
  endpoints: string[];
  mcp_servers?: string[];
  [key: string]: unknown;
};

// BEGIN GENERATED: model-catalog-snapshot
// Generated from spec/model-catalog-snapshot.json (snapshot version: 2026-11-14, schema_version: 1, catalog_revision: 1).
// Do not edit by hand; run `node scripts/generate-model-constants.mjs` to regenerate.
// Naming rule: `MODEL_` + uppercase model id with non-alphanumeric runs replaced by `_`.

export const MODEL_AMAZON_NOVA_LITE_V1 = 'amazon-nova-lite-v1';
export const MODEL_AMAZON_NOVA_MICRO_V1 = 'amazon-nova-micro-v1';
export const MODEL_AMAZON_NOVA_PRO_V1 = 'amazon-nova-pro-v1';
export const MODEL_CHATGPT_IMAGE_LATEST = 'chatgpt-image-latest';
export const MODEL_CHAT_LATEST = 'chat-latest';
/** @deprecated Model `claude-3-7-sonnet` is retired. */
export const MODEL_CLAUDE_3_7_SONNET = 'claude-3-7-sonnet';
export const MODEL_CLAUDE_FABLE_5 = 'claude-fable-5';
export const MODEL_CLAUDE_FABLE_5_1 = 'claude-fable-5-1';
export const MODEL_CLAUDE_HAIKU_4_5_20251001 = 'claude-haiku-4-5-20251001';
export const MODEL_CLAUDE_OPUS_4_5_20251101 = 'claude-opus-4-5-20251101';
export const MODEL_CLAUDE_OPUS_4_6 = 'claude-opus-4-6';
export const MODEL_CLAUDE_OPUS_4_7 = 'claude-opus-4-7';
export const MODEL_CLAUDE_OPUS_4_8 = 'claude-opus-4-8';
export const MODEL_CLAUDE_OPUS_5 = 'claude-opus-5';
export const MODEL_CLAUDE_OPUS_5_5 = 'claude-opus-5-5';
/** @deprecated Model `claude-sonnet-4-5-20250929` is retired; compatibility alias for `MODEL_CLAUDE_SONNET_4_5_20250929`. */
export const MODEL_CLAUDE_SONNET_4_5 = 'claude-sonnet-4-5-20250929';
/** @deprecated Model `claude-sonnet-4-5-20250929` is retired. */
export const MODEL_CLAUDE_SONNET_4_5_20250929 = 'claude-sonnet-4-5-20250929';
export const MODEL_CLAUDE_SONNET_4_6 = 'claude-sonnet-4-6';
export const MODEL_CLAUDE_SONNET_5 = 'claude-sonnet-5';
export const MODEL_CLAUDE_SONNET_5_5 = 'claude-sonnet-5-5';
export const MODEL_DEEPSEEK_R1_0528_MAAS = 'deepseek-r1-0528-maas';
export const MODEL_DEEPSEEK_V3_2_MAAS = 'deepseek-v3.2-maas';
export const MODEL_DEEPSEEK_V4_1_FLASH = 'deepseek-v4.1-flash';
export const MODEL_DEEPSEEK_V4_FLASH_0731 = 'deepseek-v4-flash-0731';
export const MODEL_DEEPSEEK_V4_PRO = 'deepseek-v4-pro';
export const MODEL_DEEPSEEK_V4_PRO_0813 = 'deepseek-v4-pro-0813';
export const MODEL_DEVSTRAL_2_123B = 'devstral-2-123b';
/** @deprecated Model `google/gemini-1.5-flash-002` is retired; compatibility alias for `MODEL_GOOGLE_GEMINI_1_5_FLASH_002`. */
export const MODEL_GEMINI_1_5_FLASH_002 = 'google/gemini-1.5-flash-002';
/** @deprecated Model `google/gemini-1.5-pro-002` is retired; compatibility alias for `MODEL_GOOGLE_GEMINI_1_5_PRO_002`. */
export const MODEL_GEMINI_1_5_PRO_002 = 'google/gemini-1.5-pro-002';
/** @deprecated Model `google/gemini-2.0-flash` is retired; compatibility alias for `MODEL_GOOGLE_GEMINI_2_0_FLASH`. */
export const MODEL_GEMINI_2_0_FLASH = 'google/gemini-2.0-flash';
/** @deprecated Model `google/gemini-2.0-flash-lite` is retired; compatibility alias for `MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE`. */
export const MODEL_GEMINI_2_0_FLASH_LITE = 'google/gemini-2.0-flash-lite';
/** @deprecated Model `google/gemini-2.5-flash` is retired; compatibility alias for `MODEL_GOOGLE_GEMINI_2_5_FLASH`. */
export const MODEL_GEMINI_2_5_FLASH = 'google/gemini-2.5-flash';
/** @deprecated Model `google/gemini-2.5-pro` is retired; compatibility alias for `MODEL_GOOGLE_GEMINI_2_5_PRO`. */
export const MODEL_GEMINI_2_5_PRO = 'google/gemini-2.5-pro';
/** @deprecated Compatibility alias; use `MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE` instead. */
export const MODEL_GEMINI_3_1_FLASH_LITE = 'google/gemini-3.1-flash-lite';
/** @deprecated Model `google/gemini-3.1-pro` is retired; compatibility alias for `MODEL_GOOGLE_GEMINI_3_1_PRO`. */
export const MODEL_GEMINI_3_1_PRO = 'google/gemini-3.1-pro';
export const MODEL_GEMINI_3_1_PRO_PREVIEW = 'gemini-3.1-pro-preview';
export const MODEL_GEMINI_3_5_FLASH = 'gemini-3.5-flash';
export const MODEL_GEMINI_3_5_FLASH_LITE = 'gemini-3.5-flash-lite';
export const MODEL_GEMINI_3_5_LIVE_TRANSLATE_PREVIEW = 'gemini-3.5-live-translate-preview';
export const MODEL_GEMINI_3_6_FLASH = 'gemini-3.6-flash';
export const MODEL_GEMINI_3_7_FLASH = 'gemini-3.7-flash';
/** @deprecated Model `google/gemini-3.8-flash` is retired; compatibility alias for `MODEL_GOOGLE_GEMINI_3_8_FLASH`. */
export const MODEL_GEMINI_3_8_FLASH = 'google/gemini-3.8-flash';
export const MODEL_GEMINI_3_FLASH_PREVIEW = 'gemini-3-flash-preview';
export const MODEL_GEMMA_3_12B_IT = 'gemma-3-12b-it';
export const MODEL_GEMMA_3_27B_IT = 'gemma-3-27b-it';
export const MODEL_GEMMA_3_4B_IT = 'gemma-3-4b-it';
export const MODEL_GLM_4_7 = 'glm-4.7';
export const MODEL_GLM_4_7_FLASH = 'glm-4.7-flash';
export const MODEL_GLM_4_7_MAAS = 'glm-4.7-maas';
export const MODEL_GLM_5 = 'glm-5';
export const MODEL_GLM_5_1 = 'glm-5.1';
export const MODEL_GLM_5_2 = 'glm-5.2';
export const MODEL_GLM_5_2_FAST_PREVIEW = 'glm-5.2-fast-preview';
export const MODEL_GLM_5_2_MAAS = 'glm-5.2-maas';
export const MODEL_GLM_5_3 = 'glm-5.3';
export const MODEL_GLM_5_3_PRIME = 'glm-5.3-prime';
export const MODEL_GLM_5_MAAS = 'glm-5-maas';
export const MODEL_GLOBAL_AMAZON_NOVA_2_LITE_V1_0 = 'global.amazon.nova-2-lite-v1:0';
/** @deprecated Model `google/gemini-1.5-flash-002` is retired. */
export const MODEL_GOOGLE_GEMINI_1_5_FLASH_002 = 'google/gemini-1.5-flash-002';
/** @deprecated Model `google/gemini-1.5-pro-002` is retired. */
export const MODEL_GOOGLE_GEMINI_1_5_PRO_002 = 'google/gemini-1.5-pro-002';
/** @deprecated Model `google/gemini-2.0-flash` is retired. */
export const MODEL_GOOGLE_GEMINI_2_0_FLASH = 'google/gemini-2.0-flash';
/** @deprecated Model `google/gemini-2.0-flash-lite` is retired. */
export const MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE = 'google/gemini-2.0-flash-lite';
/** @deprecated Model `google/gemini-2.5-flash` is retired. */
export const MODEL_GOOGLE_GEMINI_2_5_FLASH = 'google/gemini-2.5-flash';
/** @deprecated Model `google/gemini-2.5-pro` is retired. */
export const MODEL_GOOGLE_GEMINI_2_5_PRO = 'google/gemini-2.5-pro';
export const MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE = 'google/gemini-3.1-flash-lite';
/** @deprecated Model `google/gemini-3.1-pro` is retired. */
export const MODEL_GOOGLE_GEMINI_3_1_PRO = 'google/gemini-3.1-pro';
/** @deprecated Model `google/gemini-3.8-flash` is retired. */
export const MODEL_GOOGLE_GEMINI_3_8_FLASH = 'google/gemini-3.8-flash';
export const MODEL_GPT_3_5_TURBO = 'gpt-3.5-turbo';
export const MODEL_GPT_3_5_TURBO_0125 = 'gpt-3.5-turbo-0125';
export const MODEL_GPT_3_5_TURBO_1106 = 'gpt-3.5-turbo-1106';
export const MODEL_GPT_3_5_TURBO_16K = 'gpt-3.5-turbo-16k';
export const MODEL_GPT_3_5_TURBO_INSTRUCT = 'gpt-3.5-turbo-instruct';
export const MODEL_GPT_4 = 'gpt-4';
export const MODEL_GPT_4O = 'gpt-4o';
export const MODEL_GPT_4O_2024_05_13 = 'gpt-4o-2024-05-13';
export const MODEL_GPT_4O_2024_08_06 = 'gpt-4o-2024-08-06';
export const MODEL_GPT_4O_2024_11_20 = 'gpt-4o-2024-11-20';
export const MODEL_GPT_4O_MINI = 'gpt-4o-mini';
export const MODEL_GPT_4O_MINI_2024_07_18 = 'gpt-4o-mini-2024-07-18';
export const MODEL_GPT_4O_MINI_SEARCH_PREVIEW = 'gpt-4o-mini-search-preview';
export const MODEL_GPT_4O_MINI_SEARCH_PREVIEW_2025_03_11 = 'gpt-4o-mini-search-preview-2025-03-11';
export const MODEL_GPT_4O_MINI_TRANSCRIBE = 'gpt-4o-mini-transcribe';
export const MODEL_GPT_4O_MINI_TRANSCRIBE_2025_03_20 = 'gpt-4o-mini-transcribe-2025-03-20';
export const MODEL_GPT_4O_MINI_TRANSCRIBE_2025_12_15 = 'gpt-4o-mini-transcribe-2025-12-15';
export const MODEL_GPT_4O_MINI_TTS = 'gpt-4o-mini-tts';
export const MODEL_GPT_4O_MINI_TTS_2025_03_20 = 'gpt-4o-mini-tts-2025-03-20';
export const MODEL_GPT_4O_MINI_TTS_2025_12_15 = 'gpt-4o-mini-tts-2025-12-15';
export const MODEL_GPT_4O_SEARCH_PREVIEW = 'gpt-4o-search-preview';
export const MODEL_GPT_4O_SEARCH_PREVIEW_2025_03_11 = 'gpt-4o-search-preview-2025-03-11';
export const MODEL_GPT_4O_TRANSCRIBE = 'gpt-4o-transcribe';
export const MODEL_GPT_4O_TRANSCRIBE_DIARIZE = 'gpt-4o-transcribe-diarize';
export const MODEL_GPT_4_0613 = 'gpt-4-0613';
export const MODEL_GPT_4_1 = 'gpt-4.1';
export const MODEL_GPT_4_1_2025_04_14 = 'gpt-4.1-2025-04-14';
export const MODEL_GPT_4_1_MINI = 'gpt-4.1-mini';
export const MODEL_GPT_4_1_MINI_2025_04_14 = 'gpt-4.1-mini-2025-04-14';
export const MODEL_GPT_4_1_NANO = 'gpt-4.1-nano';
export const MODEL_GPT_4_1_NANO_2025_04_14 = 'gpt-4.1-nano-2025-04-14';
export const MODEL_GPT_4_TURBO = 'gpt-4-turbo';
export const MODEL_GPT_4_TURBO_2024_04_09 = 'gpt-4-turbo-2024-04-09';
export const MODEL_GPT_5 = 'gpt-5';
export const MODEL_GPT_5_1 = 'gpt-5.1';
export const MODEL_GPT_5_1_2025_11_13 = 'gpt-5.1-2025-11-13';
export const MODEL_GPT_5_1_CHAT_LATEST = 'gpt-5.1-chat-latest';
export const MODEL_GPT_5_2 = 'gpt-5.2';
export const MODEL_GPT_5_2025_08_07 = 'gpt-5-2025-08-07';
export const MODEL_GPT_5_2_2025_12_11 = 'gpt-5.2-2025-12-11';
export const MODEL_GPT_5_2_CHAT_LATEST = 'gpt-5.2-chat-latest';
export const MODEL_GPT_5_2_PRO = 'gpt-5.2-pro';
export const MODEL_GPT_5_2_PRO_2025_12_11 = 'gpt-5.2-pro-2025-12-11';
export const MODEL_GPT_5_3_CHAT_LATEST = 'gpt-5.3-chat-latest';
export const MODEL_GPT_5_3_CODEX = 'gpt-5.3-codex';
export const MODEL_GPT_5_4 = 'gpt-5.4';
export const MODEL_GPT_5_4_2026_03_05 = 'gpt-5.4-2026-03-05';
export const MODEL_GPT_5_4_MINI = 'gpt-5.4-mini';
export const MODEL_GPT_5_4_MINI_2026_03_17 = 'gpt-5.4-mini-2026-03-17';
export const MODEL_GPT_5_4_NANO = 'gpt-5.4-nano';
export const MODEL_GPT_5_4_NANO_2026_03_17 = 'gpt-5.4-nano-2026-03-17';
export const MODEL_GPT_5_4_PRO = 'gpt-5.4-pro';
export const MODEL_GPT_5_4_PRO_2026_03_05 = 'gpt-5.4-pro-2026-03-05';
export const MODEL_GPT_5_5 = 'gpt-5.5';
export const MODEL_GPT_5_5_2026_04_23 = 'gpt-5.5-2026-04-23';
export const MODEL_GPT_5_5_PRO = 'gpt-5.5-pro';
export const MODEL_GPT_5_5_PRO_2026_04_23 = 'gpt-5.5-pro-2026-04-23';
export const MODEL_GPT_5_6_LUNA = 'gpt-5.6-luna';
export const MODEL_GPT_5_6_SOL = 'gpt-5.6-sol';
export const MODEL_GPT_5_6_TERRA = 'gpt-5.6-terra';
export const MODEL_GPT_5_MINI = 'gpt-5-mini';
export const MODEL_GPT_5_MINI_2025_08_07 = 'gpt-5-mini-2025-08-07';
export const MODEL_GPT_5_NANO = 'gpt-5-nano';
export const MODEL_GPT_5_NANO_2025_08_07 = 'gpt-5-nano-2025-08-07';
export const MODEL_GPT_5_PRO = 'gpt-5-pro';
export const MODEL_GPT_5_PRO_2025_10_06 = 'gpt-5-pro-2025-10-06';
export const MODEL_GPT_5_SEARCH_API = 'gpt-5-search-api';
export const MODEL_GPT_5_SEARCH_API_2025_10_14 = 'gpt-5-search-api-2025-10-14';
export const MODEL_GPT_6_1_SOL = 'gpt-6.1-sol';
export const MODEL_GPT_6_ASTRA = 'gpt-6-astra';
export const MODEL_GPT_6_LUNA = 'gpt-6-luna';
export const MODEL_GPT_6_SOL = 'gpt-6-sol';
export const MODEL_GPT_AUDIO = 'gpt-audio';
export const MODEL_GPT_AUDIO_1_5 = 'gpt-audio-1.5';
export const MODEL_GPT_AUDIO_2025_08_28 = 'gpt-audio-2025-08-28';
export const MODEL_GPT_AUDIO_MINI = 'gpt-audio-mini';
export const MODEL_GPT_AUDIO_MINI_2025_12_15 = 'gpt-audio-mini-2025-12-15';
export const MODEL_GPT_IMAGE_1 = 'gpt-image-1';
export const MODEL_GPT_IMAGE_1_5 = 'gpt-image-1.5';
export const MODEL_GPT_IMAGE_1_MINI = 'gpt-image-1-mini';
export const MODEL_GPT_IMAGE_2 = 'gpt-image-2';
export const MODEL_GPT_IMAGE_2_2026_04_21 = 'gpt-image-2-2026-04-21';
export const MODEL_GPT_IMAGE_2_5_FLARE = 'gpt-image-2.5-flare';
export const MODEL_GPT_IMAGE_2_5_FLARE_2026_09_08 = 'gpt-image-2.5-flare-2026-09-08';
export const MODEL_GPT_IMAGE_2_5_SUNBURST = 'gpt-image-2.5-sunburst';
export const MODEL_GPT_IMAGE_2_5_SUNBURST_2026_09_08 = 'gpt-image-2.5-sunburst-2026-09-08';
export const MODEL_GPT_LIVE_TRANSCRIBE = 'gpt-live-transcribe';
export const MODEL_GPT_OSS_120B_1 = 'gpt-oss-120b-1';
export const MODEL_GPT_OSS_120B_MAAS = 'gpt-oss-120b-maas';
export const MODEL_GPT_OSS_20B_1 = 'gpt-oss-20b-1';
export const MODEL_GPT_OSS_SAFEGUARD_120B = 'gpt-oss-safeguard-120b';
export const MODEL_GPT_OSS_SAFEGUARD_20B = 'gpt-oss-safeguard-20b';
export const MODEL_GPT_TRANSCRIBE = 'gpt-transcribe';
export const MODEL_GROK_4_1_FAST_NON_REASONING = 'grok-4-1-fast-non-reasoning';
export const MODEL_GROK_4_1_FAST_REASONING = 'grok-4-1-fast-reasoning';
export const MODEL_KIMI_K2_5 = 'kimi-k2.5';
export const MODEL_KIMI_K2_7_CODE = 'kimi-k2.7-code';
export const MODEL_KIMI_K2_THINKING = 'kimi-k2-thinking';
export const MODEL_KIMI_K2_THINKING_MAAS = 'kimi-k2-thinking-maas';
export const MODEL_KIMI_K3 = 'kimi-k3';
export const MODEL_KIMI_KIMI_K3 = 'kimi/kimi-k3';
export const MODEL_LLAMA3_1_70B_INSTRUCT = 'llama3-1-70b-instruct';
export const MODEL_LLAMA3_1_8B_INSTRUCT = 'llama3-1-8b-instruct';
export const MODEL_LLAMA3_3_70B_INSTRUCT = 'llama3-3-70b-instruct';
export const MODEL_LLAMA4_MAVERICK_17B_INSTRUCT = 'llama4-maverick-17b-instruct';
export const MODEL_LLAMA4_SCOUT_17B_INSTRUCT = 'llama4-scout-17b-instruct';
export const MODEL_LLAMA_3_3_70B_INSTRUCT = 'Llama-3.3-70B-Instruct';
export const MODEL_LLAMA_4_MAVERICK_17B_128E_INSTRUCT_FP8 = 'Llama-4-Maverick-17B-128E-Instruct-FP8';
export const MODEL_LLAMA_4_SCOUT_17B_16E_INSTRUCT = 'Llama-4-Scout-17B-16E-Instruct';
export const MODEL_MAGISTRAL_SMALL_2509 = 'magistral-small-2509';
/** @deprecated Model `meta/llama-3.1-70b-instruct` is retired. */
export const MODEL_META_LLAMA_3_1_70B_INSTRUCT = 'meta/llama-3.1-70b-instruct';
/** @deprecated Model `meta/llama-3.1-8b-instruct` is retired. */
export const MODEL_META_LLAMA_3_1_8B_INSTRUCT = 'meta/llama-3.1-8b-instruct';
/** @deprecated Model `meta/llama-3.2-11b-vision-instruct` is retired; compatibility alias for `MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT`. */
export const MODEL_META_LLAMA_3_2_11B_VISION = 'meta/llama-3.2-11b-vision-instruct';
/** @deprecated Model `meta/llama-3.2-11b-vision-instruct` is retired. */
export const MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT = 'meta/llama-3.2-11b-vision-instruct';
/** @deprecated Model `meta/llama-3.2-1b-instruct` is retired. */
export const MODEL_META_LLAMA_3_2_1B_INSTRUCT = 'meta/llama-3.2-1b-instruct';
/** @deprecated Model `meta/llama-3.2-3b-instruct` is retired. */
export const MODEL_META_LLAMA_3_2_3B_INSTRUCT = 'meta/llama-3.2-3b-instruct';
/** @deprecated Model `meta/llama-3.2-90b-vision-instruct` is retired; compatibility alias for `MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT`. */
export const MODEL_META_LLAMA_3_2_90B_VISION = 'meta/llama-3.2-90b-vision-instruct';
/** @deprecated Model `meta/llama-3.2-90b-vision-instruct` is retired. */
export const MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT = 'meta/llama-3.2-90b-vision-instruct';
/** @deprecated Model `meta/llama-3.3-70b-instruct` is retired. */
export const MODEL_META_LLAMA_3_3_70B_INSTRUCT = 'meta/llama-3.3-70b-instruct';
export const MODEL_MINIMAX_M2 = 'minimax-m2';
export const MODEL_MINIMAX_M2_1 = 'minimax-m2.1';
export const MODEL_MINIMAX_M2_5 = 'minimax-m2.5';
export const MODEL_MINIMAX_M2_MAAS = 'minimax-m2-maas';
export const MODEL_MINISTRAL_3_14B_INSTRUCT = 'ministral-3-14b-instruct';
export const MODEL_MINISTRAL_3_3B_INSTRUCT = 'ministral-3-3b-instruct';
export const MODEL_MINISTRAL_3_8B_INSTRUCT = 'ministral-3-8b-instruct';
export const MODEL_MISTRAL_LARGE_3_675B_INSTRUCT = 'mistral-large-3-675b-instruct';
export const MODEL_MISTRAL_MEDIUM_2505 = 'mistral-medium-2505';
export const MODEL_MISTRAL_SMALL_2503 = 'mistral-small-2503';
export const MODEL_NEMOTRON_NANO_12B_V2 = 'nemotron-nano-12b-v2';
export const MODEL_NEMOTRON_NANO_3_30B = 'nemotron-nano-3-30b';
export const MODEL_NEMOTRON_NANO_9B_V2 = 'nemotron-nano-9b-v2';
export const MODEL_NEMOTRON_SUPER_3_120B = 'nemotron-super-3-120b';
export const MODEL_NOVA_2_LITE = 'nova-2-lite';
export const MODEL_NOVA_LITE = 'nova-lite';
export const MODEL_O1 = 'o1';
export const MODEL_O1_2024_12_17 = 'o1-2024-12-17';
export const MODEL_O1_PRO = 'o1-pro';
export const MODEL_O1_PRO_2025_03_19 = 'o1-pro-2025-03-19';
export const MODEL_O3 = 'o3';
export const MODEL_O3_2025_04_16 = 'o3-2025-04-16';
export const MODEL_O3_MINI = 'o3-mini';
export const MODEL_O3_MINI_2025_01_31 = 'o3-mini-2025-01-31';
export const MODEL_O4_MINI = 'o4-mini';
export const MODEL_O4_MINI_2025_04_16 = 'o4-mini-2025-04-16';
export const MODEL_PALMYRA_VISION_7B = 'palmyra-vision-7b';
export const MODEL_PHI_4 = 'Phi-4';
export const MODEL_PHI_4_MINI_INSTRUCT = 'Phi-4-mini-instruct';
export const MODEL_PHI_4_MINI_REASONING = 'Phi-4-mini-reasoning';
export const MODEL_PHI_4_MULTIMODAL_INSTRUCT = 'Phi-4-multimodal-instruct';
export const MODEL_PHI_4_REASONING = 'Phi-4-reasoning';
export const MODEL_PIXTRAL_LARGE_2502 = 'pixtral-large-2502';
export const MODEL_QWEN2_7B_INSTRUCT = 'qwen2-7b-instruct';
export const MODEL_QWEN3_235B_A22B_2507 = 'qwen3-235b-a22b-2507';
export const MODEL_QWEN3_235B_A22B_INSTRUCT_2507_MAAS = 'qwen3-235b-a22b-instruct-2507-maas';
export const MODEL_QWEN3_32B = 'qwen3-32b';
export const MODEL_QWEN3_5_122B_A10B = 'qwen3.5-122b-a10b';
export const MODEL_QWEN3_5_27B = 'qwen3.5-27b';
export const MODEL_QWEN3_5_35B_A3B = 'qwen3.5-35b-a3b';
export const MODEL_QWEN3_5_397B_A17B = 'qwen3.5-397b-a17b';
export const MODEL_QWEN3_5_FLASH = 'qwen3.5-flash';
export const MODEL_QWEN3_5_FLASH_2026_02_23 = 'qwen3.5-flash-2026-02-23';
export const MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME = 'qwen3.5-livetranslate-flash-realtime';
export const MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME_2026_05_19 = 'qwen3.5-livetranslate-flash-realtime-2026-05-19';
export const MODEL_QWEN3_5_OMNI_FLASH = 'qwen3.5-omni-flash';
export const MODEL_QWEN3_5_OMNI_FLASH_2026_03_15 = 'qwen3.5-omni-flash-2026-03-15';
export const MODEL_QWEN3_5_OMNI_FLASH_REALTIME = 'qwen3.5-omni-flash-realtime';
export const MODEL_QWEN3_5_OMNI_FLASH_REALTIME_2026_03_15 = 'qwen3.5-omni-flash-realtime-2026-03-15';
export const MODEL_QWEN3_5_OMNI_PLUS = 'qwen3.5-omni-plus';
export const MODEL_QWEN3_5_OMNI_PLUS_2026_03_15 = 'qwen3.5-omni-plus-2026-03-15';
export const MODEL_QWEN3_5_OMNI_PLUS_REALTIME = 'qwen3.5-omni-plus-realtime';
export const MODEL_QWEN3_5_OMNI_PLUS_REALTIME_2026_03_15 = 'qwen3.5-omni-plus-realtime-2026-03-15';
export const MODEL_QWEN3_5_PLUS = 'qwen3.5-plus';
export const MODEL_QWEN3_5_PLUS_2026_02_15 = 'qwen3.5-plus-2026-02-15';
export const MODEL_QWEN3_5_PLUS_2026_04_20 = 'qwen3.5-plus-2026-04-20';
export const MODEL_QWEN3_6_27B = 'qwen3.6-27b';
export const MODEL_QWEN3_6_35B_A3B = 'qwen3.6-35b-a3b';
export const MODEL_QWEN3_6_FLASH = 'qwen3.6-flash';
export const MODEL_QWEN3_6_FLASH_2026_04_16 = 'qwen3.6-flash-2026-04-16';
export const MODEL_QWEN3_6_PLUS = 'qwen3.6-plus';
export const MODEL_QWEN3_6_PLUS_2026_04_02 = 'qwen3.6-plus-2026-04-02';
export const MODEL_QWEN3_7_FLASH = 'qwen3.7-flash';
export const MODEL_QWEN3_7_FLASH_2026_07_15 = 'qwen3.7-flash-2026-07-15';
export const MODEL_QWEN3_7_MAX = 'qwen3.7-max';
export const MODEL_QWEN3_7_MAX_2026_05_17 = 'qwen3.7-max-2026-05-17';
export const MODEL_QWEN3_7_MAX_2026_05_20 = 'qwen3.7-max-2026-05-20';
export const MODEL_QWEN3_7_MAX_2026_06_08 = 'qwen3.7-max-2026-06-08';
export const MODEL_QWEN3_7_MAX_PREVIEW = 'qwen3.7-max-preview';
export const MODEL_QWEN3_7_PLUS = 'qwen3.7-plus';
export const MODEL_QWEN3_7_PLUS_2026_05_26 = 'qwen3.7-plus-2026-05-26';
export const MODEL_QWEN3_8_27B = 'qwen3.8-27b';
export const MODEL_QWEN3_8_2_4T_A95B = 'qwen3.8-2.4t-a95b';
export const MODEL_QWEN3_8_FLASH = 'qwen3.8-flash';
export const MODEL_QWEN3_8_LIVETRANSLATE_FLASH_REALTIME = 'qwen3.8-livetranslate-flash-realtime';
export const MODEL_QWEN3_8_MAX = 'qwen3.8-max';
export const MODEL_QWEN3_8_MAX_0902 = 'qwen3.8-max-0902';
export const MODEL_QWEN3_8_OMNI_FLASH = 'qwen3.8-omni-flash';
export const MODEL_QWEN3_CODER_30B_A3B = 'qwen3-coder-30b-a3b';
export const MODEL_QWEN3_CODER_480B_A35B = 'qwen3-coder-480b-a35b';
export const MODEL_QWEN3_CODER_480B_A35B_INSTRUCT_MAAS = 'qwen3-coder-480b-a35b-instruct-maas';
export const MODEL_QWEN3_CODER_FLASH = 'qwen3-coder-flash';
export const MODEL_QWEN3_LIVETRANSLATE_FLASH = 'qwen3-livetranslate-flash';
export const MODEL_QWEN3_LIVETRANSLATE_FLASH_2025_12_01 = 'qwen3-livetranslate-flash-2025-12-01';
export const MODEL_QWEN3_NEXT_80B_A3B = 'qwen3-next-80b-a3b';
export const MODEL_QWEN3_NEXT_80B_A3B_INSTRUCT_MAAS = 'qwen3-next-80b-a3b-instruct-maas';
export const MODEL_QWEN3_NEXT_80B_A3B_THINKING_MAAS = 'qwen3-next-80b-a3b-thinking-maas';
export const MODEL_QWEN3_OMNI_FLASH = 'qwen3-omni-flash';
export const MODEL_QWEN3_OMNI_FLASH_REALTIME_2025_09_15 = 'qwen3-omni-flash-realtime-2025-09-15';
export const MODEL_QWEN3_S2S_FLASH_REALTIME = 'qwen3-s2s-flash-realtime';
export const MODEL_QWEN3_VL_235B_A22B = 'qwen3-vl-235b-a22b';
export const MODEL_QWEN3_VL_PLUS = 'qwen3-vl-plus';
export const MODEL_QWEN_FLASH = 'qwen-flash';
export const MODEL_QWEN_FLASH_CHARACTER = 'qwen-flash-character';
export const MODEL_QWEN_MAX = 'qwen-max';
export const MODEL_QWEN_MT_FLASH = 'qwen-mt-flash';
export const MODEL_QWEN_MT_LITE = 'qwen-mt-lite';
export const MODEL_QWEN_MT_PLUS = 'qwen-mt-plus';
export const MODEL_QWEN_PLUS = 'qwen-plus';
export const MODEL_QWEN_PLUS_2025_01_25 = 'qwen-plus-2025-01-25';
export const MODEL_QWEN_PLUS_2025_04_28 = 'qwen-plus-2025-04-28';
export const MODEL_QWEN_PLUS_2025_07_14 = 'qwen-plus-2025-07-14';
export const MODEL_QWEN_PLUS_2025_12_01 = 'qwen-plus-2025-12-01';
export const MODEL_QWEN_PLUS_CHARACTER = 'qwen-plus-character';
export const MODEL_QWEN_PLUS_LATEST = 'qwen-plus-latest';
export const MODEL_QWEN_TURBO = 'qwen-turbo';
export const MODEL_QWEN_VL_OCR_2025_11_20 = 'qwen-vl-ocr-2025-11-20';
export const MODEL_QWQ_PLUS_2025_03_05 = 'qwq-plus-2025-03-05';
export const MODEL_R1 = 'r1';
export const MODEL_SORA_2 = 'sora-2';
export const MODEL_SORA_2_PRO = 'sora-2-pro';
export const MODEL_TEXT_EMBEDDING_3_LARGE = 'text-embedding-3-large';
export const MODEL_TEXT_EMBEDDING_3_SMALL = 'text-embedding-3-small';
export const MODEL_TEXT_EMBEDDING_ADA_002 = 'text-embedding-ada-002';
export const MODEL_TTS_1 = 'tts-1';
export const MODEL_TTS_1_1106 = 'tts-1-1106';
export const MODEL_TTS_1_HD = 'tts-1-hd';
export const MODEL_TTS_1_HD_1106 = 'tts-1-hd-1106';
export const MODEL_TYPESAFE_JEV = 'typesafe/jev';
/** @deprecated Compatibility alias; use `MODEL_TYPESAFE_JEV` instead. */
export const MODEL_TYPESAFE_JEV_SYSTEM_ONE = 'typesafe/jev';
export const MODEL_V3 = 'v3';
export const MODEL_V3_2 = 'v3.2';
export const MODEL_VOXTRAL_MINI_3B_2507 = 'voxtral-mini-3b-2507';
export const MODEL_VOXTRAL_SMALL_24B_2507 = 'voxtral-small-24b-2507';
export const MODEL_WHISPER_1 = 'whisper-1';
export const MODEL_ZHIPU_GLM_5_3 = 'ZHIPU/GLM-5.3';

export const MODELS = {
  AMAZON_NOVA_LITE_V1: MODEL_AMAZON_NOVA_LITE_V1,
  AMAZON_NOVA_MICRO_V1: MODEL_AMAZON_NOVA_MICRO_V1,
  AMAZON_NOVA_PRO_V1: MODEL_AMAZON_NOVA_PRO_V1,
  CHATGPT_IMAGE_LATEST: MODEL_CHATGPT_IMAGE_LATEST,
  CHAT_LATEST: MODEL_CHAT_LATEST,
  CLAUDE_3_7_SONNET: MODEL_CLAUDE_3_7_SONNET,
  CLAUDE_FABLE_5: MODEL_CLAUDE_FABLE_5,
  CLAUDE_FABLE_5_1: MODEL_CLAUDE_FABLE_5_1,
  CLAUDE_HAIKU_4_5_20251001: MODEL_CLAUDE_HAIKU_4_5_20251001,
  CLAUDE_OPUS_4_5_20251101: MODEL_CLAUDE_OPUS_4_5_20251101,
  CLAUDE_OPUS_4_6: MODEL_CLAUDE_OPUS_4_6,
  CLAUDE_OPUS_4_7: MODEL_CLAUDE_OPUS_4_7,
  CLAUDE_OPUS_4_8: MODEL_CLAUDE_OPUS_4_8,
  CLAUDE_OPUS_5: MODEL_CLAUDE_OPUS_5,
  CLAUDE_OPUS_5_5: MODEL_CLAUDE_OPUS_5_5,
  CLAUDE_SONNET_4_5: MODEL_CLAUDE_SONNET_4_5,
  CLAUDE_SONNET_4_5_20250929: MODEL_CLAUDE_SONNET_4_5_20250929,
  CLAUDE_SONNET_4_6: MODEL_CLAUDE_SONNET_4_6,
  CLAUDE_SONNET_5: MODEL_CLAUDE_SONNET_5,
  CLAUDE_SONNET_5_5: MODEL_CLAUDE_SONNET_5_5,
  DEEPSEEK_R1_0528_MAAS: MODEL_DEEPSEEK_R1_0528_MAAS,
  DEEPSEEK_V3_2_MAAS: MODEL_DEEPSEEK_V3_2_MAAS,
  DEEPSEEK_V4_1_FLASH: MODEL_DEEPSEEK_V4_1_FLASH,
  DEEPSEEK_V4_FLASH_0731: MODEL_DEEPSEEK_V4_FLASH_0731,
  DEEPSEEK_V4_PRO: MODEL_DEEPSEEK_V4_PRO,
  DEEPSEEK_V4_PRO_0813: MODEL_DEEPSEEK_V4_PRO_0813,
  DEVSTRAL_2_123B: MODEL_DEVSTRAL_2_123B,
  GEMINI_1_5_FLASH_002: MODEL_GEMINI_1_5_FLASH_002,
  GEMINI_1_5_PRO_002: MODEL_GEMINI_1_5_PRO_002,
  GEMINI_2_0_FLASH: MODEL_GEMINI_2_0_FLASH,
  GEMINI_2_0_FLASH_LITE: MODEL_GEMINI_2_0_FLASH_LITE,
  /** @deprecated Compatibility alias; use `GOOGLE_GEMINI_2_5_FLASH` instead. */
  GEMINI_2_5_FLASH: 'gemini-2.5-flash',
  /** @deprecated Compatibility alias; use `GOOGLE_GEMINI_2_5_PRO` instead. */
  GEMINI_2_5_PRO: 'gemini-2.5-pro',
  GEMINI_3_1_FLASH_LITE: MODEL_GEMINI_3_1_FLASH_LITE,
  GEMINI_3_1_PRO: MODEL_GEMINI_3_1_PRO,
  GEMINI_3_1_PRO_PREVIEW: MODEL_GEMINI_3_1_PRO_PREVIEW,
  GEMINI_3_5_FLASH: MODEL_GEMINI_3_5_FLASH,
  GEMINI_3_5_FLASH_LITE: MODEL_GEMINI_3_5_FLASH_LITE,
  GEMINI_3_5_LIVE_TRANSLATE_PREVIEW: MODEL_GEMINI_3_5_LIVE_TRANSLATE_PREVIEW,
  GEMINI_3_6_FLASH: MODEL_GEMINI_3_6_FLASH,
  GEMINI_3_7_FLASH: MODEL_GEMINI_3_7_FLASH,
  GEMINI_3_8_FLASH: MODEL_GEMINI_3_8_FLASH,
  GEMINI_3_FLASH_PREVIEW: MODEL_GEMINI_3_FLASH_PREVIEW,
  GEMMA_3_12B_IT: MODEL_GEMMA_3_12B_IT,
  GEMMA_3_27B_IT: MODEL_GEMMA_3_27B_IT,
  GEMMA_3_4B_IT: MODEL_GEMMA_3_4B_IT,
  GLM_4_7: MODEL_GLM_4_7,
  GLM_4_7_FLASH: MODEL_GLM_4_7_FLASH,
  GLM_4_7_MAAS: MODEL_GLM_4_7_MAAS,
  GLM_5: MODEL_GLM_5,
  GLM_5_1: MODEL_GLM_5_1,
  GLM_5_2: MODEL_GLM_5_2,
  GLM_5_2_FAST_PREVIEW: MODEL_GLM_5_2_FAST_PREVIEW,
  GLM_5_2_MAAS: MODEL_GLM_5_2_MAAS,
  GLM_5_3: MODEL_GLM_5_3,
  GLM_5_3_PRIME: MODEL_GLM_5_3_PRIME,
  GLM_5_MAAS: MODEL_GLM_5_MAAS,
  GLOBAL_AMAZON_NOVA_2_LITE_V1_0: MODEL_GLOBAL_AMAZON_NOVA_2_LITE_V1_0,
  GOOGLE_GEMINI_1_5_FLASH_002: MODEL_GOOGLE_GEMINI_1_5_FLASH_002,
  GOOGLE_GEMINI_1_5_PRO_002: MODEL_GOOGLE_GEMINI_1_5_PRO_002,
  GOOGLE_GEMINI_2_0_FLASH: MODEL_GOOGLE_GEMINI_2_0_FLASH,
  GOOGLE_GEMINI_2_0_FLASH_LITE: MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE,
  GOOGLE_GEMINI_2_5_FLASH: MODEL_GOOGLE_GEMINI_2_5_FLASH,
  GOOGLE_GEMINI_2_5_PRO: MODEL_GOOGLE_GEMINI_2_5_PRO,
  GOOGLE_GEMINI_3_1_FLASH_LITE: MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE,
  GOOGLE_GEMINI_3_1_PRO: MODEL_GOOGLE_GEMINI_3_1_PRO,
  GOOGLE_GEMINI_3_8_FLASH: MODEL_GOOGLE_GEMINI_3_8_FLASH,
  GPT_3_5_TURBO: MODEL_GPT_3_5_TURBO,
  GPT_3_5_TURBO_0125: MODEL_GPT_3_5_TURBO_0125,
  GPT_3_5_TURBO_1106: MODEL_GPT_3_5_TURBO_1106,
  GPT_3_5_TURBO_16K: MODEL_GPT_3_5_TURBO_16K,
  GPT_3_5_TURBO_INSTRUCT: MODEL_GPT_3_5_TURBO_INSTRUCT,
  GPT_4: MODEL_GPT_4,
  GPT_4O: MODEL_GPT_4O,
  GPT_4O_2024_05_13: MODEL_GPT_4O_2024_05_13,
  GPT_4O_2024_08_06: MODEL_GPT_4O_2024_08_06,
  GPT_4O_2024_11_20: MODEL_GPT_4O_2024_11_20,
  GPT_4O_MINI: MODEL_GPT_4O_MINI,
  GPT_4O_MINI_2024_07_18: MODEL_GPT_4O_MINI_2024_07_18,
  GPT_4O_MINI_SEARCH_PREVIEW: MODEL_GPT_4O_MINI_SEARCH_PREVIEW,
  GPT_4O_MINI_SEARCH_PREVIEW_2025_03_11: MODEL_GPT_4O_MINI_SEARCH_PREVIEW_2025_03_11,
  GPT_4O_MINI_TRANSCRIBE: MODEL_GPT_4O_MINI_TRANSCRIBE,
  GPT_4O_MINI_TRANSCRIBE_2025_03_20: MODEL_GPT_4O_MINI_TRANSCRIBE_2025_03_20,
  GPT_4O_MINI_TRANSCRIBE_2025_12_15: MODEL_GPT_4O_MINI_TRANSCRIBE_2025_12_15,
  GPT_4O_MINI_TTS: MODEL_GPT_4O_MINI_TTS,
  GPT_4O_MINI_TTS_2025_03_20: MODEL_GPT_4O_MINI_TTS_2025_03_20,
  GPT_4O_MINI_TTS_2025_12_15: MODEL_GPT_4O_MINI_TTS_2025_12_15,
  GPT_4O_SEARCH_PREVIEW: MODEL_GPT_4O_SEARCH_PREVIEW,
  GPT_4O_SEARCH_PREVIEW_2025_03_11: MODEL_GPT_4O_SEARCH_PREVIEW_2025_03_11,
  GPT_4O_TRANSCRIBE: MODEL_GPT_4O_TRANSCRIBE,
  GPT_4O_TRANSCRIBE_DIARIZE: MODEL_GPT_4O_TRANSCRIBE_DIARIZE,
  GPT_4_0613: MODEL_GPT_4_0613,
  GPT_4_1: MODEL_GPT_4_1,
  GPT_4_1_2025_04_14: MODEL_GPT_4_1_2025_04_14,
  GPT_4_1_MINI: MODEL_GPT_4_1_MINI,
  GPT_4_1_MINI_2025_04_14: MODEL_GPT_4_1_MINI_2025_04_14,
  GPT_4_1_NANO: MODEL_GPT_4_1_NANO,
  GPT_4_1_NANO_2025_04_14: MODEL_GPT_4_1_NANO_2025_04_14,
  GPT_4_TURBO: MODEL_GPT_4_TURBO,
  GPT_4_TURBO_2024_04_09: MODEL_GPT_4_TURBO_2024_04_09,
  GPT_5: MODEL_GPT_5,
  GPT_5_1: MODEL_GPT_5_1,
  GPT_5_1_2025_11_13: MODEL_GPT_5_1_2025_11_13,
  GPT_5_1_CHAT_LATEST: MODEL_GPT_5_1_CHAT_LATEST,
  GPT_5_2: MODEL_GPT_5_2,
  GPT_5_2025_08_07: MODEL_GPT_5_2025_08_07,
  GPT_5_2_2025_12_11: MODEL_GPT_5_2_2025_12_11,
  GPT_5_2_CHAT_LATEST: MODEL_GPT_5_2_CHAT_LATEST,
  GPT_5_2_PRO: MODEL_GPT_5_2_PRO,
  GPT_5_2_PRO_2025_12_11: MODEL_GPT_5_2_PRO_2025_12_11,
  GPT_5_3_CHAT_LATEST: MODEL_GPT_5_3_CHAT_LATEST,
  GPT_5_3_CODEX: MODEL_GPT_5_3_CODEX,
  GPT_5_4: MODEL_GPT_5_4,
  GPT_5_4_2026_03_05: MODEL_GPT_5_4_2026_03_05,
  GPT_5_4_MINI: MODEL_GPT_5_4_MINI,
  GPT_5_4_MINI_2026_03_17: MODEL_GPT_5_4_MINI_2026_03_17,
  GPT_5_4_NANO: MODEL_GPT_5_4_NANO,
  GPT_5_4_NANO_2026_03_17: MODEL_GPT_5_4_NANO_2026_03_17,
  GPT_5_4_PRO: MODEL_GPT_5_4_PRO,
  GPT_5_4_PRO_2026_03_05: MODEL_GPT_5_4_PRO_2026_03_05,
  GPT_5_5: MODEL_GPT_5_5,
  GPT_5_5_2026_04_23: MODEL_GPT_5_5_2026_04_23,
  GPT_5_5_PRO: MODEL_GPT_5_5_PRO,
  GPT_5_5_PRO_2026_04_23: MODEL_GPT_5_5_PRO_2026_04_23,
  GPT_5_6_LUNA: MODEL_GPT_5_6_LUNA,
  GPT_5_6_SOL: MODEL_GPT_5_6_SOL,
  GPT_5_6_TERRA: MODEL_GPT_5_6_TERRA,
  GPT_5_MINI: MODEL_GPT_5_MINI,
  GPT_5_MINI_2025_08_07: MODEL_GPT_5_MINI_2025_08_07,
  GPT_5_NANO: MODEL_GPT_5_NANO,
  GPT_5_NANO_2025_08_07: MODEL_GPT_5_NANO_2025_08_07,
  GPT_5_PRO: MODEL_GPT_5_PRO,
  GPT_5_PRO_2025_10_06: MODEL_GPT_5_PRO_2025_10_06,
  GPT_5_SEARCH_API: MODEL_GPT_5_SEARCH_API,
  GPT_5_SEARCH_API_2025_10_14: MODEL_GPT_5_SEARCH_API_2025_10_14,
  GPT_6_1_SOL: MODEL_GPT_6_1_SOL,
  GPT_6_ASTRA: MODEL_GPT_6_ASTRA,
  GPT_6_LUNA: MODEL_GPT_6_LUNA,
  GPT_6_SOL: MODEL_GPT_6_SOL,
  GPT_AUDIO: MODEL_GPT_AUDIO,
  GPT_AUDIO_1_5: MODEL_GPT_AUDIO_1_5,
  GPT_AUDIO_2025_08_28: MODEL_GPT_AUDIO_2025_08_28,
  GPT_AUDIO_MINI: MODEL_GPT_AUDIO_MINI,
  GPT_AUDIO_MINI_2025_12_15: MODEL_GPT_AUDIO_MINI_2025_12_15,
  GPT_IMAGE_1: MODEL_GPT_IMAGE_1,
  GPT_IMAGE_1_5: MODEL_GPT_IMAGE_1_5,
  GPT_IMAGE_1_MINI: MODEL_GPT_IMAGE_1_MINI,
  GPT_IMAGE_2: MODEL_GPT_IMAGE_2,
  GPT_IMAGE_2_2026_04_21: MODEL_GPT_IMAGE_2_2026_04_21,
  GPT_IMAGE_2_5_FLARE: MODEL_GPT_IMAGE_2_5_FLARE,
  GPT_IMAGE_2_5_FLARE_2026_09_08: MODEL_GPT_IMAGE_2_5_FLARE_2026_09_08,
  GPT_IMAGE_2_5_SUNBURST: MODEL_GPT_IMAGE_2_5_SUNBURST,
  GPT_IMAGE_2_5_SUNBURST_2026_09_08: MODEL_GPT_IMAGE_2_5_SUNBURST_2026_09_08,
  GPT_LIVE_TRANSCRIBE: MODEL_GPT_LIVE_TRANSCRIBE,
  GPT_OSS_120B_1: MODEL_GPT_OSS_120B_1,
  GPT_OSS_120B_MAAS: MODEL_GPT_OSS_120B_MAAS,
  GPT_OSS_20B_1: MODEL_GPT_OSS_20B_1,
  GPT_OSS_SAFEGUARD_120B: MODEL_GPT_OSS_SAFEGUARD_120B,
  GPT_OSS_SAFEGUARD_20B: MODEL_GPT_OSS_SAFEGUARD_20B,
  GPT_TRANSCRIBE: MODEL_GPT_TRANSCRIBE,
  GROK_4_1_FAST_NON_REASONING: MODEL_GROK_4_1_FAST_NON_REASONING,
  GROK_4_1_FAST_REASONING: MODEL_GROK_4_1_FAST_REASONING,
  KIMI_K2_5: MODEL_KIMI_K2_5,
  KIMI_K2_7_CODE: MODEL_KIMI_K2_7_CODE,
  KIMI_K2_THINKING: MODEL_KIMI_K2_THINKING,
  KIMI_K2_THINKING_MAAS: MODEL_KIMI_K2_THINKING_MAAS,
  KIMI_K3: MODEL_KIMI_K3,
  KIMI_KIMI_K3: MODEL_KIMI_KIMI_K3,
  LLAMA3_1_70B_INSTRUCT: MODEL_LLAMA3_1_70B_INSTRUCT,
  LLAMA3_1_8B_INSTRUCT: MODEL_LLAMA3_1_8B_INSTRUCT,
  LLAMA3_3_70B_INSTRUCT: MODEL_LLAMA3_3_70B_INSTRUCT,
  LLAMA4_MAVERICK_17B_INSTRUCT: MODEL_LLAMA4_MAVERICK_17B_INSTRUCT,
  LLAMA4_SCOUT_17B_INSTRUCT: MODEL_LLAMA4_SCOUT_17B_INSTRUCT,
  LLAMA_3_3_70B_INSTRUCT: MODEL_LLAMA_3_3_70B_INSTRUCT,
  LLAMA_4_MAVERICK_17B_128E_INSTRUCT_FP8: MODEL_LLAMA_4_MAVERICK_17B_128E_INSTRUCT_FP8,
  LLAMA_4_SCOUT_17B_16E_INSTRUCT: MODEL_LLAMA_4_SCOUT_17B_16E_INSTRUCT,
  MAGISTRAL_SMALL_2509: MODEL_MAGISTRAL_SMALL_2509,
  META_LLAMA_3_1_70B_INSTRUCT: MODEL_META_LLAMA_3_1_70B_INSTRUCT,
  META_LLAMA_3_1_8B_INSTRUCT: MODEL_META_LLAMA_3_1_8B_INSTRUCT,
  META_LLAMA_3_2_11B_VISION: MODEL_META_LLAMA_3_2_11B_VISION,
  META_LLAMA_3_2_11B_VISION_INSTRUCT: MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT,
  META_LLAMA_3_2_1B_INSTRUCT: MODEL_META_LLAMA_3_2_1B_INSTRUCT,
  META_LLAMA_3_2_3B_INSTRUCT: MODEL_META_LLAMA_3_2_3B_INSTRUCT,
  META_LLAMA_3_2_90B_VISION: MODEL_META_LLAMA_3_2_90B_VISION,
  META_LLAMA_3_2_90B_VISION_INSTRUCT: MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT,
  META_LLAMA_3_3_70B_INSTRUCT: MODEL_META_LLAMA_3_3_70B_INSTRUCT,
  MINIMAX_M2: MODEL_MINIMAX_M2,
  MINIMAX_M2_1: MODEL_MINIMAX_M2_1,
  MINIMAX_M2_5: MODEL_MINIMAX_M2_5,
  MINIMAX_M2_MAAS: MODEL_MINIMAX_M2_MAAS,
  MINISTRAL_3_14B_INSTRUCT: MODEL_MINISTRAL_3_14B_INSTRUCT,
  MINISTRAL_3_3B_INSTRUCT: MODEL_MINISTRAL_3_3B_INSTRUCT,
  MINISTRAL_3_8B_INSTRUCT: MODEL_MINISTRAL_3_8B_INSTRUCT,
  MISTRAL_LARGE_3_675B_INSTRUCT: MODEL_MISTRAL_LARGE_3_675B_INSTRUCT,
  MISTRAL_MEDIUM_2505: MODEL_MISTRAL_MEDIUM_2505,
  MISTRAL_SMALL_2503: MODEL_MISTRAL_SMALL_2503,
  NEMOTRON_NANO_12B_V2: MODEL_NEMOTRON_NANO_12B_V2,
  NEMOTRON_NANO_3_30B: MODEL_NEMOTRON_NANO_3_30B,
  NEMOTRON_NANO_9B_V2: MODEL_NEMOTRON_NANO_9B_V2,
  NEMOTRON_SUPER_3_120B: MODEL_NEMOTRON_SUPER_3_120B,
  NOVA_2_LITE: MODEL_NOVA_2_LITE,
  NOVA_LITE: MODEL_NOVA_LITE,
  O1: MODEL_O1,
  O1_2024_12_17: MODEL_O1_2024_12_17,
  O1_PRO: MODEL_O1_PRO,
  O1_PRO_2025_03_19: MODEL_O1_PRO_2025_03_19,
  O3: MODEL_O3,
  O3_2025_04_16: MODEL_O3_2025_04_16,
  O3_MINI: MODEL_O3_MINI,
  O3_MINI_2025_01_31: MODEL_O3_MINI_2025_01_31,
  O4_MINI: MODEL_O4_MINI,
  O4_MINI_2025_04_16: MODEL_O4_MINI_2025_04_16,
  PALMYRA_VISION_7B: MODEL_PALMYRA_VISION_7B,
  PHI_4: MODEL_PHI_4,
  PHI_4_MINI_INSTRUCT: MODEL_PHI_4_MINI_INSTRUCT,
  PHI_4_MINI_REASONING: MODEL_PHI_4_MINI_REASONING,
  PHI_4_MULTIMODAL_INSTRUCT: MODEL_PHI_4_MULTIMODAL_INSTRUCT,
  PHI_4_REASONING: MODEL_PHI_4_REASONING,
  PIXTRAL_LARGE_2502: MODEL_PIXTRAL_LARGE_2502,
  QWEN2_7B_INSTRUCT: MODEL_QWEN2_7B_INSTRUCT,
  QWEN3_235B_A22B_2507: MODEL_QWEN3_235B_A22B_2507,
  QWEN3_235B_A22B_INSTRUCT_2507_MAAS: MODEL_QWEN3_235B_A22B_INSTRUCT_2507_MAAS,
  QWEN3_32B: MODEL_QWEN3_32B,
  QWEN3_5_122B_A10B: MODEL_QWEN3_5_122B_A10B,
  QWEN3_5_27B: MODEL_QWEN3_5_27B,
  QWEN3_5_35B_A3B: MODEL_QWEN3_5_35B_A3B,
  QWEN3_5_397B_A17B: MODEL_QWEN3_5_397B_A17B,
  QWEN3_5_FLASH: MODEL_QWEN3_5_FLASH,
  QWEN3_5_FLASH_2026_02_23: MODEL_QWEN3_5_FLASH_2026_02_23,
  QWEN3_5_LIVETRANSLATE_FLASH_REALTIME: MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME,
  QWEN3_5_LIVETRANSLATE_FLASH_REALTIME_2026_05_19: MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME_2026_05_19,
  QWEN3_5_OMNI_FLASH: MODEL_QWEN3_5_OMNI_FLASH,
  QWEN3_5_OMNI_FLASH_2026_03_15: MODEL_QWEN3_5_OMNI_FLASH_2026_03_15,
  QWEN3_5_OMNI_FLASH_REALTIME: MODEL_QWEN3_5_OMNI_FLASH_REALTIME,
  QWEN3_5_OMNI_FLASH_REALTIME_2026_03_15: MODEL_QWEN3_5_OMNI_FLASH_REALTIME_2026_03_15,
  QWEN3_5_OMNI_PLUS: MODEL_QWEN3_5_OMNI_PLUS,
  QWEN3_5_OMNI_PLUS_2026_03_15: MODEL_QWEN3_5_OMNI_PLUS_2026_03_15,
  QWEN3_5_OMNI_PLUS_REALTIME: MODEL_QWEN3_5_OMNI_PLUS_REALTIME,
  QWEN3_5_OMNI_PLUS_REALTIME_2026_03_15: MODEL_QWEN3_5_OMNI_PLUS_REALTIME_2026_03_15,
  QWEN3_5_PLUS: MODEL_QWEN3_5_PLUS,
  QWEN3_5_PLUS_2026_02_15: MODEL_QWEN3_5_PLUS_2026_02_15,
  QWEN3_5_PLUS_2026_04_20: MODEL_QWEN3_5_PLUS_2026_04_20,
  QWEN3_6_27B: MODEL_QWEN3_6_27B,
  QWEN3_6_35B_A3B: MODEL_QWEN3_6_35B_A3B,
  QWEN3_6_FLASH: MODEL_QWEN3_6_FLASH,
  QWEN3_6_FLASH_2026_04_16: MODEL_QWEN3_6_FLASH_2026_04_16,
  QWEN3_6_PLUS: MODEL_QWEN3_6_PLUS,
  QWEN3_6_PLUS_2026_04_02: MODEL_QWEN3_6_PLUS_2026_04_02,
  QWEN3_7_FLASH: MODEL_QWEN3_7_FLASH,
  QWEN3_7_FLASH_2026_07_15: MODEL_QWEN3_7_FLASH_2026_07_15,
  QWEN3_7_MAX: MODEL_QWEN3_7_MAX,
  QWEN3_7_MAX_2026_05_17: MODEL_QWEN3_7_MAX_2026_05_17,
  QWEN3_7_MAX_2026_05_20: MODEL_QWEN3_7_MAX_2026_05_20,
  QWEN3_7_MAX_2026_06_08: MODEL_QWEN3_7_MAX_2026_06_08,
  QWEN3_7_MAX_PREVIEW: MODEL_QWEN3_7_MAX_PREVIEW,
  QWEN3_7_PLUS: MODEL_QWEN3_7_PLUS,
  QWEN3_7_PLUS_2026_05_26: MODEL_QWEN3_7_PLUS_2026_05_26,
  QWEN3_8_27B: MODEL_QWEN3_8_27B,
  QWEN3_8_2_4T_A95B: MODEL_QWEN3_8_2_4T_A95B,
  QWEN3_8_FLASH: MODEL_QWEN3_8_FLASH,
  QWEN3_8_LIVETRANSLATE_FLASH_REALTIME: MODEL_QWEN3_8_LIVETRANSLATE_FLASH_REALTIME,
  QWEN3_8_MAX: MODEL_QWEN3_8_MAX,
  QWEN3_8_MAX_0902: MODEL_QWEN3_8_MAX_0902,
  QWEN3_8_OMNI_FLASH: MODEL_QWEN3_8_OMNI_FLASH,
  QWEN3_CODER_30B_A3B: MODEL_QWEN3_CODER_30B_A3B,
  QWEN3_CODER_480B_A35B: MODEL_QWEN3_CODER_480B_A35B,
  QWEN3_CODER_480B_A35B_INSTRUCT_MAAS: MODEL_QWEN3_CODER_480B_A35B_INSTRUCT_MAAS,
  QWEN3_CODER_FLASH: MODEL_QWEN3_CODER_FLASH,
  QWEN3_LIVETRANSLATE_FLASH: MODEL_QWEN3_LIVETRANSLATE_FLASH,
  QWEN3_LIVETRANSLATE_FLASH_2025_12_01: MODEL_QWEN3_LIVETRANSLATE_FLASH_2025_12_01,
  QWEN3_NEXT_80B_A3B: MODEL_QWEN3_NEXT_80B_A3B,
  QWEN3_NEXT_80B_A3B_INSTRUCT_MAAS: MODEL_QWEN3_NEXT_80B_A3B_INSTRUCT_MAAS,
  QWEN3_NEXT_80B_A3B_THINKING_MAAS: MODEL_QWEN3_NEXT_80B_A3B_THINKING_MAAS,
  QWEN3_OMNI_FLASH: MODEL_QWEN3_OMNI_FLASH,
  QWEN3_OMNI_FLASH_REALTIME_2025_09_15: MODEL_QWEN3_OMNI_FLASH_REALTIME_2025_09_15,
  QWEN3_S2S_FLASH_REALTIME: MODEL_QWEN3_S2S_FLASH_REALTIME,
  QWEN3_VL_235B_A22B: MODEL_QWEN3_VL_235B_A22B,
  QWEN3_VL_PLUS: MODEL_QWEN3_VL_PLUS,
  QWEN_FLASH: MODEL_QWEN_FLASH,
  QWEN_FLASH_CHARACTER: MODEL_QWEN_FLASH_CHARACTER,
  QWEN_MAX: MODEL_QWEN_MAX,
  QWEN_MT_FLASH: MODEL_QWEN_MT_FLASH,
  QWEN_MT_LITE: MODEL_QWEN_MT_LITE,
  QWEN_MT_PLUS: MODEL_QWEN_MT_PLUS,
  QWEN_PLUS: MODEL_QWEN_PLUS,
  QWEN_PLUS_2025_01_25: MODEL_QWEN_PLUS_2025_01_25,
  QWEN_PLUS_2025_04_28: MODEL_QWEN_PLUS_2025_04_28,
  QWEN_PLUS_2025_07_14: MODEL_QWEN_PLUS_2025_07_14,
  QWEN_PLUS_2025_12_01: MODEL_QWEN_PLUS_2025_12_01,
  QWEN_PLUS_CHARACTER: MODEL_QWEN_PLUS_CHARACTER,
  QWEN_PLUS_LATEST: MODEL_QWEN_PLUS_LATEST,
  QWEN_TURBO: MODEL_QWEN_TURBO,
  QWEN_VL_OCR_2025_11_20: MODEL_QWEN_VL_OCR_2025_11_20,
  QWQ_PLUS_2025_03_05: MODEL_QWQ_PLUS_2025_03_05,
  R1: MODEL_R1,
  SORA_2: MODEL_SORA_2,
  SORA_2_PRO: MODEL_SORA_2_PRO,
  TEXT_EMBEDDING_3_LARGE: MODEL_TEXT_EMBEDDING_3_LARGE,
  TEXT_EMBEDDING_3_SMALL: MODEL_TEXT_EMBEDDING_3_SMALL,
  TEXT_EMBEDDING_ADA_002: MODEL_TEXT_EMBEDDING_ADA_002,
  TTS_1: MODEL_TTS_1,
  TTS_1_1106: MODEL_TTS_1_1106,
  TTS_1_HD: MODEL_TTS_1_HD,
  TTS_1_HD_1106: MODEL_TTS_1_HD_1106,
  TYPESAFE_JEV: MODEL_TYPESAFE_JEV,
  TYPESAFE_JEV_SYSTEM_ONE: MODEL_TYPESAFE_JEV_SYSTEM_ONE,
  V3: MODEL_V3,
  V3_2: MODEL_V3_2,
  VOXTRAL_MINI_3B_2507: MODEL_VOXTRAL_MINI_3B_2507,
  VOXTRAL_SMALL_24B_2507: MODEL_VOXTRAL_SMALL_24B_2507,
  WHISPER_1: MODEL_WHISPER_1,
  ZHIPU_GLM_5_3: MODEL_ZHIPU_GLM_5_3,
} as const;

export type WellKnownModel = (typeof MODELS)[keyof typeof MODELS];
// END GENERATED: model-catalog-snapshot

/**
 * The slice of the inherited OpenAI client this helper needs: its own request
 * pipeline. Going through it is what keeps the caller's `fetch` override,
 * `timeout`, `maxRetries`, `fetchOptions`, `defaultHeaders` and `defaultQuery`
 * applied to model discovery, and is why no global `fetch` is required.
 *
 * It is a structural type rather than an import of the vendor client so this
 * module stays testable with a hand-written double, and so a vendor-side type
 * change is a compile error at one seam instead of a rewrite here.
 */
export interface RawRequester {
  get(
    path: string,
    opts?: unknown
  ): { asResponse(): Promise<{ json(): Promise<unknown>; headers?: Headers }> };
}

/** Whether a value is a plain, non-null object we can read fields off. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Percent-encode each component of a model id while preserving `/`.
 *
 * The gateway intentionally exposes this as a wildcard route because provider
 * model ids commonly carry `/` (`meta/llama-3.1-70b`). Its WAF rejects an
 * encoded slash, so encoding the whole id makes valid models unreachable.
 * Encoding each component protects spaces, query markers and fragments without
 * changing the gateway's model-id semantics.
 */
function encodeModelId(modelId: string): string {
  return modelId.split('/').map(encodeURIComponent).join('/');
}

async function fetchCapabilities(client: RawRequester): Promise<NRouterCapabilities> {
  const req = (path: string) => client.get(path).asResponse();
  let response;
  try {
    response = await req('/../capabilities');
  } catch {
    response = await req('/capabilities');
  }
  const body: unknown = await response.json();
  if (!isRecord(body)) {
    return { gateway: 'nrouter', providers: [], models: [], endpoints: [] };
  }
  return {
    gateway: typeof body.gateway === 'string' ? body.gateway : 'nrouter',
    providers: Array.isArray(body.providers) ? (body.providers as string[]) : [],
    models: Array.isArray(body.models) ? (body.models as string[]) : [],
    endpoints: Array.isArray(body.endpoints) ? (body.endpoints as string[]) : [],
    ...(Array.isArray(body.mcp_servers) ? { mcp_servers: body.mcp_servers as string[] } : {}),
    ...body,
  };
}

/**
 * Model discovery against `/models` and `/models/{id}`.
 *
 * Constructed with the nRouter client itself; see `RawRequester` for why the
 * client's pipeline — not a bare `fetch` — is the transport.
 */
export class NRouterModels {
  constructor(private readonly client: RawRequester) {}

  /**
   * List every model this key can reach, from nRouter's raw JSON response.
   *
   * The OpenAI JS SDK receives the right raw body from nRouter, but its page
   * parser exposes an EMPTY `data` array. Reading the raw response is the fix,
   * and it keeps model discovery reliable without leaving the client's
   * configured transport. A future "simplify this to `client.models.list()`"
   * is therefore the regression, not the cleanup: it compiles, it returns a
   * well-formed empty list, and every caller concludes the account has no
   * models.
   *
   * Errors are NOT handled here on purpose: a non-2xx raises the vendor
   * client's own typed error (`APIError` and its subclasses) inside `get()`,
   * before this method ever sees a body. The defensiveness below is about a
   * SUCCESSFUL response whose shape is unexpected — a proxy returning HTML, a
   * gateway version that renames the envelope — where returning an empty list
   * lets a caller degrade rather than crash on a discovery call that is
   * usually decorative.
   */
  async list(): Promise<NRouterModelList> {
    const response = await this.client.get('/models').asResponse();
    const body: unknown = await response.json();

    if (!isRecord(body) || !Array.isArray(body.data)) {
      return { data: [] };
    }

    // Spread first so `object` and any future envelope fields survive, then
    // pin `data` to the array we just proved is one.
    return { ...body, data: body.data as NRouterModel[] };
  }

  /**
   * Just the model ids, in the order the gateway returned them.
   *
   * Entries without a usable string `id` are dropped rather than surfaced as
   * `undefined`, because every consumer of this list feeds it straight into a
   * `model:` field where an `undefined` becomes the string "undefined" and a
   * baffling upstream error.
   */
  async ids(): Promise<string[]> {
    const { data } = await this.list();
    return data
      .map((model) => model.id)
      .filter((id): id is string => typeof id === 'string' && id.length > 0);
  }

  /**
   * Fetch one model's descriptor from `/models/{id}`.
   *
   * The gateway serves this route (confirmed: without a key it answers 401,
   * not 404). As with `list()`, a non-2xx — including the 404 for an unknown
   * model — raises the vendor client's typed error before we see a body, so a
   * caller who wants a boolean should use `has()` rather than try/catch here,
   * which would swallow auth and network failures as "not found".
   */
  async get(modelId: string): Promise<NRouterModel> {
    if (typeof modelId !== 'string' || modelId.trim() === '') {
      // Guarded rather than passed through: an empty id builds `/models/`,
      // which is the LIST endpoint, so the caller would get a 200 carrying an
      // envelope instead of an error telling them the id was missing.
      throw new TypeError('modelId must be a non-empty string.');
    }

    const response = await this.client
      .get(`/models/${encodeModelId(modelId)}`)
      .asResponse();
    const body: unknown = await response.json();

    if (!isRecord(body) || typeof body.id !== 'string') {
      throw new Error(
        `Unexpected /models response for '${modelId}': no string 'id' field.`
      );
    }

    return body as NRouterModel;
  }

  /**
   * Whether `modelId` appears in this key's model list.
   *
   * The comparison is EXACT and case-sensitive, deliberately. Model aliases
   * are case-sensitive on the wire, so a case-insensitive match would answer
   * `true` for `Claude-Sonnet-4-5` and then fail at call time — turning a
   * cheap, correct pre-flight check into a false reassurance.
   *
   * Implemented over `ids()` rather than over `get()` so a 401, a timeout or a
   * transport failure propagates as itself instead of being reported as "the
   * model does not exist".
   */
  async has(modelId: string): Promise<boolean> {
    const ids = await this.ids();
    return ids.includes(modelId);
  }

  /**
   * Fetch the gateway's self-described capabilities from `/capabilities`.
   *
   * The gateway mounts `/capabilities` at root, which resolves via `/../capabilities`
   * when baseURL has a `/v1` suffix (e.g. https://api.nrouter.ai/v1), or directly via
   * `/capabilities`.
   */
  capabilities(): Promise<NRouterCapabilities> {
    return fetchCapabilities(this.client);
  }

  /**
   * Return the list of distinct provider names the gateway currently serves.
   */
  async providers(): Promise<string[]> {
    const caps = await this.capabilities();
    return caps.providers ?? [];
  }
}
