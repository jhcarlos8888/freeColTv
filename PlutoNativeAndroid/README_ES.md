# Pluto Native Android — Kotlin + Compose + Media3

Proyecto experimental de Android Studio que consulta las secciones de **TV en vivo, películas y series** de Pluto TV mediante sus endpoints web no documentados y construye URLs HLS asociadas a una sesión anónima. No implementa login de usuario de Pluto TV.

> **Estado honesto:** el proyecto incluye código para los tres catálogos y para navegar temporadas/episodios. No pude ejecutar una compilación Gradle completa en el entorno donde se generó este ZIP porque no había acceso a `services.gradle.org` ni Android SDK. Tampoco se ha probado una reproducción real en un teléfono. Compila y prueba en tu Android Studio y confirma el streaming con un canal y un título concretos.

## Funcionalidades

- **TV en vivo:** consulta `api.pluto.tv/v2/channels`, filtra canales ocultos, agrupa por categoría y muestra logotipos y descripción.
- **Películas:** consulta `api.pluto.tv/v3/vod/categories?includeItems=true`, deduplica títulos repetidos entre categorías y muestra títulos reconocidos como películas.
- **Series:** lista series, consulta `api.pluto.tv/v3/vod/series/{id}/seasons?includeItems=true` y presenta temporadas y episodios.
- **Sesión automática sin cuenta:** solicita una sesión a `boot.pluto.tv/v4/start`; conserva un identificador de dispositivo local y renueva la sesión cuando se acerca su vencimiento.
- **Resolución HLS:** reconstruye la ruta con el host y los parámetros que devolvió la sesión vigente, en vez de confiar ciegamente en hosts y queries antiguos almacenados en la entrada del catálogo.
- **Reproductor:** AndroidX Media3 / ExoPlayer con controles y mensajes de error.
- **Búsqueda, categorías y refresco** en la interfaz nativa Jetpack Compose.

## Qué no garantiza

1. Pluto TV no publica estos endpoints como una API abierta y estable para desarrolladores externos. Puede cambiar el formato, bloquear clientes, limitar catálogo por región o devolver HTTP 4xx.
2. **HTTP 200 no prueba que el stream contenga el programa esperado.** Debe comprobarse reproducción real con audio y vídeo. Si Pluto entrega un mensaje de dispositivo no compatible, la aplicación no lo oculta ni intenta eludirlo.
3. Se solicita entrega con anuncios y se declara capacidad Widevine L3. El código no elimina anuncios, no quita DRM y no solicita una versión sin protección. Los títulos protegidos pueden necesitar mecanismos/licencias que esta integración no tiene.
4. La detección de películas usa los tipos descritos por la respuesta regional. Si el proveedor omite tipos o cambia el esquema, la categoría puede quedar incompleta y requerir ajustes.
5. Antes de distribuir la aplicación, revisa los términos del proveedor y obtén autorización si corresponde. Este proyecto no es oficial ni está afiliado con Pluto TV/Paramount.

## Requisitos

- Android Studio actualizado.
- JDK 17.
- Android SDK Platform 36.
- Acceso a Internet para descargar dependencias Gradle.
- Android 7.0 / API 24 o superior.

## Abrir y compilar

1. Descomprime `PlutoNativeAndroid.zip`.
2. En Android Studio, usa **Open** y selecciona la carpeta que contiene `settings.gradle.kts`.
3. Deja que Gradle sincronice y que Android Studio instale la plataforma SDK requerida.
4. Ejecuta la app en un dispositivo o emulador con Internet.

En Linux, desde la carpeta descomprimida:

```bash
chmod +x gradlew
./gradlew test
./gradlew :app:assembleDebug
# Solo con un dispositivo conectado por ADB:
./gradlew :app:installDebug
```

Si el wrapper no puede descargar Gradle por restricciones de red, abre el proyecto desde Android Studio en una máquina con conexión o usa una distribución aprobada por tu entorno.

## Uso

- Abre la app y selecciona `TV en vivo`, `Películas` o `Series`.
- En `Series`, abre el título y después una temporada para ver episodios.
- Selecciona un canal, película o episodio para preparar el stream y abrir el reproductor.
- Si falla, guarda el código de error mostrado. **No compartas** URLs completas de reproducción, JWT, token de sesión, identificadores de sesión ni cabeceras de autorización.

Errores frecuentes:

- `HTTP 401/403`: sesión, región o endpoint rechazado.
- Catálogo vacío: formato de respuesta cambiado o contenido no disponible para esa región.
- HTTP 200 pero vídeo de aviso: Pluto ha devuelto un flujo de aviso en vez del contenido seleccionado.
- Error de ExoPlayer/Media3: URL o segmento no accesible, formato/codec no compatible, sesión vencida o DRM que requiere licencia/configuración no integrada.

## Arquitectura

```text
MainActivity (Jetpack Compose)
  └─ PlutoRepository
      ├─ boot.pluto.tv/v4/start (sesión anónima)
      ├─ api.pluto.tv/v2/channels (TV en vivo)
      ├─ api.pluto.tv/v3/vod/categories (películas/series/categorías)
      ├─ api.pluto.tv/v3/vod/series/{id}/seasons (temporadas y episodios)
      └─ StreamUrlBuilder (URL HLS con sesión vigente)
           └─ PlayerActivity (Media3 / ExoPlayer)
```

## Versiones configuradas

- Android Gradle Plugin: 8.13.2
- Gradle: 8.13
- Kotlin: 2.2.20
- Compose BOM: 2026.09.00
- Media3: 1.11.1
- Coil Compose: 3.6.3

## Referencias

- Proyecto de referencia de la UI: https://github.com/ps5-payload-dev/plutotv
- Media3 HLS: https://developer.android.com/media/media3/exoplayer/hls
- Media3 releases: https://developer.android.com/jetpack/androidx/releases/media3
- Compose BOM: https://developer.android.com/develop/ui/compose/bom

Esta adaptación es código experimental. Distribución bajo GPL-3.0-or-later; consulte `LICENSE`.
