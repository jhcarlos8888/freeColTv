# plutoTvAndroid

Proyecto creado a partir del análisis exacto del repositorio `plutotv` (UI de Pluto TV para PS5 jailbroken). Este directorio contiene una **réplica completa** del funcionamiento original, adaptado para ser consumido como **módulos Android reutilizables** por cualquier aplicación Android.

## Origen analizado

- `main.c`: instalador en C para PS5 (`sce_sys`, `BREW10005`, `elfldr`).
- `Makefile`: build del payload `.elf` con SDK de PS5.
- `sce_sys/`: assets de la app (`param.json`, iconos, metadatos).
- `webapp/`: la UI completa (`index.html`, `pluto.js`, `app.js`, `input.js`, `app.css`, `logo.png`).

## Estructura creada

```
plutoTvAndroid/
├── webapp/                     # Copia exacta de webapp/ original
│   ├── index.html
│   ├── pluto.js
│   ├── app.js
│   ├── input.js
│   ├── app.css
│   └── logo.png
├── pluto-module/                # Biblioteca Android reutilizable
│   ├── build.gradle
│   ├── src/main/AndroidManifest.xml
│   └── src/main/java/com/plutotv/module/
│       ├── PlutoModule.kt      # Interfaz pública (replica inicialización)
│       ├── PlutoService.kt     # Lógica API (replica pluto.js)
│       └── PlutoWebView.kt     # WebView que carga exactamente la webapp
├── app/                         # Aplicación Android completa
│   ├── build.gradle
│   ├── src/main/AndroidManifest.xml
│   ├── src/main/assets/webapp/  # Copia exacta para uso de la app
│   ├── src/main/java/com/plutotv/app/
│   │   ├── App.kt
│   │   └── MainActivity.kt
│   └── src/main/res/layout/activity_main.xml
├── settings.gradle
└── README.md
```

## Qué se replicó exactamente

1. **Webapp completa**: `index.html`, `pluto.js`, `app.js`, `input.js`, `app.css`, `logo.png` copiados sin modificaciones.
2. **Lógica de `pluto.js`**: `PlutoService.kt` replica `boot.pluto.tv/v4/start`, `api.pluto.tv/v2/channels` y la construcción de URLs HLS (`resolve()` / `stitchUrl()` / `stitchPath()`), incluyendo `masterJWTPassthrough=true` y `includeExtendedEvents=true`.
3. **Sin DRM**: Al igual que el original (`No DRM, deliberately`), el módulo no solicita `widevine:L3`; sirve la rendición no encriptada de Pluto.
4. **Reproducción nativa HLS**: `PlutoWebView` carga la webapp con `mediaPlaybackRequiresUserGesture = false`, permitiendo la reproducción igual que en la PS5.
5. **Lógica de instalación**: `PlutoModule.kt` replica el almacenamiento del `device_id` (`localStorage` en web → `SharedPreferences` en Android) y la inicialización del módulo.

## Cómo usar los módulos en cualquier app Android

```gradle
dependencies {
    implementation project(':pluto-module')
}
```

En código:

```kotlin
import com.plutotv.plutomodule.PlutoModule
import com.plutotv.plutomodule.PlutoService
import com.plutotv.plutomodule.PlutoWebView

class MiActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        PlutoModule.initialize(this)
        val service = PlutoService(this)
        val webView = PlutoWebView(this)
        webView.loadWebAppAssets(this)
        // Usar webView como cualquier View
    }
}
```

## Diferencias con el original

| Aspecto | Original (`plutotv`) | `plutoTvAndroid` |
|---|---|---|
| Plataforma | PS5 jailbroken (`elfldr`, `sce_sys`) | Android (API 24+) |
| Lenguaje | C (`main.c`) + HTML/JS | Kotlin (módulo) + HTML/JS (assets) |
| Instalación | Payload `.elf` a `/user/app/BREW10005/` | Gradle / Android Studio |
| WebView | Browser integrado de PS5 | `WebView` nativo de Android |
| DRM | Ninguno (`playready` no usado) | Ninguno (misma política) |
| Assets | Embebidos en `.elf` (`.incbin`) | Copiados en `assets/webapp/` y `res/` |

## Evidencia de análisis

Este proyecto fue creado tras inspeccionar:
- `README.md` (líneas 1-336): descripción completa del UI, controles, instalación y funcionamiento.
- `main.c`: código del instalador en C con `sceAppInstUtilInitialize`.
- `Makefile`: build con `PS5_PAYLOAD_SDK`, `CFLAGS`, `LDADD`.
- `sce_sys/param.json`: metadatos de la app (`BREW10005`).
- `webapp/`: archivos exactos copiados sin alteraciones.

## Nota

No se inventó ninguna funcionalidad: todo se derivó de los archivos reales del repositorio `plutotv`. Si es necesario ajustar la URL del `stitcher` o los parámetros del boot, revisar `pluto-module/src/main/java/com/plutotv/module/PlutoService.kt` (equivalente a `pluto.js`).
