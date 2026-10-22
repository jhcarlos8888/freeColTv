package com.freecoltv.app.data.channel

import com.freecoltv.app.data.model.Channel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Repositorio que consume una playlist M3U pública (IPTV-org).
 *
 * Fuente: colección abierta de canales. IMPORTANTE: que una URL sea pública
 * no implica permiso para redistribuirla; revisa las licencias de cada canal
 * antes de publicar la app. Algunos streams pueden estar caídos o geobloqueados.
 *
 * Para películas: este repositorio NO sirve películas; usa el módulo de
 * películas con Internet Archive (public domain) para contenido VOD legal.
 */
class IptvOrgRepository(
    private val option: PlaylistOption = PlaylistCatalog.countries.first(),
    private val sourceTag: String = "iptv-org",
) : ChannelRepository {

    private val url = option.url

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    override suspend fun getChannels(token: String): List<Channel> =
        withContext(Dispatchers.IO) {
            val request = Request.Builder()
                .url(url)
                .header("User-Agent", "freeColTv/0.1")
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    throw IOException("HTTP ${response.code} al descargar: ${option.label}")
                }
                val body = response.body?.string()
                    ?: throw IOException("Respuesta vacía: ${option.label}")
                M3uParser.parse(body, sourceTag)
            }
        }

    fun getOptionLabel(): String = option.label
    fun getOptionId(): String = option.id
}
