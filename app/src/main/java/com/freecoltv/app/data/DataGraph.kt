package com.freecoltv.app.data

import com.freecoltv.app.data.auth.AuthRepository
import com.freecoltv.app.data.auth.MockAuthRepository
import com.freecoltv.app.data.channel.ChannelRepository
import com.freecoltv.app.data.channel.FallbackChannelRepository
import com.freecoltv.app.data.channel.IptvOrgRepository
import com.freecoltv.app.data.channel.MockChannelRepository
import com.freecoltv.app.data.channel.PlaylistCatalog
import com.freecoltv.app.data.channel.PlaylistOption

/**
 * Contenedor de dependencias simple.
 *
 * Fuente activa: IPTV-org (pública, sin credenciales) con fallback mock.
 * Puedes cambiar `activePlaylist` para usar otro país/categoría.
 */
object DataGraph {
    val authRepository: AuthRepository by lazy { MockAuthRepository() }

    /** Opción activa: cambia esta para cambiar de país/categoría. */
    var activePlaylist: PlaylistOption = PlaylistCatalog.countries.find { it.id == "co" }
        ?: PlaylistCatalog.countries.first()
        set(value) {
            field = value
            // Al cambiar, recrea el repositorio con la nueva URL.
            _channelRepo = null
        }

    private var _channelRepo: ChannelRepository? = null

    val channelRepository: ChannelRepository
        get() = _channelRepo ?: FallbackChannelRepository(
            primary = IptvOrgRepository(activePlaylist),
            fallback = MockChannelRepository(),
        ).also { _channelRepo = it }
}
