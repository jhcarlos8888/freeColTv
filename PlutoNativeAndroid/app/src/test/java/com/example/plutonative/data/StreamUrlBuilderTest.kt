package com.example.plutonative.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class StreamUrlBuilderTest {
    @Test
    fun normalisesOldVersionAndDropsStaleQueryForChannel() {
        val path = StreamUrlBuilder.normalisePath(
            "https://old-stitcher.example/v1/stitch/hls/channel/channel-123/master.m3u8?jwt=stale",
            "channel-123",
            StreamUrlBuilder.StreamKind.CHANNEL
        )
        assertEquals("/v2/stitch/hls/channel/channel-123/master.m3u8", path)
    }

    @Test
    fun normalisesEpisodePathForVod() {
        val path = StreamUrlBuilder.normalisePath(
            "https://old-stitcher.example/v1/stitch/hls/episode/movie-123/master.m3u8?jwt=stale",
            "movie-123",
            StreamUrlBuilder.StreamKind.EPISODE
        )
        assertEquals("/v2/stitch/hls/episode/movie-123/master.m3u8", path)
    }

    @Test
    fun buildsFallbackEpisodePathWhenCatalogHasNoStitchPath() {
        val path = StreamUrlBuilder.normalisePath(
            "",
            "episode-123",
            StreamUrlBuilder.StreamKind.EPISODE
        )
        assertEquals("/v2/stitch/hls/episode/episode-123/master.m3u8", path)
    }

    @Test
    fun usesSessionStitcherAndCurrentToken() {
        val url = StreamUrlBuilder.build(
            originalUrl = "https://old.example/v1/stitch/hls/channel/channel-1/master.m3u8?jwt=old",
            contentId = "channel-1",
            stitcherBaseUrl = "https://current.example/",
            stitcherParams = "appName=web&deviceModel=web",
            sessionToken = "token-value",
            streamKind = StreamUrlBuilder.StreamKind.CHANNEL
        )
        assertTrue(url.startsWith("https://current.example/v2/stitch/hls/channel/channel-1/master.m3u8?"))
        assertTrue(url.contains("jwt=token-value"))
        assertTrue(url.contains("masterJWTPassthrough=true"))
        assertTrue(url.contains("includeExtendedEvents=true"))
        assertTrue(!url.contains("jwt=old"))
    }
}
