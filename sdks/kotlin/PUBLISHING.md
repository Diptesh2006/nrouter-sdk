# Kotlin source distribution

The Kotlin SDK is a source preview. It is versioned and conformance-tested with
all ten SDKs, but it is not released to Maven Central and its workflow accepts
no registry or signing credentials.

Build and stage the package only in the local Maven cache:

```bash
./gradlew clean check publishToMavenLocal
python3 ../../conformance/check_conformance.py
ls ~/.m2/repository/ai/nrouter/nrouter-sdk-kotlin/3.0.0/
```

The expected local artifacts are the main jar, sources jar, javadoc jar, and
POM. `build.gradle.kts` intentionally configures no remote publication
repository. A future registry launch is an owner decision and must add a new
reviewed release path; do not repurpose the verification workflow.
