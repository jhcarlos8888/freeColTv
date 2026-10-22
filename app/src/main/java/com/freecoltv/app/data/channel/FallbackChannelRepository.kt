package com.freecoltv.app.data.channel

import com.freecoltv.app.data.model.Channel
import kotlinx.coroutines.CancellationException

/**
 * Intenta primero la fuente primaria; si falla (sin red, servidor caído),
 * devuelve los canales del fallback. Los fallos de cancelación se propagan
 * para no romper corroutines.
 */
class FallbackChannelRepository(
    private val primary: ChannelRepository,
    private val fallback: ChannelRepository,
) : ChannelRepository {

    override suspend fun getChannels(token: String): List<Channel> {
        return try {
            val result = primary.getChannels(token)
            if (result.isNotEmpty()) result else fallback.getChannels(token)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            try {
                fallback.getChannels(token)
            } catch (_: CancellationException) {
                throw e
            } catch (_: Exception) {
                emptyList()
            }
        }
    }
}
