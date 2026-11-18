plugins {
    id("com.android.library") version "8.6.1"
    kotlin("android") version "2.0.21"
    `maven-publish`
    signing
}

dependencyLocking { lockAllConfigurations() }

android {
    namespace = "ai.nrouter.sdk.android"
    compileSdk = 34

    defaultConfig {
        // API 21 is the floor OkHttp 4 supports; going lower would compile and
        // then fail TLS handshakes on-device.
        minSdk = 21
        consumerProguardFiles("consumer-rules.pro")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    testOptions { unitTests.isIncludeAndroidResources = true }

    publishing {
        singleVariant("release") {
            withSourcesJar()
            withJavadocJar()
        }
    }
}

dependencies {
    // The wire behaviour is the shared JVM artifact — deliberately not a second
    // copy. A duplicated client is how two SDKs drift apart on the same gateway.
    api("ai.nrouter:nrouter-sdk-kotlin:3.1.5") {
        // Android ships org.json inside the platform. The JVM artifact has to
        // declare a real dependency on it, but letting that reach an APK is a
        // DuplicatePlatformClasses lint ERROR and, unlinted, a a runtime class
        // clash. Excluding it here is the documented fix; the platform copy is
        // API-compatible with the one the core compiles against.
        exclude(group = "org.json", module = "json")
    }

    testImplementation(kotlin("test"))
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.robolectric:robolectric:4.16.1")
    // Robolectric's transitive floor has shipped vulnerable Bouncy Castle
    // versions. Pin the test runtime to the current fixed line; the dependency
    // lock and security audit prevent a future downgrade.
    testImplementation("org.bouncycastle:bcprov-jdk18on:1.85.2")
    testImplementation("androidx.test:core:1.6.1")

    constraints {
        // Guava reaches only the unit-test classpath, through Robolectric.
        // Versions before 33.7.2 carry GHSA-xxph-c9ww-hj94 (unbounded allocation
        // when deserializing CompactHashMap/CompactHashSet). Raise the floor
        // here rather than declaring Guava directly; the lock keeps it there.
        testImplementation("com.google.guava:guava:33.7.2-jre") {
            because("GHSA-xxph-c9ww-hj94 is fixed in 33.7.2")
        }
    }
}

kotlin { jvmToolchain(11) }

tasks.withType<org.gradle.api.publish.tasks.GenerateModuleMetadata>().configureEach {
    enabled = false
}

tasks.withType<org.gradle.jvm.tasks.Jar>().configureEach {
    if (name.endsWith("JavadocJar", ignoreCase = true)) {
        from("README.md")
    }
}

publishing {
    publications {
        register<MavenPublication>("release") {
            afterEvaluate { from(components["release"]) }
            artifactId = "nrouter-sdk-android"
            pom {
                name.set("nRouter SDK for Android")
                description.set("nRouter SDK for Android — one API key for models across six provider clouds")
                url.set("https://nrouter.ai")
                licenses {
                    license {
                        name.set("MIT License")
                        url.set("https://opensource.org/licenses/MIT")
                    }
                }
                developers {
                    developer {
                        id.set("nrouter")
                        name.set("nRouter")
                        email.set("hello@nrouter.ai")
                        organization.set("nRouter")
                        organizationUrl.set("https://nrouter.ai")
                    }
                }
                scm {
                    connection.set("scm:git:https://github.com/nRouterGateway/nrouter-sdk.git")
                    developerConnection.set("scm:git:ssh://git@github.com/nRouterGateway/nrouter-sdk.git")
                    url.set("https://github.com/nRouterGateway/nrouter-sdk")
                }
            }
        }
    }

    // Same shape as sdks/kotlin: Central takes a bundle zip laid out as a Maven
    // repo, so stage locally first and keep every artifact and signature
    // inspectable before anything leaves the runner.
    repositories {
        maven {
            name = "centralStaging"
            url = uri(layout.buildDirectory.dir("central-staging"))
        }
    }
}

signing {
    // In-memory only; a keyring import outlives the step that needed it.
    // Absent credentials leave signing OFF so `check` and publishToMavenLocal
    // still work for a contributor with no release material.
    val signingKey = providers.environmentVariable("GPG_PRIVATE_KEY").orNull
    val signingPassphrase = providers.environmentVariable("MAVEN_GPG_PASSPHRASE").orNull
    if (!signingKey.isNullOrBlank() && !signingPassphrase.isNullOrBlank()) {
        useInMemoryPgpKeys(signingKey, signingPassphrase)
        // The Android publication is registered lazily by the AGP `release`
        // component, so it does not exist yet at configuration time.
        afterEvaluate { sign(publishing.publications["release"]) }
    }
}
