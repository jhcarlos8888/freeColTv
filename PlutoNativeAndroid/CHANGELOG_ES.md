# Cambios de esta versión

- Añadida pestaña **Películas** con consulta del catálogo VOD.
- Añadida pestaña **Series**, pantalla de temporadas y listado de episodios.
- Añadidos modelos `PlutoMediaItem`, `PlutoMediaKind` y `PlutoSeason`.
- Ampliado `PlutoRepository` para consultar categorías VOD, cargar temporadas/episodios y resolver el HLS de películas/episodios con la sesión actual.
- Generalizado `StreamUrlBuilder` para rutas de canales y episodios.
- Añadidas pruebas de normalización de rutas de episodio.
- Se mantiene sesión anónima sin login de usuario; se mantienen anuncios y capacidades DRM declaradas, sin código para quitarlos o degradar la protección.

## Validación disponible

- Compilación independiente del constructor de URL con `kotlinc`: correcta.
- Pruebas rápidas de normalización de rutas de canal/episodio: correctas.
- XML de Android: parsea correctamente.
- **Compilación Gradle completa y reproducción en dispositivo: no verificadas en el entorno de generación**, porque no puede resolver `services.gradle.org` y no dispone de Android SDK.
