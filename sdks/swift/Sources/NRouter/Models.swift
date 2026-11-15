// Generated from spec/model-catalog-snapshot.json (snapshot version: 2026-11-14, schema_version: 1, catalog_revision: 1).
// Do not edit by hand; run `node scripts/generate-model-constants.mjs` to regenerate.

/// Generated well-known nRouter model constants.
public enum NRouterModels {
    public static let MODEL_AMAZON_NOVA_LITE_V1: String = "amazon-nova-lite-v1"
    public static let MODEL_AMAZON_NOVA_MICRO_V1: String = "amazon-nova-micro-v1"
    public static let MODEL_AMAZON_NOVA_PRO_V1: String = "amazon-nova-pro-v1"
    public static let MODEL_CHATGPT_IMAGE_LATEST: String = "chatgpt-image-latest"
    public static let MODEL_CHAT_LATEST: String = "chat-latest"
    @available(*, deprecated, message: "Model 'claude-3-7-sonnet' is retired.")
    public static let MODEL_CLAUDE_3_7_SONNET: String = "claude-3-7-sonnet"
    public static let MODEL_CLAUDE_FABLE_5: String = "claude-fable-5"
    public static let MODEL_CLAUDE_FABLE_5_1: String = "claude-fable-5-1"
    public static let MODEL_CLAUDE_HAIKU_4_5_20251001: String = "claude-haiku-4-5-20251001"
    public static let MODEL_CLAUDE_OPUS_4_5_20251101: String = "claude-opus-4-5-20251101"
    public static let MODEL_CLAUDE_OPUS_4_6: String = "claude-opus-4-6"
    public static let MODEL_CLAUDE_OPUS_4_7: String = "claude-opus-4-7"
    public static let MODEL_CLAUDE_OPUS_4_8: String = "claude-opus-4-8"
    public static let MODEL_CLAUDE_OPUS_5: String = "claude-opus-5"
    public static let MODEL_CLAUDE_OPUS_5_5: String = "claude-opus-5-5"
    @available(*, deprecated, renamed: "MODEL_CLAUDE_SONNET_4_5_20250929", message: "Model 'claude-sonnet-4-5-20250929' is retired; compatibility alias for MODEL_CLAUDE_SONNET_4_5_20250929.")
    public static let MODEL_CLAUDE_SONNET_4_5: String = "claude-sonnet-4-5-20250929"
    @available(*, deprecated, message: "Model 'claude-sonnet-4-5-20250929' is retired.")
    public static let MODEL_CLAUDE_SONNET_4_5_20250929: String = "claude-sonnet-4-5-20250929"
    public static let MODEL_CLAUDE_SONNET_4_6: String = "claude-sonnet-4-6"
    public static let MODEL_CLAUDE_SONNET_5: String = "claude-sonnet-5"
    public static let MODEL_CLAUDE_SONNET_5_5: String = "claude-sonnet-5-5"
    public static let MODEL_DEEPSEEK_R1_0528_MAAS: String = "deepseek-r1-0528-maas"
    public static let MODEL_DEEPSEEK_V3_2_MAAS: String = "deepseek-v3.2-maas"
    public static let MODEL_DEEPSEEK_V4_1_FLASH: String = "deepseek-v4.1-flash"
    public static let MODEL_DEEPSEEK_V4_FLASH_0731: String = "deepseek-v4-flash-0731"
    public static let MODEL_DEEPSEEK_V4_PRO: String = "deepseek-v4-pro"
    public static let MODEL_DEEPSEEK_V4_PRO_0813: String = "deepseek-v4-pro-0813"
    public static let MODEL_DEVSTRAL_2_123B: String = "devstral-2-123b"
    @available(*, deprecated, renamed: "MODEL_GOOGLE_GEMINI_1_5_FLASH_002", message: "Model 'google/gemini-1.5-flash-002' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_1_5_FLASH_002.")
    public static let MODEL_GEMINI_1_5_FLASH_002: String = "google/gemini-1.5-flash-002"
    @available(*, deprecated, renamed: "MODEL_GOOGLE_GEMINI_1_5_PRO_002", message: "Model 'google/gemini-1.5-pro-002' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_1_5_PRO_002.")
    public static let MODEL_GEMINI_1_5_PRO_002: String = "google/gemini-1.5-pro-002"
    @available(*, deprecated, renamed: "MODEL_GOOGLE_GEMINI_2_0_FLASH", message: "Model 'google/gemini-2.0-flash' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_0_FLASH.")
    public static let MODEL_GEMINI_2_0_FLASH: String = "google/gemini-2.0-flash"
    @available(*, deprecated, renamed: "MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE", message: "Model 'google/gemini-2.0-flash-lite' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE.")
    public static let MODEL_GEMINI_2_0_FLASH_LITE: String = "google/gemini-2.0-flash-lite"
    @available(*, deprecated, renamed: "MODEL_GOOGLE_GEMINI_2_5_FLASH", message: "Model 'google/gemini-2.5-flash' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_5_FLASH.")
    public static let MODEL_GEMINI_2_5_FLASH: String = "google/gemini-2.5-flash"
    @available(*, deprecated, renamed: "MODEL_GOOGLE_GEMINI_2_5_PRO", message: "Model 'google/gemini-2.5-pro' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_5_PRO.")
    public static let MODEL_GEMINI_2_5_PRO: String = "google/gemini-2.5-pro"
    @available(*, deprecated, renamed: "MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE", message: "Compatibility alias; use MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE instead.")
    public static let MODEL_GEMINI_3_1_FLASH_LITE: String = "google/gemini-3.1-flash-lite"
    @available(*, deprecated, renamed: "MODEL_GOOGLE_GEMINI_3_1_PRO", message: "Model 'google/gemini-3.1-pro' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_3_1_PRO.")
    public static let MODEL_GEMINI_3_1_PRO: String = "google/gemini-3.1-pro"
    public static let MODEL_GEMINI_3_1_PRO_PREVIEW: String = "gemini-3.1-pro-preview"
    public static let MODEL_GEMINI_3_5_FLASH: String = "gemini-3.5-flash"
    public static let MODEL_GEMINI_3_5_FLASH_LITE: String = "gemini-3.5-flash-lite"
    public static let MODEL_GEMINI_3_5_LIVE_TRANSLATE_PREVIEW: String = "gemini-3.5-live-translate-preview"
    public static let MODEL_GEMINI_3_6_FLASH: String = "gemini-3.6-flash"
    public static let MODEL_GEMINI_3_7_FLASH: String = "gemini-3.7-flash"
    @available(*, deprecated, renamed: "MODEL_GOOGLE_GEMINI_3_8_FLASH", message: "Model 'google/gemini-3.8-flash' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_3_8_FLASH.")
    public static let MODEL_GEMINI_3_8_FLASH: String = "google/gemini-3.8-flash"
    public static let MODEL_GEMINI_3_FLASH_PREVIEW: String = "gemini-3-flash-preview"
    public static let MODEL_GEMMA_3_12B_IT: String = "gemma-3-12b-it"
    public static let MODEL_GEMMA_3_27B_IT: String = "gemma-3-27b-it"
    public static let MODEL_GEMMA_3_4B_IT: String = "gemma-3-4b-it"
    public static let MODEL_GLM_4_7: String = "glm-4.7"
    public static let MODEL_GLM_4_7_FLASH: String = "glm-4.7-flash"
    public static let MODEL_GLM_4_7_MAAS: String = "glm-4.7-maas"
    public static let MODEL_GLM_5: String = "glm-5"
    public static let MODEL_GLM_5_1: String = "glm-5.1"
    public static let MODEL_GLM_5_2: String = "glm-5.2"
    public static let MODEL_GLM_5_2_FAST_PREVIEW: String = "glm-5.2-fast-preview"
    public static let MODEL_GLM_5_2_MAAS: String = "glm-5.2-maas"
    public static let MODEL_GLM_5_3: String = "glm-5.3"
    public static let MODEL_GLM_5_3_PRIME: String = "glm-5.3-prime"
    public static let MODEL_GLM_5_MAAS: String = "glm-5-maas"
    public static let MODEL_GLOBAL_AMAZON_NOVA_2_LITE_V1_0: String = "global.amazon.nova-2-lite-v1:0"
    @available(*, deprecated, message: "Model 'google/gemini-1.5-flash-002' is retired.")
    public static let MODEL_GOOGLE_GEMINI_1_5_FLASH_002: String = "google/gemini-1.5-flash-002"
    @available(*, deprecated, message: "Model 'google/gemini-1.5-pro-002' is retired.")
    public static let MODEL_GOOGLE_GEMINI_1_5_PRO_002: String = "google/gemini-1.5-pro-002"
    @available(*, deprecated, message: "Model 'google/gemini-2.0-flash' is retired.")
    public static let MODEL_GOOGLE_GEMINI_2_0_FLASH: String = "google/gemini-2.0-flash"
    @available(*, deprecated, message: "Model 'google/gemini-2.0-flash-lite' is retired.")
    public static let MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE: String = "google/gemini-2.0-flash-lite"
    @available(*, deprecated, message: "Model 'google/gemini-2.5-flash' is retired.")
    public static let MODEL_GOOGLE_GEMINI_2_5_FLASH: String = "google/gemini-2.5-flash"
    @available(*, deprecated, message: "Model 'google/gemini-2.5-pro' is retired.")
    public static let MODEL_GOOGLE_GEMINI_2_5_PRO: String = "google/gemini-2.5-pro"
    public static let MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE: String = "google/gemini-3.1-flash-lite"
    @available(*, deprecated, message: "Model 'google/gemini-3.1-pro' is retired.")
    public static let MODEL_GOOGLE_GEMINI_3_1_PRO: String = "google/gemini-3.1-pro"
    @available(*, deprecated, message: "Model 'google/gemini-3.8-flash' is retired.")
    public static let MODEL_GOOGLE_GEMINI_3_8_FLASH: String = "google/gemini-3.8-flash"
    public static let MODEL_GPT_3_5_TURBO: String = "gpt-3.5-turbo"
    public static let MODEL_GPT_3_5_TURBO_0125: String = "gpt-3.5-turbo-0125"
    public static let MODEL_GPT_3_5_TURBO_1106: String = "gpt-3.5-turbo-1106"
    public static let MODEL_GPT_3_5_TURBO_16K: String = "gpt-3.5-turbo-16k"
    public static let MODEL_GPT_3_5_TURBO_INSTRUCT: String = "gpt-3.5-turbo-instruct"
    public static let MODEL_GPT_4: String = "gpt-4"
    public static let MODEL_GPT_4O: String = "gpt-4o"
    public static let MODEL_GPT_4O_2024_05_13: String = "gpt-4o-2024-05-13"
    public static let MODEL_GPT_4O_2024_08_06: String = "gpt-4o-2024-08-06"
    public static let MODEL_GPT_4O_2024_11_20: String = "gpt-4o-2024-11-20"
    public static let MODEL_GPT_4O_MINI: String = "gpt-4o-mini"
    public static let MODEL_GPT_4O_MINI_2024_07_18: String = "gpt-4o-mini-2024-07-18"
    public static let MODEL_GPT_4O_MINI_SEARCH_PREVIEW: String = "gpt-4o-mini-search-preview"
    public static let MODEL_GPT_4O_MINI_SEARCH_PREVIEW_2025_03_11: String = "gpt-4o-mini-search-preview-2025-03-11"
    public static let MODEL_GPT_4O_MINI_TRANSCRIBE: String = "gpt-4o-mini-transcribe"
    public static let MODEL_GPT_4O_MINI_TRANSCRIBE_2025_03_20: String = "gpt-4o-mini-transcribe-2025-03-20"
    public static let MODEL_GPT_4O_MINI_TRANSCRIBE_2025_12_15: String = "gpt-4o-mini-transcribe-2025-12-15"
    public static let MODEL_GPT_4O_MINI_TTS: String = "gpt-4o-mini-tts"
    public static let MODEL_GPT_4O_MINI_TTS_2025_03_20: String = "gpt-4o-mini-tts-2025-03-20"
    public static let MODEL_GPT_4O_MINI_TTS_2025_12_15: String = "gpt-4o-mini-tts-2025-12-15"
    public static let MODEL_GPT_4O_SEARCH_PREVIEW: String = "gpt-4o-search-preview"
    public static let MODEL_GPT_4O_SEARCH_PREVIEW_2025_03_11: String = "gpt-4o-search-preview-2025-03-11"
    public static let MODEL_GPT_4O_TRANSCRIBE: String = "gpt-4o-transcribe"
    public static let MODEL_GPT_4O_TRANSCRIBE_DIARIZE: String = "gpt-4o-transcribe-diarize"
    public static let MODEL_GPT_4_0613: String = "gpt-4-0613"
    public static let MODEL_GPT_4_1: String = "gpt-4.1"
    public static let MODEL_GPT_4_1_2025_04_14: String = "gpt-4.1-2025-04-14"
    public static let MODEL_GPT_4_1_MINI: String = "gpt-4.1-mini"
    public static let MODEL_GPT_4_1_MINI_2025_04_14: String = "gpt-4.1-mini-2025-04-14"
    public static let MODEL_GPT_4_1_NANO: String = "gpt-4.1-nano"
    public static let MODEL_GPT_4_1_NANO_2025_04_14: String = "gpt-4.1-nano-2025-04-14"
    public static let MODEL_GPT_4_TURBO: String = "gpt-4-turbo"
    public static let MODEL_GPT_4_TURBO_2024_04_09: String = "gpt-4-turbo-2024-04-09"
    public static let MODEL_GPT_5: String = "gpt-5"
    public static let MODEL_GPT_5_1: String = "gpt-5.1"
    public static let MODEL_GPT_5_1_2025_11_13: String = "gpt-5.1-2025-11-13"
    public static let MODEL_GPT_5_1_CHAT_LATEST: String = "gpt-5.1-chat-latest"
    public static let MODEL_GPT_5_2: String = "gpt-5.2"
    public static let MODEL_GPT_5_2025_08_07: String = "gpt-5-2025-08-07"
    public static let MODEL_GPT_5_2_2025_12_11: String = "gpt-5.2-2025-12-11"
    public static let MODEL_GPT_5_2_CHAT_LATEST: String = "gpt-5.2-chat-latest"
    public static let MODEL_GPT_5_2_PRO: String = "gpt-5.2-pro"
    public static let MODEL_GPT_5_2_PRO_2025_12_11: String = "gpt-5.2-pro-2025-12-11"
    public static let MODEL_GPT_5_3_CHAT_LATEST: String = "gpt-5.3-chat-latest"
    public static let MODEL_GPT_5_3_CODEX: String = "gpt-5.3-codex"
    public static let MODEL_GPT_5_4: String = "gpt-5.4"
    public static let MODEL_GPT_5_4_2026_03_05: String = "gpt-5.4-2026-03-05"
    public static let MODEL_GPT_5_4_MINI: String = "gpt-5.4-mini"
    public static let MODEL_GPT_5_4_MINI_2026_03_17: String = "gpt-5.4-mini-2026-03-17"
    public static let MODEL_GPT_5_4_NANO: String = "gpt-5.4-nano"
    public static let MODEL_GPT_5_4_NANO_2026_03_17: String = "gpt-5.4-nano-2026-03-17"
    public static let MODEL_GPT_5_4_PRO: String = "gpt-5.4-pro"
    public static let MODEL_GPT_5_4_PRO_2026_03_05: String = "gpt-5.4-pro-2026-03-05"
    public static let MODEL_GPT_5_5: String = "gpt-5.5"
    public static let MODEL_GPT_5_5_2026_04_23: String = "gpt-5.5-2026-04-23"
    public static let MODEL_GPT_5_5_PRO: String = "gpt-5.5-pro"
    public static let MODEL_GPT_5_5_PRO_2026_04_23: String = "gpt-5.5-pro-2026-04-23"
    public static let MODEL_GPT_5_6_LUNA: String = "gpt-5.6-luna"
    public static let MODEL_GPT_5_6_SOL: String = "gpt-5.6-sol"
    public static let MODEL_GPT_5_6_TERRA: String = "gpt-5.6-terra"
    public static let MODEL_GPT_5_MINI: String = "gpt-5-mini"
    public static let MODEL_GPT_5_MINI_2025_08_07: String = "gpt-5-mini-2025-08-07"
    public static let MODEL_GPT_5_NANO: String = "gpt-5-nano"
    public static let MODEL_GPT_5_NANO_2025_08_07: String = "gpt-5-nano-2025-08-07"
    public static let MODEL_GPT_5_PRO: String = "gpt-5-pro"
    public static let MODEL_GPT_5_PRO_2025_10_06: String = "gpt-5-pro-2025-10-06"
    public static let MODEL_GPT_5_SEARCH_API: String = "gpt-5-search-api"
    public static let MODEL_GPT_5_SEARCH_API_2025_10_14: String = "gpt-5-search-api-2025-10-14"
    public static let MODEL_GPT_6_1_SOL: String = "gpt-6.1-sol"
    public static let MODEL_GPT_6_ASTRA: String = "gpt-6-astra"
    public static let MODEL_GPT_6_LUNA: String = "gpt-6-luna"
    public static let MODEL_GPT_6_SOL: String = "gpt-6-sol"
    public static let MODEL_GPT_AUDIO: String = "gpt-audio"
    public static let MODEL_GPT_AUDIO_1_5: String = "gpt-audio-1.5"
    public static let MODEL_GPT_AUDIO_2025_08_28: String = "gpt-audio-2025-08-28"
    public static let MODEL_GPT_AUDIO_MINI: String = "gpt-audio-mini"
    public static let MODEL_GPT_AUDIO_MINI_2025_12_15: String = "gpt-audio-mini-2025-12-15"
    public static let MODEL_GPT_IMAGE_1: String = "gpt-image-1"
    public static let MODEL_GPT_IMAGE_1_5: String = "gpt-image-1.5"
    public static let MODEL_GPT_IMAGE_1_MINI: String = "gpt-image-1-mini"
    public static let MODEL_GPT_IMAGE_2: String = "gpt-image-2"
    public static let MODEL_GPT_IMAGE_2_2026_04_21: String = "gpt-image-2-2026-04-21"
    public static let MODEL_GPT_IMAGE_2_5_FLARE: String = "gpt-image-2.5-flare"
    public static let MODEL_GPT_IMAGE_2_5_FLARE_2026_09_08: String = "gpt-image-2.5-flare-2026-09-08"
    public static let MODEL_GPT_IMAGE_2_5_SUNBURST: String = "gpt-image-2.5-sunburst"
    public static let MODEL_GPT_IMAGE_2_5_SUNBURST_2026_09_08: String = "gpt-image-2.5-sunburst-2026-09-08"
    public static let MODEL_GPT_LIVE_TRANSCRIBE: String = "gpt-live-transcribe"
    public static let MODEL_GPT_OSS_120B_1: String = "gpt-oss-120b-1"
    public static let MODEL_GPT_OSS_120B_MAAS: String = "gpt-oss-120b-maas"
    public static let MODEL_GPT_OSS_20B_1: String = "gpt-oss-20b-1"
    public static let MODEL_GPT_OSS_SAFEGUARD_120B: String = "gpt-oss-safeguard-120b"
    public static let MODEL_GPT_OSS_SAFEGUARD_20B: String = "gpt-oss-safeguard-20b"
    public static let MODEL_GPT_TRANSCRIBE: String = "gpt-transcribe"
    public static let MODEL_GROK_4_1_FAST_NON_REASONING: String = "grok-4-1-fast-non-reasoning"
    public static let MODEL_GROK_4_1_FAST_REASONING: String = "grok-4-1-fast-reasoning"
    public static let MODEL_KIMI_K2_5: String = "kimi-k2.5"
    public static let MODEL_KIMI_K2_7_CODE: String = "kimi-k2.7-code"
    public static let MODEL_KIMI_K2_THINKING: String = "kimi-k2-thinking"
    public static let MODEL_KIMI_K2_THINKING_MAAS: String = "kimi-k2-thinking-maas"
    public static let MODEL_KIMI_K3: String = "kimi-k3"
    public static let MODEL_KIMI_KIMI_K3: String = "kimi/kimi-k3"
    public static let MODEL_LLAMA3_1_70B_INSTRUCT: String = "llama3-1-70b-instruct"
    public static let MODEL_LLAMA3_1_8B_INSTRUCT: String = "llama3-1-8b-instruct"
    public static let MODEL_LLAMA3_3_70B_INSTRUCT: String = "llama3-3-70b-instruct"
    public static let MODEL_LLAMA4_MAVERICK_17B_INSTRUCT: String = "llama4-maverick-17b-instruct"
    public static let MODEL_LLAMA4_SCOUT_17B_INSTRUCT: String = "llama4-scout-17b-instruct"
    public static let MODEL_LLAMA_3_3_70B_INSTRUCT: String = "Llama-3.3-70B-Instruct"
    public static let MODEL_LLAMA_4_MAVERICK_17B_128E_INSTRUCT_FP8: String = "Llama-4-Maverick-17B-128E-Instruct-FP8"
    public static let MODEL_LLAMA_4_SCOUT_17B_16E_INSTRUCT: String = "Llama-4-Scout-17B-16E-Instruct"
    public static let MODEL_MAGISTRAL_SMALL_2509: String = "magistral-small-2509"
    @available(*, deprecated, message: "Model 'meta/llama-3.1-70b-instruct' is retired.")
    public static let MODEL_META_LLAMA_3_1_70B_INSTRUCT: String = "meta/llama-3.1-70b-instruct"
    @available(*, deprecated, message: "Model 'meta/llama-3.1-8b-instruct' is retired.")
    public static let MODEL_META_LLAMA_3_1_8B_INSTRUCT: String = "meta/llama-3.1-8b-instruct"
    @available(*, deprecated, renamed: "MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT", message: "Model 'meta/llama-3.2-11b-vision-instruct' is retired; compatibility alias for MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT.")
    public static let MODEL_META_LLAMA_3_2_11B_VISION: String = "meta/llama-3.2-11b-vision-instruct"
    @available(*, deprecated, message: "Model 'meta/llama-3.2-11b-vision-instruct' is retired.")
    public static let MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT: String = "meta/llama-3.2-11b-vision-instruct"
    @available(*, deprecated, message: "Model 'meta/llama-3.2-1b-instruct' is retired.")
    public static let MODEL_META_LLAMA_3_2_1B_INSTRUCT: String = "meta/llama-3.2-1b-instruct"
    @available(*, deprecated, message: "Model 'meta/llama-3.2-3b-instruct' is retired.")
    public static let MODEL_META_LLAMA_3_2_3B_INSTRUCT: String = "meta/llama-3.2-3b-instruct"
    @available(*, deprecated, renamed: "MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT", message: "Model 'meta/llama-3.2-90b-vision-instruct' is retired; compatibility alias for MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT.")
    public static let MODEL_META_LLAMA_3_2_90B_VISION: String = "meta/llama-3.2-90b-vision-instruct"
    @available(*, deprecated, message: "Model 'meta/llama-3.2-90b-vision-instruct' is retired.")
    public static let MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT: String = "meta/llama-3.2-90b-vision-instruct"
    @available(*, deprecated, message: "Model 'meta/llama-3.3-70b-instruct' is retired.")
    public static let MODEL_META_LLAMA_3_3_70B_INSTRUCT: String = "meta/llama-3.3-70b-instruct"
    public static let MODEL_MINIMAX_M2: String = "minimax-m2"
    public static let MODEL_MINIMAX_M2_1: String = "minimax-m2.1"
    public static let MODEL_MINIMAX_M2_5: String = "minimax-m2.5"
    public static let MODEL_MINIMAX_M2_MAAS: String = "minimax-m2-maas"
    public static let MODEL_MINISTRAL_3_14B_INSTRUCT: String = "ministral-3-14b-instruct"
    public static let MODEL_MINISTRAL_3_3B_INSTRUCT: String = "ministral-3-3b-instruct"
    public static let MODEL_MINISTRAL_3_8B_INSTRUCT: String = "ministral-3-8b-instruct"
    public static let MODEL_MISTRAL_LARGE_3_675B_INSTRUCT: String = "mistral-large-3-675b-instruct"
    public static let MODEL_MISTRAL_MEDIUM_2505: String = "mistral-medium-2505"
    public static let MODEL_MISTRAL_SMALL_2503: String = "mistral-small-2503"
    public static let MODEL_NEMOTRON_NANO_12B_V2: String = "nemotron-nano-12b-v2"
    public static let MODEL_NEMOTRON_NANO_3_30B: String = "nemotron-nano-3-30b"
    public static let MODEL_NEMOTRON_NANO_9B_V2: String = "nemotron-nano-9b-v2"
    public static let MODEL_NEMOTRON_SUPER_3_120B: String = "nemotron-super-3-120b"
    public static let MODEL_NOVA_2_LITE: String = "nova-2-lite"
    public static let MODEL_NOVA_LITE: String = "nova-lite"
    public static let MODEL_O1: String = "o1"
    public static let MODEL_O1_2024_12_17: String = "o1-2024-12-17"
    public static let MODEL_O1_PRO: String = "o1-pro"
    public static let MODEL_O1_PRO_2025_03_19: String = "o1-pro-2025-03-19"
    public static let MODEL_O3: String = "o3"
    public static let MODEL_O3_2025_04_16: String = "o3-2025-04-16"
    public static let MODEL_O3_MINI: String = "o3-mini"
    public static let MODEL_O3_MINI_2025_01_31: String = "o3-mini-2025-01-31"
    public static let MODEL_O4_MINI: String = "o4-mini"
    public static let MODEL_O4_MINI_2025_04_16: String = "o4-mini-2025-04-16"
    public static let MODEL_PALMYRA_VISION_7B: String = "palmyra-vision-7b"
    public static let MODEL_PHI_4: String = "Phi-4"
    public static let MODEL_PHI_4_MINI_INSTRUCT: String = "Phi-4-mini-instruct"
    public static let MODEL_PHI_4_MINI_REASONING: String = "Phi-4-mini-reasoning"
    public static let MODEL_PHI_4_MULTIMODAL_INSTRUCT: String = "Phi-4-multimodal-instruct"
    public static let MODEL_PHI_4_REASONING: String = "Phi-4-reasoning"
    public static let MODEL_PIXTRAL_LARGE_2502: String = "pixtral-large-2502"
    public static let MODEL_QWEN2_7B_INSTRUCT: String = "qwen2-7b-instruct"
    public static let MODEL_QWEN3_235B_A22B_2507: String = "qwen3-235b-a22b-2507"
    public static let MODEL_QWEN3_235B_A22B_INSTRUCT_2507_MAAS: String = "qwen3-235b-a22b-instruct-2507-maas"
    public static let MODEL_QWEN3_32B: String = "qwen3-32b"
    public static let MODEL_QWEN3_5_122B_A10B: String = "qwen3.5-122b-a10b"
    public static let MODEL_QWEN3_5_27B: String = "qwen3.5-27b"
    public static let MODEL_QWEN3_5_35B_A3B: String = "qwen3.5-35b-a3b"
    public static let MODEL_QWEN3_5_397B_A17B: String = "qwen3.5-397b-a17b"
    public static let MODEL_QWEN3_5_FLASH: String = "qwen3.5-flash"
    public static let MODEL_QWEN3_5_FLASH_2026_02_23: String = "qwen3.5-flash-2026-02-23"
    public static let MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME: String = "qwen3.5-livetranslate-flash-realtime"
    public static let MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME_2026_05_19: String = "qwen3.5-livetranslate-flash-realtime-2026-05-19"
    public static let MODEL_QWEN3_5_OMNI_FLASH: String = "qwen3.5-omni-flash"
    public static let MODEL_QWEN3_5_OMNI_FLASH_2026_03_15: String = "qwen3.5-omni-flash-2026-03-15"
    public static let MODEL_QWEN3_5_OMNI_FLASH_REALTIME: String = "qwen3.5-omni-flash-realtime"
    public static let MODEL_QWEN3_5_OMNI_FLASH_REALTIME_2026_03_15: String = "qwen3.5-omni-flash-realtime-2026-03-15"
    public static let MODEL_QWEN3_5_OMNI_PLUS: String = "qwen3.5-omni-plus"
    public static let MODEL_QWEN3_5_OMNI_PLUS_2026_03_15: String = "qwen3.5-omni-plus-2026-03-15"
    public static let MODEL_QWEN3_5_OMNI_PLUS_REALTIME: String = "qwen3.5-omni-plus-realtime"
    public static let MODEL_QWEN3_5_OMNI_PLUS_REALTIME_2026_03_15: String = "qwen3.5-omni-plus-realtime-2026-03-15"
    public static let MODEL_QWEN3_5_PLUS: String = "qwen3.5-plus"
    public static let MODEL_QWEN3_5_PLUS_2026_02_15: String = "qwen3.5-plus-2026-02-15"
    public static let MODEL_QWEN3_5_PLUS_2026_04_20: String = "qwen3.5-plus-2026-04-20"
    public static let MODEL_QWEN3_6_27B: String = "qwen3.6-27b"
    public static let MODEL_QWEN3_6_35B_A3B: String = "qwen3.6-35b-a3b"
    public static let MODEL_QWEN3_6_FLASH: String = "qwen3.6-flash"
    public static let MODEL_QWEN3_6_FLASH_2026_04_16: String = "qwen3.6-flash-2026-04-16"
    public static let MODEL_QWEN3_6_PLUS: String = "qwen3.6-plus"
    public static let MODEL_QWEN3_6_PLUS_2026_04_02: String = "qwen3.6-plus-2026-04-02"
    public static let MODEL_QWEN3_7_FLASH: String = "qwen3.7-flash"
    public static let MODEL_QWEN3_7_FLASH_2026_07_15: String = "qwen3.7-flash-2026-07-15"
    public static let MODEL_QWEN3_7_MAX: String = "qwen3.7-max"
    public static let MODEL_QWEN3_7_MAX_2026_05_17: String = "qwen3.7-max-2026-05-17"
    public static let MODEL_QWEN3_7_MAX_2026_05_20: String = "qwen3.7-max-2026-05-20"
    public static let MODEL_QWEN3_7_MAX_2026_06_08: String = "qwen3.7-max-2026-06-08"
    public static let MODEL_QWEN3_7_MAX_PREVIEW: String = "qwen3.7-max-preview"
    public static let MODEL_QWEN3_7_PLUS: String = "qwen3.7-plus"
    public static let MODEL_QWEN3_7_PLUS_2026_05_26: String = "qwen3.7-plus-2026-05-26"
    public static let MODEL_QWEN3_8_27B: String = "qwen3.8-27b"
    public static let MODEL_QWEN3_8_2_4T_A95B: String = "qwen3.8-2.4t-a95b"
    public static let MODEL_QWEN3_8_FLASH: String = "qwen3.8-flash"
    public static let MODEL_QWEN3_8_LIVETRANSLATE_FLASH_REALTIME: String = "qwen3.8-livetranslate-flash-realtime"
    public static let MODEL_QWEN3_8_MAX: String = "qwen3.8-max"
    public static let MODEL_QWEN3_8_MAX_0902: String = "qwen3.8-max-0902"
    public static let MODEL_QWEN3_8_OMNI_FLASH: String = "qwen3.8-omni-flash"
    public static let MODEL_QWEN3_CODER_30B_A3B: String = "qwen3-coder-30b-a3b"
    public static let MODEL_QWEN3_CODER_480B_A35B: String = "qwen3-coder-480b-a35b"
    public static let MODEL_QWEN3_CODER_480B_A35B_INSTRUCT_MAAS: String = "qwen3-coder-480b-a35b-instruct-maas"
    public static let MODEL_QWEN3_CODER_FLASH: String = "qwen3-coder-flash"
    public static let MODEL_QWEN3_LIVETRANSLATE_FLASH: String = "qwen3-livetranslate-flash"
    public static let MODEL_QWEN3_LIVETRANSLATE_FLASH_2025_12_01: String = "qwen3-livetranslate-flash-2025-12-01"
    public static let MODEL_QWEN3_NEXT_80B_A3B: String = "qwen3-next-80b-a3b"
    public static let MODEL_QWEN3_NEXT_80B_A3B_INSTRUCT_MAAS: String = "qwen3-next-80b-a3b-instruct-maas"
    public static let MODEL_QWEN3_NEXT_80B_A3B_THINKING_MAAS: String = "qwen3-next-80b-a3b-thinking-maas"
    public static let MODEL_QWEN3_OMNI_FLASH: String = "qwen3-omni-flash"
    public static let MODEL_QWEN3_OMNI_FLASH_REALTIME_2025_09_15: String = "qwen3-omni-flash-realtime-2025-09-15"
    public static let MODEL_QWEN3_S2S_FLASH_REALTIME: String = "qwen3-s2s-flash-realtime"
    public static let MODEL_QWEN3_VL_235B_A22B: String = "qwen3-vl-235b-a22b"
    public static let MODEL_QWEN3_VL_PLUS: String = "qwen3-vl-plus"
    public static let MODEL_QWEN_FLASH: String = "qwen-flash"
    public static let MODEL_QWEN_FLASH_CHARACTER: String = "qwen-flash-character"
    public static let MODEL_QWEN_MAX: String = "qwen-max"
    public static let MODEL_QWEN_MT_FLASH: String = "qwen-mt-flash"
    public static let MODEL_QWEN_MT_LITE: String = "qwen-mt-lite"
    public static let MODEL_QWEN_MT_PLUS: String = "qwen-mt-plus"
    public static let MODEL_QWEN_PLUS: String = "qwen-plus"
    public static let MODEL_QWEN_PLUS_2025_01_25: String = "qwen-plus-2025-01-25"
    public static let MODEL_QWEN_PLUS_2025_04_28: String = "qwen-plus-2025-04-28"
    public static let MODEL_QWEN_PLUS_2025_07_14: String = "qwen-plus-2025-07-14"
    public static let MODEL_QWEN_PLUS_2025_12_01: String = "qwen-plus-2025-12-01"
    public static let MODEL_QWEN_PLUS_CHARACTER: String = "qwen-plus-character"
    public static let MODEL_QWEN_PLUS_LATEST: String = "qwen-plus-latest"
    public static let MODEL_QWEN_TURBO: String = "qwen-turbo"
    public static let MODEL_QWEN_VL_OCR_2025_11_20: String = "qwen-vl-ocr-2025-11-20"
    public static let MODEL_QWQ_PLUS_2025_03_05: String = "qwq-plus-2025-03-05"
    public static let MODEL_R1: String = "r1"
    public static let MODEL_SORA_2: String = "sora-2"
    public static let MODEL_SORA_2_PRO: String = "sora-2-pro"
    public static let MODEL_TEXT_EMBEDDING_3_LARGE: String = "text-embedding-3-large"
    public static let MODEL_TEXT_EMBEDDING_3_SMALL: String = "text-embedding-3-small"
    public static let MODEL_TEXT_EMBEDDING_ADA_002: String = "text-embedding-ada-002"
    public static let MODEL_TTS_1: String = "tts-1"
    public static let MODEL_TTS_1_1106: String = "tts-1-1106"
    public static let MODEL_TTS_1_HD: String = "tts-1-hd"
    public static let MODEL_TTS_1_HD_1106: String = "tts-1-hd-1106"
    public static let MODEL_TYPESAFE_JEV: String = "typesafe/jev"
    @available(*, deprecated, renamed: "MODEL_TYPESAFE_JEV", message: "Compatibility alias; use MODEL_TYPESAFE_JEV instead.")
    public static let MODEL_TYPESAFE_JEV_SYSTEM_ONE: String = "typesafe/jev"
    public static let MODEL_V3: String = "v3"
    public static let MODEL_V3_2: String = "v3.2"
    public static let MODEL_VOXTRAL_MINI_3B_2507: String = "voxtral-mini-3b-2507"
    public static let MODEL_VOXTRAL_SMALL_24B_2507: String = "voxtral-small-24b-2507"
    public static let MODEL_WHISPER_1: String = "whisper-1"
    public static let MODEL_ZHIPU_GLM_5_3: String = "ZHIPU/GLM-5.3"

    /// Map of well-known model keys matching `MODELS` across all nRouter SDKs.
    public static let MODELS: [String: String] = [
        "AMAZON_NOVA_LITE_V1": "amazon-nova-lite-v1",
        "AMAZON_NOVA_MICRO_V1": "amazon-nova-micro-v1",
        "AMAZON_NOVA_PRO_V1": "amazon-nova-pro-v1",
        "CHATGPT_IMAGE_LATEST": "chatgpt-image-latest",
        "CHAT_LATEST": "chat-latest",
        "CLAUDE_3_7_SONNET": "claude-3-7-sonnet",
        "CLAUDE_FABLE_5": "claude-fable-5",
        "CLAUDE_FABLE_5_1": "claude-fable-5-1",
        "CLAUDE_HAIKU_4_5_20251001": "claude-haiku-4-5-20251001",
        "CLAUDE_OPUS_4_5_20251101": "claude-opus-4-5-20251101",
        "CLAUDE_OPUS_4_6": "claude-opus-4-6",
        "CLAUDE_OPUS_4_7": "claude-opus-4-7",
        "CLAUDE_OPUS_4_8": "claude-opus-4-8",
        "CLAUDE_OPUS_5": "claude-opus-5",
        "CLAUDE_OPUS_5_5": "claude-opus-5-5",
        "CLAUDE_SONNET_4_5": "claude-sonnet-4-5-20250929",
        "CLAUDE_SONNET_4_5_20250929": "claude-sonnet-4-5-20250929",
        "CLAUDE_SONNET_4_6": "claude-sonnet-4-6",
        "CLAUDE_SONNET_5": "claude-sonnet-5",
        "CLAUDE_SONNET_5_5": "claude-sonnet-5-5",
        "DEEPSEEK_R1_0528_MAAS": "deepseek-r1-0528-maas",
        "DEEPSEEK_V3_2_MAAS": "deepseek-v3.2-maas",
        "DEEPSEEK_V4_1_FLASH": "deepseek-v4.1-flash",
        "DEEPSEEK_V4_FLASH_0731": "deepseek-v4-flash-0731",
        "DEEPSEEK_V4_PRO": "deepseek-v4-pro",
        "DEEPSEEK_V4_PRO_0813": "deepseek-v4-pro-0813",
        "DEVSTRAL_2_123B": "devstral-2-123b",
        "GEMINI_1_5_FLASH_002": "google/gemini-1.5-flash-002",
        "GEMINI_1_5_PRO_002": "google/gemini-1.5-pro-002",
        "GEMINI_2_0_FLASH": "google/gemini-2.0-flash",
        "GEMINI_2_0_FLASH_LITE": "google/gemini-2.0-flash-lite",
        "GEMINI_2_5_FLASH": "gemini-2.5-flash",
        "GEMINI_2_5_PRO": "gemini-2.5-pro",
        "GEMINI_3_1_FLASH_LITE": "google/gemini-3.1-flash-lite",
        "GEMINI_3_1_PRO": "google/gemini-3.1-pro",
        "GEMINI_3_1_PRO_PREVIEW": "gemini-3.1-pro-preview",
        "GEMINI_3_5_FLASH": "gemini-3.5-flash",
        "GEMINI_3_5_FLASH_LITE": "gemini-3.5-flash-lite",
        "GEMINI_3_5_LIVE_TRANSLATE_PREVIEW": "gemini-3.5-live-translate-preview",
        "GEMINI_3_6_FLASH": "gemini-3.6-flash",
        "GEMINI_3_7_FLASH": "gemini-3.7-flash",
        "GEMINI_3_8_FLASH": "google/gemini-3.8-flash",
        "GEMINI_3_FLASH_PREVIEW": "gemini-3-flash-preview",
        "GEMMA_3_12B_IT": "gemma-3-12b-it",
        "GEMMA_3_27B_IT": "gemma-3-27b-it",
        "GEMMA_3_4B_IT": "gemma-3-4b-it",
        "GLM_4_7": "glm-4.7",
        "GLM_4_7_FLASH": "glm-4.7-flash",
        "GLM_4_7_MAAS": "glm-4.7-maas",
        "GLM_5": "glm-5",
        "GLM_5_1": "glm-5.1",
        "GLM_5_2": "glm-5.2",
        "GLM_5_2_FAST_PREVIEW": "glm-5.2-fast-preview",
        "GLM_5_2_MAAS": "glm-5.2-maas",
        "GLM_5_3": "glm-5.3",
        "GLM_5_3_PRIME": "glm-5.3-prime",
        "GLM_5_MAAS": "glm-5-maas",
        "GLOBAL_AMAZON_NOVA_2_LITE_V1_0": "global.amazon.nova-2-lite-v1:0",
        "GOOGLE_GEMINI_1_5_FLASH_002": "google/gemini-1.5-flash-002",
        "GOOGLE_GEMINI_1_5_PRO_002": "google/gemini-1.5-pro-002",
        "GOOGLE_GEMINI_2_0_FLASH": "google/gemini-2.0-flash",
        "GOOGLE_GEMINI_2_0_FLASH_LITE": "google/gemini-2.0-flash-lite",
        "GOOGLE_GEMINI_2_5_FLASH": "google/gemini-2.5-flash",
        "GOOGLE_GEMINI_2_5_PRO": "google/gemini-2.5-pro",
        "GOOGLE_GEMINI_3_1_FLASH_LITE": "google/gemini-3.1-flash-lite",
        "GOOGLE_GEMINI_3_1_PRO": "google/gemini-3.1-pro",
        "GOOGLE_GEMINI_3_8_FLASH": "google/gemini-3.8-flash",
        "GPT_3_5_TURBO": "gpt-3.5-turbo",
        "GPT_3_5_TURBO_0125": "gpt-3.5-turbo-0125",
        "GPT_3_5_TURBO_1106": "gpt-3.5-turbo-1106",
        "GPT_3_5_TURBO_16K": "gpt-3.5-turbo-16k",
        "GPT_3_5_TURBO_INSTRUCT": "gpt-3.5-turbo-instruct",
        "GPT_4": "gpt-4",
        "GPT_4O": "gpt-4o",
        "GPT_4O_2024_05_13": "gpt-4o-2024-05-13",
        "GPT_4O_2024_08_06": "gpt-4o-2024-08-06",
        "GPT_4O_2024_11_20": "gpt-4o-2024-11-20",
        "GPT_4O_MINI": "gpt-4o-mini",
        "GPT_4O_MINI_2024_07_18": "gpt-4o-mini-2024-07-18",
        "GPT_4O_MINI_SEARCH_PREVIEW": "gpt-4o-mini-search-preview",
        "GPT_4O_MINI_SEARCH_PREVIEW_2025_03_11": "gpt-4o-mini-search-preview-2025-03-11",
        "GPT_4O_MINI_TRANSCRIBE": "gpt-4o-mini-transcribe",
        "GPT_4O_MINI_TRANSCRIBE_2025_03_20": "gpt-4o-mini-transcribe-2025-03-20",
        "GPT_4O_MINI_TRANSCRIBE_2025_12_15": "gpt-4o-mini-transcribe-2025-12-15",
        "GPT_4O_MINI_TTS": "gpt-4o-mini-tts",
        "GPT_4O_MINI_TTS_2025_03_20": "gpt-4o-mini-tts-2025-03-20",
        "GPT_4O_MINI_TTS_2025_12_15": "gpt-4o-mini-tts-2025-12-15",
        "GPT_4O_SEARCH_PREVIEW": "gpt-4o-search-preview",
        "GPT_4O_SEARCH_PREVIEW_2025_03_11": "gpt-4o-search-preview-2025-03-11",
        "GPT_4O_TRANSCRIBE": "gpt-4o-transcribe",
        "GPT_4O_TRANSCRIBE_DIARIZE": "gpt-4o-transcribe-diarize",
        "GPT_4_0613": "gpt-4-0613",
        "GPT_4_1": "gpt-4.1",
        "GPT_4_1_2025_04_14": "gpt-4.1-2025-04-14",
        "GPT_4_1_MINI": "gpt-4.1-mini",
        "GPT_4_1_MINI_2025_04_14": "gpt-4.1-mini-2025-04-14",
        "GPT_4_1_NANO": "gpt-4.1-nano",
        "GPT_4_1_NANO_2025_04_14": "gpt-4.1-nano-2025-04-14",
        "GPT_4_TURBO": "gpt-4-turbo",
        "GPT_4_TURBO_2024_04_09": "gpt-4-turbo-2024-04-09",
        "GPT_5": "gpt-5",
        "GPT_5_1": "gpt-5.1",
        "GPT_5_1_2025_11_13": "gpt-5.1-2025-11-13",
        "GPT_5_1_CHAT_LATEST": "gpt-5.1-chat-latest",
        "GPT_5_2": "gpt-5.2",
        "GPT_5_2025_08_07": "gpt-5-2025-08-07",
        "GPT_5_2_2025_12_11": "gpt-5.2-2025-12-11",
        "GPT_5_2_CHAT_LATEST": "gpt-5.2-chat-latest",
        "GPT_5_2_PRO": "gpt-5.2-pro",
        "GPT_5_2_PRO_2025_12_11": "gpt-5.2-pro-2025-12-11",
        "GPT_5_3_CHAT_LATEST": "gpt-5.3-chat-latest",
        "GPT_5_3_CODEX": "gpt-5.3-codex",
        "GPT_5_4": "gpt-5.4",
        "GPT_5_4_2026_03_05": "gpt-5.4-2026-03-05",
        "GPT_5_4_MINI": "gpt-5.4-mini",
        "GPT_5_4_MINI_2026_03_17": "gpt-5.4-mini-2026-03-17",
        "GPT_5_4_NANO": "gpt-5.4-nano",
        "GPT_5_4_NANO_2026_03_17": "gpt-5.4-nano-2026-03-17",
        "GPT_5_4_PRO": "gpt-5.4-pro",
        "GPT_5_4_PRO_2026_03_05": "gpt-5.4-pro-2026-03-05",
        "GPT_5_5": "gpt-5.5",
        "GPT_5_5_2026_04_23": "gpt-5.5-2026-04-23",
        "GPT_5_5_PRO": "gpt-5.5-pro",
        "GPT_5_5_PRO_2026_04_23": "gpt-5.5-pro-2026-04-23",
        "GPT_5_6_LUNA": "gpt-5.6-luna",
        "GPT_5_6_SOL": "gpt-5.6-sol",
        "GPT_5_6_TERRA": "gpt-5.6-terra",
        "GPT_5_MINI": "gpt-5-mini",
        "GPT_5_MINI_2025_08_07": "gpt-5-mini-2025-08-07",
        "GPT_5_NANO": "gpt-5-nano",
        "GPT_5_NANO_2025_08_07": "gpt-5-nano-2025-08-07",
        "GPT_5_PRO": "gpt-5-pro",
        "GPT_5_PRO_2025_10_06": "gpt-5-pro-2025-10-06",
        "GPT_5_SEARCH_API": "gpt-5-search-api",
        "GPT_5_SEARCH_API_2025_10_14": "gpt-5-search-api-2025-10-14",
        "GPT_6_1_SOL": "gpt-6.1-sol",
        "GPT_6_ASTRA": "gpt-6-astra",
        "GPT_6_LUNA": "gpt-6-luna",
        "GPT_6_SOL": "gpt-6-sol",
        "GPT_AUDIO": "gpt-audio",
        "GPT_AUDIO_1_5": "gpt-audio-1.5",
        "GPT_AUDIO_2025_08_28": "gpt-audio-2025-08-28",
        "GPT_AUDIO_MINI": "gpt-audio-mini",
        "GPT_AUDIO_MINI_2025_12_15": "gpt-audio-mini-2025-12-15",
        "GPT_IMAGE_1": "gpt-image-1",
        "GPT_IMAGE_1_5": "gpt-image-1.5",
        "GPT_IMAGE_1_MINI": "gpt-image-1-mini",
        "GPT_IMAGE_2": "gpt-image-2",
        "GPT_IMAGE_2_2026_04_21": "gpt-image-2-2026-04-21",
        "GPT_IMAGE_2_5_FLARE": "gpt-image-2.5-flare",
        "GPT_IMAGE_2_5_FLARE_2026_09_08": "gpt-image-2.5-flare-2026-09-08",
        "GPT_IMAGE_2_5_SUNBURST": "gpt-image-2.5-sunburst",
        "GPT_IMAGE_2_5_SUNBURST_2026_09_08": "gpt-image-2.5-sunburst-2026-09-08",
        "GPT_LIVE_TRANSCRIBE": "gpt-live-transcribe",
        "GPT_OSS_120B_1": "gpt-oss-120b-1",
        "GPT_OSS_120B_MAAS": "gpt-oss-120b-maas",
        "GPT_OSS_20B_1": "gpt-oss-20b-1",
        "GPT_OSS_SAFEGUARD_120B": "gpt-oss-safeguard-120b",
        "GPT_OSS_SAFEGUARD_20B": "gpt-oss-safeguard-20b",
        "GPT_TRANSCRIBE": "gpt-transcribe",
        "GROK_4_1_FAST_NON_REASONING": "grok-4-1-fast-non-reasoning",
        "GROK_4_1_FAST_REASONING": "grok-4-1-fast-reasoning",
        "KIMI_K2_5": "kimi-k2.5",
        "KIMI_K2_7_CODE": "kimi-k2.7-code",
        "KIMI_K2_THINKING": "kimi-k2-thinking",
        "KIMI_K2_THINKING_MAAS": "kimi-k2-thinking-maas",
        "KIMI_K3": "kimi-k3",
        "KIMI_KIMI_K3": "kimi/kimi-k3",
        "LLAMA3_1_70B_INSTRUCT": "llama3-1-70b-instruct",
        "LLAMA3_1_8B_INSTRUCT": "llama3-1-8b-instruct",
        "LLAMA3_3_70B_INSTRUCT": "llama3-3-70b-instruct",
        "LLAMA4_MAVERICK_17B_INSTRUCT": "llama4-maverick-17b-instruct",
        "LLAMA4_SCOUT_17B_INSTRUCT": "llama4-scout-17b-instruct",
        "LLAMA_3_3_70B_INSTRUCT": "Llama-3.3-70B-Instruct",
        "LLAMA_4_MAVERICK_17B_128E_INSTRUCT_FP8": "Llama-4-Maverick-17B-128E-Instruct-FP8",
        "LLAMA_4_SCOUT_17B_16E_INSTRUCT": "Llama-4-Scout-17B-16E-Instruct",
        "MAGISTRAL_SMALL_2509": "magistral-small-2509",
        "META_LLAMA_3_1_70B_INSTRUCT": "meta/llama-3.1-70b-instruct",
        "META_LLAMA_3_1_8B_INSTRUCT": "meta/llama-3.1-8b-instruct",
        "META_LLAMA_3_2_11B_VISION": "meta/llama-3.2-11b-vision-instruct",
        "META_LLAMA_3_2_11B_VISION_INSTRUCT": "meta/llama-3.2-11b-vision-instruct",
        "META_LLAMA_3_2_1B_INSTRUCT": "meta/llama-3.2-1b-instruct",
        "META_LLAMA_3_2_3B_INSTRUCT": "meta/llama-3.2-3b-instruct",
        "META_LLAMA_3_2_90B_VISION": "meta/llama-3.2-90b-vision-instruct",
        "META_LLAMA_3_2_90B_VISION_INSTRUCT": "meta/llama-3.2-90b-vision-instruct",
        "META_LLAMA_3_3_70B_INSTRUCT": "meta/llama-3.3-70b-instruct",
        "MINIMAX_M2": "minimax-m2",
        "MINIMAX_M2_1": "minimax-m2.1",
        "MINIMAX_M2_5": "minimax-m2.5",
        "MINIMAX_M2_MAAS": "minimax-m2-maas",
        "MINISTRAL_3_14B_INSTRUCT": "ministral-3-14b-instruct",
        "MINISTRAL_3_3B_INSTRUCT": "ministral-3-3b-instruct",
        "MINISTRAL_3_8B_INSTRUCT": "ministral-3-8b-instruct",
        "MISTRAL_LARGE_3_675B_INSTRUCT": "mistral-large-3-675b-instruct",
        "MISTRAL_MEDIUM_2505": "mistral-medium-2505",
        "MISTRAL_SMALL_2503": "mistral-small-2503",
        "NEMOTRON_NANO_12B_V2": "nemotron-nano-12b-v2",
        "NEMOTRON_NANO_3_30B": "nemotron-nano-3-30b",
        "NEMOTRON_NANO_9B_V2": "nemotron-nano-9b-v2",
        "NEMOTRON_SUPER_3_120B": "nemotron-super-3-120b",
        "NOVA_2_LITE": "nova-2-lite",
        "NOVA_LITE": "nova-lite",
        "O1": "o1",
        "O1_2024_12_17": "o1-2024-12-17",
        "O1_PRO": "o1-pro",
        "O1_PRO_2025_03_19": "o1-pro-2025-03-19",
        "O3": "o3",
        "O3_2025_04_16": "o3-2025-04-16",
        "O3_MINI": "o3-mini",
        "O3_MINI_2025_01_31": "o3-mini-2025-01-31",
        "O4_MINI": "o4-mini",
        "O4_MINI_2025_04_16": "o4-mini-2025-04-16",
        "PALMYRA_VISION_7B": "palmyra-vision-7b",
        "PHI_4": "Phi-4",
        "PHI_4_MINI_INSTRUCT": "Phi-4-mini-instruct",
        "PHI_4_MINI_REASONING": "Phi-4-mini-reasoning",
        "PHI_4_MULTIMODAL_INSTRUCT": "Phi-4-multimodal-instruct",
        "PHI_4_REASONING": "Phi-4-reasoning",
        "PIXTRAL_LARGE_2502": "pixtral-large-2502",
        "QWEN2_7B_INSTRUCT": "qwen2-7b-instruct",
        "QWEN3_235B_A22B_2507": "qwen3-235b-a22b-2507",
        "QWEN3_235B_A22B_INSTRUCT_2507_MAAS": "qwen3-235b-a22b-instruct-2507-maas",
        "QWEN3_32B": "qwen3-32b",
        "QWEN3_5_122B_A10B": "qwen3.5-122b-a10b",
        "QWEN3_5_27B": "qwen3.5-27b",
        "QWEN3_5_35B_A3B": "qwen3.5-35b-a3b",
        "QWEN3_5_397B_A17B": "qwen3.5-397b-a17b",
        "QWEN3_5_FLASH": "qwen3.5-flash",
        "QWEN3_5_FLASH_2026_02_23": "qwen3.5-flash-2026-02-23",
        "QWEN3_5_LIVETRANSLATE_FLASH_REALTIME": "qwen3.5-livetranslate-flash-realtime",
        "QWEN3_5_LIVETRANSLATE_FLASH_REALTIME_2026_05_19": "qwen3.5-livetranslate-flash-realtime-2026-05-19",
        "QWEN3_5_OMNI_FLASH": "qwen3.5-omni-flash",
        "QWEN3_5_OMNI_FLASH_2026_03_15": "qwen3.5-omni-flash-2026-03-15",
        "QWEN3_5_OMNI_FLASH_REALTIME": "qwen3.5-omni-flash-realtime",
        "QWEN3_5_OMNI_FLASH_REALTIME_2026_03_15": "qwen3.5-omni-flash-realtime-2026-03-15",
        "QWEN3_5_OMNI_PLUS": "qwen3.5-omni-plus",
        "QWEN3_5_OMNI_PLUS_2026_03_15": "qwen3.5-omni-plus-2026-03-15",
        "QWEN3_5_OMNI_PLUS_REALTIME": "qwen3.5-omni-plus-realtime",
        "QWEN3_5_OMNI_PLUS_REALTIME_2026_03_15": "qwen3.5-omni-plus-realtime-2026-03-15",
        "QWEN3_5_PLUS": "qwen3.5-plus",
        "QWEN3_5_PLUS_2026_02_15": "qwen3.5-plus-2026-02-15",
        "QWEN3_5_PLUS_2026_04_20": "qwen3.5-plus-2026-04-20",
        "QWEN3_6_27B": "qwen3.6-27b",
        "QWEN3_6_35B_A3B": "qwen3.6-35b-a3b",
        "QWEN3_6_FLASH": "qwen3.6-flash",
        "QWEN3_6_FLASH_2026_04_16": "qwen3.6-flash-2026-04-16",
        "QWEN3_6_PLUS": "qwen3.6-plus",
        "QWEN3_6_PLUS_2026_04_02": "qwen3.6-plus-2026-04-02",
        "QWEN3_7_FLASH": "qwen3.7-flash",
        "QWEN3_7_FLASH_2026_07_15": "qwen3.7-flash-2026-07-15",
        "QWEN3_7_MAX": "qwen3.7-max",
        "QWEN3_7_MAX_2026_05_17": "qwen3.7-max-2026-05-17",
        "QWEN3_7_MAX_2026_05_20": "qwen3.7-max-2026-05-20",
        "QWEN3_7_MAX_2026_06_08": "qwen3.7-max-2026-06-08",
        "QWEN3_7_MAX_PREVIEW": "qwen3.7-max-preview",
        "QWEN3_7_PLUS": "qwen3.7-plus",
        "QWEN3_7_PLUS_2026_05_26": "qwen3.7-plus-2026-05-26",
        "QWEN3_8_27B": "qwen3.8-27b",
        "QWEN3_8_2_4T_A95B": "qwen3.8-2.4t-a95b",
        "QWEN3_8_FLASH": "qwen3.8-flash",
        "QWEN3_8_LIVETRANSLATE_FLASH_REALTIME": "qwen3.8-livetranslate-flash-realtime",
        "QWEN3_8_MAX": "qwen3.8-max",
        "QWEN3_8_MAX_0902": "qwen3.8-max-0902",
        "QWEN3_8_OMNI_FLASH": "qwen3.8-omni-flash",
        "QWEN3_CODER_30B_A3B": "qwen3-coder-30b-a3b",
        "QWEN3_CODER_480B_A35B": "qwen3-coder-480b-a35b",
        "QWEN3_CODER_480B_A35B_INSTRUCT_MAAS": "qwen3-coder-480b-a35b-instruct-maas",
        "QWEN3_CODER_FLASH": "qwen3-coder-flash",
        "QWEN3_LIVETRANSLATE_FLASH": "qwen3-livetranslate-flash",
        "QWEN3_LIVETRANSLATE_FLASH_2025_12_01": "qwen3-livetranslate-flash-2025-12-01",
        "QWEN3_NEXT_80B_A3B": "qwen3-next-80b-a3b",
        "QWEN3_NEXT_80B_A3B_INSTRUCT_MAAS": "qwen3-next-80b-a3b-instruct-maas",
        "QWEN3_NEXT_80B_A3B_THINKING_MAAS": "qwen3-next-80b-a3b-thinking-maas",
        "QWEN3_OMNI_FLASH": "qwen3-omni-flash",
        "QWEN3_OMNI_FLASH_REALTIME_2025_09_15": "qwen3-omni-flash-realtime-2025-09-15",
        "QWEN3_S2S_FLASH_REALTIME": "qwen3-s2s-flash-realtime",
        "QWEN3_VL_235B_A22B": "qwen3-vl-235b-a22b",
        "QWEN3_VL_PLUS": "qwen3-vl-plus",
        "QWEN_FLASH": "qwen-flash",
        "QWEN_FLASH_CHARACTER": "qwen-flash-character",
        "QWEN_MAX": "qwen-max",
        "QWEN_MT_FLASH": "qwen-mt-flash",
        "QWEN_MT_LITE": "qwen-mt-lite",
        "QWEN_MT_PLUS": "qwen-mt-plus",
        "QWEN_PLUS": "qwen-plus",
        "QWEN_PLUS_2025_01_25": "qwen-plus-2025-01-25",
        "QWEN_PLUS_2025_04_28": "qwen-plus-2025-04-28",
        "QWEN_PLUS_2025_07_14": "qwen-plus-2025-07-14",
        "QWEN_PLUS_2025_12_01": "qwen-plus-2025-12-01",
        "QWEN_PLUS_CHARACTER": "qwen-plus-character",
        "QWEN_PLUS_LATEST": "qwen-plus-latest",
        "QWEN_TURBO": "qwen-turbo",
        "QWEN_VL_OCR_2025_11_20": "qwen-vl-ocr-2025-11-20",
        "QWQ_PLUS_2025_03_05": "qwq-plus-2025-03-05",
        "R1": "r1",
        "SORA_2": "sora-2",
        "SORA_2_PRO": "sora-2-pro",
        "TEXT_EMBEDDING_3_LARGE": "text-embedding-3-large",
        "TEXT_EMBEDDING_3_SMALL": "text-embedding-3-small",
        "TEXT_EMBEDDING_ADA_002": "text-embedding-ada-002",
        "TTS_1": "tts-1",
        "TTS_1_1106": "tts-1-1106",
        "TTS_1_HD": "tts-1-hd",
        "TTS_1_HD_1106": "tts-1-hd-1106",
        "TYPESAFE_JEV": "typesafe/jev",
        "TYPESAFE_JEV_SYSTEM_ONE": "typesafe/jev",
        "V3": "v3",
        "V3_2": "v3.2",
        "VOXTRAL_MINI_3B_2507": "voxtral-mini-3b-2507",
        "VOXTRAL_SMALL_24B_2507": "voxtral-small-24b-2507",
        "WHISPER_1": "whisper-1",
        "ZHIPU_GLM_5_3": "ZHIPU/GLM-5.3",
    ]
}
