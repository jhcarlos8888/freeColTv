package com.freecoltv.app.data.model

/**
 * Modelos de dominio.
 *
 * Inspirados en los modelos observados con REA en el APK de referencia
 * (com.request.result.Channel / LiveAddress y LoginResultData), pero
 * simplificados y con nombres propios: es una reconstrucción limpia, no
 * una copia del código original.
 */

/** Sesión de usuario devuelta por el login. */
data class Session(
    val userId: String,
    val token: String,
    val displayName: String,
)

/** Una dirección de reproducción posible de un canal. */
data class LiveAddress(
    val url: String,
    val quality: String,
    val format: String, // p.ej. "hls", "ts"
)

/** Canal de TV en vivo. */
data class Channel(
    val code: String,
    val name: String,
    val number: Int,
    val logoUrl: String?,
    val tags: String?,
    val addresses: List<LiveAddress>,
) {
    /** URL de reproducción por defecto: la primera dirección disponible. */
    val primaryUrl: String?
        get() = addresses.firstOrNull()?.url
}
