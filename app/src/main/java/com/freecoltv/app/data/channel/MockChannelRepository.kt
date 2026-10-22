package com.freecoltv.app.data.channel

import com.freecoltv.app.data.model.Channel
import com.freecoltv.app.data.model.LiveAddress
import kotlinx.coroutines.delay

/**
 * Repositorio de prueba con canales de ejemplo usando streams HLS públicos
 * de prueba. Sustituir por la implementación real (API IPTV o playlist M3U).
 */
class MockChannelRepository : ChannelRepository {

    override suspend fun getChannels(token: String): List<Channel> {
        delay(500) // simula la llamada de red
        return DEMO_CHANNELS
    }

    private companion object {
        // Streams HLS públicos de prueba (Big Buck Bunny / Sintel).
        private fun hls(url: String) = LiveAddress(url = url, quality = "auto", format = "hls")

        val DEMO_CHANNELS = listOf(
            Channel(
                code = "CH001",
                name = "Canal Demo 1",
                number = 1,
                logoUrl = null,
                tags = "Entretenimiento",
                addresses = listOf(hls("https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8")),
            ),
            Channel(
                code = "CH002",
                name = "Canal Demo 2",
                number = 2,
                logoUrl = null,
                tags = "Cine",
                addresses = listOf(hls("https://bitdash-a.akamaihd.net/content/sintel/hls/playlist.m3u8")),
            ),
            Channel(
                code = "CH003",
                name = "Canal Demo 3",
                number = 3,
                logoUrl = null,
                tags = "Deportes",
                addresses = listOf(hls("https://demo.unified-streaming.com/k8s/features/stable/video/tears-of-steel/tears-of-steel.ism/.m3u8")),
            ),
        )
    }
}
