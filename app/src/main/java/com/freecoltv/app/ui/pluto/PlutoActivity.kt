package com.freecoltv.app.ui.pluto

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import androidx.recyclerview.widget.GridLayoutManager
import com.freecoltv.app.R
import com.freecoltv.app.data.pluto.PlutoChannel
import com.freecoltv.app.data.pluto.PlutoMediaItem
import com.freecoltv.app.data.pluto.PlutoMediaKind
import com.freecoltv.app.data.pluto.PlutoRepository
import com.freecoltv.app.databinding.ActivityPlutoBinding
import com.google.android.material.chip.Chip
import com.freecoltv.app.ui.player.PlayerActivity

class PlutoActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPlutoBinding
    private lateinit var repo: PlutoRepository
    private val adapter = PlutoCategoryAdapter { item -> openPlayer(item) }
    private var currentTab = 0 // 0=TV, 1=Peliculas, 2=Series
    private var currentChannels: List<PlutoChannel> = emptyList()
    private var currentMovies: List<PlutoMediaItem> = emptyList()
    private var currentSeries: List<PlutoMediaItem> = emptyList()
    private var selectedCategory: String? = null
    private var currentCategories: List<String> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        repo = PlutoRepository(this)
        binding = ActivityPlutoBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.recyclerPluto.layoutManager = GridLayoutManager(this, 2)
        binding.recyclerPluto.adapter = adapter

        binding.buttonBack.setOnClickListener { finish() }
        binding.buttonRetry.setOnClickListener { loadCurrentTab() }

        binding.tabPluto.addTab(binding.tabPluto.newTab().setText("TV en vivo"))
        binding.tabPluto.addTab(binding.tabPluto.newTab().setText("Películas"))
        binding.tabPluto.addTab(binding.tabPluto.newTab().setText("Series"))
        binding.tabPluto.addOnTabSelectedListener(object : com.google.android.material.tabs.TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: com.google.android.material.tabs.TabLayout.Tab?) {
                currentTab = tab?.position ?: 0
                loadCurrentTab()
            }
            override fun onTabUnselected(tab: com.google.android.material.tabs.TabLayout.Tab?) {}
            override fun onTabReselected(tab: com.google.android.material.tabs.TabLayout.Tab?) {}
        })

        loadCurrentTab()
    }

    private fun loadCurrentTab() {
        selectedCategory = null
        setLoading(true)
        lifecycleScope.launch {
            try {
                when (currentTab) {
                    0 -> {
                        val channels = repo.fetchLiveChannels()
                        currentChannels = channels
                        adapter.submit(channels)
                        val channelCategories = channels.map { it.category }.distinct()
                        currentCategories = channelCategories
                        updateChips(channelCategories)
                        binding.empty.visibility = if (channels.isEmpty()) View.VISIBLE else View.GONE
                    }
                    1 -> {
                        val vod = repo.fetchVodCatalog()
                        val movies = vod.filter { it.kind == PlutoMediaKind.MOVIE }
                        currentMovies = movies
                        adapter.submit(movies)
                        val movieCategories = movies.flatMap { it.categories }.distinct().ifEmpty { movies.map { it.genre }.distinct() }
                        currentCategories = movieCategories
                        updateChips(movieCategories)
                        binding.empty.visibility = if (movies.isEmpty()) View.VISIBLE else View.GONE
                    }
                    2 -> {
                        val vod = repo.fetchVodCatalog()
                        val series = vod.filter { it.kind == PlutoMediaKind.SERIES }
                        currentSeries = series
                        adapter.submit(series)
                        val seriesCategories = series.flatMap { it.categories }.distinct().ifEmpty { series.map { it.genre }.distinct() }
                        currentCategories = seriesCategories
                        updateChips(seriesCategories)
                        binding.empty.visibility = if (series.isEmpty()) View.VISIBLE else View.GONE
                    }
                }
            } catch (e: Exception) {
                Toast.makeText(this@PlutoActivity, "Error al cargar Pluto TV. Intenta más tarde.", Toast.LENGTH_LONG).show()
                adapter.submit(emptyList())
                binding.empty.visibility = View.VISIBLE
            } finally {
                setLoading(false)
            }
        }
    }

    private fun updateChips(categories: List<String>) {
        binding.chipGroupPluto.removeAllViews()
        val allChip = Chip(this).apply {
            text = "Todos"
            isCheckable = true
            isChecked = selectedCategory == null
            setOnClickListener {
                selectedCategory = null
                loadCurrentTab()
            }
        }
        binding.chipGroupPluto.addView(allChip)
        for (cat in categories) {
            val chip = Chip(this).apply {
                text = cat
                isCheckable = true
                isChecked = selectedCategory == cat
                setOnClickListener {
                    selectedCategory = if (selectedCategory == cat) null else cat
                    filterItems()
                }
            }
            binding.chipGroupPluto.addView(chip)
        }
    }

    private fun filterItems() {
        when (currentTab) {
            0 -> {
                val filtered = if (selectedCategory == null) currentChannels else currentChannels.filter { it.category == selectedCategory }
                adapter.submit(filtered)
            }
            1 -> {
                val filtered = if (selectedCategory == null) currentMovies else currentMovies.filter { selectedCategory in it.categories || it.genre == selectedCategory }
                adapter.submit(filtered)
            }
            2 -> {
                val filtered = if (selectedCategory == null) currentSeries else currentSeries.filter { selectedCategory in it.categories || it.genre == selectedCategory }
                adapter.submit(filtered)
            }
        }
        updateChips(currentCategories)
    }

    private fun setLoading(loading: Boolean) {
        binding.progress.visibility = if (loading) View.VISIBLE else View.GONE
    }

    private fun openPlayer(item: Any) {
        val url = runCatching {
            when (item) {
                is PlutoChannel -> {
                    kotlinx.coroutines.runBlocking { repo.playbackUrl(item) }
                }
                is PlutoMediaItem -> {
                    if (item.kind == PlutoMediaKind.SERIES) {
                        val seasons = kotlinx.coroutines.runBlocking { repo.fetchSeriesSeasons(item) }
                        val firstSeason = seasons.firstOrNull()
                        val firstEpisode = firstSeason?.episodes?.firstOrNull()
                        if (firstEpisode != null) kotlinx.coroutines.runBlocking { repo.playbackUrl(firstEpisode) } else null
                    } else {
                        kotlinx.coroutines.runBlocking { repo.playbackUrl(item) }
                    }
                }
                else -> null
            }
        }.getOrNull()
        val title = when (item) {
            is PlutoChannel -> item.name
            is PlutoMediaItem -> item.name
            else -> "Contenido"
        }
        if (url.isNullOrBlank()) {
            Toast.makeText(this, "Stream no disponible para $title", Toast.LENGTH_SHORT).show()
            return
        }
        startActivity(Intent(this, PlayerActivity::class.java).apply {
            putExtra(PlayerActivity.EXTRA_URL, url)
            putExtra(PlayerActivity.EXTRA_TITLE, title)
        })
    }
}
