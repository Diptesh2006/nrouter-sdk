# Android source distribution

The Android SDK is a source preview. It is versioned and conformance-tested with
all ten SDKs, but it is not released to Maven Central and its workflow accepts
no registry or signing credentials.

The AAR depends on the same-version Kotlin core. Build both into the local Maven
cache before consuming the Android coordinate:

```bash
cd ../kotlin && ./gradlew clean check publishToMavenLocal
cd ../android && ./gradlew clean build publishToMavenLocal
python3 ../../conformance/check_conformance.py
ls ~/.m2/repository/ai/nrouter/nrouter-sdk-android/2.2.1/
```

`build.gradle.kts` intentionally configures no remote publication repository.
Keep `org.json` excluded from the Android dependency: Android provides that
class itself, and including the JVM copy causes duplicate platform classes.
A future registry launch is an owner decision and needs a new reviewed release
path for both Kotlin and Android together.
