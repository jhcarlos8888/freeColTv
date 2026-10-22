package com.freecoltv.app.data.pluto

import java.net.URI
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

/** Builds a session-bound HLS URL without reusing the stale query from catalogue data. */
internal object StreamUrlBuilder {
    fun normalisePath(originalUrl: String, channelId: String): String {
        val parsedPath = runCatching { URI(originalUrl).rawPath }.getOrNull().orEmpty()
        var path = parsedPath.ifBlank {
            "/stitch/hls/channel/${channelId.trim()}/master.m3u8"
        }
        path = path.substringBefore('?')
        if (!path.startsWith('/')) path = "/$path"
        path = path.replace(Regex("^/v\\d+(?=/)"), "")
        if (!path.startsWith("/stitch/")) {
            path = "/stitch/hls/channel/${channelId.trim()}/master.m3u8"
        }
        return "/v2$path"
    }

    fun build(
        originalUrl: String,
        channelId: String,
        stitcherBaseUrl: String,
        stitcherParams: String,
        sessionToken: String
    ): String {
        val base = stitcherBaseUrl.trim().trimEnd('/')
            .let { if (it.startsWith("http://") || it.startsWith("https://")) it else "https://$it" }
        val path = normalisePath(originalUrl, channelId)
        val params = stitcherParams.trim().removePrefix("?").trimEnd('&')
        val queryStart = if (params.isBlank()) "" else "$params&"
        val token = URLEncoder.encode(sessionToken, StandardCharsets.UTF_8.name())
        return "$base$path?${queryStart}jwt=$token&masterJWTPassthrough=true&includeExtendedEvents=true"
    }
}
