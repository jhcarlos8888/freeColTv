package com.example.plutonative.data

/** A live channel returned by Pluto TV's undocumented channel endpoint. */
data class PlutoChannel(
    val id: String,
    val name: String,
    val category: String,
    val description: String,
    val logoUrl: String?,
    val number: String?,
    internal val originalPlaybackUrl: String
)

enum class PlutoMediaKind { MOVIE, SERIES, EPISODE }

data class PlutoMediaItem(
    /** Pluto catalog id (not the prefixed UI id). */
    val id: String,
    val name: String,
    val kind: PlutoMediaKind,
    val genre: String,
    val description: String,
    val posterUrl: String?,
    val durationMillis: Long = 0L,
    val rating: String = "",
    val originalPlaybackUrl: String = "",
    val seasonNumber: Int? = null,
    val episodeNumber: Int? = null
)

data class PlutoSeason(
    val number: Int,
    val episodes: List<PlutoMediaItem>
)

internal data class PlutoSession(
    val token: String,
    val stitcherBaseUrl: String,
    val stitcherParams: String,
    val expiresAtMillis: Long,
    val region: String
)
