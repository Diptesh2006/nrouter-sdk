// Code generated from spec/model-catalog-snapshot.json (snapshot version: 2026-11-14, schema_version: 1, catalog_revision: 1); DO NOT EDIT.
// Run `node scripts/generate-model-constants.mjs` to regenerate.

package nrouter

const (
	MODEL_AMAZON_NOVA_LITE_V1  = "amazon-nova-lite-v1"
	MODEL_AMAZON_NOVA_MICRO_V1 = "amazon-nova-micro-v1"
	MODEL_AMAZON_NOVA_PRO_V1   = "amazon-nova-pro-v1"
	MODEL_CHATGPT_IMAGE_LATEST = "chatgpt-image-latest"
	MODEL_CHAT_LATEST          = "chat-latest"
	// MODEL_CLAUDE_3_7_SONNET is retained for compatibility.
	//
	// Deprecated: Model 'claude-3-7-sonnet' is retired.
	MODEL_CLAUDE_3_7_SONNET         = "claude-3-7-sonnet"
	MODEL_CLAUDE_FABLE_5            = "claude-fable-5"
	MODEL_CLAUDE_FABLE_5_1          = "claude-fable-5-1"
	MODEL_CLAUDE_HAIKU_4_5_20251001 = "claude-haiku-4-5-20251001"
	MODEL_CLAUDE_OPUS_4_5_20251101  = "claude-opus-4-5-20251101"
	MODEL_CLAUDE_OPUS_4_6           = "claude-opus-4-6"
	MODEL_CLAUDE_OPUS_4_7           = "claude-opus-4-7"
	MODEL_CLAUDE_OPUS_4_8           = "claude-opus-4-8"
	MODEL_CLAUDE_OPUS_5             = "claude-opus-5"
	MODEL_CLAUDE_OPUS_5_5           = "claude-opus-5-5"
	// MODEL_CLAUDE_SONNET_4_5 is retained for compatibility.
	//
	// Deprecated: Model 'claude-sonnet-4-5-20250929' is retired; compatibility alias for MODEL_CLAUDE_SONNET_4_5_20250929.
	MODEL_CLAUDE_SONNET_4_5 = "claude-sonnet-4-5-20250929"
	// MODEL_CLAUDE_SONNET_4_5_20250929 is retained for compatibility.
	//
	// Deprecated: Model 'claude-sonnet-4-5-20250929' is retired.
	MODEL_CLAUDE_SONNET_4_5_20250929 = "claude-sonnet-4-5-20250929"
	MODEL_CLAUDE_SONNET_4_6          = "claude-sonnet-4-6"
	MODEL_CLAUDE_SONNET_5            = "claude-sonnet-5"
	MODEL_CLAUDE_SONNET_5_5          = "claude-sonnet-5-5"
	MODEL_DEEPSEEK_R1_0528_MAAS      = "deepseek-r1-0528-maas"
	MODEL_DEEPSEEK_V3_2_MAAS         = "deepseek-v3.2-maas"
	MODEL_DEEPSEEK_V4_1_FLASH        = "deepseek-v4.1-flash"
	MODEL_DEEPSEEK_V4_FLASH_0731     = "deepseek-v4-flash-0731"
	MODEL_DEEPSEEK_V4_PRO            = "deepseek-v4-pro"
	MODEL_DEEPSEEK_V4_PRO_0813       = "deepseek-v4-pro-0813"
	MODEL_DEVSTRAL_2_123B            = "devstral-2-123b"
	// MODEL_GEMINI_1_5_FLASH_002 is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-1.5-flash-002' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_1_5_FLASH_002.
	MODEL_GEMINI_1_5_FLASH_002 = "google/gemini-1.5-flash-002"
	// MODEL_GEMINI_1_5_PRO_002 is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-1.5-pro-002' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_1_5_PRO_002.
	MODEL_GEMINI_1_5_PRO_002 = "google/gemini-1.5-pro-002"
	// MODEL_GEMINI_2_0_FLASH is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-2.0-flash' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_0_FLASH.
	MODEL_GEMINI_2_0_FLASH = "google/gemini-2.0-flash"
	// MODEL_GEMINI_2_0_FLASH_LITE is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-2.0-flash-lite' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE.
	MODEL_GEMINI_2_0_FLASH_LITE = "google/gemini-2.0-flash-lite"
	// MODEL_GEMINI_2_5_FLASH is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-2.5-flash' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_5_FLASH.
	MODEL_GEMINI_2_5_FLASH = "google/gemini-2.5-flash"
	// MODEL_GEMINI_2_5_PRO is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-2.5-pro' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_2_5_PRO.
	MODEL_GEMINI_2_5_PRO = "google/gemini-2.5-pro"
	// MODEL_GEMINI_3_1_FLASH_LITE is retained for compatibility.
	//
	// Deprecated: Compatibility alias; use MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE instead.
	MODEL_GEMINI_3_1_FLASH_LITE = "google/gemini-3.1-flash-lite"
	// MODEL_GEMINI_3_1_PRO is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-3.1-pro' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_3_1_PRO.
	MODEL_GEMINI_3_1_PRO                    = "google/gemini-3.1-pro"
	MODEL_GEMINI_3_1_PRO_PREVIEW            = "gemini-3.1-pro-preview"
	MODEL_GEMINI_3_5_FLASH                  = "gemini-3.5-flash"
	MODEL_GEMINI_3_5_FLASH_LITE             = "gemini-3.5-flash-lite"
	MODEL_GEMINI_3_5_LIVE_TRANSLATE_PREVIEW = "gemini-3.5-live-translate-preview"
	MODEL_GEMINI_3_6_FLASH                  = "gemini-3.6-flash"
	MODEL_GEMINI_3_7_FLASH                  = "gemini-3.7-flash"
	// MODEL_GEMINI_3_8_FLASH is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-3.8-flash' is retired; compatibility alias for MODEL_GOOGLE_GEMINI_3_8_FLASH.
	MODEL_GEMINI_3_8_FLASH               = "google/gemini-3.8-flash"
	MODEL_GEMINI_3_FLASH_PREVIEW         = "gemini-3-flash-preview"
	MODEL_GEMMA_3_12B_IT                 = "gemma-3-12b-it"
	MODEL_GEMMA_3_27B_IT                 = "gemma-3-27b-it"
	MODEL_GEMMA_3_4B_IT                  = "gemma-3-4b-it"
	MODEL_GLM_4_7                        = "glm-4.7"
	MODEL_GLM_4_7_FLASH                  = "glm-4.7-flash"
	MODEL_GLM_4_7_MAAS                   = "glm-4.7-maas"
	MODEL_GLM_5                          = "glm-5"
	MODEL_GLM_5_1                        = "glm-5.1"
	MODEL_GLM_5_2                        = "glm-5.2"
	MODEL_GLM_5_2_FAST_PREVIEW           = "glm-5.2-fast-preview"
	MODEL_GLM_5_2_MAAS                   = "glm-5.2-maas"
	MODEL_GLM_5_3                        = "glm-5.3"
	MODEL_GLM_5_3_PRIME                  = "glm-5.3-prime"
	MODEL_GLM_5_MAAS                     = "glm-5-maas"
	MODEL_GLOBAL_AMAZON_NOVA_2_LITE_V1_0 = "global.amazon.nova-2-lite-v1:0"
	// MODEL_GOOGLE_GEMINI_1_5_FLASH_002 is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-1.5-flash-002' is retired.
	MODEL_GOOGLE_GEMINI_1_5_FLASH_002 = "google/gemini-1.5-flash-002"
	// MODEL_GOOGLE_GEMINI_1_5_PRO_002 is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-1.5-pro-002' is retired.
	MODEL_GOOGLE_GEMINI_1_5_PRO_002 = "google/gemini-1.5-pro-002"
	// MODEL_GOOGLE_GEMINI_2_0_FLASH is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-2.0-flash' is retired.
	MODEL_GOOGLE_GEMINI_2_0_FLASH = "google/gemini-2.0-flash"
	// MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-2.0-flash-lite' is retired.
	MODEL_GOOGLE_GEMINI_2_0_FLASH_LITE = "google/gemini-2.0-flash-lite"
	// MODEL_GOOGLE_GEMINI_2_5_FLASH is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-2.5-flash' is retired.
	MODEL_GOOGLE_GEMINI_2_5_FLASH = "google/gemini-2.5-flash"
	// MODEL_GOOGLE_GEMINI_2_5_PRO is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-2.5-pro' is retired.
	MODEL_GOOGLE_GEMINI_2_5_PRO        = "google/gemini-2.5-pro"
	MODEL_GOOGLE_GEMINI_3_1_FLASH_LITE = "google/gemini-3.1-flash-lite"
	// MODEL_GOOGLE_GEMINI_3_1_PRO is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-3.1-pro' is retired.
	MODEL_GOOGLE_GEMINI_3_1_PRO = "google/gemini-3.1-pro"
	// MODEL_GOOGLE_GEMINI_3_8_FLASH is retained for compatibility.
	//
	// Deprecated: Model 'google/gemini-3.8-flash' is retired.
	MODEL_GOOGLE_GEMINI_3_8_FLASH                = "google/gemini-3.8-flash"
	MODEL_GPT_3_5_TURBO                          = "gpt-3.5-turbo"
	MODEL_GPT_3_5_TURBO_0125                     = "gpt-3.5-turbo-0125"
	MODEL_GPT_3_5_TURBO_1106                     = "gpt-3.5-turbo-1106"
	MODEL_GPT_3_5_TURBO_16K                      = "gpt-3.5-turbo-16k"
	MODEL_GPT_3_5_TURBO_INSTRUCT                 = "gpt-3.5-turbo-instruct"
	MODEL_GPT_4                                  = "gpt-4"
	MODEL_GPT_4O                                 = "gpt-4o"
	MODEL_GPT_4O_2024_05_13                      = "gpt-4o-2024-05-13"
	MODEL_GPT_4O_2024_08_06                      = "gpt-4o-2024-08-06"
	MODEL_GPT_4O_2024_11_20                      = "gpt-4o-2024-11-20"
	MODEL_GPT_4O_MINI                            = "gpt-4o-mini"
	MODEL_GPT_4O_MINI_2024_07_18                 = "gpt-4o-mini-2024-07-18"
	MODEL_GPT_4O_MINI_SEARCH_PREVIEW             = "gpt-4o-mini-search-preview"
	MODEL_GPT_4O_MINI_SEARCH_PREVIEW_2025_03_11  = "gpt-4o-mini-search-preview-2025-03-11"
	MODEL_GPT_4O_MINI_TRANSCRIBE                 = "gpt-4o-mini-transcribe"
	MODEL_GPT_4O_MINI_TRANSCRIBE_2025_03_20      = "gpt-4o-mini-transcribe-2025-03-20"
	MODEL_GPT_4O_MINI_TRANSCRIBE_2025_12_15      = "gpt-4o-mini-transcribe-2025-12-15"
	MODEL_GPT_4O_MINI_TTS                        = "gpt-4o-mini-tts"
	MODEL_GPT_4O_MINI_TTS_2025_03_20             = "gpt-4o-mini-tts-2025-03-20"
	MODEL_GPT_4O_MINI_TTS_2025_12_15             = "gpt-4o-mini-tts-2025-12-15"
	MODEL_GPT_4O_SEARCH_PREVIEW                  = "gpt-4o-search-preview"
	MODEL_GPT_4O_SEARCH_PREVIEW_2025_03_11       = "gpt-4o-search-preview-2025-03-11"
	MODEL_GPT_4O_TRANSCRIBE                      = "gpt-4o-transcribe"
	MODEL_GPT_4O_TRANSCRIBE_DIARIZE              = "gpt-4o-transcribe-diarize"
	MODEL_GPT_4_0613                             = "gpt-4-0613"
	MODEL_GPT_4_1                                = "gpt-4.1"
	MODEL_GPT_4_1_2025_04_14                     = "gpt-4.1-2025-04-14"
	MODEL_GPT_4_1_MINI                           = "gpt-4.1-mini"
	MODEL_GPT_4_1_MINI_2025_04_14                = "gpt-4.1-mini-2025-04-14"
	MODEL_GPT_4_1_NANO                           = "gpt-4.1-nano"
	MODEL_GPT_4_1_NANO_2025_04_14                = "gpt-4.1-nano-2025-04-14"
	MODEL_GPT_4_TURBO                            = "gpt-4-turbo"
	MODEL_GPT_4_TURBO_2024_04_09                 = "gpt-4-turbo-2024-04-09"
	MODEL_GPT_5                                  = "gpt-5"
	MODEL_GPT_5_1                                = "gpt-5.1"
	MODEL_GPT_5_1_2025_11_13                     = "gpt-5.1-2025-11-13"
	MODEL_GPT_5_1_CHAT_LATEST                    = "gpt-5.1-chat-latest"
	MODEL_GPT_5_2                                = "gpt-5.2"
	MODEL_GPT_5_2025_08_07                       = "gpt-5-2025-08-07"
	MODEL_GPT_5_2_2025_12_11                     = "gpt-5.2-2025-12-11"
	MODEL_GPT_5_2_CHAT_LATEST                    = "gpt-5.2-chat-latest"
	MODEL_GPT_5_2_PRO                            = "gpt-5.2-pro"
	MODEL_GPT_5_2_PRO_2025_12_11                 = "gpt-5.2-pro-2025-12-11"
	MODEL_GPT_5_3_CHAT_LATEST                    = "gpt-5.3-chat-latest"
	MODEL_GPT_5_3_CODEX                          = "gpt-5.3-codex"
	MODEL_GPT_5_4                                = "gpt-5.4"
	MODEL_GPT_5_4_2026_03_05                     = "gpt-5.4-2026-03-05"
	MODEL_GPT_5_4_MINI                           = "gpt-5.4-mini"
	MODEL_GPT_5_4_MINI_2026_03_17                = "gpt-5.4-mini-2026-03-17"
	MODEL_GPT_5_4_NANO                           = "gpt-5.4-nano"
	MODEL_GPT_5_4_NANO_2026_03_17                = "gpt-5.4-nano-2026-03-17"
	MODEL_GPT_5_4_PRO                            = "gpt-5.4-pro"
	MODEL_GPT_5_4_PRO_2026_03_05                 = "gpt-5.4-pro-2026-03-05"
	MODEL_GPT_5_5                                = "gpt-5.5"
	MODEL_GPT_5_5_2026_04_23                     = "gpt-5.5-2026-04-23"
	MODEL_GPT_5_5_PRO                            = "gpt-5.5-pro"
	MODEL_GPT_5_5_PRO_2026_04_23                 = "gpt-5.5-pro-2026-04-23"
	MODEL_GPT_5_6_LUNA                           = "gpt-5.6-luna"
	MODEL_GPT_5_6_SOL                            = "gpt-5.6-sol"
	MODEL_GPT_5_6_TERRA                          = "gpt-5.6-terra"
	MODEL_GPT_5_MINI                             = "gpt-5-mini"
	MODEL_GPT_5_MINI_2025_08_07                  = "gpt-5-mini-2025-08-07"
	MODEL_GPT_5_NANO                             = "gpt-5-nano"
	MODEL_GPT_5_NANO_2025_08_07                  = "gpt-5-nano-2025-08-07"
	MODEL_GPT_5_PRO                              = "gpt-5-pro"
	MODEL_GPT_5_PRO_2025_10_06                   = "gpt-5-pro-2025-10-06"
	MODEL_GPT_5_SEARCH_API                       = "gpt-5-search-api"
	MODEL_GPT_5_SEARCH_API_2025_10_14            = "gpt-5-search-api-2025-10-14"
	MODEL_GPT_6_1_SOL                            = "gpt-6.1-sol"
	MODEL_GPT_6_ASTRA                            = "gpt-6-astra"
	MODEL_GPT_6_LUNA                             = "gpt-6-luna"
	MODEL_GPT_6_SOL                              = "gpt-6-sol"
	MODEL_GPT_AUDIO                              = "gpt-audio"
	MODEL_GPT_AUDIO_1_5                          = "gpt-audio-1.5"
	MODEL_GPT_AUDIO_2025_08_28                   = "gpt-audio-2025-08-28"
	MODEL_GPT_AUDIO_MINI                         = "gpt-audio-mini"
	MODEL_GPT_AUDIO_MINI_2025_12_15              = "gpt-audio-mini-2025-12-15"
	MODEL_GPT_IMAGE_1                            = "gpt-image-1"
	MODEL_GPT_IMAGE_1_5                          = "gpt-image-1.5"
	MODEL_GPT_IMAGE_1_MINI                       = "gpt-image-1-mini"
	MODEL_GPT_IMAGE_2                            = "gpt-image-2"
	MODEL_GPT_IMAGE_2_2026_04_21                 = "gpt-image-2-2026-04-21"
	MODEL_GPT_IMAGE_2_5_FLARE                    = "gpt-image-2.5-flare"
	MODEL_GPT_IMAGE_2_5_FLARE_2026_09_08         = "gpt-image-2.5-flare-2026-09-08"
	MODEL_GPT_IMAGE_2_5_SUNBURST                 = "gpt-image-2.5-sunburst"
	MODEL_GPT_IMAGE_2_5_SUNBURST_2026_09_08      = "gpt-image-2.5-sunburst-2026-09-08"
	MODEL_GPT_LIVE_TRANSCRIBE                    = "gpt-live-transcribe"
	MODEL_GPT_OSS_120B_1                         = "gpt-oss-120b-1"
	MODEL_GPT_OSS_120B_MAAS                      = "gpt-oss-120b-maas"
	MODEL_GPT_OSS_20B_1                          = "gpt-oss-20b-1"
	MODEL_GPT_OSS_SAFEGUARD_120B                 = "gpt-oss-safeguard-120b"
	MODEL_GPT_OSS_SAFEGUARD_20B                  = "gpt-oss-safeguard-20b"
	MODEL_GPT_TRANSCRIBE                         = "gpt-transcribe"
	MODEL_GROK_4_1_FAST_NON_REASONING            = "grok-4-1-fast-non-reasoning"
	MODEL_GROK_4_1_FAST_REASONING                = "grok-4-1-fast-reasoning"
	MODEL_KIMI_K2_5                              = "kimi-k2.5"
	MODEL_KIMI_K2_7_CODE                         = "kimi-k2.7-code"
	MODEL_KIMI_K2_THINKING                       = "kimi-k2-thinking"
	MODEL_KIMI_K2_THINKING_MAAS                  = "kimi-k2-thinking-maas"
	MODEL_KIMI_K3                                = "kimi-k3"
	MODEL_KIMI_KIMI_K3                           = "kimi/kimi-k3"
	MODEL_LLAMA3_1_70B_INSTRUCT                  = "llama3-1-70b-instruct"
	MODEL_LLAMA3_1_8B_INSTRUCT                   = "llama3-1-8b-instruct"
	MODEL_LLAMA3_3_70B_INSTRUCT                  = "llama3-3-70b-instruct"
	MODEL_LLAMA4_MAVERICK_17B_INSTRUCT           = "llama4-maverick-17b-instruct"
	MODEL_LLAMA4_SCOUT_17B_INSTRUCT              = "llama4-scout-17b-instruct"
	MODEL_LLAMA_3_3_70B_INSTRUCT                 = "Llama-3.3-70B-Instruct"
	MODEL_LLAMA_4_MAVERICK_17B_128E_INSTRUCT_FP8 = "Llama-4-Maverick-17B-128E-Instruct-FP8"
	MODEL_LLAMA_4_SCOUT_17B_16E_INSTRUCT         = "Llama-4-Scout-17B-16E-Instruct"
	MODEL_MAGISTRAL_SMALL_2509                   = "magistral-small-2509"
	// MODEL_META_LLAMA_3_1_70B_INSTRUCT is retained for compatibility.
	//
	// Deprecated: Model 'meta/llama-3.1-70b-instruct' is retired.
	MODEL_META_LLAMA_3_1_70B_INSTRUCT = "meta/llama-3.1-70b-instruct"
	// MODEL_META_LLAMA_3_1_8B_INSTRUCT is retained for compatibility.
	//
	// Deprecated: Model 'meta/llama-3.1-8b-instruct' is retired.
	MODEL_META_LLAMA_3_1_8B_INSTRUCT = "meta/llama-3.1-8b-instruct"
	// MODEL_META_LLAMA_3_2_11B_VISION is retained for compatibility.
	//
	// Deprecated: Model 'meta/llama-3.2-11b-vision-instruct' is retired; compatibility alias for MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT.
	MODEL_META_LLAMA_3_2_11B_VISION = "meta/llama-3.2-11b-vision-instruct"
	// MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT is retained for compatibility.
	//
	// Deprecated: Model 'meta/llama-3.2-11b-vision-instruct' is retired.
	MODEL_META_LLAMA_3_2_11B_VISION_INSTRUCT = "meta/llama-3.2-11b-vision-instruct"
	// MODEL_META_LLAMA_3_2_1B_INSTRUCT is retained for compatibility.
	//
	// Deprecated: Model 'meta/llama-3.2-1b-instruct' is retired.
	MODEL_META_LLAMA_3_2_1B_INSTRUCT = "meta/llama-3.2-1b-instruct"
	// MODEL_META_LLAMA_3_2_3B_INSTRUCT is retained for compatibility.
	//
	// Deprecated: Model 'meta/llama-3.2-3b-instruct' is retired.
	MODEL_META_LLAMA_3_2_3B_INSTRUCT = "meta/llama-3.2-3b-instruct"
	// MODEL_META_LLAMA_3_2_90B_VISION is retained for compatibility.
	//
	// Deprecated: Model 'meta/llama-3.2-90b-vision-instruct' is retired; compatibility alias for MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT.
	MODEL_META_LLAMA_3_2_90B_VISION = "meta/llama-3.2-90b-vision-instruct"
	// MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT is retained for compatibility.
	//
	// Deprecated: Model 'meta/llama-3.2-90b-vision-instruct' is retired.
	MODEL_META_LLAMA_3_2_90B_VISION_INSTRUCT = "meta/llama-3.2-90b-vision-instruct"
	// MODEL_META_LLAMA_3_3_70B_INSTRUCT is retained for compatibility.
	//
	// Deprecated: Model 'meta/llama-3.3-70b-instruct' is retired.
	MODEL_META_LLAMA_3_3_70B_INSTRUCT                     = "meta/llama-3.3-70b-instruct"
	MODEL_MINIMAX_M2                                      = "minimax-m2"
	MODEL_MINIMAX_M2_1                                    = "minimax-m2.1"
	MODEL_MINIMAX_M2_5                                    = "minimax-m2.5"
	MODEL_MINIMAX_M2_MAAS                                 = "minimax-m2-maas"
	MODEL_MINISTRAL_3_14B_INSTRUCT                        = "ministral-3-14b-instruct"
	MODEL_MINISTRAL_3_3B_INSTRUCT                         = "ministral-3-3b-instruct"
	MODEL_MINISTRAL_3_8B_INSTRUCT                         = "ministral-3-8b-instruct"
	MODEL_MISTRAL_LARGE_3_675B_INSTRUCT                   = "mistral-large-3-675b-instruct"
	MODEL_MISTRAL_MEDIUM_2505                             = "mistral-medium-2505"
	MODEL_MISTRAL_SMALL_2503                              = "mistral-small-2503"
	MODEL_NEMOTRON_NANO_12B_V2                            = "nemotron-nano-12b-v2"
	MODEL_NEMOTRON_NANO_3_30B                             = "nemotron-nano-3-30b"
	MODEL_NEMOTRON_NANO_9B_V2                             = "nemotron-nano-9b-v2"
	MODEL_NEMOTRON_SUPER_3_120B                           = "nemotron-super-3-120b"
	MODEL_NOVA_2_LITE                                     = "nova-2-lite"
	MODEL_NOVA_LITE                                       = "nova-lite"
	MODEL_O1                                              = "o1"
	MODEL_O1_2024_12_17                                   = "o1-2024-12-17"
	MODEL_O1_PRO                                          = "o1-pro"
	MODEL_O1_PRO_2025_03_19                               = "o1-pro-2025-03-19"
	MODEL_O3                                              = "o3"
	MODEL_O3_2025_04_16                                   = "o3-2025-04-16"
	MODEL_O3_MINI                                         = "o3-mini"
	MODEL_O3_MINI_2025_01_31                              = "o3-mini-2025-01-31"
	MODEL_O4_MINI                                         = "o4-mini"
	MODEL_O4_MINI_2025_04_16                              = "o4-mini-2025-04-16"
	MODEL_PALMYRA_VISION_7B                               = "palmyra-vision-7b"
	MODEL_PHI_4                                           = "Phi-4"
	MODEL_PHI_4_MINI_INSTRUCT                             = "Phi-4-mini-instruct"
	MODEL_PHI_4_MINI_REASONING                            = "Phi-4-mini-reasoning"
	MODEL_PHI_4_MULTIMODAL_INSTRUCT                       = "Phi-4-multimodal-instruct"
	MODEL_PHI_4_REASONING                                 = "Phi-4-reasoning"
	MODEL_PIXTRAL_LARGE_2502                              = "pixtral-large-2502"
	MODEL_QWEN2_7B_INSTRUCT                               = "qwen2-7b-instruct"
	MODEL_QWEN3_235B_A22B_2507                            = "qwen3-235b-a22b-2507"
	MODEL_QWEN3_235B_A22B_INSTRUCT_2507_MAAS              = "qwen3-235b-a22b-instruct-2507-maas"
	MODEL_QWEN3_32B                                       = "qwen3-32b"
	MODEL_QWEN3_5_122B_A10B                               = "qwen3.5-122b-a10b"
	MODEL_QWEN3_5_27B                                     = "qwen3.5-27b"
	MODEL_QWEN3_5_35B_A3B                                 = "qwen3.5-35b-a3b"
	MODEL_QWEN3_5_397B_A17B                               = "qwen3.5-397b-a17b"
	MODEL_QWEN3_5_FLASH                                   = "qwen3.5-flash"
	MODEL_QWEN3_5_FLASH_2026_02_23                        = "qwen3.5-flash-2026-02-23"
	MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME            = "qwen3.5-livetranslate-flash-realtime"
	MODEL_QWEN3_5_LIVETRANSLATE_FLASH_REALTIME_2026_05_19 = "qwen3.5-livetranslate-flash-realtime-2026-05-19"
	MODEL_QWEN3_5_OMNI_FLASH                              = "qwen3.5-omni-flash"
	MODEL_QWEN3_5_OMNI_FLASH_2026_03_15                   = "qwen3.5-omni-flash-2026-03-15"
	MODEL_QWEN3_5_OMNI_FLASH_REALTIME                     = "qwen3.5-omni-flash-realtime"
	MODEL_QWEN3_5_OMNI_FLASH_REALTIME_2026_03_15          = "qwen3.5-omni-flash-realtime-2026-03-15"
	MODEL_QWEN3_5_OMNI_PLUS                               = "qwen3.5-omni-plus"
	MODEL_QWEN3_5_OMNI_PLUS_2026_03_15                    = "qwen3.5-omni-plus-2026-03-15"
	MODEL_QWEN3_5_OMNI_PLUS_REALTIME                      = "qwen3.5-omni-plus-realtime"
	MODEL_QWEN3_5_OMNI_PLUS_REALTIME_2026_03_15           = "qwen3.5-omni-plus-realtime-2026-03-15"
	MODEL_QWEN3_5_PLUS                                    = "qwen3.5-plus"
	MODEL_QWEN3_5_PLUS_2026_02_15                         = "qwen3.5-plus-2026-02-15"
	MODEL_QWEN3_5_PLUS_2026_04_20                         = "qwen3.5-plus-2026-04-20"
	MODEL_QWEN3_6_27B                                     = "qwen3.6-27b"
	MODEL_QWEN3_6_35B_A3B                                 = "qwen3.6-35b-a3b"
	MODEL_QWEN3_6_FLASH                                   = "qwen3.6-flash"
	MODEL_QWEN3_6_FLASH_2026_04_16                        = "qwen3.6-flash-2026-04-16"
	MODEL_QWEN3_6_PLUS                                    = "qwen3.6-plus"
	MODEL_QWEN3_6_PLUS_2026_04_02                         = "qwen3.6-plus-2026-04-02"
	MODEL_QWEN3_7_FLASH                                   = "qwen3.7-flash"
	MODEL_QWEN3_7_FLASH_2026_07_15                        = "qwen3.7-flash-2026-07-15"
	MODEL_QWEN3_7_MAX                                     = "qwen3.7-max"
	MODEL_QWEN3_7_MAX_2026_05_17                          = "qwen3.7-max-2026-05-17"
	MODEL_QWEN3_7_MAX_2026_05_20                          = "qwen3.7-max-2026-05-20"
	MODEL_QWEN3_7_MAX_2026_06_08                          = "qwen3.7-max-2026-06-08"
	MODEL_QWEN3_7_MAX_PREVIEW                             = "qwen3.7-max-preview"
	MODEL_QWEN3_7_PLUS                                    = "qwen3.7-plus"
	MODEL_QWEN3_7_PLUS_2026_05_26                         = "qwen3.7-plus-2026-05-26"
	MODEL_QWEN3_8_27B                                     = "qwen3.8-27b"
	MODEL_QWEN3_8_2_4T_A95B                               = "qwen3.8-2.4t-a95b"
	MODEL_QWEN3_8_FLASH                                   = "qwen3.8-flash"
	MODEL_QWEN3_8_LIVETRANSLATE_FLASH_REALTIME            = "qwen3.8-livetranslate-flash-realtime"
	MODEL_QWEN3_8_MAX                                     = "qwen3.8-max"
	MODEL_QWEN3_8_MAX_0902                                = "qwen3.8-max-0902"
	MODEL_QWEN3_8_OMNI_FLASH                              = "qwen3.8-omni-flash"
	MODEL_QWEN3_CODER_30B_A3B                             = "qwen3-coder-30b-a3b"
	MODEL_QWEN3_CODER_480B_A35B                           = "qwen3-coder-480b-a35b"
	MODEL_QWEN3_CODER_480B_A35B_INSTRUCT_MAAS             = "qwen3-coder-480b-a35b-instruct-maas"
	MODEL_QWEN3_CODER_FLASH                               = "qwen3-coder-flash"
	MODEL_QWEN3_LIVETRANSLATE_FLASH                       = "qwen3-livetranslate-flash"
	MODEL_QWEN3_LIVETRANSLATE_FLASH_2025_12_01            = "qwen3-livetranslate-flash-2025-12-01"
	MODEL_QWEN3_NEXT_80B_A3B                              = "qwen3-next-80b-a3b"
	MODEL_QWEN3_NEXT_80B_A3B_INSTRUCT_MAAS                = "qwen3-next-80b-a3b-instruct-maas"
	MODEL_QWEN3_NEXT_80B_A3B_THINKING_MAAS                = "qwen3-next-80b-a3b-thinking-maas"
	MODEL_QWEN3_OMNI_FLASH                                = "qwen3-omni-flash"
	MODEL_QWEN3_OMNI_FLASH_REALTIME_2025_09_15            = "qwen3-omni-flash-realtime-2025-09-15"
	MODEL_QWEN3_S2S_FLASH_REALTIME                        = "qwen3-s2s-flash-realtime"
	MODEL_QWEN3_VL_235B_A22B                              = "qwen3-vl-235b-a22b"
	MODEL_QWEN3_VL_PLUS                                   = "qwen3-vl-plus"
	MODEL_QWEN_FLASH                                      = "qwen-flash"
	MODEL_QWEN_FLASH_CHARACTER                            = "qwen-flash-character"
	MODEL_QWEN_MAX                                        = "qwen-max"
	MODEL_QWEN_MT_FLASH                                   = "qwen-mt-flash"
	MODEL_QWEN_MT_LITE                                    = "qwen-mt-lite"
	MODEL_QWEN_MT_PLUS                                    = "qwen-mt-plus"
	MODEL_QWEN_PLUS                                       = "qwen-plus"
	MODEL_QWEN_PLUS_2025_01_25                            = "qwen-plus-2025-01-25"
	MODEL_QWEN_PLUS_2025_04_28                            = "qwen-plus-2025-04-28"
	MODEL_QWEN_PLUS_2025_07_14                            = "qwen-plus-2025-07-14"
	MODEL_QWEN_PLUS_2025_12_01                            = "qwen-plus-2025-12-01"
	MODEL_QWEN_PLUS_CHARACTER                             = "qwen-plus-character"
	MODEL_QWEN_PLUS_LATEST                                = "qwen-plus-latest"
	MODEL_QWEN_TURBO                                      = "qwen-turbo"
	MODEL_QWEN_VL_OCR_2025_11_20                          = "qwen-vl-ocr-2025-11-20"
	MODEL_QWQ_PLUS_2025_03_05                             = "qwq-plus-2025-03-05"
	MODEL_R1                                              = "r1"
	MODEL_SORA_2                                          = "sora-2"
	MODEL_SORA_2_PRO                                      = "sora-2-pro"
	MODEL_TEXT_EMBEDDING_3_LARGE                          = "text-embedding-3-large"
	MODEL_TEXT_EMBEDDING_3_SMALL                          = "text-embedding-3-small"
	MODEL_TEXT_EMBEDDING_ADA_002                          = "text-embedding-ada-002"
	MODEL_TTS_1                                           = "tts-1"
	MODEL_TTS_1_1106                                      = "tts-1-1106"
	MODEL_TTS_1_HD                                        = "tts-1-hd"
	MODEL_TTS_1_HD_1106                                   = "tts-1-hd-1106"
	MODEL_TYPESAFE_JEV                                    = "typesafe/jev"
	// MODEL_TYPESAFE_JEV_SYSTEM_ONE is retained for compatibility.
	//
	// Deprecated: Compatibility alias; use MODEL_TYPESAFE_JEV instead.
	MODEL_TYPESAFE_JEV_SYSTEM_ONE = "typesafe/jev"
	MODEL_V3                      = "v3"
	MODEL_V3_2                    = "v3.2"
	MODEL_VOXTRAL_MINI_3B_2507    = "voxtral-mini-3b-2507"
	MODEL_VOXTRAL_SMALL_24B_2507  = "voxtral-small-24b-2507"
	MODEL_WHISPER_1               = "whisper-1"
	MODEL_ZHIPU_GLM_5_3           = "ZHIPU/GLM-5.3"
)

// MODELS maps each short constant key to its wire model identifier.
var MODELS = map[string]string{
	"AMAZON_NOVA_LITE_V1":                    "amazon-nova-lite-v1",
	"AMAZON_NOVA_MICRO_V1":                   "amazon-nova-micro-v1",
	"AMAZON_NOVA_PRO_V1":                     "amazon-nova-pro-v1",
	"CHATGPT_IMAGE_LATEST":                   "chatgpt-image-latest",
	"CHAT_LATEST":                            "chat-latest",
	"CLAUDE_3_7_SONNET":                      "claude-3-7-sonnet",
	"CLAUDE_FABLE_5":                         "claude-fable-5",
	"CLAUDE_FABLE_5_1":                       "claude-fable-5-1",
	"CLAUDE_HAIKU_4_5_20251001":              "claude-haiku-4-5-20251001",
	"CLAUDE_OPUS_4_5_20251101":               "claude-opus-4-5-20251101",
	"CLAUDE_OPUS_4_6":                        "claude-opus-4-6",
	"CLAUDE_OPUS_4_7":                        "claude-opus-4-7",
	"CLAUDE_OPUS_4_8":                        "claude-opus-4-8",
	"CLAUDE_OPUS_5":                          "claude-opus-5",
	"CLAUDE_OPUS_5_5":                        "claude-opus-5-5",
	"CLAUDE_SONNET_4_5":                      "claude-sonnet-4-5-20250929",
	"CLAUDE_SONNET_4_5_20250929":             "claude-sonnet-4-5-20250929",
	"CLAUDE_SONNET_4_6":                      "claude-sonnet-4-6",
	"CLAUDE_SONNET_5":                        "claude-sonnet-5",
	"CLAUDE_SONNET_5_5":                      "claude-sonnet-5-5",
	"DEEPSEEK_R1_0528_MAAS":                  "deepseek-r1-0528-maas",
	"DEEPSEEK_V3_2_MAAS":                     "deepseek-v3.2-maas",
	"DEEPSEEK_V4_1_FLASH":                    "deepseek-v4.1-flash",
	"DEEPSEEK_V4_FLASH_0731":                 "deepseek-v4-flash-0731",
	"DEEPSEEK_V4_PRO":                        "deepseek-v4-pro",
	"DEEPSEEK_V4_PRO_0813":                   "deepseek-v4-pro-0813",
	"DEVSTRAL_2_123B":                        "devstral-2-123b",
	"GEMINI_1_5_FLASH_002":                   "google/gemini-1.5-flash-002",
	"GEMINI_1_5_PRO_002":                     "google/gemini-1.5-pro-002",
	"GEMINI_2_0_FLASH":                       "google/gemini-2.0-flash",
	"GEMINI_2_0_FLASH_LITE":                  "google/gemini-2.0-flash-lite",
	"GEMINI_2_5_FLASH":                       "gemini-2.5-flash",
	"GEMINI_2_5_PRO":                         "gemini-2.5-pro",
	"GEMINI_3_1_FLASH_LITE":                  "google/gemini-3.1-flash-lite",
	"GEMINI_3_1_PRO":                         "google/gemini-3.1-pro",
	"GEMINI_3_1_PRO_PREVIEW":                 "gemini-3.1-pro-preview",
	"GEMINI_3_5_FLASH":                       "gemini-3.5-flash",
	"GEMINI_3_5_FLASH_LITE":                  "gemini-3.5-flash-lite",
	"GEMINI_3_5_LIVE_TRANSLATE_PREVIEW":      "gemini-3.5-live-translate-preview",
	"GEMINI_3_6_FLASH":                       "gemini-3.6-flash",
	"GEMINI_3_7_FLASH":                       "gemini-3.7-flash",
	"GEMINI_3_8_FLASH":                       "google/gemini-3.8-flash",
	"GEMINI_3_FLASH_PREVIEW":                 "gemini-3-flash-preview",
	"GEMMA_3_12B_IT":                         "gemma-3-12b-it",
	"GEMMA_3_27B_IT":                         "gemma-3-27b-it",
	"GEMMA_3_4B_IT":                          "gemma-3-4b-it",
	"GLM_4_7":                                "glm-4.7",
	"GLM_4_7_FLASH":                          "glm-4.7-flash",
	"GLM_4_7_MAAS":                           "glm-4.7-maas",
	"GLM_5":                                  "glm-5",
	"GLM_5_1":                                "glm-5.1",
	"GLM_5_2":                                "glm-5.2",
	"GLM_5_2_FAST_PREVIEW":                   "glm-5.2-fast-preview",
	"GLM_5_2_MAAS":                           "glm-5.2-maas",
	"GLM_5_3":                                "glm-5.3",
	"GLM_5_3_PRIME":                          "glm-5.3-prime",
	"GLM_5_MAAS":                             "glm-5-maas",
	"GLOBAL_AMAZON_NOVA_2_LITE_V1_0":         "global.amazon.nova-2-lite-v1:0",
	"GOOGLE_GEMINI_1_5_FLASH_002":            "google/gemini-1.5-flash-002",
	"GOOGLE_GEMINI_1_5_PRO_002":              "google/gemini-1.5-pro-002",
	"GOOGLE_GEMINI_2_0_FLASH":                "google/gemini-2.0-flash",
	"GOOGLE_GEMINI_2_0_FLASH_LITE":           "google/gemini-2.0-flash-lite",
	"GOOGLE_GEMINI_2_5_FLASH":                "google/gemini-2.5-flash",
	"GOOGLE_GEMINI_2_5_PRO":                  "google/gemini-2.5-pro",
	"GOOGLE_GEMINI_3_1_FLASH_LITE":           "google/gemini-3.1-flash-lite",
	"GOOGLE_GEMINI_3_1_PRO":                  "google/gemini-3.1-pro",
	"GOOGLE_GEMINI_3_8_FLASH":                "google/gemini-3.8-flash",
	"GPT_3_5_TURBO":                          "gpt-3.5-turbo",
	"GPT_3_5_TURBO_0125":                     "gpt-3.5-turbo-0125",
	"GPT_3_5_TURBO_1106":                     "gpt-3.5-turbo-1106",
	"GPT_3_5_TURBO_16K":                      "gpt-3.5-turbo-16k",
	"GPT_3_5_TURBO_INSTRUCT":                 "gpt-3.5-turbo-instruct",
	"GPT_4":                                  "gpt-4",
	"GPT_4O":                                 "gpt-4o",
	"GPT_4O_2024_05_13":                      "gpt-4o-2024-05-13",
	"GPT_4O_2024_08_06":                      "gpt-4o-2024-08-06",
	"GPT_4O_2024_11_20":                      "gpt-4o-2024-11-20",
	"GPT_4O_MINI":                            "gpt-4o-mini",
	"GPT_4O_MINI_2024_07_18":                 "gpt-4o-mini-2024-07-18",
	"GPT_4O_MINI_SEARCH_PREVIEW":             "gpt-4o-mini-search-preview",
	"GPT_4O_MINI_SEARCH_PREVIEW_2025_03_11":  "gpt-4o-mini-search-preview-2025-03-11",
	"GPT_4O_MINI_TRANSCRIBE":                 "gpt-4o-mini-transcribe",
	"GPT_4O_MINI_TRANSCRIBE_2025_03_20":      "gpt-4o-mini-transcribe-2025-03-20",
	"GPT_4O_MINI_TRANSCRIBE_2025_12_15":      "gpt-4o-mini-transcribe-2025-12-15",
	"GPT_4O_MINI_TTS":                        "gpt-4o-mini-tts",
	"GPT_4O_MINI_TTS_2025_03_20":             "gpt-4o-mini-tts-2025-03-20",
	"GPT_4O_MINI_TTS_2025_12_15":             "gpt-4o-mini-tts-2025-12-15",
	"GPT_4O_SEARCH_PREVIEW":                  "gpt-4o-search-preview",
	"GPT_4O_SEARCH_PREVIEW_2025_03_11":       "gpt-4o-search-preview-2025-03-11",
	"GPT_4O_TRANSCRIBE":                      "gpt-4o-transcribe",
	"GPT_4O_TRANSCRIBE_DIARIZE":              "gpt-4o-transcribe-diarize",
	"GPT_4_0613":                             "gpt-4-0613",
	"GPT_4_1":                                "gpt-4.1",
	"GPT_4_1_2025_04_14":                     "gpt-4.1-2025-04-14",
	"GPT_4_1_MINI":                           "gpt-4.1-mini",
	"GPT_4_1_MINI_2025_04_14":                "gpt-4.1-mini-2025-04-14",
	"GPT_4_1_NANO":                           "gpt-4.1-nano",
	"GPT_4_1_NANO_2025_04_14":                "gpt-4.1-nano-2025-04-14",
	"GPT_4_TURBO":                            "gpt-4-turbo",
	"GPT_4_TURBO_2024_04_09":                 "gpt-4-turbo-2024-04-09",
	"GPT_5":                                  "gpt-5",
	"GPT_5_1":                                "gpt-5.1",
	"GPT_5_1_2025_11_13":                     "gpt-5.1-2025-11-13",
	"GPT_5_1_CHAT_LATEST":                    "gpt-5.1-chat-latest",
	"GPT_5_2":                                "gpt-5.2",
	"GPT_5_2025_08_07":                       "gpt-5-2025-08-07",
	"GPT_5_2_2025_12_11":                     "gpt-5.2-2025-12-11",
	"GPT_5_2_CHAT_LATEST":                    "gpt-5.2-chat-latest",
	"GPT_5_2_PRO":                            "gpt-5.2-pro",
	"GPT_5_2_PRO_2025_12_11":                 "gpt-5.2-pro-2025-12-11",
	"GPT_5_3_CHAT_LATEST":                    "gpt-5.3-chat-latest",
	"GPT_5_3_CODEX":                          "gpt-5.3-codex",
	"GPT_5_4":                                "gpt-5.4",
	"GPT_5_4_2026_03_05":                     "gpt-5.4-2026-03-05",
	"GPT_5_4_MINI":                           "gpt-5.4-mini",
	"GPT_5_4_MINI_2026_03_17":                "gpt-5.4-mini-2026-03-17",
	"GPT_5_4_NANO":                           "gpt-5.4-nano",
	"GPT_5_4_NANO_2026_03_17":                "gpt-5.4-nano-2026-03-17",
	"GPT_5_4_PRO":                            "gpt-5.4-pro",
	"GPT_5_4_PRO_2026_03_05":                 "gpt-5.4-pro-2026-03-05",
	"GPT_5_5":                                "gpt-5.5",
	"GPT_5_5_2026_04_23":                     "gpt-5.5-2026-04-23",
	"GPT_5_5_PRO":                            "gpt-5.5-pro",
	"GPT_5_5_PRO_2026_04_23":                 "gpt-5.5-pro-2026-04-23",
	"GPT_5_6_LUNA":                           "gpt-5.6-luna",
	"GPT_5_6_SOL":                            "gpt-5.6-sol",
	"GPT_5_6_TERRA":                          "gpt-5.6-terra",
	"GPT_5_MINI":                             "gpt-5-mini",
	"GPT_5_MINI_2025_08_07":                  "gpt-5-mini-2025-08-07",
	"GPT_5_NANO":                             "gpt-5-nano",
	"GPT_5_NANO_2025_08_07":                  "gpt-5-nano-2025-08-07",
	"GPT_5_PRO":                              "gpt-5-pro",
	"GPT_5_PRO_2025_10_06":                   "gpt-5-pro-2025-10-06",
	"GPT_5_SEARCH_API":                       "gpt-5-search-api",
	"GPT_5_SEARCH_API_2025_10_14":            "gpt-5-search-api-2025-10-14",
	"GPT_6_1_SOL":                            "gpt-6.1-sol",
	"GPT_6_ASTRA":                            "gpt-6-astra",
	"GPT_6_LUNA":                             "gpt-6-luna",
	"GPT_6_SOL":                              "gpt-6-sol",
	"GPT_AUDIO":                              "gpt-audio",
	"GPT_AUDIO_1_5":                          "gpt-audio-1.5",
	"GPT_AUDIO_2025_08_28":                   "gpt-audio-2025-08-28",
	"GPT_AUDIO_MINI":                         "gpt-audio-mini",
	"GPT_AUDIO_MINI_2025_12_15":              "gpt-audio-mini-2025-12-15",
	"GPT_IMAGE_1":                            "gpt-image-1",
	"GPT_IMAGE_1_5":                          "gpt-image-1.5",
	"GPT_IMAGE_1_MINI":                       "gpt-image-1-mini",
	"GPT_IMAGE_2":                            "gpt-image-2",
	"GPT_IMAGE_2_2026_04_21":                 "gpt-image-2-2026-04-21",
	"GPT_IMAGE_2_5_FLARE":                    "gpt-image-2.5-flare",
	"GPT_IMAGE_2_5_FLARE_2026_09_08":         "gpt-image-2.5-flare-2026-09-08",
	"GPT_IMAGE_2_5_SUNBURST":                 "gpt-image-2.5-sunburst",
	"GPT_IMAGE_2_5_SUNBURST_2026_09_08":      "gpt-image-2.5-sunburst-2026-09-08",
	"GPT_LIVE_TRANSCRIBE":                    "gpt-live-transcribe",
	"GPT_OSS_120B_1":                         "gpt-oss-120b-1",
	"GPT_OSS_120B_MAAS":                      "gpt-oss-120b-maas",
	"GPT_OSS_20B_1":                          "gpt-oss-20b-1",
	"GPT_OSS_SAFEGUARD_120B":                 "gpt-oss-safeguard-120b",
	"GPT_OSS_SAFEGUARD_20B":                  "gpt-oss-safeguard-20b",
	"GPT_TRANSCRIBE":                         "gpt-transcribe",
	"GROK_4_1_FAST_NON_REASONING":            "grok-4-1-fast-non-reasoning",
	"GROK_4_1_FAST_REASONING":                "grok-4-1-fast-reasoning",
	"KIMI_K2_5":                              "kimi-k2.5",
	"KIMI_K2_7_CODE":                         "kimi-k2.7-code",
	"KIMI_K2_THINKING":                       "kimi-k2-thinking",
	"KIMI_K2_THINKING_MAAS":                  "kimi-k2-thinking-maas",
	"KIMI_K3":                                "kimi-k3",
	"KIMI_KIMI_K3":                           "kimi/kimi-k3",
	"LLAMA3_1_70B_INSTRUCT":                  "llama3-1-70b-instruct",
	"LLAMA3_1_8B_INSTRUCT":                   "llama3-1-8b-instruct",
	"LLAMA3_3_70B_INSTRUCT":                  "llama3-3-70b-instruct",
	"LLAMA4_MAVERICK_17B_INSTRUCT":           "llama4-maverick-17b-instruct",
	"LLAMA4_SCOUT_17B_INSTRUCT":              "llama4-scout-17b-instruct",
	"LLAMA_3_3_70B_INSTRUCT":                 "Llama-3.3-70B-Instruct",
	"LLAMA_4_MAVERICK_17B_128E_INSTRUCT_FP8": "Llama-4-Maverick-17B-128E-Instruct-FP8",
	"LLAMA_4_SCOUT_17B_16E_INSTRUCT":         "Llama-4-Scout-17B-16E-Instruct",
	"MAGISTRAL_SMALL_2509":                   "magistral-small-2509",
	"META_LLAMA_3_1_70B_INSTRUCT":            "meta/llama-3.1-70b-instruct",
	"META_LLAMA_3_1_8B_INSTRUCT":             "meta/llama-3.1-8b-instruct",
	"META_LLAMA_3_2_11B_VISION":              "meta/llama-3.2-11b-vision-instruct",
	"META_LLAMA_3_2_11B_VISION_INSTRUCT":     "meta/llama-3.2-11b-vision-instruct",
	"META_LLAMA_3_2_1B_INSTRUCT":             "meta/llama-3.2-1b-instruct",
	"META_LLAMA_3_2_3B_INSTRUCT":             "meta/llama-3.2-3b-instruct",
	"META_LLAMA_3_2_90B_VISION":              "meta/llama-3.2-90b-vision-instruct",
	"META_LLAMA_3_2_90B_VISION_INSTRUCT":     "meta/llama-3.2-90b-vision-instruct",
	"META_LLAMA_3_3_70B_INSTRUCT":            "meta/llama-3.3-70b-instruct",
	"MINIMAX_M2":                             "minimax-m2",
	"MINIMAX_M2_1":                           "minimax-m2.1",
	"MINIMAX_M2_5":                           "minimax-m2.5",
	"MINIMAX_M2_MAAS":                        "minimax-m2-maas",
	"MINISTRAL_3_14B_INSTRUCT":               "ministral-3-14b-instruct",
	"MINISTRAL_3_3B_INSTRUCT":                "ministral-3-3b-instruct",
	"MINISTRAL_3_8B_INSTRUCT":                "ministral-3-8b-instruct",
	"MISTRAL_LARGE_3_675B_INSTRUCT":          "mistral-large-3-675b-instruct",
	"MISTRAL_MEDIUM_2505":                    "mistral-medium-2505",
	"MISTRAL_SMALL_2503":                     "mistral-small-2503",
	"NEMOTRON_NANO_12B_V2":                   "nemotron-nano-12b-v2",
	"NEMOTRON_NANO_3_30B":                    "nemotron-nano-3-30b",
	"NEMOTRON_NANO_9B_V2":                    "nemotron-nano-9b-v2",
	"NEMOTRON_SUPER_3_120B":                  "nemotron-super-3-120b",
	"NOVA_2_LITE":                            "nova-2-lite",
	"NOVA_LITE":                              "nova-lite",
	"O1":                                     "o1",
	"O1_2024_12_17":                          "o1-2024-12-17",
	"O1_PRO":                                 "o1-pro",
	"O1_PRO_2025_03_19":                      "o1-pro-2025-03-19",
	"O3":                                     "o3",
	"O3_2025_04_16":                          "o3-2025-04-16",
	"O3_MINI":                                "o3-mini",
	"O3_MINI_2025_01_31":                     "o3-mini-2025-01-31",
	"O4_MINI":                                "o4-mini",
	"O4_MINI_2025_04_16":                     "o4-mini-2025-04-16",
	"PALMYRA_VISION_7B":                      "palmyra-vision-7b",
	"PHI_4":                                  "Phi-4",
	"PHI_4_MINI_INSTRUCT":                    "Phi-4-mini-instruct",
	"PHI_4_MINI_REASONING":                   "Phi-4-mini-reasoning",
	"PHI_4_MULTIMODAL_INSTRUCT":              "Phi-4-multimodal-instruct",
	"PHI_4_REASONING":                        "Phi-4-reasoning",
	"PIXTRAL_LARGE_2502":                     "pixtral-large-2502",
	"QWEN2_7B_INSTRUCT":                      "qwen2-7b-instruct",
	"QWEN3_235B_A22B_2507":                   "qwen3-235b-a22b-2507",
	"QWEN3_235B_A22B_INSTRUCT_2507_MAAS":     "qwen3-235b-a22b-instruct-2507-maas",
	"QWEN3_32B":                              "qwen3-32b",
	"QWEN3_5_122B_A10B":                      "qwen3.5-122b-a10b",
	"QWEN3_5_27B":                            "qwen3.5-27b",
	"QWEN3_5_35B_A3B":                        "qwen3.5-35b-a3b",
	"QWEN3_5_397B_A17B":                      "qwen3.5-397b-a17b",
	"QWEN3_5_FLASH":                          "qwen3.5-flash",
	"QWEN3_5_FLASH_2026_02_23":               "qwen3.5-flash-2026-02-23",
	"QWEN3_5_LIVETRANSLATE_FLASH_REALTIME":   "qwen3.5-livetranslate-flash-realtime",
	"QWEN3_5_LIVETRANSLATE_FLASH_REALTIME_2026_05_19": "qwen3.5-livetranslate-flash-realtime-2026-05-19",
	"QWEN3_5_OMNI_FLASH":                              "qwen3.5-omni-flash",
	"QWEN3_5_OMNI_FLASH_2026_03_15":                   "qwen3.5-omni-flash-2026-03-15",
	"QWEN3_5_OMNI_FLASH_REALTIME":                     "qwen3.5-omni-flash-realtime",
	"QWEN3_5_OMNI_FLASH_REALTIME_2026_03_15":          "qwen3.5-omni-flash-realtime-2026-03-15",
	"QWEN3_5_OMNI_PLUS":                               "qwen3.5-omni-plus",
	"QWEN3_5_OMNI_PLUS_2026_03_15":                    "qwen3.5-omni-plus-2026-03-15",
	"QWEN3_5_OMNI_PLUS_REALTIME":                      "qwen3.5-omni-plus-realtime",
	"QWEN3_5_OMNI_PLUS_REALTIME_2026_03_15":           "qwen3.5-omni-plus-realtime-2026-03-15",
	"QWEN3_5_PLUS":                                    "qwen3.5-plus",
	"QWEN3_5_PLUS_2026_02_15":                         "qwen3.5-plus-2026-02-15",
	"QWEN3_5_PLUS_2026_04_20":                         "qwen3.5-plus-2026-04-20",
	"QWEN3_6_27B":                                     "qwen3.6-27b",
	"QWEN3_6_35B_A3B":                                 "qwen3.6-35b-a3b",
	"QWEN3_6_FLASH":                                   "qwen3.6-flash",
	"QWEN3_6_FLASH_2026_04_16":                        "qwen3.6-flash-2026-04-16",
	"QWEN3_6_PLUS":                                    "qwen3.6-plus",
	"QWEN3_6_PLUS_2026_04_02":                         "qwen3.6-plus-2026-04-02",
	"QWEN3_7_FLASH":                                   "qwen3.7-flash",
	"QWEN3_7_FLASH_2026_07_15":                        "qwen3.7-flash-2026-07-15",
	"QWEN3_7_MAX":                                     "qwen3.7-max",
	"QWEN3_7_MAX_2026_05_17":                          "qwen3.7-max-2026-05-17",
	"QWEN3_7_MAX_2026_05_20":                          "qwen3.7-max-2026-05-20",
	"QWEN3_7_MAX_2026_06_08":                          "qwen3.7-max-2026-06-08",
	"QWEN3_7_MAX_PREVIEW":                             "qwen3.7-max-preview",
	"QWEN3_7_PLUS":                                    "qwen3.7-plus",
	"QWEN3_7_PLUS_2026_05_26":                         "qwen3.7-plus-2026-05-26",
	"QWEN3_8_27B":                                     "qwen3.8-27b",
	"QWEN3_8_2_4T_A95B":                               "qwen3.8-2.4t-a95b",
	"QWEN3_8_FLASH":                                   "qwen3.8-flash",
	"QWEN3_8_LIVETRANSLATE_FLASH_REALTIME":            "qwen3.8-livetranslate-flash-realtime",
	"QWEN3_8_MAX":                                     "qwen3.8-max",
	"QWEN3_8_MAX_0902":                                "qwen3.8-max-0902",
	"QWEN3_8_OMNI_FLASH":                              "qwen3.8-omni-flash",
	"QWEN3_CODER_30B_A3B":                             "qwen3-coder-30b-a3b",
	"QWEN3_CODER_480B_A35B":                           "qwen3-coder-480b-a35b",
	"QWEN3_CODER_480B_A35B_INSTRUCT_MAAS":             "qwen3-coder-480b-a35b-instruct-maas",
	"QWEN3_CODER_FLASH":                               "qwen3-coder-flash",
	"QWEN3_LIVETRANSLATE_FLASH":                       "qwen3-livetranslate-flash",
	"QWEN3_LIVETRANSLATE_FLASH_2025_12_01":            "qwen3-livetranslate-flash-2025-12-01",
	"QWEN3_NEXT_80B_A3B":                              "qwen3-next-80b-a3b",
	"QWEN3_NEXT_80B_A3B_INSTRUCT_MAAS":                "qwen3-next-80b-a3b-instruct-maas",
	"QWEN3_NEXT_80B_A3B_THINKING_MAAS":                "qwen3-next-80b-a3b-thinking-maas",
	"QWEN3_OMNI_FLASH":                                "qwen3-omni-flash",
	"QWEN3_OMNI_FLASH_REALTIME_2025_09_15":            "qwen3-omni-flash-realtime-2025-09-15",
	"QWEN3_S2S_FLASH_REALTIME":                        "qwen3-s2s-flash-realtime",
	"QWEN3_VL_235B_A22B":                              "qwen3-vl-235b-a22b",
	"QWEN3_VL_PLUS":                                   "qwen3-vl-plus",
	"QWEN_FLASH":                                      "qwen-flash",
	"QWEN_FLASH_CHARACTER":                            "qwen-flash-character",
	"QWEN_MAX":                                        "qwen-max",
	"QWEN_MT_FLASH":                                   "qwen-mt-flash",
	"QWEN_MT_LITE":                                    "qwen-mt-lite",
	"QWEN_MT_PLUS":                                    "qwen-mt-plus",
	"QWEN_PLUS":                                       "qwen-plus",
	"QWEN_PLUS_2025_01_25":                            "qwen-plus-2025-01-25",
	"QWEN_PLUS_2025_04_28":                            "qwen-plus-2025-04-28",
	"QWEN_PLUS_2025_07_14":                            "qwen-plus-2025-07-14",
	"QWEN_PLUS_2025_12_01":                            "qwen-plus-2025-12-01",
	"QWEN_PLUS_CHARACTER":                             "qwen-plus-character",
	"QWEN_PLUS_LATEST":                                "qwen-plus-latest",
	"QWEN_TURBO":                                      "qwen-turbo",
	"QWEN_VL_OCR_2025_11_20":                          "qwen-vl-ocr-2025-11-20",
	"QWQ_PLUS_2025_03_05":                             "qwq-plus-2025-03-05",
	"R1":                                              "r1",
	"SORA_2":                                          "sora-2",
	"SORA_2_PRO":                                      "sora-2-pro",
	"TEXT_EMBEDDING_3_LARGE":                          "text-embedding-3-large",
	"TEXT_EMBEDDING_3_SMALL":                          "text-embedding-3-small",
	"TEXT_EMBEDDING_ADA_002":                          "text-embedding-ada-002",
	"TTS_1":                                           "tts-1",
	"TTS_1_1106":                                      "tts-1-1106",
	"TTS_1_HD":                                        "tts-1-hd",
	"TTS_1_HD_1106":                                   "tts-1-hd-1106",
	"TYPESAFE_JEV":                                    "typesafe/jev",
	"TYPESAFE_JEV_SYSTEM_ONE":                         "typesafe/jev",
	"V3":                                              "v3",
	"V3_2":                                            "v3.2",
	"VOXTRAL_MINI_3B_2507":                            "voxtral-mini-3b-2507",
	"VOXTRAL_SMALL_24B_2507":                          "voxtral-small-24b-2507",
	"WHISPER_1":                                       "whisper-1",
	"ZHIPU_GLM_5_3":                                   "ZHIPU/GLM-5.3",
}
