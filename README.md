# freeColTv
App with IPTV Free channels

## Pluto TV (categoría PlutoTV)
- El servicio local `pluto-proxy` (`192.168.20.4:3000`) fue eliminado porque ya no funciona.
- La categoría "Pluto TV" ahora consume directamente la API pública `https://api.pluto.tv/v2/channels`.
- Las URLs HLS requieren completar los parámetros `deviceModel`, `deviceType`, `deviceMake`, `appName` y `appVersion`. El repositorio `PlutoRepository` realiza esta normalización automáticamente.
- La interfaz usa vistas XML nativas (`PlutoActivity` + `PlutoCategoryAdapter`) reutilizando el reproductor existente (`PlayerActivity`).
- Se recomienda usar solo con contenido autorizado; la API es de uso público pero no oficial para terceros. Algunos streams pueden tener restricciones geográficas o de términos de servicio.
