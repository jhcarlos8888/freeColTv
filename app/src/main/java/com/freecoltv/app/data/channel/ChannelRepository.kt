package com.freecoltv.app.data.channel

import com.freecoltv.app.data.model.Channel

/**
 * Contrato de obtención de canales. El backend real (o una playlist M3U)
 * se conecta implementando esta interfaz.
 */
interface ChannelRepository {
    /** Devuelve los canales en vivo para la sesión dada. */
    suspend fun getChannels(token: String): List<Channel>
}
