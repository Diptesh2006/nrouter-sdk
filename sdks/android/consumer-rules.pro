# Shipped to consumers automatically; they need no ProGuard changes of their own.
# The SDK carries no reflection of its own, but OkHttp and org.json do enough
# that R8 strips classes they resolve by name unless told otherwise.
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
-keep class ai.nrouter.sdk.** { *; }
