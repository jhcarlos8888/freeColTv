package com.freecoltv.app.ui.player

import android.net.Uri
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.freecoltv.app.databinding.ActivityPlayerBinding
import com.freecoltv.app.R

class PlayerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPlayerBinding
    private var player: ExoPlayer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPlayerBinding.inflate(layoutInflater)
        setContentView(binding.root)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val url = intent.getStringExtra(EXTRA_URL)
        val title = intent.getStringExtra(EXTRA_TITLE)
        binding.title.text = title.orEmpty()

        findViewById<android.widget.ImageButton>(R.id.buttonBack)?.setOnClickListener {
            finish()
        }

        if (url.isNullOrBlank()) {
            showError()
            return
        }
        setupPlayer(url)
    }

    private fun setupPlayer(url: String) {
        binding.progress.visibility = View.VISIBLE
        val exo = ExoPlayer.Builder(this).build()
        player = exo
        binding.playerView.player = exo

        exo.setMediaItem(MediaItem.fromUri(Uri.parse(url)))
        exo.playWhenReady = true
        exo.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_READY || playbackState == Player.STATE_ENDED) {
                    binding.progress.visibility = View.GONE
                }
            }

            override fun onPlayerError(error: PlaybackException) {
                binding.progress.visibility = View.GONE
                showError()
            }
        })
        exo.prepare()
    }

    private fun showError() {
        binding.error.visibility = View.VISIBLE
        binding.progress.visibility = View.GONE
    }

    override fun onStart() {
        super.onStart()
        player?.playWhenReady = true
    }

    override fun onStop() {
        super.onStop()
        player?.playWhenReady = false
    }

    override fun onDestroy() {
        super.onDestroy()
        player?.release()
        player = null
    }

    companion object {
        const val EXTRA_URL = "extra_url"
        const val EXTRA_TITLE = "extra_title"
    }
}
