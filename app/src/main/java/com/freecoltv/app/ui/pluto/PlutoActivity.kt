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
import com.freecoltv.app.data.pluto.PlutoRepository
import com.freecoltv.app.databinding.ActivityPlutoBinding
import com.freecoltv.app.ui.player.PlayerActivity

class PlutoActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPlutoBinding
    private lateinit var repo: PlutoRepository
    private val adapter = PlutoCategoryAdapter { openPlayer(it) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        repo = PlutoRepository(this)
        binding = ActivityPlutoBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.recyclerPluto.layoutManager = GridLayoutManager(this, 2)
        binding.recyclerPluto.adapter = adapter

        binding.buttonBack.setOnClickListener { finish() }
        binding.buttonRetry.setOnClickListener { loadChannels() }

        loadChannels()
    }

    private fun loadChannels() {
        setLoading(true)
        lifecycleScope.launch {
            try {
                val channels = repo.fetchLiveChannels()
                adapter.submit(channels)
                binding.empty.visibility = if (channels.isEmpty()) View.VISIBLE else View.GONE
            } catch (e: Exception) {
                Toast.makeText(this@PlutoActivity, "Error al cargar Pluto TV. Intenta más tarde.", Toast.LENGTH_LONG).show()
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

    private fun openPlayer(channel: PlutoChannel) {
        val url = runCatching {
            kotlinx.coroutines.runBlocking { repo.playbackUrl(channel) }
        }.getOrNull()
        if (url.isNullOrBlank()) {
            Toast.makeText(this, "Stream no disponible para ${channel.name}", Toast.LENGTH_SHORT).show()
            return
        }
        startActivity(Intent(this, PlayerActivity::class.java).apply {
            putExtra(PlayerActivity.EXTRA_URL, url)
            putExtra(PlayerActivity.EXTRA_TITLE, channel.name)
        })
    }
}
