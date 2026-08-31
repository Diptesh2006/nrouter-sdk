plugins {
    kotlin("jvm") version "2.0.21"
    `java-library`
    `maven-publish`
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

tasks.named<org.gradle.jvm.tasks.Jar>("javadocJar") {
    from("README.md")
}

tasks.withType<org.gradle.api.publish.tasks.GenerateModuleMetadata>().configureEach {
    enabled = false
}

tasks.test { useJUnitPlatform() }

publishing {
    publications {
        create<MavenPublication>("maven") {
            from(components["java"])
            // NOT "nrouter-sdk": the Java SDK already publishes
            // ai.nrouter:nrouter-sdk. Sharing the GAV would make one version
            // number mean two incompatible APIs. Distinct coordinates let the
            // coordinated version identify each ecosystem-specific artifact.
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
