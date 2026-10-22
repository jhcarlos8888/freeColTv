package com.freecoltv.app.data.pluto

import java.net.URI
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

/** Builds a session-bound HLS URL from a path in the current catalogue. */
internal object StreamUrlBuilder {
    enum class StreamKind { CHANNEL, EPISODE }

    fun normalisePath(
        originalUrl: String,
        contentId: String,
        streamKind: StreamKind = StreamKind.CHANNEL
    ): String {
        val parsedPath = runCatching { URI(originalUrl).rawPath }.getOrNull().orEmpty()
        val fallbackType = if (streamKind == StreamKind.CHANNEL) "channel" else "episode"
        var path = parsedPath.ifBlank {
            "/stitch/hls/$fallbackType/${contentId.trim()}/master.m3u8"
        }
        path = path.substringBefore('?')
        if (!path.startsWith('/')) path = "/$path"
        path = path.replace(Regex("^/v\\d+(?=/)"), "")
        if (!path.startsWith("/stitch/hls/$fallbackType/")) {
            val expectedType = if (streamKind == StreamKind.CHANNEL) "/stitch/hls/channel/" else "/stitch/hls/episode/"
            path = if (path.startsWith("/stitch/hls/channel/") || path.startsWith("/stitch/hls/episode/")) {
                // Preserve a valid channel/episode path actually supplied by the catalogue.
                path
            } else {
                "$expectedType${contentId.trim()}/master.m3u8"
            }
        }
        return "/v2$path"
    }

    fun build(
        originalUrl: String,
        contentId: String,
        stitcherBaseUrl: String,
        stitcherParams: String,
        sessionToken: String,
        streamKind: StreamKind = StreamKind.CHANNEL
    ): String {
        val base = stitcherBaseUrl.trim().trimEnd('/')
            .let { if (it.startsWith("http://") || it.startsWith("https://")) it else "https://$it" }
        val path = normalisePath(originalUrl, contentId, streamKind)
        val params = stitcherParams.trim().removePrefix("?").trimEnd('&')
        val queryStart = if (params.isBlank()) "" else "$params&"
        val token = URLEncoder.encode(sessionToken, StandardCharsets.UTF_8.name())
        return "$base$path?${queryStart}jwt=$token&masterJWTPassthrough=true&includeExtendedEvents=true"
    }
}
