plugins {
    id("com.android.library") version "8.6.1"
    kotlin("android") version "2.0.21"
    `maven-publish`
    signing
}

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
    api("ai.nrouter:nrouter-sdk-kotlin:2.1.0") {
        // Android ships org.json inside the platform. The JVM artifact has to
        // declare a real dependency on it, but letting that reach an APK is a
        // DuplicatePlatformClasses lint ERROR and, unlinted, a a runtime class
        // clash. Excluding it here is the documented fix; the platform copy is
        // API-compatible with the one the core compiles against.
        exclude(group = "org.json", module = "json")
    }

    testImplementation(kotlin("test"))
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.robolectric:robolectric:4.13")
    testImplementation("androidx.test:core:1.6.1")
}

kotlin { jvmToolchain(11) }

publishing {
    repositories {
        maven {
            name = "central"
            // Without a repositories block Gradle generates no remote publish
            // task, so `./gradlew publish` succeeds having uploaded nothing.
            url = uri("https://ossrh-staging-api.central.sonatype.com/service/local/staging/deploy/maven2/")
            credentials {
                username = System.getenv("SONATYPE_USERNAME")
                password = System.getenv("SONATYPE_PASSWORD")
            }
        }
    }
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
                    connection.set("scm:git:https://github.com/nRouterAI/nrouter-sdk.git")
                    developerConnection.set("scm:git:ssh://git@github.com/nRouterAI/nrouter-sdk.git")
                    url.set("https://github.com/nRouterAI/nrouter-sdk")
                }
            }
        }
    }
}

signing {
    setRequired { gradle.taskGraph.hasTask("publish") }
    val key = System.getenv("SIGNING_KEY")
    val password = System.getenv("SIGNING_PASSWORD")
    if (key != null && password != null) {
        useInMemoryPgpKeys(key, password)
        sign(publishing.publications["release"])
    }
}
