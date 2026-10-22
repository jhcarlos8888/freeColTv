package com.example.plutonative.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class StreamUrlBuilderTest {
    @Test
    fun normalisesOldVersionAndDropsStaleQuery() {
        val path = StreamUrlBuilder.normalisePath(
            "https://old-stitcher.example/v1/stitch/hls/channel/channel-123/master.m3u8?jwt=stale",
            "channel-123"
        )
        assertEquals("/v2/stitch/hls/channel/channel-123/master.m3u8", path)
    }

    @Test
    fun usesSessionStitcherAndCurrentToken() {
        val url = StreamUrlBuilder.build(
            originalUrl = "https://old.example/v1/stitch/hls/channel/channel-1/master.m3u8?jwt=old",
            channelId = "channel-1",
            stitcherBaseUrl = "https://current.example/",
            stitcherParams = "appName=web&deviceModel=web",
            sessionToken = "token-value"
        )
        assertTrue(url.startsWith("https://current.example/v2/stitch/hls/channel/channel-1/master.m3u8?"))
        assertTrue(url.contains("jwt=token-value"))
        assertTrue(url.contains("masterJWTPassthrough=true"))
        assertTrue(url.contains("includeExtendedEvents=true"))
        assertTrue(!url.contains("jwt=old"))
    }
}
