pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    // mavenLocal() first so `gradle publishToMavenLocal` in ../kotlin is picked
    // up before a released artifact. That is how this module is built and
    // tested against an unreleased core, and it is the loop to use when
    // changing both at once.
    repositories { mavenLocal(); google(); mavenCentral() }
}
rootProject.name = "nrouter-sdk-android"
