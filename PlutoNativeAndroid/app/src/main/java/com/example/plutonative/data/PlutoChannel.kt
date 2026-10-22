package com.example.plutonative.data

/** A live channel returned by Pluto TV's current (undocumented) channel endpoint. */
data class PlutoChannel(
    val id: String,
    val name: String,
    val category: String,
    val description: String,
    val logoUrl: String?,
    val number: String?,
    internal val originalPlaybackUrl: String
)

internal data class PlutoSession(
    val token: String,
    val stitcherBaseUrl: String,
    val stitcherParams: String,
    val expiresAtMillis: Long,
    val region: String
)
