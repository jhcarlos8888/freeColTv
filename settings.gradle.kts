pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "freeColTv"
include(":app")

// El repo vive en una ruta con espacios ("NEGOCIOS Y FINANZAS"), y el
// compilador Kotlin parte la clasepath en ese espacio, rompiendo la
// compilación (NoSuchFileException en kotlin-classes). Se reubica todo el
// directorio de build a una ruta sin espacios.
val buildRoot = file("/tmp/freecoltv-build")
gradle.beforeProject {
    val name = if (path == ":") "root" else path.substring(1).replace(':', '-')
    layout.buildDirectory.set(buildRoot.resolve(name))
}
