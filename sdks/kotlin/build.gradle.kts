plugins {
    kotlin("jvm") version "2.0.21"
    `java-library`
    `maven-publish`
    signing
}

kotlin {
    jvmToolchain(11)          // matches the Java SDK's floor; runs on Android too
    explicitApi()             // a public API is a promise; make adding one deliberate
}

repositories { mavenCentral() }

dependencyLocking { lockAllConfigurations() }

dependencies {
    api("com.squareup.okhttp3:okhttp:4.12.0")
    api("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")
    // org.json ships inside Android already; declaring it compileOnly there is
    // what avoids a duplicate-class failure. On the JVM it must be a real dep.
    api("org.json:json:20240303")

    testImplementation(kotlin("test"))
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}

java {
    withSourcesJar()
    withJavadocJar()
}

tasks.test { useJUnitPlatform() }

publishing {
    repositories {
        maven {
            name = "central"
            // Sonatype's Central Portal OSSRH-compatible endpoint. Without a
            // repositories block Gradle generates no remote publish task at
            // all, so `./gradlew publish` succeeds having uploaded nothing.
            url = uri("https://ossrh-staging-api.central.sonatype.com/service/local/staging/deploy/maven2/")
            credentials {
                username = System.getenv("SONATYPE_USERNAME")
                password = System.getenv("SONATYPE_PASSWORD")
            }
        }
    }
    publications {
        create<MavenPublication>("maven") {
            from(components["java"])
            // NOT "nrouter-sdk": the Java SDK already publishes
            // ai.nrouter:nrouter-sdk. Sharing the GAV would make one version
            // number mean two incompatible APIs, and the two SDKs could never
            // release independently.
            artifactId = "nrouter-sdk-kotlin"
            pom {
                name.set("nRouter SDK")
                description.set("nRouter SDK — one API key for models across six provider clouds")
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
                    // The WRITE path. HTTPS git does not work from the nRouter
                    // workspace, so a release tag/push must travel SSH.
                    developerConnection.set("scm:git:ssh://git@github.com/nRouterAI/nrouter-sdk.git")
                    url.set("https://github.com/nRouterAI/nrouter-sdk")
                }
            }
        }
    }
}

// Signing is required by Maven Central and skipped everywhere else, so a local
// `gradle build` never asks for a key it has no reason to need.
signing {
    setRequired { gradle.taskGraph.hasTask("publish") }
    val key = System.getenv("SIGNING_KEY")
    val password = System.getenv("SIGNING_PASSWORD")
    if (key != null && password != null) {
        useInMemoryPgpKeys(key, password)
        sign(publishing.publications["maven"])
    }
}
