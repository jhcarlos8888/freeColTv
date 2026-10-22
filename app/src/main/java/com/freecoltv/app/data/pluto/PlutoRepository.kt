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
 * Live-TV data source for the unofficial Pluto TV web endpoints.
 *
 * These endpoints are not a supported public developer API. They may change,
 * be region-limited, or reject third-party clients at any time.
 */
class PlutoRepository(context: Context) {
    private val preferences = context.applicationContext
        .getSharedPreferences("pluto_native", Context.MODE_PRIVATE)
    private val deviceId: String = preferences.getString("device_id", null)
        ?: UUID.randomUUID().toString().also { preferences.edit().putString("device_id", it).apply() }

    @Volatile private var cachedSession: PlutoSession? = null

    suspend fun fetchLiveChannels(forceRefresh: Boolean = false): List<PlutoChannel> =
        withContext(Dispatchers.IO) {
            if (forceRefresh) cachedSession = null
            val session = getSessionBlocking()
            val start = Instant.now().truncatedTo(ChronoUnit.SECONDS)
            val stop = start.plus(2, ChronoUnit.HOURS)
            val url = "$CHANNELS_URL?start=${encode(start.toString())}&stop=${encode(stop.toString())}"
            val response = requestText(url, session.token)
            val root = response.trim()
            val array = when {
                root.startsWith("[") -> JSONArray(root)
                else -> {
                    val obj = JSONObject(root)
                    obj.optJSONArray("data")
                        ?: obj.optJSONArray("channels")
                        ?: throw IOException("Pluto respondió con un JSON sin lista de canales.")
                }
            }

            val channels = buildList {
                for (index in 0 until array.length()) {
                    val item = array.optJSONObject(index) ?: continue
                    val id = item.optText("_id")
                        .ifBlank { item.optText("id") }
                        .ifBlank { item.optText("slug") }
                    if (id.isBlank()) continue
                    if (item.optText("visibility").equals("hidden", ignoreCase = true)) continue

                    val urls = item.optJSONObject("stitched")?.optJSONArray("urls")
                    val rawUrl = urls?.optJSONObject(0)?.optText("url").orEmpty()
                    val stitched = item.optBoolean("isStitched", rawUrl.isNotBlank())
                    if (!stitched || rawUrl.isBlank()) continue

                    val category = item.optText("category")
                        .ifBlank { item.optJSONArray("categories")?.optJSONObject(0)?.optText("name").orEmpty() }
                        .ifBlank { item.optText("genre") }
                        .ifBlank { "Otros" }
                    val logoPath = item.optJSONObject("colorLogoPNG")?.optText("path").orEmpty()
                        .ifBlank { item.optJSONObject("logo")?.optText("path").orEmpty() }
                    val logo = normaliseImageUrl(logoPath)

                    add(
                        PlutoChannel(
                            id = id,
                            name = item.optText("name").ifBlank { "Canal sin nombre" },
                            category = category,
                            description = item.optText("summary").ifBlank { item.optText("description") },
                            logoUrl = logo,
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

    suspend fun playbackUrl(channel: PlutoChannel): String = withContext(Dispatchers.IO) {
        val session = getSessionBlocking()
        StreamUrlBuilder.build(
            originalUrl = channel.originalPlaybackUrl,
            channelId = channel.id,
            stitcherBaseUrl = session.stitcherBaseUrl,
            stitcherParams = session.stitcherParams,
            sessionToken = session.token
        )
    }

    private fun getSessionBlocking(): PlutoSession {
        val cached = cachedSession
        if (cached != null && cached.expiresAtMillis - SESSION_REFRESH_MARGIN_MS > System.currentTimeMillis()) {
            return cached
        }
        synchronized(this) {
            val rechecked = cachedSession
            if (rechecked != null && rechecked.expiresAtMillis - SESSION_REFRESH_MARGIN_MS > System.currentTimeMillis()) {
                return rechecked
            }
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
                // Keep normal ad-supported delivery; advertise Widevine L3 rather than
                // asking the service to downgrade to an unprotected rendition.
                "serverSideAds" to "true",
                "drmCapabilities" to "widevine:L3"
            )
            val bootUrl = "$BOOT_URL?${params.entries.joinToString("&") { "${encode(it.key)}=${encode(it.value)}" }}"
            val body = requestText(bootUrl, bearerToken = null)
            val json = JSONObject(body)
            val token = json.optText("sessionToken")
            if (token.isBlank()) throw IOException("Pluto no entregó un token de sesión.")

            val stitcherParams = json.optText("stitcherParams")
                .ifBlank { params.entries.joinToString("&") { "${encode(it.key)}=${encode(it.value)}" } }
                .removePrefix("?")
            val stitcher = json.optJSONObject("servers")?.optText("stitcher").orEmpty()
                .ifBlank { STITCHER_FALLBACK }
                .let { value -> if (value.startsWith("http://") || value.startsWith("https://")) value else "https://$value" }
            val expiry = jwtExpiryMillis(token) ?: (System.currentTimeMillis() + FALLBACK_SESSION_LIFETIME_MS)
            val region = jwtPayload(token)?.optText("activeRegion").orEmpty()
                .ifBlank { jwtPayload(token)?.optText("country").orEmpty() }

            return PlutoSession(
                token = token,
                stitcherBaseUrl = stitcher,
                stitcherParams = stitcherParams,
                expiresAtMillis = expiry,
                region = region
            ).also { cachedSession = it }
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
            if (code !in 200..299) {
                // Don't include request URLs or JWTs in exceptions/logs.
                throw IOException("Pluto devolvió HTTP $code al consultar el servicio.")
            }
            return content
        } catch (e: IOException) {
            throw e
        } catch (e: Exception) {
            throw IOException("No se pudo completar la solicitud a Pluto: ${e.javaClass.simpleName}.")
        } finally {
            connection.disconnect()
        }
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

    private fun jwtExpiryMillis(token: String): Long? =
        jwtPayload(token)?.optLong("exp", 0L)?.takeIf { it > 0 }?.times(1000L)

    private fun encode(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.name())

    private fun JSONObject.optText(key: String): String {
        val value = optString(key, "").trim()
        return if (value == "null") "" else value
    }

    private companion object {
        const val BOOT_URL = "https://boot.pluto.tv/v4/start"
        const val CHANNELS_URL = "https://api.pluto.tv/v2/channels"
        const val STITCHER_FALLBACK = "https://cfd-v4-service-channel-stitcher-use1-1.prd.pluto.tv"
        const val APP_NAME = "web"
        const val APP_VERSION = "9.1.0"
        const val DEVICE_VERSION = "122.0.0"
        const val CLIENT_MODEL = "1.0.0"
        const val USER_AGENT = "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
        const val SESSION_REFRESH_MARGIN_MS = 60_000L
        const val FALLBACK_SESSION_LIFETIME_MS = 45 * 60 * 1000L
    }
}
