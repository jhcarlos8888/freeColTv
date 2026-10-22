# Pluto Native Android — Kotlin + Media3

Proyecto independiente de Android Studio (Kotlin + Jetpack Compose) que consulta el catálogo de canales en vivo de Pluto TV mediante endpoints internos no oficiales y prepara la reproducción HLS con AndroidX Media3/ExoPlayer. **No contiene un catálogo ficticio**: las tarjetas se generan a partir de la respuesta real del endpoint de canales.

## Qué incluye

- Pantalla nativa con diseño oscuro, búsqueda, categorías y logotipos de los canales recibidos por la API.
- Creación y caché en memoria de la sesión de Pluto; refresco previo a la expiración.
- Lectura del catálogo en vivo con `Authorization: Bearer …`.
- Construcción de la URL de reproducción utilizando el host y los parámetros de sesión vigentes, en vez de reutilizar el host/query posiblemente obsoletos que lleguen en los datos del catálogo.
- Reproductor HLS con ExoPlayer/Media3, controles y diagnóstico básico.
- Tests unitarios de la construcción de la URL de reproducción.
- Código que evita imprimir tokens o URL de reproducción firmadas en Logcat.

## Limitaciones importantes

1. Pluto TV **no documenta estos endpoints como una API pública para terceros**. Pueden cambiar, devolver HTTP 401/403/4xx, variar por país o dejar de estar disponibles sin aviso. El código no puede garantizar que un canal o película concreta se reproduzca.
2. Este primer paquete implementa **TV en vivo**. No incluye todavía una integración VOD de películas/series.
3. La app anuncia capacidad Widevine L3 en la solicitud de sesión y **no intenta desactivar DRM, quitar anuncios ni convertir una emisión protegida en una emisión sin protección**. Si Pluto entrega una emisión que necesita una configuración de DRM/licencia no disponible para esta integración, el reproductor informará del error.
4. El funcionamiento del catálogo y el streaming son cosas distintas: recibir JSON o un manifiesto HLS con HTTP 200 no demuestra que se pueda ver contenido. Verifica un canal real en un dispositivo Android.
5. Antes de distribuir o publicar la app, revisa los términos de Pluto TV y solicita autorización si corresponde. Este proyecto es experimental y no está afiliado con Pluto TV ni Paramount.

## Requisitos

- Android Studio con JDK 17.
- Android SDK Platform 36 instalado desde SDK Manager.
- Conexión a internet para que Gradle descargue las dependencias.
- Android 7.0/API 24 o superior recomendado para esta configuración.

## Abrir y compilar

1. Descomprime `PlutoNativeAndroid.zip`.
2. Abre la carpeta `PlutoNativeAndroid` desde Android Studio (**Open**, selecciona la carpeta que contiene `settings.gradle.kts`).
3. Acepta instalar Android SDK Platform 36 si el IDE lo solicita y pulsa **Sync Project with Gradle Files**.
4. Ejecuta `:app:assembleDebug` o presiona Run para instalar en un dispositivo/emulador.

Desde Linux, en un equipo con JDK 17, Android SDK y conexión a internet:

```bash
chmod +x gradlew
./gradlew --version
./gradlew test
./gradlew :app:assembleDebug
# opcional, si hay un dispositivo conectado por ADB:
./gradlew :app:installDebug
```

El script `gradlew` de este paquete es un pequeño bootstrap incluido para descargar la distribución oficial Gradle 8.13 al caché local. Si tu entorno corporativo bloquea `services.gradle.org`, configura un mirror aprobado o usa Android Studio/una instalación de Gradle ya preparada.

## Uso

Al abrir la app, pulsa actualizar si no carga el catálogo. Selecciona un canal para solicitar una URL de reproducción de la sesión actual y abrir el reproductor.

Si falla, copia **solo** el código/mensaje del error, no tokens, cabeceras `Authorization`, JWT ni la URL completa del stream. Los errores comunes:

- **HTTP 401/403**: sesión rechazada, región o endpoint cambió.
- **Lista vacía**: respuesta del endpoint distinta de la esperada o catálogo no disponible para la sesión.
- **Error de playback/HTTP en Media3**: manifiesto/segmentos no accesibles, URL expirada, restricción regional o formato/DRM no compatible.
- **Aparece un aviso de dispositivo no compatible**: Pluto entrega un vídeo de aviso en lugar del programa; no es un fallo del grid Android.

## Arquitectura

```text
MainActivity (Compose)
  └─ PlutoRepository
      ├─ boot.pluto.tv/v4/start (sesión)
      ├─ api.pluto.tv/v2/channels (catálogo)
      └─ URL HLS asociada a la sesión vigente
           └─ PlayerActivity (Media3 / ExoPlayer)
```

## Versiones

- Android Gradle Plugin: 8.13.2
- Gradle: 8.13
- Kotlin: 2.2.20
- Compose BOM: 2026.09.00
- Media3: 1.11.1

Referencias oficiales de dependencias:
- https://developer.android.com/jetpack/androidx/releases/media3
- https://developer.android.com/develop/ui/compose/bom
- https://developer.android.com/jetpack/androidx/releases/activity

Proyecto de referencia: https://github.com/ps5-payload-dev/plutotv

Licencia de esta adaptación: GPL-3.0-or-later; consulte `LICENSE`.
