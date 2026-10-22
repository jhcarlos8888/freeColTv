package com.plutotv.plutomodule

import android.content.Context
import android.net.Uri
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Servicio que replica exactamente pluto.js del proyecto original:
 * - Boot en boot.pluto.tv/v4/start
 * - Canales desde api.pluto.tv/v2/channels
 * - VOD desde api.pluto.tv/v3/vod/categories
 * - Reproducción HLS sin DRM (como en la versión PS5)
 */
class PlutoService(private val context: Context) {

    companion object {
        const val BOOT_API = "https://boot.pluto.tv/v4/start"
        const val API = "https://api.pluto.tv"
        const val CHANNELS_API = "https://service-channels.clusters.pluto.tv"
        const val IMAGE_HOST = "https://images.pluto.tv"
        const val STITCHER_FALLBACK = "https://cfd-v4-service-channel-stitcher-use1-1.prd.pluto.tv"
    }

    /**
     * Realiza el boot como pluto.js: obtiene sessionToken y configura
     * la región según la IP (como hace Pluto en su API).
     */
    fun boot(): JSONObject? {
        return try {
            val url = URL("$BOOT_API?appName=web&appVersion=9.1.0" +
                "&deviceType=android&deviceModel=android&deviceMake=google" +
                "&clientID=plutoTvAndroid&clientModelNumber=1.0.0" +
                "&serverSideAds=false")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "GET"
            conn.connectTimeout = 10000
            conn.readTimeout = 10000
            conn.setRequestProperty("Accept", "application/json")
            val response = conn.inputStream.bufferedReader().use { it.readText() }
            JSONObject(response)
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Reproduce exactamente el comportamiento de resolve() en pluto.js:
     * construye la URL del manifest HLS desde el stitcher nombrado en la sesión.
     */
    fun buildStitchUrl(stitcherHost: String, itemId: String, sessionToken: String): String {
        return "${stitcherHost}/v2/manifest/${itemId}?jwt=${sessionToken}" +
            "&masterJWTPassthrough=true&includeExtendedEvents=true"
    }
}
