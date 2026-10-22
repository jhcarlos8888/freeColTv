package com.freecoltv.app.ui.home

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.freecoltv.app.R
import com.freecoltv.app.data.DataGraph
import com.freecoltv.app.data.channel.PlaylistCatalog
import com.freecoltv.app.data.model.Channel
import com.freecoltv.app.databinding.ActivityChannelListBinding
import com.freecoltv.app.ui.movies.MovieListActivity
import com.freecoltv.app.ui.player.PlayerActivity
import com.freecoltv.app.ui.pluto.PlutoActivity
import kotlinx.coroutines.launch

class ChannelListActivity : AppCompatActivity() {

    private lateinit var binding: ActivityChannelListBinding
    private val adapter = ChannelAdapter(onClick = ::openPlayer)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityChannelListBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.recyclerChannels.layoutManager = LinearLayoutManager(this)
        binding.recyclerChannels.adapter = adapter

        setupTabs()
        setupCountrySpinner()

        binding.buttonMovies.setOnClickListener {
            startActivity(Intent(this, MovieListActivity::class.java))
        }

        loadChannels()
    }

    private fun setupCountrySpinner() {
        val allOptions = PlaylistCatalog.countries + PlaylistCatalog.global
        val options = allOptions.map { it.label }
        val spinnerAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, options)
        binding.spinnerCountry.adapter = spinnerAdapter
        binding.spinnerCountry.setSelection(allOptions.indexOfFirst { it.id == DataGraph.activePlaylist.id })
        binding.spinnerCountry.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>, view: View?, pos: Int, id: Long) {
                val selected = allOptions.getOrNull(pos) ?: return
                DataGraph.activePlaylist = selected
                loadChannels()
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>) {}
        }
    }

    private fun loadChannels() {
        binding.title.text = "Canales · ${DataGraph.activePlaylist.label}"
        setLoading(true)
        lifecycleScope.launch {
            try {
                val channels = DataGraph.channelRepository.getChannels("")
                adapter.submit(channels)
                binding.empty.visibility = if (channels.isEmpty()) View.VISIBLE else View.GONE
            } catch (e: Exception) {
                Toast.makeText(this@ChannelListActivity, "Error de red. Mostrando datos locales.", Toast.LENGTH_LONG).show()
                adapter.submit(emptyList())
                binding.empty.visibility = View.VISIBLE
            } finally {
                setLoading(false)
            }
        }
    }

    private fun setLoading(loading: Boolean) {
        binding.progress.visibility = if (loading) View.VISIBLE else View.GONE
    }

    private fun openPlayer(channel: Channel) {
        val url = channel.primaryUrl ?: return
        startActivity(Intent(this, PlayerActivity::class.java).apply {
            putExtra(PlayerActivity.EXTRA_URL, url)
            putExtra(PlayerActivity.EXTRA_TITLE, channel.name)
        })
    }

    private fun setupTabs() {
        binding.tabLayout.addTab(binding.tabLayout.newTab().setText("Canales"))
        binding.tabLayout.addTab(binding.tabLayout.newTab().setText("Películas"))
        binding.tabLayout.addTab(binding.tabLayout.newTab().setText("Pluto TV"))
        binding.tabLayout.addOnTabSelectedListener(object : com.google.android.material.tabs.TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: com.google.android.material.tabs.TabLayout.Tab?) {
                when (tab?.position) {
                    0 -> loadChannels()
                    1 -> startActivity(Intent(this@ChannelListActivity, MovieListActivity::class.java))
                    2 -> startActivity(Intent(this@ChannelListActivity, PlutoActivity::class.java))
                }
            }
            override fun onTabUnselected(tab: com.google.android.material.tabs.TabLayout.Tab?) {}
            override fun onTabReselected(tab: com.google.android.material.tabs.TabLayout.Tab?) {}
        })
    }
}
