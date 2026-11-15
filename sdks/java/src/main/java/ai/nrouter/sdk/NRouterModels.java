package ai.nrouter.sdk;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Model constants generated from {@code spec/model-catalog-snapshot.json} (snapshot version: 2026-11-14, schema_version: 1, catalog_revision: 1).
 *
 * <p>Do not edit by hand; run {@code node scripts/generate-model-constants.mjs} to regenerate.
 * Naming rule: {@code MODEL_} + uppercase model id with non-alphanumeric runs replaced by {@code _}.
 */
public final class NRouterModels {

    private NRouterModels() {
    }

    public static final String MODEL_AMAZON_NOVA_LITE_V1 = "amazon-nova-lite-v1";
    public static final String MODEL_AMAZON_NOVA_MICRO_V1 = "amazon-nova-micro-v1";
    public static final String MODEL_AMAZON_NOVA_PRO_V1 = "amazon-nova-pro-v1";
    public static final String MODEL_CHATGPT_IMAGE_LATEST = "chatgpt-image-latest";
    public static final String MODEL_CHAT_LATEST = "chat-latest";
    /** @deprecated Model 'claude-3-7-sonnet' is retired. */
    @Deprecated
    public static final String MODEL_CLAUDE_3_7_SONNET = "claude-3-7-sonnet";
    public static final String MODEL_CLAUDE_FABLE_5 = "claude-fable-5";
    public static final String MODEL_CLAUDE_FABLE_5_1 = "claude-fable-5-1";
    public static final String MODEL_CLAUDE_HAIKU_4_5_20251001 = "claude-haiku-4-5-20251001";
    public static final String MODEL_CLAUDE_OPUS_4_5_20251101 = "claude-opus-4-5-20251101";
    public static final String MODEL_CLAUDE_OPUS_4_6 = "claude-opus-4-6";
    public static final String MODEL_CLAUDE_OPUS_4_7 = "claude-opus-4-7";
    public static final String MODEL_CLAUDE_OPUS_4_8 = "claude-opus-4-8";
    public static final String MODEL_CLAUDE_OPUS_5 = "claude-opus-5";
    public static final String MODEL_CLAUDE_OPUS_5_5 = "claude-opus-5-5";
    /** @deprecated Model 'claude-sonnet-4-5-20250929' is retired; compatibility alias for MODEL_CLAUDE_SONNET_4_5_20250929. */
    @Deprecated
    public static final String MODEL_CLAUDE_SONNET_4_5 = "claude-sonnet-4-5-20250929";
    /** @deprecated Model 'claude-sonnet-4-5-20250929' is retired. */
    @Deprecated
    public static final String MODEL_CLAUDE_SONNET_4_5_20250929 = "claude-sonnet-4-5-20250929";
    public static final String MODEL_CLAUDE_SONNET_4_6 = "claude-sonnet-4-6";
    public static final String MODEL_CLAUDE_SONNET_5 = "claude-sonnet-5";
    public static final String MODEL_CLAUDE_SONNET_5_5 = "claude-sonnet-5-5";
    public static final String MODEL_DEEPSEEK_R1_0528_MAAS = "deepseek-r1-0528-maas";
    public static final String MODEL_DEEPSEEK_V3_2_MAAS = "deepseek-v3.2-maas";
    public static final String MODEL_DEEPSEEK_V4_1_FLASH = "deepseek-v4.1-flash";
    public static final String MODEL_DEEPSEEK_V4_FLASH_0731 = "deepseek-v4-flash-0731";
    public static final String MODEL_DEEPSEEK_V4_PRO = "deepseek-v4-pro";
    public static final String MODEL_DEEPSEEK_V4_PRO_0813 = "deepseek-v4-pro-0813";
    public static final String MODEL_DEVSTRAL_2_123B = "devstral-2-123b";
    /** @deprecated Model 'google/gemini-1.5-flash-002' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_1_5_FLASH_002. */
    @Deprecated
    public static final String MODEL_GEMINI_1_5_FLASH_002 = "google/gemini-1.5-flash-002";
    /** @deprecated Model 'google/gemini-1.5-pro-002' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_1_5_PRO_002. */
    @Deprecated
    public static final String MODEL_GEMINI_1_5_PRO_002 = "google/gemini-1.5-pro-002";
    /** @deprecated Model 'google/gemini-2.0-flash' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_0_FLASH. */
    @Deprecated
    public static final String MODEL_GEMINI_2_0_FLASH = "google/gemini-2.0-flash";
    /** @deprecated Model 'google/gemini-2.0-flash-lite' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE. */
    @Deprecated
    public static final String MODEL_GEMINI_2_0_FLASH_LITE = "google/gemini-2.0-flash-lite";
    /** @deprecated Model 'google/gemini-2.5-flash' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_5_FLASH. */
    @Deprecated
    public static final String MODEL_GEMINI_2_5_FLASH = "google/gemini-2.5-flash";
    /** @deprecated Model 'google/gemini-2.5-pro' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_5_PRO. */
    @Deprecated
    public static final String MODEL_GEMINI_2_5_PRO = "google/gemini-2.5-pro";
    /** @deprecated Compatibility alias; use MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE instead. */
    @Deprecated
    public static final String MODEL_GEMINI_3_1_FLASH_LITE = "google/gemini-3.1-flash-lite";
    /** @deprecated Model 'google/gemini-3.1-pro' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_3_1_PRO. */
    @Deprecated
    public static final String MODEL_GEMINI_3_1_PRO = "google/gemini-3.1-pro";
    public static final String MODEL_GEMINI_3_1_PRO_PREVIEW = "gemini-3.1-pro-preview";
    public static final String MODEL_GEMINI_3_5_FLASH = "gemini-3.5-flash";
    public static final String MODEL_GEMINI_3_5_FLASH_LITE = "gemini-3.5-flash-lite";
    public static final String MODEL_GEMINI_3_5_LIVE_TRANSLATE_PREVIEW = "gemini-3.5-live-translate-preview";
    public static final String MODEL_GEMINI_3_6_FLASH = "gemini-3.6-flash";
    public static final String MODEL_GEMINI_3_7_FLASH = "gemini-3.7-flash";
    /** @deprecated Model 'google/gemini-3.8-flash' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_3_8_FLASH. */
    @Deprecated
    public static final String MODEL_GEMINI_3_8_FLASH = "google/gemini-3.8-flash";
    public static final String MODEL_GEMINI_3_FLASH_PREVIEW = "gemini-3-flash-preview";
    public static final String MODEL_GEMMA_3_12B_IT = "gemma-3-12b-it";
    public static final String MODEL_GEMMA_3_27B_IT = "gemma-3-27b-it";
    public static final String MODEL_GEMMA_3_4B_IT = "gemma-3-4b-it";
    public static final String MODEL_GLM_4_7 = "glm-4.7";
    public static final String MODEL_GLM_4_7_FLASH = "glm-4.7-flash";
    public static final String MODEL_GLM_4_7_MAAS = "glm-4.7-maas";
    public static final String MODEL_GLM_5 = "glm-5";
    public static final String MODEL_GLM_5_1 = "glm-5.1";
    public static final String MODEL_GLM_5_2 = "glm-5.2";
    public static final String MODEL_GLM_5_2_FAST_PREVIEW = "glm-5.2-fast-preview";
    public static final String MODEL_GLM_5_2_MAAS = "glm-5.2-maas";
    public static final String MODEL_GLM_5_3 = "glm-5.3";
    public static final String MODEL_GLM_5_3_PRIME = "glm-5.3-prime";
    public static final String MODEL_GLM_5_MAAS = "glm-5-maas";
    public static final String MODEL_GLOBAL_AMAZON_NOVA_2_LITE_V1_0 = "global.amazon.nova-2-lite-v1:0";
    /** @deprecated Model 'google/gemini-1.5-flash-002' is retired. */
    @Deprecated
    public static final String MODEL_GOOGLE_GEMINI_1_5_FLASH_002 = "google/gemini-1.5-flash-002";
    /** @deprecated Model 'google/gemini-1.5-pro-002' is retired. */
    @Deprecated
    public static final String MODEL_GOOGLE_GEMINI_1_5_PRO_002 = "google/gemini-1.5-pro-002";
    /** @deprecated Model 'google/gemini-2.0-flash' is retired. */
    @Deprecated
    public static final String MODEL_GOOGLE_GEMINI_2_0_FLASH = "google/gemini-2.0-flash";
    /** @deprecated Model 'google/gemini-2.0-flash-lite' is retired. */
    @Deprecated
    public static final String MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE = "google/gemini-2.0-flash-lite";
    /** @deprecated Model 'google/gemini-2.5-flash' is retired. */
    @Deprecated
    public static final String MODEL_GOOGLE_GEMINI_2_5_FLASH = "google/gemini-2.5-flash";
    /** @deprecated Model 'google/gemini-2.5-pro' is retired. */
    @Deprecated
    public static final String MODEL_GOOGLE_GEMINI_2_5_PRO = "google/gemini-2.5-pro";
    public static final String MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE = "google/gemini-3.1-flash-lite";
    /** @deprecated Model 'google/gemini-3.1-pro' is retired. */
    @Deprecated
    public static final String MODEL_GOOGLE_GEMINI_3_1_PRO = "google/gemini-3.1-pro";
    /** @deprecated Model 'google/gemini-3.8-flash' is retired. */
    @Deprecated
    public static final String MODEL_GOOGLE_GEMINI_3_8_FLASH = "google/gemini-3.8-flash";
    public static final String MODEL_GPT_3_5_TURBO = "gpt-3.5-turbo";
    public static final String MODEL_GPT_3_5_TURBO_0125 = "gpt-3.5-turbo-0125";
    public static final String MODEL_GPT_3_5_TURBO_1106 = "gpt-3.5-turbo-1106";
    public static final String MODEL_GPT_3_5_TURBO_16K = "gpt-3.5-turbo-16k";
    public static final String MODEL_GPT_3_5_TURBO_INSTRUCT = "gpt-3.5-turbo-instruct";
    public static final String MODEL_GPT_4 = "gpt-4";
    public static final String MODEL_GPT_4O = "gpt-4o";
    public static final String MODEL_GPT_4O_2024_05_13 = "gpt-4o-2024-05-13";
    public static final String MODEL_GPT_4O_2024_08_06 = "gpt-4o-2024-08-06";
    public static final String MODEL_GPT_4O_2024_11_20 = "gpt-4o-2024-11-20";
    public static final String MODEL_GPT_4O_MINI = "gpt-4o-mini";
    public static final String MODEL_GPT_4O_MINI_2024_07_18 = "gpt-4o-mini-2024-07-18";
    public static final String MODEL_GPT_4O_MINI_SEARCH_PREVIEW = "gpt-4o-mini-search-preview";
    public static final String MODEL_GPT_4O_MINI_SEARCH_PREVIEW_2025_03_11 = "gpt-4o-mini-search-preview-2025-03-11";
    public static final String MODEL_GPT_4O_MINI_TRANSCRIBE = "gpt-4o-mini-transcribe";
    public static final String MODEL_GPT_4O_MINI_TRANSCRIBE_2025_03_20 = "gpt-4o-mini-transcribe-2025-03-20";
    public static final String MODEL_GPT_4O_MINI_TRANSCRIBE_2025_12_15 = "gpt-4o-mini-transcribe-2025-12-15";
    public static final String MODEL_GPT_4O_MINI_TTS = "gpt-4o-mini-tts";
    public static final String MODEL_GPT_4O_MINI_TTS_2025_03_20 = "gpt-4o-mini-tts-2025-03-20";
    public static final String MODEL_GPT_4O_MINI_TTS_2025_12_15 = "gpt-4o-mini-tts-2025-12-15";
    public static final String MODEL_GPT_4O_SEARCH_PREVIEW = "gpt-4o-search-preview";
    public static final String MODEL_GPT_4O_SEARCH_PREVIEW_2025_03_11 = "gpt-4o-search-preview-2025-03-11";
    public static final String MODEL_GPT_4O_TRANSCRIBE = "gpt-4o-transcribe";
    public static final String MODEL_GPT_4O_TRANSCRIBE_DIARIZE = "gpt-4o-transcribe-diarize";
    public static final String MODEL_GPT_4_0613 = "gpt-4-0613";
    public static final String MODEL_GPT_4_1 = "gpt-4.1";
    public static final String MODEL_GPT_4_1_2025_04_14 = "gpt-4.1-2025-04-14";
    public static final String MODEL_GPT_4_1_MINI = "gpt-4.1-mini";
    public static final String MODEL_GPT_4_1_MINI_2025_04_14 = "gpt-4.1-mini-2025-04-14";
    public static final String MODEL_GPT_4_1_NANO = "gpt-4.1-nano";
    public static final String MODEL_GPT_4_1_NANO_2025_04_14 = "gpt-4.1-nano-2025-04-14";
    public static final String MODEL_GPT_4_TURBO = "gpt-4-turbo";
    public static final String MODEL_GPT_4_TURBO_2024_04_09 = "gpt-4-turbo-2024-04-09";
    public static final String MODEL_GPT_5 = "gpt-5";
    public static final String MODEL_GPT_5_1 = "gpt-5.1";
    public static final String MODEL_GPT_5_1_2025_11_13 = "gpt-5.1-2025-11-13";
    public static final String MODEL_GPT_5_1_CHAT_LATEST = "gpt-5.1-chat-latest";
    public static final String MODEL_GPT_5_2 = "gpt-5.2";
    public static final String MODEL_GPT_5_2025_08_07 = "gpt-5-2025-08-07";
    public static final String MODEL_GPT_5_2_2025_12_11 = "gpt-5.2-2025-12-11";
    public static final String MODEL_GPT_5_2_CHAT_LATEST = "gpt-5.2-chat-latest";
    public static final String MODEL_GPT_5_2_PRO = "gpt-5.2-pro";
    public static final String MODEL_GPT_5_2_PRO_2025_12_11 = "gpt-5.2-pro-2025-12-11";
    public static final String MODEL_GPT_5_3_CHAT_LATEST = "gpt-5.3-chat-latest";
    public static final String MODEL_GPT_5_3_CODEX = "gpt-5.3-codex";
    public static final String MODEL_GPT_5_4 = "gpt-5.4";
    public static final String MODEL_GPT_5_4_2026_03_05 = "gpt-5.4-2026-03-05";
    public static final String MODEL_GPT_5_4_MINI = "gpt-5.4-mini";
    public static final String MODEL_GPT_5_4_MINI_2026_03_17 = "gpt-5.4-mini-2026-03-17";
    public static final String MODEL_GPT_5_4_NANO = "gpt-5.4-nano";
    public static final String MODEL_GPT_5_4_NANO_2026_03_17 = "gpt-5.4-nano-2026-03-17";
    public static final String MODEL_GPT_5_4_PRO = "gpt-5.4-pro";
    public static final String MODEL_GPT_5_4_PRO_2026_03_05 = "gpt-5.4-pro-2026-03-05";
    public static final String MODEL_GPT_5_5 = "gpt-5.5";
    public static final String MODEL_GPT_5_5_2026_04_23 = "gpt-5.5-2026-04-23";
    public static final String MODEL_GPT_5_5_PRO = "gpt-5.5-pro";
    public static final String MODEL_GPT_5_5_PRO_2026_04_23 = "gpt-5.5-pro-2026-04-23";
    public static final String MODEL_GPT_5_6_LUNA = "gpt-5.6-luna";
    public static final String MODEL_GPT_5_6_SOL = "gpt-5.6-sol";
    public static final String MODEL_GPT_5_6_TERRA = "gpt-5.6-terra";
    public static final String MODEL_GPT_5_MINI = "gpt-5-mini";
    public static final String MODEL_GPT_5_MINI_2025_08_07 = "gpt-5-mini-2025-08-07";
    public static final String MODEL_GPT_5_NANO = "gpt-5-nano";
    public static final String MODEL_GPT_5_NANO_2025_08_07 = "gpt-5-nano-2025-08-07";
    public static final String MODEL_GPT_5_PRO = "gpt-5-pro";
    public static final String MODEL_GPT_5_PRO_2025_10_06 = "gpt-5-pro-2025-10-06";
    public static final String MODEL_GPT_5_SEARCH_API = "gpt-5-search-api";
    public static final String MODEL_GPT_5_SEARCH_API_2025_10_14 = "gpt-5-search-api-2025-10-14";
    public static final String MODEL_GPT_6_1_SOL = "gpt-6.1-sol";
    public static final String MODEL_GPT_6_ASTRA = "gpt-6-astra";
    public static final String MODEL_GPT_6_LUNA = "gpt-6-luna";
    public static final String MODEL_GPT_6_SOL = "gpt-6-sol";
    public static final String MODEL_GPT_AUDIO = "gpt-audio";
    public static final String MODEL_GPT_AUDIO_1_5 = "gpt-audio-1.5";
    public static final String MODEL_GPT_AUDIO_2025_08_28 = "gpt-audio-2025-08-28";
    public static final String MODEL_GPT_AUDIO_MINI = "gpt-audio-mini";
    public static final String MODEL_GPT_AUDIO_MINI_2025_12_15 = "gpt-audio-mini-2025-12-15";
    public static final String MODEL_GPT_IMAGE_1 = "gpt-image-1";
    public static final String MODEL_GPT_IMAGE_1_5 = "gpt-image-1.5";
    public static final String MODEL_GPT_IMAGE_1_MINI = "gpt-image-1-mini";
    public static final String MODEL_GPT_IMAGE_2 = "gpt-image-2";
    public static final String MODEL_GPT_IMAGE_2_2026_04_21 = "gpt-image-2-2026-04-21";
    public static final String MODEL_GPT_IMAGE_2_5_FLARE = "gpt-image-2.5-flare";
    public static final String MODEL_GPT_IMAGE_2_5_FLARE_2026_09_08 = "gpt-image-2.5-flare-2026-09-08";
    public static final String MODEL_GPT_IMAGE_2_5_SUNBURST = "gpt-image-2.5-sunburst";
    public static final String MODEL_GPT_IMAGE_2_5_SUNBURST_2026_09_08 = "gpt-image-2.5-sunburst-2026-09-08";
    public static final String MODEL_GPT_LIVE_TRANSCRIBE = "gpt-live-transcribe";
    public static final String MODEL_GPT_OSS_120B_1 = "gpt-oss-120b-1";
    public static final String MODEL_GPT_OSS_120B_MAAS = "gpt-oss-120b-maas";
    public static final String MODEL_GPT_OSS_20B_1 = "gpt-oss-20b-1";
    public static final String MODEL_GPT_OSS_SAFEGUARD_120B = "gpt-oss-safeguard-120b";
    public static final String MODEL_GPT_OSS_SAFEGUARD_20B = "gpt-oss-safeguard-20b";
    public static final String MODEL_GPT_TRANSCRIBE = "gpt-transcribe";
    public static final String MODEL_GROK_4_1_FAST_NON_REASONING = "grok-4-1-fast-non-reasoning";
    public static final String MODEL_GROK_4_1_FAST_REASONING = "grok-4-1-fast-reasoning";
    public static final String MODEL_KIMI_K2_5 = "kimi-k2.5";
    public static final String MODEL_KIMI_K2_7_CODE = "kimi-k2.7-code";
    public static final String MODEL_KIMI_K2_THINKING = "kimi-k2-thinking";
    public static final String MODEL_KIMI_K2_THINKING_MAAS = "kimi-k2-thinking-maas";
    public static final String MODEL_KIMI_K3 = "kimi-k3";
    public static final String MODEL_KIMI_KIMI_K3 = "kimi/kimi-k3";
    public static final String MODEL_LLAMA3_1_70B_INSTRUCT = "llama3-1-70b-instruct";
    public static final String MODEL_LLAMA3_1_8B_INSTRUCT = "llama3-1-8b-instruct";
    public static final String MODEL_LLAMA3_3_70B_INSTRUCT = "llama3-3-70b-instruct";
    public static final String MODEL_LLAMA4_MAVERICK_17B_INSTRUCT = "llama4-maverick-17b-instruct";
    public static final String MODEL_LLAMA4_SCOUT_17B_INSTRUCT = "llama4-scout-17b-instruct";
    public static final String MODEL_LLAMA_3_3_70B_INSTRUCT = "Llama-3.3-70B-Instruct";
    public static final String MODEL_LLAMA_4_MAVERICK_17B_128E_INSTRUCT_FP8 = "Llama-4-Maverick-17B-128E-Instruct-FP8";
    public static final String MODEL_LLAMA_4_SCOUT_17B_16E_INSTRUCT = "Llama-4-Scout-17B-16E-Instruct";
    public static final String MODEL_MAGISTRAL_SMALL_2509 = "magistral-small-2509";
    /** @deprecated Model 'meta/llama-3.1-70b-instruct' is retired. */
    @Deprecated
    public static final String MODEL_META_LLAMA_3_1_70B_INSTRUCT = "meta/llama-3.1-70b-instruct";
    /** @deprecated Model 'meta/llama-3.1-8b-instruct' is retired. */
    @Deprecated
    public static final String MODEL_META_LLAMA_3_1_8B_INSTRUCT = "meta/llama-3.1-8b-instruct";
    /** @deprecated Model 'meta/llama-3.2-11b-vision-instruct' is retired; compatibility alias for MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT. */
    @Deprecated
    public static final String MODEL_META_LLAMA_3_2_11B_VISION = "meta/llama-3.2-11b-vision-instruct";
    /** @deprecated Model 'meta/llama-3.2-11b-vision-instruct' is retired. */
    @Deprecated
    public static final String MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT = "meta/llama-3.2-11b-vision-instruct";
    /** @deprecated Model 'meta/llama-3.2-1b-instruct' is retired. */
    @Deprecated
    public static final String MODEL_META_LLAMA_3_2_1B_INSTRUCT = "meta/llama-3.2-1b-instruct";
    /** @deprecated Model 'meta/llama-3.2-3b-instruct' is retired. */
    @Deprecated
    public static final String MODEL_META_LLAMA_3_2_3B_INSTRUCT = "meta/llama-3.2-3b-instruct";
    /** @deprecated Model 'meta/llama-3.2-90b-vision-instruct' is retired; compatibility alias for MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT. */
    @Deprecated
    public static final String MODEL_META_LLAMA_3_2_90B_VISION = "meta/llama-3.2-90b-vision-instruct";
    /** @deprecated Model 'meta/llama-3.2-90b-vision-instruct' is retired. */
    @Deprecated
    public static final String MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT = "meta/llama-3.2-90b-vision-instruct";
    /** @deprecated Model 'meta/llama-3.3-70b-instruct' is retired. */
    @Deprecated
    public static final String MODEL_META_LLAMA_3_3_70B_INSTRUCT = "meta/llama-3.3-70b-instruct";
    public static final String MODEL_MINIMAX_M2 = "minimax-m2";
    public static final String MODEL_MINIMAX_M2_1 = "minimax-m2.1";
    public static final String MODEL_MINIMAX_M2_5 = "minimax-m2.5";
    public static final String MODEL_MINIMAX_M2_MAAS = "minimax-m2-maas";
    public static final String MODEL_MINISTRAL_3_14B_INSTRUCT = "ministral-3-14b-instruct";
    public static final String MODEL_MINISTRAL_3_3B_INSTRUCT = "ministral-3-3b-instruct";
    public static final String MODEL_MINISTRAL_3_8B_INSTRUCT = "ministral-3-8b-instruct";
    public static final String MODEL_MISTRAL_LARGE_3_675B_INSTRUCT = "mistral-large-3-675b-instruct";
    public static final String MODEL_MISTRAL_MEDIUM_2505 = "mistral-medium-2505";
    public static final String MODEL_MISTRAL_SMALL_2503 = "mistral-small-2503";
    public static final String MODEL_NEMOTRON_NANO_12B_V2 = "nemotron-nano-12b-v2";
    public static final String MODEL_NEMOTRON_NANO_3_30B = "nemotron-nano-3-30b";
    public static final String MODEL_NEMOTRON_NANO_9B_V2 = "nemotron-nano-9b-v2";
    public static final String MODEL_NEMOTRON_SUPER_3_120B = "nemotron-super-3-120b";
    public static final String MODEL_NOVA_2_LITE = "nova-2-lite";
    public static final String MODEL_NOVA_LITE = "nova-lite";
    public static final String MODEL_O1 = "o1";
    public static final String MODEL_O1_2024_12_17 = "o1-2024-12-17";
    public static final String MODEL_O1_PRO = "o1-pro";
    public static final String MODEL_O1_PRO_2025_03_19 = "o1-pro-2025-03-19";
    public static final String MODEL_O3 = "o3";
    public static final String MODEL_O3_2025_04_16 = "o3-2025-04-16";
    public static final String MODEL_O3_MINI = "o3-mini";
    public static final String MODEL_O3_MINI_2025_01_31 = "o3-mini-2025-01-31";
    public static final String MODEL_O4_MINI = "o4-mini";
    public static final String MODEL_O4_MINI_2025_04_16 = "o4-mini-2025-04-16";
    public static final String MODEL_PALMYRA_VISION_7B = "palmyra-vision-7b";
    public static final String MODEL_PHI_4 = "Phi-4";
    public static final String MODEL_PHI_4_MINI_INSTRUCT = "Phi-4-mini-instruct";
    public static final String MODEL_PHI_4_MINI_REASONING = "Phi-4-mini-reasoning";
    public static final String MODEL_PHI_4_MULTIMODAL_INSTRUCT = "Phi-4-multimodal-instruct";
    public static final String MODEL_PHI_4_REASONING = "Phi-4-reasoning";
    public static final String MODEL_PIXTRAL_LARGE_2502 = "pixtral-large-2502";
    public static final String MODEL_QWEN2_7B_INSTRUCT = "qwen2-7b-instruct";
    public static final String MODEL_QWEN3_235B_A22B_2507 = "qwen3-235b-a22b-2507";
    public static final String MODEL_QWEN3_235B_A22B_INSTRUCT_2507_MAAS = "qwen3-235b-a22b-instruct-2507-maas";
    public static final String MODEL_QWEN3_32B = "qwen3-32b";
    public static final String MODEL_QWEN3_5_122B_A10B = "qwen3.5-122b-a10b";
    public static final String MODEL_QWEN3_5_27B = "qwen3.5-27b";
    public static final String MODEL_QWEN3_5_35B_A3B = "qwen3.5-35b-a3b";
    public static final String MODEL_QWEN3_5_397B_A17B = "qwen3.5-397b-a17b";
    public static final String MODEL_QWEN3_5_FLASH = "qwen3.5-flash";
    public static final String MODEL_QWEN3_5_FLASH_2026_02_23 = "qwen3.5-flash-2026-02-23";
    public static final String MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME = "qwen3.5-livetranslate-flash-realtime";
    public static final String MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME_2026_05_19 = "qwen3.5-livetranslate-flash-realtime-2026-05-19";
    public static final String MODEL_QWEN3_5_OMNI_FLASH = "qwen3.5-omni-flash";
    public static final String MODEL_QWEN3_5_OMNI_FLASH_2026_03_15 = "qwen3.5-omni-flash-2026-03-15";
    public static final String MODEL_QWEN3_5_OMNI_FLASH_REALTIME = "qwen3.5-omni-flash-realtime";
    public static final String MODEL_QWEN3_5_OMNI_FLASH_REALTIME_2026_03_15 = "qwen3.5-omni-flash-realtime-2026-03-15";
    public static final String MODEL_QWEN3_5_OMNI_PLUS = "qwen3.5-omni-plus";
    public static final String MODEL_QWEN3_5_OMNI_PLUS_2026_03_15 = "qwen3.5-omni-plus-2026-03-15";
    public static final String MODEL_QWEN3_5_OMNI_PLUS_REALTIME = "qwen3.5-omni-plus-realtime";
    public static final String MODEL_QWEN3_5_OMNI_PLUS_REALTIME_2026_03_15 = "qwen3.5-omni-plus-realtime-2026-03-15";
    public static final String MODEL_QWEN3_5_PLUS = "qwen3.5-plus";
    public static final String MODEL_QWEN3_5_PLUS_2026_02_15 = "qwen3.5-plus-2026-02-15";
    public static final String MODEL_QWEN3_5_PLUS_2026_04_20 = "qwen3.5-plus-2026-04-20";
    public static final String MODEL_QWEN3_6_27B = "qwen3.6-27b";
    public static final String MODEL_QWEN3_6_35B_A3B = "qwen3.6-35b-a3b";
    public static final String MODEL_QWEN3_6_FLASH = "qwen3.6-flash";
    public static final String MODEL_QWEN3_6_FLASH_2026_04_16 = "qwen3.6-flash-2026-04-16";
    public static final String MODEL_QWEN3_6_PLUS = "qwen3.6-plus";
    public static final String MODEL_QWEN3_6_PLUS_2026_04_02 = "qwen3.6-plus-2026-04-02";
    public static final String MODEL_QWEN3_7_FLASH = "qwen3.7-flash";
    public static final String MODEL_QWEN3_7_FLASH_2026_07_15 = "qwen3.7-flash-2026-07-15";
    public static final String MODEL_QWEN3_7_MAX = "qwen3.7-max";
    public static final String MODEL_QWEN3_7_MAX_2026_05_17 = "qwen3.7-max-2026-05-17";
    public static final String MODEL_QWEN3_7_MAX_2026_05_20 = "qwen3.7-max-2026-05-20";
    public static final String MODEL_QWEN3_7_MAX_2026_06_08 = "qwen3.7-max-2026-06-08";
    public static final String MODEL_QWEN3_7_MAX_PREVIEW = "qwen3.7-max-preview";
    public static final String MODEL_QWEN3_7_PLUS = "qwen3.7-plus";
    public static final String MODEL_QWEN3_7_PLUS_2026_05_26 = "qwen3.7-plus-2026-05-26";
    public static final String MODEL_QWEN3_8_27B = "qwen3.8-27b";
    public static final String MODEL_QWEN3_8_2_4T_A95B = "qwen3.8-2.4t-a95b";
    public static final String MODEL_QWEN3_8_FLASH = "qwen3.8-flash";
    public static final String MODEL_QWEN3_8_LIVETRANSLATE_FLASH_REALTIME = "qwen3.8-livetranslate-flash-realtime";
    public static final String MODEL_QWEN3_8_MAX = "qwen3.8-max";
    public static final String MODEL_QWEN3_8_MAX_0902 = "qwen3.8-max-0902";
    public static final String MODEL_QWEN3_8_OMNI_FLASH = "qwen3.8-omni-flash";
    public static final String MODEL_QWEN3_CODER_30B_A3B = "qwen3-coder-30b-a3b";
    public static final String MODEL_QWEN3_CODER_480B_A35B = "qwen3-coder-480b-a35b";
    public static final String MODEL_QWEN3_CODER_480B_A35B_INSTRUCT_MAAS = "qwen3-coder-480b-a35b-instruct-maas";
    public static final String MODEL_QWEN3_CODER_FLASH = "qwen3-coder-flash";
    public static final String MODEL_QWEN3_LIVETRANSLATE_FLASH = "qwen3-livetranslate-flash";
    public static final String MODEL_QWEN3_LIVETRANSLATE_FLASH_2025_12_01 = "qwen3-livetranslate-flash-2025-12-01";
    public static final String MODEL_QWEN3_NEXT_80B_A3B = "qwen3-next-80b-a3b";
    public static final String MODEL_QWEN3_NEXT_80B_A3B_INSTRUCT_MAAS = "qwen3-next-80b-a3b-instruct-maas";
    public static final String MODEL_QWEN3_NEXT_80B_A3B_THINKING_MAAS = "qwen3-next-80b-a3b-thinking-maas";
    public static final String MODEL_QWEN3_OMNI_FLASH = "qwen3-omni-flash";
    public static final String MODEL_QWEN3_OMNI_FLASH_REALTIME_2025_09_15 = "qwen3-omni-flash-realtime-2025-09-15";
    public static final String MODEL_QWEN3_S2S_FLASH_REALTIME = "qwen3-s2s-flash-realtime";
    public static final String MODEL_QWEN3_VL_235B_A22B = "qwen3-vl-235b-a22b";
    public static final String MODEL_QWEN3_VL_PLUS = "qwen3-vl-plus";
    public static final String MODEL_QWEN_FLASH = "qwen-flash";
    public static final String MODEL_QWEN_FLASH_CHARACTER = "qwen-flash-character";
    public static final String MODEL_QWEN_MAX = "qwen-max";
    public static final String MODEL_QWEN_MT_FLASH = "qwen-mt-flash";
    public static final String MODEL_QWEN_MT_LITE = "qwen-mt-lite";
    public static final String MODEL_QWEN_MT_PLUS = "qwen-mt-plus";
    public static final String MODEL_QWEN_PLUS = "qwen-plus";
    public static final String MODEL_QWEN_PLUS_2025_01_25 = "qwen-plus-2025-01-25";
    public static final String MODEL_QWEN_PLUS_2025_04_28 = "qwen-plus-2025-04-28";
    public static final String MODEL_QWEN_PLUS_2025_07_14 = "qwen-plus-2025-07-14";
    public static final String MODEL_QWEN_PLUS_2025_12_01 = "qwen-plus-2025-12-01";
    public static final String MODEL_QWEN_PLUS_CHARACTER = "qwen-plus-character";
    public static final String MODEL_QWEN_PLUS_LATEST = "qwen-plus-latest";
    public static final String MODEL_QWEN_TURBO = "qwen-turbo";
    public static final String MODEL_QWEN_VL_OCR_2025_11_20 = "qwen-vl-ocr-2025-11-20";
    public static final String MODEL_QWQ_PLUS_2025_03_05 = "qwq-plus-2025-03-05";
    public static final String MODEL_R1 = "r1";
    public static final String MODEL_SORA_2 = "sora-2";
    public static final String MODEL_SORA_2_PRO = "sora-2-pro";
    public static final String MODEL_TEXT_EMBEDDING_3_LARGE = "text-embedding-3-large";
    public static final String MODEL_TEXT_EMBEDDING_3_SMALL = "text-embedding-3-small";
    public static final String MODEL_TEXT_EMBEDDING_ADA_002 = "text-embedding-ada-002";
    public static final String MODEL_TTS_1 = "tts-1";
    public static final String MODEL_TTS_1_1106 = "tts-1-1106";
    public static final String MODEL_TTS_1_HD = "tts-1-hd";
    public static final String MODEL_TTS_1_HD_1106 = "tts-1-hd-1106";
    public static final String MODEL_TYPESAFE_JEV = "typesafe/jev";
    /** @deprecated Compatibility alias; use MODEL_TYPESAFE_JEV instead. */
    @Deprecated
    public static final String MODEL_TYPESAFE_JEV_SYSTEM_ONE = "typesafe/jev";
    public static final String MODEL_V3 = "v3";
    public static final String MODEL_V3_2 = "v3.2";
    public static final String MODEL_VOXTRAL_MINI_3B_2507 = "voxtral-mini-3b-2507";
    public static final String MODEL_VOXTRAL_SMALL_24B_2507 = "voxtral-small-24b-2507";
    public static final String MODEL_WHISPER_1 = "whisper-1";
    public static final String MODEL_ZHIPU_GLM_5_3 = "ZHIPU/GLM-5.3";

    /** Unmodifiable map of well-known model keys matching {@code MODELS} across all nRouter SDKs. */
    public static final Map<String, String> MODELS = buildModels();

    @SuppressWarnings("deprecation")
    private static Map<String, String> buildModels() {
        Map<String, String> map = new LinkedHashMap<>();
        map.put("AMAZON_NOVA_LITE_V1", MODEL_AMAZON_NOVA_LITE_V1);
        map.put("AMAZON_NOVA_MICRO_V1", MODEL_AMAZON_NOVA_MICRO_V1);
        map.put("AMAZON_NOVA_PRO_V1", MODEL_AMAZON_NOVA_PRO_V1);
        map.put("CHATGPT_IMAGE_LATEST", MODEL_CHATGPT_IMAGE_LATEST);
        map.put("CHAT_LATEST", MODEL_CHAT_LATEST);
        map.put("CLAUDE_3_7_SONNET", MODEL_CLAUDE_3_7_SONNET);
        map.put("CLAUDE_FABLE_5", MODEL_CLAUDE_FABLE_5);
        map.put("CLAUDE_FABLE_5_1", MODEL_CLAUDE_FABLE_5_1);
        map.put("CLAUDE_HAIKU_4_5_20251001", MODEL_CLAUDE_HAIKU_4_5_20251001);
        map.put("CLAUDE_OPUS_4_5_20251101", MODEL_CLAUDE_OPUS_4_5_20251101);
        map.put("CLAUDE_OPUS_4_6", MODEL_CLAUDE_OPUS_4_6);
        map.put("CLAUDE_OPUS_4_7", MODEL_CLAUDE_OPUS_4_7);
        map.put("CLAUDE_OPUS_4_8", MODEL_CLAUDE_OPUS_4_8);
        map.put("CLAUDE_OPUS_5", MODEL_CLAUDE_OPUS_5);
        map.put("CLAUDE_OPUS_5_5", MODEL_CLAUDE_OPUS_5_5);
        map.put("CLAUDE_SONNET_4_5", MODEL_CLAUDE_SONNET_4_5);
        map.put("CLAUDE_SONNET_4_5_20250929", MODEL_CLAUDE_SONNET_4_5_20250929);
        map.put("CLAUDE_SONNET_4_6", MODEL_CLAUDE_SONNET_4_6);
        map.put("CLAUDE_SONNET_5", MODEL_CLAUDE_SONNET_5);
        map.put("CLAUDE_SONNET_5_5", MODEL_CLAUDE_SONNET_5_5);
        map.put("DEEPSEEK_R1_0528_MAAS", MODEL_DEEPSEEK_R1_0528_MAAS);
        map.put("DEEPSEEK_V3_2_MAAS", MODEL_DEEPSEEK_V3_2_MAAS);
        map.put("DEEPSEEK_V4_1_FLASH", MODEL_DEEPSEEK_V4_1_FLASH);
        map.put("DEEPSEEK_V4_FLASH_0731", MODEL_DEEPSEEK_V4_FLASH_0731);
        map.put("DEEPSEEK_V4_PRO", MODEL_DEEPSEEK_V4_PRO);
        map.put("DEEPSEEK_V4_PRO_0813", MODEL_DEEPSEEK_V4_PRO_0813);
        map.put("DEVSTRAL_2_123B", MODEL_DEVSTRAL_2_123B);
        map.put("GEMINI_1_5_FLASH_002", MODEL_GEMINI_1_5_FLASH_002);
        map.put("GEMINI_1_5_PRO_002", MODEL_GEMINI_1_5_PRO_002);
        map.put("GEMINI_2_0_FLASH", MODEL_GEMINI_2_0_FLASH);
        map.put("GEMINI_2_0_FLASH_LITE", MODEL_GEMINI_2_0_FLASH_LITE);
        map.put("GEMINI_2_5_FLASH", "gemini-2.5-flash");
        map.put("GEMINI_2_5_PRO", "gemini-2.5-pro");
        map.put("GEMINI_3_1_FLASH_LITE", MODEL_GEMINI_3_1_FLASH_LITE);
        map.put("GEMINI_3_1_PRO", MODEL_GEMINI_3_1_PRO);
        map.put("GEMINI_3_1_PRO_PREVIEW", MODEL_GEMINI_3_1_PRO_PREVIEW);
        map.put("GEMINI_3_5_FLASH", MODEL_GEMINI_3_5_FLASH);
        map.put("GEMINI_3_5_FLASH_LITE", MODEL_GEMINI_3_5_FLASH_LITE);
        map.put("GEMINI_3_5_LIVE_TRANSLATE_PREVIEW", MODEL_GEMINI_3_5_LIVE_TRANSLATE_PREVIEW);
        map.put("GEMINI_3_6_FLASH", MODEL_GEMINI_3_6_FLASH);
        map.put("GEMINI_3_7_FLASH", MODEL_GEMINI_3_7_FLASH);
        map.put("GEMINI_3_8_FLASH", MODEL_GEMINI_3_8_FLASH);
        map.put("GEMINI_3_FLASH_PREVIEW", MODEL_GEMINI_3_FLASH_PREVIEW);
        map.put("GEMMA_3_12B_IT", MODEL_GEMMA_3_12B_IT);
        map.put("GEMMA_3_27B_IT", MODEL_GEMMA_3_27B_IT);
        map.put("GEMMA_3_4B_IT", MODEL_GEMMA_3_4B_IT);
        map.put("GLM_4_7", MODEL_GLM_4_7);
        map.put("GLM_4_7_FLASH", MODEL_GLM_4_7_FLASH);
        map.put("GLM_4_7_MAAS", MODEL_GLM_4_7_MAAS);
        map.put("GLM_5", MODEL_GLM_5);
        map.put("GLM_5_1", MODEL_GLM_5_1);
        map.put("GLM_5_2", MODEL_GLM_5_2);
        map.put("GLM_5_2_FAST_PREVIEW", MODEL_GLM_5_2_FAST_PREVIEW);
        map.put("GLM_5_2_MAAS", MODEL_GLM_5_2_MAAS);
        map.put("GLM_5_3", MODEL_GLM_5_3);
        map.put("GLM_5_3_PRIME", MODEL_GLM_5_3_PRIME);
        map.put("GLM_5_MAAS", MODEL_GLM_5_MAAS);
        map.put("GLOBAL_AMAZON_NOVA_2_LITE_V1_0", MODEL_GLOBAL_AMAZON_NOVA_2_LITE_V1_0);
        map.put("GOOGLE_GEMINI_1_5_FLASH_002", MODEL_GOOGLE_GEMINI_1_5_FLASH_002);
        map.put("GOOGLE_GEMINI_1_5_PRO_002", MODEL_GOOGLE_GEMINI_1_5_PRO_002);
        map.put("GOOGLE_GEMINI_2_0_FLASH", MODEL_GOOGLE_GEMINI_2_0_FLASH);
        map.put("GOOGLE_GEMINI_2_0_FLASH_LITE", MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE);
        map.put("GOOGLE_GEMINI_2_5_FLASH", MODEL_GOOGLE_GEMINI_2_5_FLASH);
        map.put("GOOGLE_GEMINI_2_5_PRO", MODEL_GOOGLE_GEMINI_2_5_PRO);
        map.put("GOOGLE_GEMINI_3_1_FLASH_LITE", MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE);
        map.put("GOOGLE_GEMINI_3_1_PRO", MODEL_GOOGLE_GEMINI_3_1_PRO);
        map.put("GOOGLE_GEMINI_3_8_FLASH", MODEL_GOOGLE_GEMINI_3_8_FLASH);
        map.put("GPT_3_5_TURBO", MODEL_GPT_3_5_TURBO);
        map.put("GPT_3_5_TURBO_0125", MODEL_GPT_3_5_TURBO_0125);
        map.put("GPT_3_5_TURBO_1106", MODEL_GPT_3_5_TURBO_1106);
        map.put("GPT_3_5_TURBO_16K", MODEL_GPT_3_5_TURBO_16K);
        map.put("GPT_3_5_TURBO_INSTRUCT", MODEL_GPT_3_5_TURBO_INSTRUCT);
        map.put("GPT_4", MODEL_GPT_4);
        map.put("GPT_4O", MODEL_GPT_4O);
        map.put("GPT_4O_2024_05_13", MODEL_GPT_4O_2024_05_13);
        map.put("GPT_4O_2024_08_06", MODEL_GPT_4O_2024_08_06);
        map.put("GPT_4O_2024_11_20", MODEL_GPT_4O_2024_11_20);
        map.put("GPT_4O_MINI", MODEL_GPT_4O_MINI);
        map.put("GPT_4O_MINI_2024_07_18", MODEL_GPT_4O_MINI_2024_07_18);
        map.put("GPT_4O_MINI_SEARCH_PREVIEW", MODEL_GPT_4O_MINI_SEARCH_PREVIEW);
        map.put("GPT_4O_MINI_SEARCH_PREVIEW_2025_03_11", MODEL_GPT_4O_MINI_SEARCH_PREVIEW_2025_03_11);
        map.put("GPT_4O_MINI_TRANSCRIBE", MODEL_GPT_4O_MINI_TRANSCRIBE);
        map.put("GPT_4O_MINI_TRANSCRIBE_2025_03_20", MODEL_GPT_4O_MINI_TRANSCRIBE_2025_03_20);
        map.put("GPT_4O_MINI_TRANSCRIBE_2025_12_15", MODEL_GPT_4O_MINI_TRANSCRIBE_2025_12_15);
        map.put("GPT_4O_MINI_TTS", MODEL_GPT_4O_MINI_TTS);
        map.put("GPT_4O_MINI_TTS_2025_03_20", MODEL_GPT_4O_MINI_TTS_2025_03_20);
        map.put("GPT_4O_MINI_TTS_2025_12_15", MODEL_GPT_4O_MINI_TTS_2025_12_15);
        map.put("GPT_4O_SEARCH_PREVIEW", MODEL_GPT_4O_SEARCH_PREVIEW);
        map.put("GPT_4O_SEARCH_PREVIEW_2025_03_11", MODEL_GPT_4O_SEARCH_PREVIEW_2025_03_11);
        map.put("GPT_4O_TRANSCRIBE", MODEL_GPT_4O_TRANSCRIBE);
        map.put("GPT_4O_TRANSCRIBE_DIARIZE", MODEL_GPT_4O_TRANSCRIBE_DIARIZE);
        map.put("GPT_4_0613", MODEL_GPT_4_0613);
        map.put("GPT_4_1", MODEL_GPT_4_1);
        map.put("GPT_4_1_2025_04_14", MODEL_GPT_4_1_2025_04_14);
        map.put("GPT_4_1_MINI", MODEL_GPT_4_1_MINI);
        map.put("GPT_4_1_MINI_2025_04_14", MODEL_GPT_4_1_MINI_2025_04_14);
        map.put("GPT_4_1_NANO", MODEL_GPT_4_1_NANO);
        map.put("GPT_4_1_NANO_2025_04_14", MODEL_GPT_4_1_NANO_2025_04_14);
        map.put("GPT_4_TURBO", MODEL_GPT_4_TURBO);
        map.put("GPT_4_TURBO_2024_04_09", MODEL_GPT_4_TURBO_2024_04_09);
        map.put("GPT_5", MODEL_GPT_5);
        map.put("GPT_5_1", MODEL_GPT_5_1);
        map.put("GPT_5_1_2025_11_13", MODEL_GPT_5_1_2025_11_13);
        map.put("GPT_5_1_CHAT_LATEST", MODEL_GPT_5_1_CHAT_LATEST);
        map.put("GPT_5_2", MODEL_GPT_5_2);
        map.put("GPT_5_2025_08_07", MODEL_GPT_5_2025_08_07);
        map.put("GPT_5_2_2025_12_11", MODEL_GPT_5_2_2025_12_11);
        map.put("GPT_5_2_CHAT_LATEST", MODEL_GPT_5_2_CHAT_LATEST);
        map.put("GPT_5_2_PRO", MODEL_GPT_5_2_PRO);
        map.put("GPT_5_2_PRO_2025_12_11", MODEL_GPT_5_2_PRO_2025_12_11);
        map.put("GPT_5_3_CHAT_LATEST", MODEL_GPT_5_3_CHAT_LATEST);
        map.put("GPT_5_3_CODEX", MODEL_GPT_5_3_CODEX);
        map.put("GPT_5_4", MODEL_GPT_5_4);
        map.put("GPT_5_4_2026_03_05", MODEL_GPT_5_4_2026_03_05);
        map.put("GPT_5_4_MINI", MODEL_GPT_5_4_MINI);
        map.put("GPT_5_4_MINI_2026_03_17", MODEL_GPT_5_4_MINI_2026_03_17);
        map.put("GPT_5_4_NANO", MODEL_GPT_5_4_NANO);
        map.put("GPT_5_4_NANO_2026_03_17", MODEL_GPT_5_4_NANO_2026_03_17);
        map.put("GPT_5_4_PRO", MODEL_GPT_5_4_PRO);
        map.put("GPT_5_4_PRO_2026_03_05", MODEL_GPT_5_4_PRO_2026_03_05);
        map.put("GPT_5_5", MODEL_GPT_5_5);
        map.put("GPT_5_5_2026_04_23", MODEL_GPT_5_5_2026_04_23);
        map.put("GPT_5_5_PRO", MODEL_GPT_5_5_PRO);
        map.put("GPT_5_5_PRO_2026_04_23", MODEL_GPT_5_5_PRO_2026_04_23);
        map.put("GPT_5_6_LUNA", MODEL_GPT_5_6_LUNA);
        map.put("GPT_5_6_SOL", MODEL_GPT_5_6_SOL);
        map.put("GPT_5_6_TERRA", MODEL_GPT_5_6_TERRA);
        map.put("GPT_5_MINI", MODEL_GPT_5_MINI);
        map.put("GPT_5_MINI_2025_08_07", MODEL_GPT_5_MINI_2025_08_07);
        map.put("GPT_5_NANO", MODEL_GPT_5_NANO);
        map.put("GPT_5_NANO_2025_08_07", MODEL_GPT_5_NANO_2025_08_07);
        map.put("GPT_5_PRO", MODEL_GPT_5_PRO);
        map.put("GPT_5_PRO_2025_10_06", MODEL_GPT_5_PRO_2025_10_06);
        map.put("GPT_5_SEARCH_API", MODEL_GPT_5_SEARCH_API);
        map.put("GPT_5_SEARCH_API_2025_10_14", MODEL_GPT_5_SEARCH_API_2025_10_14);
        map.put("GPT_6_1_SOL", MODEL_GPT_6_1_SOL);
        map.put("GPT_6_ASTRA", MODEL_GPT_6_ASTRA);
        map.put("GPT_6_LUNA", MODEL_GPT_6_LUNA);
        map.put("GPT_6_SOL", MODEL_GPT_6_SOL);
        map.put("GPT_AUDIO", MODEL_GPT_AUDIO);
        map.put("GPT_AUDIO_1_5", MODEL_GPT_AUDIO_1_5);
        map.put("GPT_AUDIO_2025_08_28", MODEL_GPT_AUDIO_2025_08_28);
        map.put("GPT_AUDIO_MINI", MODEL_GPT_AUDIO_MINI);
        map.put("GPT_AUDIO_MINI_2025_12_15", MODEL_GPT_AUDIO_MINI_2025_12_15);
        map.put("GPT_IMAGE_1", MODEL_GPT_IMAGE_1);
        map.put("GPT_IMAGE_1_5", MODEL_GPT_IMAGE_1_5);
        map.put("GPT_IMAGE_1_MINI", MODEL_GPT_IMAGE_1_MINI);
        map.put("GPT_IMAGE_2", MODEL_GPT_IMAGE_2);
        map.put("GPT_IMAGE_2_2026_04_21", MODEL_GPT_IMAGE_2_2026_04_21);
        map.put("GPT_IMAGE_2_5_FLARE", MODEL_GPT_IMAGE_2_5_FLARE);
        map.put("GPT_IMAGE_2_5_FLARE_2026_09_08", MODEL_GPT_IMAGE_2_5_FLARE_2026_09_08);
        map.put("GPT_IMAGE_2_5_SUNBURST", MODEL_GPT_IMAGE_2_5_SUNBURST);
        map.put("GPT_IMAGE_2_5_SUNBURST_2026_09_08", MODEL_GPT_IMAGE_2_5_SUNBURST_2026_09_08);
        map.put("GPT_LIVE_TRANSCRIBE", MODEL_GPT_LIVE_TRANSCRIBE);
        map.put("GPT_OSS_120B_1", MODEL_GPT_OSS_120B_1);
        map.put("GPT_OSS_120B_MAAS", MODEL_GPT_OSS_120B_MAAS);
        map.put("GPT_OSS_20B_1", MODEL_GPT_OSS_20B_1);
        map.put("GPT_OSS_SAFEGUARD_120B", MODEL_GPT_OSS_SAFEGUARD_120B);
        map.put("GPT_OSS_SAFEGUARD_20B", MODEL_GPT_OSS_SAFEGUARD_20B);
        map.put("GPT_TRANSCRIBE", MODEL_GPT_TRANSCRIBE);
        map.put("GROK_4_1_FAST_NON_REASONING", MODEL_GROK_4_1_FAST_NON_REASONING);
        map.put("GROK_4_1_FAST_REASONING", MODEL_GROK_4_1_FAST_REASONING);
        map.put("KIMI_K2_5", MODEL_KIMI_K2_5);
        map.put("KIMI_K2_7_CODE", MODEL_KIMI_K2_7_CODE);
        map.put("KIMI_K2_THINKING", MODEL_KIMI_K2_THINKING);
        map.put("KIMI_K2_THINKING_MAAS", MODEL_KIMI_K2_THINKING_MAAS);
        map.put("KIMI_K3", MODEL_KIMI_K3);
        map.put("KIMI_KIMI_K3", MODEL_KIMI_KIMI_K3);
        map.put("LLAMA3_1_70B_INSTRUCT", MODEL_LLAMA3_1_70B_INSTRUCT);
        map.put("LLAMA3_1_8B_INSTRUCT", MODEL_LLAMA3_1_8B_INSTRUCT);
        map.put("LLAMA3_3_70B_INSTRUCT", MODEL_LLAMA3_3_70B_INSTRUCT);
        map.put("LLAMA4_MAVERICK_17B_INSTRUCT", MODEL_LLAMA4_MAVERICK_17B_INSTRUCT);
        map.put("LLAMA4_SCOUT_17B_INSTRUCT", MODEL_LLAMA4_SCOUT_17B_INSTRUCT);
        map.put("LLAMA_3_3_70B_INSTRUCT", MODEL_LLAMA_3_3_70B_INSTRUCT);
        map.put("LLAMA_4_MAVERICK_17B_128E_INSTRUCT_FP8", MODEL_LLAMA_4_MAVERICK_17B_128E_INSTRUCT_FP8);
        map.put("LLAMA_4_SCOUT_17B_16E_INSTRUCT", MODEL_LLAMA_4_SCOUT_17B_16E_INSTRUCT);
        map.put("MAGISTRAL_SMALL_2509", MODEL_MAGISTRAL_SMALL_2509);
        map.put("META_LLAMA_3_1_70B_INSTRUCT", MODEL_META_LLAMA_3_1_70B_INSTRUCT);
        map.put("META_LLAMA_3_1_8B_INSTRUCT", MODEL_META_LLAMA_3_1_8B_INSTRUCT);
        map.put("META_LLAMA_3_2_11B_VISION", MODEL_META_LLAMA_3_2_11B_VISION);
        map.put("META_LLAMA_3_2_11B_VISION_INSTRUCT", MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT);
        map.put("META_LLAMA_3_2_1B_INSTRUCT", MODEL_META_LLAMA_3_2_1B_INSTRUCT);
        map.put("META_LLAMA_3_2_3B_INSTRUCT", MODEL_META_LLAMA_3_2_3B_INSTRUCT);
        map.put("META_LLAMA_3_2_90B_VISION", MODEL_META_LLAMA_3_2_90B_VISION);
        map.put("META_LLAMA_3_2_90B_VISION_INSTRUCT", MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT);
        map.put("META_LLAMA_3_3_70B_INSTRUCT", MODEL_META_LLAMA_3_3_70B_INSTRUCT);
        map.put("MINIMAX_M2", MODEL_MINIMAX_M2);
        map.put("MINIMAX_M2_1", MODEL_MINIMAX_M2_1);
        map.put("MINIMAX_M2_5", MODEL_MINIMAX_M2_5);
        map.put("MINIMAX_M2_MAAS", MODEL_MINIMAX_M2_MAAS);
        map.put("MINISTRAL_3_14B_INSTRUCT", MODEL_MINISTRAL_3_14B_INSTRUCT);
        map.put("MINISTRAL_3_3B_INSTRUCT", MODEL_MINISTRAL_3_3B_INSTRUCT);
        map.put("MINISTRAL_3_8B_INSTRUCT", MODEL_MINISTRAL_3_8B_INSTRUCT);
        map.put("MISTRAL_LARGE_3_675B_INSTRUCT", MODEL_MISTRAL_LARGE_3_675B_INSTRUCT);
        map.put("MISTRAL_MEDIUM_2505", MODEL_MISTRAL_MEDIUM_2505);
        map.put("MISTRAL_SMALL_2503", MODEL_MISTRAL_SMALL_2503);
        map.put("NEMOTRON_NANO_12B_V2", MODEL_NEMOTRON_NANO_12B_V2);
        map.put("NEMOTRON_NANO_3_30B", MODEL_NEMOTRON_NANO_3_30B);
        map.put("NEMOTRON_NANO_9B_V2", MODEL_NEMOTRON_NANO_9B_V2);
        map.put("NEMOTRON_SUPER_3_120B", MODEL_NEMOTRON_SUPER_3_120B);
        map.put("NOVA_2_LITE", MODEL_NOVA_2_LITE);
        map.put("NOVA_LITE", MODEL_NOVA_LITE);
        map.put("O1", MODEL_O1);
        map.put("O1_2024_12_17", MODEL_O1_2024_12_17);
        map.put("O1_PRO", MODEL_O1_PRO);
        map.put("O1_PRO_2025_03_19", MODEL_O1_PRO_2025_03_19);
        map.put("O3", MODEL_O3);
        map.put("O3_2025_04_16", MODEL_O3_2025_04_16);
        map.put("O3_MINI", MODEL_O3_MINI);
        map.put("O3_MINI_2025_01_31", MODEL_O3_MINI_2025_01_31);
        map.put("O4_MINI", MODEL_O4_MINI);
        map.put("O4_MINI_2025_04_16", MODEL_O4_MINI_2025_04_16);
        map.put("PALMYRA_VISION_7B", MODEL_PALMYRA_VISION_7B);
        map.put("PHI_4", MODEL_PHI_4);
        map.put("PHI_4_MINI_INSTRUCT", MODEL_PHI_4_MINI_INSTRUCT);
        map.put("PHI_4_MINI_REASONING", MODEL_PHI_4_MINI_REASONING);
        map.put("PHI_4_MULTIMODAL_INSTRUCT", MODEL_PHI_4_MULTIMODAL_INSTRUCT);
        map.put("PHI_4_REASONING", MODEL_PHI_4_REASONING);
        map.put("PIXTRAL_LARGE_2502", MODEL_PIXTRAL_LARGE_2502);
        map.put("QWEN2_7B_INSTRUCT", MODEL_QWEN2_7B_INSTRUCT);
        map.put("QWEN3_235B_A22B_2507", MODEL_QWEN3_235B_A22B_2507);
        map.put("QWEN3_235B_A22B_INSTRUCT_2507_MAAS", MODEL_QWEN3_235B_A22B_INSTRUCT_2507_MAAS);
        map.put("QWEN3_32B", MODEL_QWEN3_32B);
        map.put("QWEN3_5_122B_A10B", MODEL_QWEN3_5_122B_A10B);
        map.put("QWEN3_5_27B", MODEL_QWEN3_5_27B);
        map.put("QWEN3_5_35B_A3B", MODEL_QWEN3_5_35B_A3B);
        map.put("QWEN3_5_397B_A17B", MODEL_QWEN3_5_397B_A17B);
        map.put("QWEN3_5_FLASH", MODEL_QWEN3_5_FLASH);
        map.put("QWEN3_5_FLASH_2026_02_23", MODEL_QWEN3_5_FLASH_2026_02_23);
        map.put("QWEN3_5_LIVETRANSLATE_FLASH_REALTIME", MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME);
        map.put("QWEN3_5_LIVETRANSLATE_FLASH_REALTIME_2026_05_19", MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME_2026_05_19);
        map.put("QWEN3_5_OMNI_FLASH", MODEL_QWEN3_5_OMNI_FLASH);
        map.put("QWEN3_5_OMNI_FLASH_2026_03_15", MODEL_QWEN3_5_OMNI_FLASH_2026_03_15);
        map.put("QWEN3_5_OMNI_FLASH_REALTIME", MODEL_QWEN3_5_OMNI_FLASH_REALTIME);
        map.put("QWEN3_5_OMNI_FLASH_REALTIME_2026_03_15", MODEL_QWEN3_5_OMNI_FLASH_REALTIME_2026_03_15);
        map.put("QWEN3_5_OMNI_PLUS", MODEL_QWEN3_5_OMNI_PLUS);
        map.put("QWEN3_5_OMNI_PLUS_2026_03_15", MODEL_QWEN3_5_OMNI_PLUS_2026_03_15);
        map.put("QWEN3_5_OMNI_PLUS_REALTIME", MODEL_QWEN3_5_OMNI_PLUS_REALTIME);
        map.put("QWEN3_5_OMNI_PLUS_REALTIME_2026_03_15", MODEL_QWEN3_5_OMNI_PLUS_REALTIME_2026_03_15);
        map.put("QWEN3_5_PLUS", MODEL_QWEN3_5_PLUS);
        map.put("QWEN3_5_PLUS_2026_02_15", MODEL_QWEN3_5_PLUS_2026_02_15);
        map.put("QWEN3_5_PLUS_2026_04_20", MODEL_QWEN3_5_PLUS_2026_04_20);
        map.put("QWEN3_6_27B", MODEL_QWEN3_6_27B);
        map.put("QWEN3_6_35B_A3B", MODEL_QWEN3_6_35B_A3B);
        map.put("QWEN3_6_FLASH", MODEL_QWEN3_6_FLASH);
        map.put("QWEN3_6_FLASH_2026_04_16", MODEL_QWEN3_6_FLASH_2026_04_16);
        map.put("QWEN3_6_PLUS", MODEL_QWEN3_6_PLUS);
        map.put("QWEN3_6_PLUS_2026_04_02", MODEL_QWEN3_6_PLUS_2026_04_02);
        map.put("QWEN3_7_FLASH", MODEL_QWEN3_7_FLASH);
        map.put("QWEN3_7_FLASH_2026_07_15", MODEL_QWEN3_7_FLASH_2026_07_15);
        map.put("QWEN3_7_MAX", MODEL_QWEN3_7_MAX);
        map.put("QWEN3_7_MAX_2026_05_17", MODEL_QWEN3_7_MAX_2026_05_17);
        map.put("QWEN3_7_MAX_2026_05_20", MODEL_QWEN3_7_MAX_2026_05_20);
        map.put("QWEN3_7_MAX_2026_06_08", MODEL_QWEN3_7_MAX_2026_06_08);
        map.put("QWEN3_7_MAX_PREVIEW", MODEL_QWEN3_7_MAX_PREVIEW);
        map.put("QWEN3_7_PLUS", MODEL_QWEN3_7_PLUS);
        map.put("QWEN3_7_PLUS_2026_05_26", MODEL_QWEN3_7_PLUS_2026_05_26);
        map.put("QWEN3_8_27B", MODEL_QWEN3_8_27B);
        map.put("QWEN3_8_2_4T_A95B", MODEL_QWEN3_8_2_4T_A95B);
        map.put("QWEN3_8_FLASH", MODEL_QWEN3_8_FLASH);
        map.put("QWEN3_8_LIVETRANSLATE_FLASH_REALTIME", MODEL_QWEN3_8_LIVETRANSLATE_FLASH_REALTIME);
        map.put("QWEN3_8_MAX", MODEL_QWEN3_8_MAX);
        map.put("QWEN3_8_MAX_0902", MODEL_QWEN3_8_MAX_0902);
        map.put("QWEN3_8_OMNI_FLASH", MODEL_QWEN3_8_OMNI_FLASH);
        map.put("QWEN3_CODER_30B_A3B", MODEL_QWEN3_CODER_30B_A3B);
        map.put("QWEN3_CODER_480B_A35B", MODEL_QWEN3_CODER_480B_A35B);
        map.put("QWEN3_CODER_480B_A35B_INSTRUCT_MAAS", MODEL_QWEN3_CODER_480B_A35B_INSTRUCT_MAAS);
        map.put("QWEN3_CODER_FLASH", MODEL_QWEN3_CODER_FLASH);
        map.put("QWEN3_LIVETRANSLATE_FLASH", MODEL_QWEN3_LIVETRANSLATE_FLASH);
        map.put("QWEN3_LIVETRANSLATE_FLASH_2025_12_01", MODEL_QWEN3_LIVETRANSLATE_FLASH_2025_12_01);
        map.put("QWEN3_NEXT_80B_A3B", MODEL_QWEN3_NEXT_80B_A3B);
        map.put("QWEN3_NEXT_80B_A3B_INSTRUCT_MAAS", MODEL_QWEN3_NEXT_80B_A3B_INSTRUCT_MAAS);
        map.put("QWEN3_NEXT_80B_A3B_THINKING_MAAS", MODEL_QWEN3_NEXT_80B_A3B_THINKING_MAAS);
        map.put("QWEN3_OMNI_FLASH", MODEL_QWEN3_OMNI_FLASH);
        map.put("QWEN3_OMNI_FLASH_REALTIME_2025_09_15", MODEL_QWEN3_OMNI_FLASH_REALTIME_2025_09_15);
        map.put("QWEN3_S2S_FLASH_REALTIME", MODEL_QWEN3_S2S_FLASH_REALTIME);
        map.put("QWEN3_VL_235B_A22B", MODEL_QWEN3_VL_235B_A22B);
        map.put("QWEN3_VL_PLUS", MODEL_QWEN3_VL_PLUS);
        map.put("QWEN_FLASH", MODEL_QWEN_FLASH);
        map.put("QWEN_FLASH_CHARACTER", MODEL_QWEN_FLASH_CHARACTER);
        map.put("QWEN_MAX", MODEL_QWEN_MAX);
        map.put("QWEN_MT_FLASH", MODEL_QWEN_MT_FLASH);
        map.put("QWEN_MT_LITE", MODEL_QWEN_MT_LITE);
        map.put("QWEN_MT_PLUS", MODEL_QWEN_MT_PLUS);
        map.put("QWEN_PLUS", MODEL_QWEN_PLUS);
        map.put("QWEN_PLUS_2025_01_25", MODEL_QWEN_PLUS_2025_01_25);
        map.put("QWEN_PLUS_2025_04_28", MODEL_QWEN_PLUS_2025_04_28);
        map.put("QWEN_PLUS_2025_07_14", MODEL_QWEN_PLUS_2025_07_14);
        map.put("QWEN_PLUS_2025_12_01", MODEL_QWEN_PLUS_2025_12_01);
        map.put("QWEN_PLUS_CHARACTER", MODEL_QWEN_PLUS_CHARACTER);
        map.put("QWEN_PLUS_LATEST", MODEL_QWEN_PLUS_LATEST);
        map.put("QWEN_TURBO", MODEL_QWEN_TURBO);
        map.put("QWEN_VL_OCR_2025_11_20", MODEL_QWEN_VL_OCR_2025_11_20);
        map.put("QWQ_PLUS_2025_03_05", MODEL_QWQ_PLUS_2025_03_05);
        map.put("R1", MODEL_R1);
        map.put("SORA_2", MODEL_SORA_2);
        map.put("SORA_2_PRO", MODEL_SORA_2_PRO);
        map.put("TEXT_EMBEDDING_3_LARGE", MODEL_TEXT_EMBEDDING_3_LARGE);
        map.put("TEXT_EMBEDDING_3_SMALL", MODEL_TEXT_EMBEDDING_3_SMALL);
        map.put("TEXT_EMBEDDING_ADA_002", MODEL_TEXT_EMBEDDING_ADA_002);
        map.put("TTS_1", MODEL_TTS_1);
        map.put("TTS_1_1106", MODEL_TTS_1_1106);
        map.put("TTS_1_HD", MODEL_TTS_1_HD);
        map.put("TTS_1_HD_1106", MODEL_TTS_1_HD_1106);
        map.put("TYPESAFE_JEV", MODEL_TYPESAFE_JEV);
        map.put("TYPESAFE_JEV_SYSTEM_ONE", MODEL_TYPESAFE_JEV_SYSTEM_ONE);
        map.put("V3", MODEL_V3);
        map.put("V3_2", MODEL_V3_2);
        map.put("VOXTRAL_MINI_3B_2507", MODEL_VOXTRAL_MINI_3B_2507);
        map.put("VOXTRAL_SMALL_24B_2507", MODEL_VOXTRAL_SMALL_24B_2507);
        map.put("WHISPER_1", MODEL_WHISPER_1);
        map.put("ZHIPU_GLM_5_3", MODEL_ZHIPU_GLM_5_3);
        return Collections.unmodifiableMap(map);
    }
}
