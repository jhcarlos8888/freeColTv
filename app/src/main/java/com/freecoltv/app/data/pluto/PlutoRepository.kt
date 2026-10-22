package com.freecoltv.app.data.pluto

import android.content.Context
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * Experimental client for Pluto TV's undocumented web endpoints.
 * This is not an official public developer API; endpoints can change or be
 * unavailable by region. It does not attempt to remove ads or bypass DRM.
 */
class PlutoRepository(context: Context) {
    private val preferences = context.applicationContext
        .getSharedPreferences("pluto_native", Context.MODE_PRIVATE)
    private val deviceId: String = preferences.getString("device_id", null)
        ?: UUID.randomUUID().toString().also { preferences.edit().putString("device_id", it).apply() }

    @Volatile private var cachedSession: PlutoSession? = null
    @Volatile private var cachedVod: List<PlutoMediaItem>? = null
    @Volatile private var cachedVodAtMillis: Long = 0L
    @Volatile private var cachedSeasons: Map<String, List<PlutoSeason>> = emptyMap()

    suspend fun fetchLiveChannels(forceRefresh: Boolean = false): List<PlutoChannel> =
        withContext(Dispatchers.IO) {
            if (forceRefresh) cachedSession = null
            val session = getSessionBlocking()
            val start = Instant.now().truncatedTo(ChronoUnit.SECONDS)
            val stop = start.plus(2, ChronoUnit.HOURS)
            val url = "$CHANNELS_URL?start=${encode(start.toString())}&stop=${encode(stop.toString())}"
            val array = parseArrayResponse(requestText(url, session.token), "channels", "data")

            val channels = buildList {
                for (index in 0 until array.length()) {
                    val item = array.optJSONObject(index) ?: continue
                    val id = item.optText("_id").ifBlank { item.optText("id") }.ifBlank { item.optText("slug") }
                    if (id.isBlank() || item.optText("visibility").equals("hidden", ignoreCase = true)) continue

                    val rawUrl = extractPlaybackUrl(item)
                    val stitched = item.optBoolean("isStitched", rawUrl.isNotBlank())
                    if (!stitched || rawUrl.isBlank()) continue

                    val category = item.optText("category")
                        .ifBlank { item.optJSONArray("categories")?.optJSONObject(0)?.optText("name").orEmpty() }
                        .ifBlank { item.optText("genre") }
                        .ifBlank { "Otros" }
                    val logoPath = item.optJSONObject("colorLogoPNG")?.optText("path").orEmpty()
                        .ifBlank { item.optJSONObject("logo")?.optText("path").orEmpty() }

                    add(
                        PlutoChannel(
                            id = id,
                            name = item.optText("name").ifBlank { "Canal sin nombre" },
                            category = category,
                            description = item.optText("summary").ifBlank { item.optText("description") },
                            logoUrl = normaliseImageUrl(logoPath),
                            number = item.optText("number").takeIf { it.isNotBlank() },
                            originalPlaybackUrl = rawUrl
                        )
                    )
                }
            }.distinctBy { it.id }.sortedWith(compareBy<PlutoChannel>({ it.category.lowercase() }, { it.name.lowercase() }))

            if (channels.isEmpty()) {
                throw IOException("Pluto respondió, pero no devolvió canales reproducibles para esta sesión o región.")
            }
            channels
        }

    /** Fetch movies and series from the VOD categories endpoint, deduplicated by content id. */
    suspend fun fetchVodCatalog(forceRefresh: Boolean = false): List<PlutoMediaItem> =
        withContext(Dispatchers.IO) {
            val cached = cachedVod
            if (!forceRefresh && cached != null && System.currentTimeMillis() - cachedVodAtMillis < VOD_CACHE_TTL_MS) {
                return@withContext cached
            }

            val session = getSessionBlocking()
            val params = linkedMapOf(
                "includeItems" to "true",
                "deviceType" to "web",
                "offset" to "1000",
                "limit" to "1000"
            )
            val url = "$VOD_CATEGORIES_URL?${query(params)}"
            val body = requestText(url, session.token)
            val root = JSONObject(body)
            val categories = root.optJSONArray("categories")
                ?: root.optJSONObject("data")?.optJSONArray("categories")
                ?: throw IOException("Pluto respondió sin categorías VOD reconocibles.")

            // A title can occur in many editorial categories; only keep its first appearance.
            val unique = LinkedHashMap<String, JSONObject>()
            for (i in 0 until categories.length()) {
                val category = categories.optJSONObject(i) ?: continue
                val items = category.optJSONArray("items") ?: continue
                for (j in 0 until items.length()) {
                    val item = items.optJSONObject(j) ?: continue
                    val id = item.optText("_id").ifBlank { item.optText("id") }
                    if (id.isNotBlank()) unique.putIfAbsent(id, item)
                }
            }

            val rawItems = unique.values.toList()
            val hasExplicitMovieTypes = rawItems.any { it.optText("type").lowercase() in MOVIE_TYPES }
            val result = rawItems.mapNotNull { item ->
                val id = item.optText("_id").ifBlank { item.optText("id") }
                if (id.isBlank()) return@mapNotNull null
                val seasonsNumbers = item.optJSONArray("seasonsNumbers")
                val type = item.optText("type").lowercase()
                val isSeries = type == "series" || (seasonsNumbers?.length() ?: 0) > 0
                val kind = when {
                    isSeries -> PlutoMediaKind.SERIES
                    type in MOVIE_TYPES -> PlutoMediaKind.MOVIE
                    !hasExplicitMovieTypes -> PlutoMediaKind.MOVIE // Some regional feeds omit the type label.
                    else -> null
                } ?: return@mapNotNull null

                PlutoMediaItem(
                    id = id,
                    name = item.optText("name").ifBlank { "Título sin nombre" },
                    kind = kind,
                    genre = item.optText("genre").ifBlank { "Otros" },
                    description = item.optText("summary").ifBlank { item.optText("description") },
                    posterUrl = pickImage(item),
                    durationMillis = item.optLong("duration", 0L).coerceAtLeast(0L),
                    rating = item.optText("rating"),
                    originalPlaybackUrl = extractPlaybackUrl(item)
                )
            }.distinctBy { it.id }.sortedWith(compareBy<PlutoMediaItem>({ it.genre.lowercase() }, { it.name.lowercase() }) )

            if (result.isEmpty()) {
                throw IOException("Pluto respondió, pero no hay películas o series reconocibles en el catálogo VOD de esta región.")
            }
            cachedVod = result
            cachedVodAtMillis = System.currentTimeMillis()
            result
        }

    /** Loads seasons and episodes for a series. */
    suspend fun fetchSeriesSeasons(series: PlutoMediaItem, forceRefresh: Boolean = false): List<PlutoSeason> =
        withContext(Dispatchers.IO) {
            if (series.kind != PlutoMediaKind.SERIES) throw IOException("El título seleccionado no es una serie.")
            if (!forceRefresh) cachedSeasons[series.id]?.let { return@withContext it }

            val session = getSessionBlocking()
            val id = encode(series.id)
            val params = query(linkedMapOf("includeItems" to "true", "deviceType" to "web"))
            val body = requestText("$SERIES_URL/$id/seasons?$params", session.token)
            val root = JSONObject(body)
            val seasonsJson = root.optJSONArray("seasons")
                ?: root.optJSONObject("data")?.optJSONArray("seasons")
                ?: throw IOException("Pluto respondió sin temporadas para esta serie.")

            val seasons = buildList {
                for (i in 0 until seasonsJson.length()) {
                    val seasonJson = seasonsJson.optJSONObject(i) ?: continue
                    val number = seasonJson.optInt("number", i + 1)
                    val episodesJson = seasonJson.optJSONArray("episodes") ?: JSONArray()
                    val episodes = buildList {
                        for (j in 0 until episodesJson.length()) {
                            val episode = episodesJson.optJSONObject(j) ?: continue
                            val episodeId = episode.optText("_id").ifBlank { episode.optText("id") }
                            if (episodeId.isBlank()) continue
                            val episodeNumber = episode.optInt("number", j + 1)
                            val title = episode.optText("name").ifBlank { "Episodio $episodeNumber" }
                            add(
                                PlutoMediaItem(
                                    id = episodeId,
                                    name = "T${number}E${episodeNumber} · $title",
                                    kind = PlutoMediaKind.EPISODE,
                                    genre = series.genre,
                                    description = episode.optText("description").ifBlank { episode.optText("summary") },
                                    posterUrl = pickImage(episode) ?: series.posterUrl,
                                    durationMillis = episode.optLong("duration", 0L).coerceAtLeast(0L),
                                    rating = episode.optText("rating"),
                                    originalPlaybackUrl = extractPlaybackUrl(episode),
                                    seasonNumber = number,
                                    episodeNumber = episodeNumber
                                )
                            )
                        }
                    }
                    add(PlutoSeason(number, episodes))
                }
            }.sortedBy { it.number }

            if (seasons.isEmpty()) throw IOException("No se encontraron temporadas para esta serie.")
            cachedSeasons = cachedSeasons + (series.id to seasons)
            seasons
        }

    suspend fun playbackUrl(channel: PlutoChannel): String = withContext(Dispatchers.IO) {
        val session = getSessionBlocking()
        StreamUrlBuilder.build(
            originalUrl = channel.originalPlaybackUrl,
            contentId = channel.id,
            stitcherBaseUrl = session.stitcherBaseUrl,
            stitcherParams = session.stitcherParams,
            sessionToken = session.token,
            streamKind = StreamUrlBuilder.StreamKind.CHANNEL
        )
    }

    suspend fun playbackUrl(item: PlutoMediaItem): String = withContext(Dispatchers.IO) {
        if (item.kind == PlutoMediaKind.SERIES) throw IOException("Selecciona un episodio para reproducir la serie.")
        val session = getSessionBlocking()
        StreamUrlBuilder.build(
            originalUrl = item.originalPlaybackUrl,
            contentId = item.id,
            stitcherBaseUrl = session.stitcherBaseUrl,
            stitcherParams = session.stitcherParams,
            sessionToken = session.token,
            streamKind = StreamUrlBuilder.StreamKind.EPISODE
        )
    }

    private fun getSessionBlocking(): PlutoSession {
        val cached = cachedSession
        if (cached != null && cached.expiresAtMillis - SESSION_REFRESH_MARGIN_MS > System.currentTimeMillis()) return cached
        synchronized(this) {
            val rechecked = cachedSession
            if (rechecked != null && rechecked.expiresAtMillis - SESSION_REFRESH_MARGIN_MS > System.currentTimeMillis()) return rechecked

            val sid = UUID.randomUUID().toString()
            val params = linkedMapOf(
                "appName" to APP_NAME,
                "appVersion" to APP_VERSION,
                "deviceType" to "web",
                "deviceModel" to "web",
                "deviceMake" to "chrome",
                "deviceVersion" to DEVICE_VERSION,
                "deviceId" to deviceId,
                "clientID" to deviceId,
                "clientModelNumber" to CLIENT_MODEL,
                "sid" to sid,
                "serverSideAds" to "true",
                // Request normal ad-supported playback; do not request a DRM downgrade.
                "drmCapabilities" to "widevine:L3"
            )
            val bootUrl = "$BOOT_URL?${query(params)}"
            val json = JSONObject(requestText(bootUrl, bearerToken = null))
            val token = json.optText("sessionToken")
            if (token.isBlank()) throw IOException("Pluto no entregó un token de sesión.")

            val stitcherParams = json.optText("stitcherParams")
                .ifBlank { query(params) }
                .removePrefix("?")
            val stitcher = json.optJSONObject("servers")?.optText("stitcher").orEmpty()
                .ifBlank { STITCHER_FALLBACK }
                .let { if (it.startsWith("http://") || it.startsWith("https://")) it else "https://$it" }
            val payload = jwtPayload(token)
            val expiry = payload?.optLong("exp", 0L)?.takeIf { it > 0 }?.times(1000L)
                ?: (System.currentTimeMillis() + FALLBACK_SESSION_LIFETIME_MS)
            val region = payload?.optText("activeRegion").orEmpty().ifBlank { payload?.optText("country").orEmpty() }

            return PlutoSession(token, stitcher.trimEnd('/'), stitcherParams, expiry, region).also { cachedSession = it }
        }
    }

    private fun requestText(url: String, bearerToken: String?): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 20_000
            readTimeout = 30_000
            instanceFollowRedirects = true
            setRequestProperty("Accept", "application/json, application/x-mpegURL, */*")
            setRequestProperty("User-Agent", USER_AGENT)
            if (!bearerToken.isNullOrBlank()) setRequestProperty("Authorization", "Bearer $bearerToken")
        }
        try {
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val content = stream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code !in 200..299) throw IOException("Pluto devolvió HTTP $code al consultar el servicio.")
            return content
        } catch (e: IOException) {
            throw e
        } catch (e: Exception) {
            throw IOException("No se pudo completar la solicitud a Pluto: ${e.javaClass.simpleName}.")
        } finally {
            connection.disconnect()
        }
    }

    private fun parseArrayResponse(body: String, vararg keys: String): JSONArray {
        val trimmed = body.trim()
        if (trimmed.startsWith("[")) return JSONArray(trimmed)
        val obj = JSONObject(trimmed)
        for (key in keys) {
            val array = obj.optJSONArray(key)
            if (array != null) return array
        }
        throw IOException("Pluto respondió con un JSON sin lista reconocible.")
    }

    private fun extractPlaybackUrl(item: JSONObject): String {
        val stitched = item.optJSONObject("stitched") ?: return ""
        val lists = listOfNotNull(stitched.optJSONArray("paths"), stitched.optJSONArray("urls"))
        for (array in lists) {
            for (i in 0 until array.length()) {
                val candidate = array.optJSONObject(i) ?: continue
                val type = candidate.optText("type")
                val value = candidate.optText("path").ifBlank { candidate.optText("url") }
                if (value.isNotBlank() && (type.isBlank() || type.equals("hls", ignoreCase = true))) return value
            }
        }
        return stitched.optText("path")
    }

    private fun pickImage(item: JSONObject): String? {
        val covers = item.optJSONArray("covers")
        if (covers != null) {
            for (i in 0 until covers.length()) {
                val cover = covers.optJSONObject(i) ?: continue
                if (cover.optText("aspectRatio") == "16:9") {
                    normaliseImageUrl(cover.optText("url").ifBlank { cover.optText("path") })?.let { return it }
                }
            }
        }
        val namedPaths = listOf("poster16_9", "featuredImage", "tile", "thumbnail", "poster", "logo", "colorLogoPNG")
        for (key in namedPaths) {
            val path = item.optJSONObject(key)?.optText("path").orEmpty()
            normaliseImageUrl(path)?.let { return it }
        }
        val images = item.optJSONArray("images")
        if (images != null) {
            val preferred = listOf("featuredImage", "tile", "thumbnail", "colorLogoPNG", "solidLogoPNG", "logo")
            for (type in preferred) {
                for (i in 0 until images.length()) {
                    val image = images.optJSONObject(i) ?: continue
                    if (image.optText("type") == type) {
                        normaliseImageUrl(image.optText("url").ifBlank { image.optText("path") })?.let { return it }
                    }
                }
            }
            for (i in 0 until images.length()) {
                val image = images.optJSONObject(i) ?: continue
                normaliseImageUrl(image.optText("url").ifBlank { image.optText("path") })?.let { return it }
            }
        }
        if (covers != null && covers.length() > 0) {
            val cover = covers.optJSONObject(0)
            if (cover != null) return normaliseImageUrl(cover.optText("url").ifBlank { cover.optText("path") })
        }
        return null
    }

    private fun normaliseImageUrl(path: String): String? {
        if (path.isBlank()) return null
        return when {
            path.startsWith("https://") || path.startsWith("http://") -> path
            path.startsWith("//") -> "https:$path"
            path.startsWith("/") -> "https://images.pluto.tv$path"
            else -> "https://images.pluto.tv/$path"
        }
    }

    private fun jwtPayload(token: String): JSONObject? = runCatching {
        val encoded = token.split('.').getOrNull(1) ?: return null
        val decoded = Base64.decode(encoded, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        JSONObject(String(decoded, StandardCharsets.UTF_8))
    }.getOrNull()

    private fun query(params: Map<String, String>): String =
        params.entries.joinToString("&") { "${encode(it.key)}=${encode(it.value)}" }

    private fun encode(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.name())

    private fun JSONObject.optText(key: String): String {
        val value = optString(key, "").trim()
        return if (value == "null") "" else value
    }

    private companion object {
        const val BOOT_URL = "https://boot.pluto.tv/v4/start"
        const val CHANNELS_URL = "https://api.pluto.tv/v2/channels"
        const val VOD_CATEGORIES_URL = "https://api.pluto.tv/v3/vod/categories"
        const val SERIES_URL = "https://api.pluto.tv/v3/vod/series"
        const val STITCHER_FALLBACK = "https://cfd-v4-service-channel-stitcher-use1-1.prd.pluto.tv"
        const val APP_NAME = "web"
        const val APP_VERSION = "9.1.0"
        const val DEVICE_VERSION = "122.0.0"
        const val CLIENT_MODEL = "1.0.0"
        const val USER_AGENT = "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
        const val SESSION_REFRESH_MARGIN_MS = 60_000L
        const val FALLBACK_SESSION_LIFETIME_MS = 45 * 60 * 1000L
        const val VOD_CACHE_TTL_MS = 10 * 60 * 1000L
        val MOVIE_TYPES = setOf("movie", "film", "feature")
    }
}
