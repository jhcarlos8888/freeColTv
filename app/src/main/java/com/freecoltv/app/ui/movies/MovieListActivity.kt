package com.freecoltv.app.ui.movies

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.GridLayoutManager
import com.freecoltv.app.R
import com.freecoltv.app.data.movie.MovieRepository
import com.freecoltv.app.databinding.ActivityMoviesBinding

class MovieListActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMoviesBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMoviesBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.recyclerMovies.layoutManager = GridLayoutManager(this, 2)
        val movies = MovieRepository.getMovies()
        binding.recyclerMovies.adapter = MovieAdapter(movies) { movie ->
            Toast.makeText(this, "Ver: ${movie.displayTitle}", Toast.LENGTH_SHORT).show()
        }
    }
}
