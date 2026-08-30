# Publishing `ai.nrouter:nrouter-sdk-android` to Maven Central

Same account, namespace, token and GPG key as
[`sdks/kotlin`](../kotlin/PUBLISHING.md) — set that up first and the credentials
here are already in place.

## The ordering rule

**This artifact depends on `ai.nrouter:nrouter-sdk-kotlin` at the same version.**
Publish the Kotlin SDK first and wait for it to appear on Central. Publishing
Android against a core version that is not public yet produces an AAR whose POM
names a dependency nobody can resolve — it installs fine for you (it is in your
`~/.m2`) and fails for every consumer.

```bash
# 1. Core first.
cd ../kotlin && ./gradlew publish        # then release it in the Central UI

# 2. Confirm it actually resolves from Central, not just from your machine.
curl -sI https://repo1.maven.org/maven2/ai/nrouter/nrouter-sdk-kotlin/2.1.1/nrouter-sdk-kotlin-2.1.1.pom \
  | head -1        # expect: HTTP/2 200

# 3. Then Android.
cd ../android
$EDITOR gradle.properties                # version=2.1.1
$EDITOR build.gradle.kts                 # api("ai.nrouter:nrouter-sdk-kotlin:2.1.1")
./gradlew build
./gradlew publish
```

Release the staged deployment at <https://central.sonatype.com/publishing>.

## Building at all

An Android build needs the Android SDK. Point at it with `ANDROID_HOME`, or a
`local.properties` holding `sdk.dir=/path/to/android-sdk`. `local.properties` is
machine-specific and must never be committed.

```bash
brew install --cask android-commandlinetools
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PATH=/opt/homebrew/opt/openjdk@17/bin:$PATH
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
yes | sdkmanager --licenses >/dev/null
sdkmanager 'platforms;android-34' 'build-tools;34.0.0' 'platform-tools'
./gradlew build     # compiles, lints, runs the Robolectric tests, builds the AAR
```

The paths above are the Homebrew defaults on Apple Silicon. On another host,
keep the same package IDs and point `JAVA_HOME`/`ANDROID_HOME` at that host's
JDK 17 and Android SDK roots.

## Developing against an unreleased core

`settings.gradle.kts` lists `mavenLocal()` first, so:

```bash
cd ../kotlin && ./gradlew publishToMavenLocal
cd ../android && ./gradlew build
```

That is the loop for changing both at once. Remember it also means a stale
`~/.m2` copy shadows Central — `rm -rf ~/.m2/repository/ai/nrouter` if a build
resolves something you did not expect.

## Traps

- **`org.json` is excluded from the core dependency on purpose.** Android ships
  it in the platform; letting the JVM copy reach an APK is a
  `DuplicatePlatformClasses` lint ERROR, and unlinted it is a runtime class
  clash. Do not "fix" the exclude by deleting it.
- **Lint failures abort the build, deliberately.** The `org.json` collision was
  caught this way and nowhere else.
- **`minSdk = 21` is OkHttp 4's floor.** Lowering it compiles and then fails TLS
  handshakes on-device.
- **Never ship a customer key inside the APK.** `BuildConfig`, a manifest
  `meta-data` entry and a string resource are all readable by anyone holding the
  file. A shipped key is a published key.
