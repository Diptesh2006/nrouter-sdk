# nRouter SDK for Android

One API key for models across six provider clouds, packaged as an AAR.

```kotlin
dependencies {
    implementation("ai.nrouter:nrouter-sdk-android:2.1.0")
}
```

The wire behaviour is the shared [`sdks/kotlin`](../kotlin) artifact — this is
not a second client. Read that README for the response metadata and the error
table; both apply here unchanged. This module adds the Android-specific parts.

## Why this module exists

**`System.getenv` does not work on Android.** It returns `null` for anything an
app did not inherit from a shell, so the core's `NROUTER_API_KEY` fallback
silently resolves to nothing on-device. Code that passes a unit test then throws
on a handset, with an error telling you to set an environment variable that
cannot help. `NRouterAndroid.create()` takes the key from somewhere Android
actually has it, and says so when it cannot.

The module also declares `android.permission.INTERNET` so a consumer cannot ship
an app that builds cleanly and fails every call at runtime, and ships consumer
ProGuard rules so no R8 configuration is needed.

## Use it

```kotlin
import ai.nrouter.sdk.android.NRouterAndroid
import org.json.JSONObject

class ChatViewModel(app: Application) : AndroidViewModel(app) {
    // In production, `key` is one your backend minted — see below.
    private val client = NRouterAndroid.create(app, apiKey = key)

    fun send(prompt: String) = viewModelScope.launch {
        val result = client.chatCompletions(
            JSONObject()
                .put("model", "claude-sonnet-4-5")
                .put("messages", listOf(mapOf("role" to "user", "content" to prompt)))
        )
        // The SDK hops to Dispatchers.IO itself — main-thread safe.
        val text = result.body
            .getJSONArray("choices").getJSONObject(0)
            .getJSONObject("message").getString("content")

        // Unpriced is unknown, not free.
        val cost = if (result.meta.isPriced) "$${result.meta.cost}" else "unpriced"
    }
}
```

## Do not ship a customer key in the APK

Anything compiled into an app — `BuildConfig`, a manifest `meta-data` entry, a
string resource — is readable by anyone who downloads it. **A shipped key is a
published key**, and an nRouter key spends real credits.

For a production app, mint a short-lived key on your own backend and pass it to
`create()`. The manifest path exists for internal builds and prototypes:

```xml
<application>
    <meta-data android:name="ai.nrouter.sdk.API_KEY" android:value="sk-nrouter-..." />
</application>
```

```kotlin
NRouterAndroid.create(context)            // falls back to that meta-data
NRouterAndroid.manifestKey(context)       // null when absent — not an error
```

> An `android:value` that looks numeric is coerced by the toolchain and reads
> back as `null`. That is a real way to "set" a key and still get nothing; keys
> start with `sk-nrouter-` so this is unlikely, but it is why `manifestKey`
> returns `null` rather than throwing.

## Requirements

| | |
|---|---|
| `minSdk` | 21 — OkHttp 4's floor; lower compiles and then fails TLS on-device |
| `compileSdk` | 34 |
| Java | 11 |
| Permission | `INTERNET`, declared by this library |

## Build and test

```bash
export ANDROID_HOME=$HOME/Library/Android/sdk    # or set sdk.dir in local.properties
./gradlew build          # compile + lint + Robolectric tests + AAR
```

Publishing — **and the ordering rule that the core must be on Central first** —
is in [PUBLISHING.md](PUBLISHING.md).

## How guardrails, budgets and routing work

They are configured in the dashboard and enforced at the **gateway**, not in
this package. The useful guarantee is not that they are always on — it is that
**whatever you have enabled cannot be bypassed by a client**, this one
included, and behaves identically from every nRouter SDK and from raw `curl`.

- [Guardrails](https://nrouter.ai/docs/guides/guardrails) — PII redaction,
  injection protection, secret and keyword scanning, pre-call and post-call.
  Which ones run is resolved per request: the organization's guardrail switch
  first, then the narrowest applicable assignment wins across
  key > team > org > default, and a winner disabled at that scope does not run.
- [Budget controls](https://nrouter.ai/docs/guides/budget-controls) — spend
  limits per key, team and organization.
- [Observability](https://nrouter.ai/docs/guides/observability) — cost and usage
  on billable calls. Free routes are genuinely free and carry no
  `x-nr-request-cost`: `/v1/messages/count_tokens`, and video polling and
  content retrieval.

[Smart Router aliases and fallback chains](https://nrouter.ai/docs/guides/router-settings)
carry two conditions worth knowing before you rely on failover you have not
enabled:

- **Opt-in by what you put in `model`.** An alias gets the strategy and its
  chain; a concrete model is never re-routed and inherits no hidden fallback.
- **Text wires only** — chat completions, responses, messages and legacy
  completions. Audio, image and video calls take a single-provider route and
  are not cross-provider Smart Router wires.
- [API reference](https://nrouter.ai/docs/api-reference) — the wire
  contract every SDK here implements.
