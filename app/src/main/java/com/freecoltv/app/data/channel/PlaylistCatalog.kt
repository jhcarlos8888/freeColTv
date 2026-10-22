package com.freecoltv.app.data.channel

/** Opción de playlist disponible en IPTV-org. */
data class PlaylistOption(
    val id: String,
    val label: String,
    val url: String,
    val isCountry: Boolean = true,
    val countryCode: String? = null,
)

/**
 * Opciones disponibles. También puedes consultar `categories.json` para
 * crear listas por temática (animation, comedy, cooking, etc.).
 */
object PlaylistCatalog {

    val countries = listOf(
        PlaylistOption("co", "Colombia (Español)", "https://iptv-org.github.io/iptv/countries/co.m3u", isCountry = true, countryCode = "CO"),
        PlaylistOption("es", "España (Español)", "https://iptv-org.github.io/iptv/countries/es.m3u", isCountry = true, countryCode = "ES"),
        PlaylistOption("mx", "México (Español)", "https://iptv-org.github.io/iptv/countries/mx.m3u", isCountry = true, countryCode = "MX"),
        PlaylistOption("us", "USA (Inglés)", "https://iptv-org.github.io/iptv/countries/us.m3u", isCountry = true, countryCode = "US"),
        PlaylistOption("gb", "Reino Unido (Inglés)", "https://iptv-org.github.io/iptv/countries/gb.m3u", isCountry = true, countryCode = "GB"),
    )

    val global = PlaylistOption(
        id = "global",
        label = "Todos los canales (global)",
        url = "https://iptv-org.github.io/iptv/index.m3u",
        isCountry = false,
    )

    val plutoProxy = PlaylistOption(
        id = "pluto-proxy",
        label = "Pluto TV (proxy local - 195 canales)",
        url = "http://192.168.20.4:3000/playlist.m3u8",
        isCountry = false,
    )

    /** Categorías de contenido disponibles según categories.json. */
    val categories = listOf(
        "animation", "classic", "comedy", "cooking", "documentary",
        "entertainment", "movies", "music", "news", "religion",
        "sport", "family",
    )

    val moviesOption = PlaylistOption(
        id = "movies-vod",
        label = "Películas / VOD (dominio público)",
        url = "https://archive.org/download/feature_films/",
        isCountry = false,
    )

    fun getOption(id: String): PlaylistOption? {
        return when (id) {
            in countries.map { it.id } -> countries.find { it.id == id }
            global.id -> global
            plutoProxy.id -> plutoProxy
            else -> null
        }
    }
}
