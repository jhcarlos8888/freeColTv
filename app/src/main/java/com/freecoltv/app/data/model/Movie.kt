package com.freecoltv.app.data.model

data class Movie(
    val id: String,
    val title: String,
    val year: Int?,
    val thumbnailUrl: String?,
    val description: String?,
) {
    val displayTitle: String
        get() = if (year != null) "$title ($year)" else title
}
