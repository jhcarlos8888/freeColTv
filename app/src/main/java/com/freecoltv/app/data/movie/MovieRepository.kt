package com.freecoltv.app.data.movie

import com.freecoltv.app.data.model.Movie

object MovieRepository {
    fun getMovies(): List<Movie> {
        return listOf(
            Movie(
                id = "m1", title = "A Star Is Born (1937)", year = 1937,
                thumbnailUrl = "https://archive.org/download/feature_films/a_star_is_born_1937.jpg",
                description = "Drama clásico de dominio público."
            ),
            Movie(
                id = "m2", title = "Nosferatu (1922)", year = 1922,
                thumbnailUrl = "https://archive.org/download/nosferatu_1922.jpg",
                description = "Clásico de terror de dominio público."
            ),
            Movie(
                id = "m3", title = "The Great Train Robbery (1903)", year = 1903,
                thumbnailUrl = "https://archive.org/download/great_train_robbery_1903.jpg",
                description = "Película histórica de dominio público."
            ),
            Movie(
                id = "m4", title = "Night of the Living Dead (1968)", year = 1968,
                thumbnailUrl = "https://archive.org/download/night_of_the_living_dead.jpg",
                description = "Clásico independiente de dominio público."
            ),
        )
    }
}
