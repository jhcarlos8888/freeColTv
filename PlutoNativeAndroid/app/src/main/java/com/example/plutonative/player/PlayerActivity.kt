package com.example.plutonative.player

import android.os.Bundle
import android.util.Log
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

class PlayerActivity : ComponentActivity() {
    private var exoPlayer: ExoPlayer? = null
    private var videoView: PlayerView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val streamUrl = intent.getStringExtra(EXTRA_STREAM_URL)
        val title = intent.getStringExtra(EXTRA_TITLE).orEmpty().ifBlank { "Pluto TV" }
        if (streamUrl.isNullOrBlank() || !streamUrl.startsWith("https://")) {
            Toast.makeText(this, "No se recibió una URL HTTPS válida.", Toast.LENGTH_LONG).show()
            finish()
            return
        }
        title.let { setTitle(it) }
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val playerView = PlayerView(this).apply {
            layoutParams = FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            useController = true
            setShowBuffering(PlayerView.SHOW_BUFFERING_WHEN_PLAYING)
        }
        videoView = playerView
        setContentView(FrameLayout(this).apply { addView(playerView) })

        val player = ExoPlayer.Builder(this).build()
        exoPlayer = player
        playerView.player = player
        player.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                Log.e(TAG, "Playback error code=${error.errorCodeName}", error)
                val message = when (error.errorCode) {
                    PlaybackException.ERROR_CODE_DRM_SCHEME_UNSUPPORTED,
                    PlaybackException.ERROR_CODE_DRM_CONTENT_ERROR ->
                        "El stream requiere una configuración de DRM que esta prueba no tiene."
                    PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED,
                    PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT ->
                        "Fallo de red al cargar el vídeo."
                    else -> "Pluto TV no entregó un vídeo reproducible (código ${error.errorCodeName})."
                }
                Toast.makeText(this@PlayerActivity, message, Toast.LENGTH_LONG).show()
            }
        })

        val item = MediaItem.Builder()
            .setUri(streamUrl)
            .setMimeType(MimeTypes.APPLICATION_M3U8)
            .build()
        player.setMediaItem(item)
        player.prepare()
        player.playWhenReady = true
    }

    override fun onStop() {
        exoPlayer?.pause()
        super.onStop()
    }

    override fun onDestroy() {
        videoView?.player = null
        exoPlayer?.release()
        exoPlayer = null
        window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        super.onDestroy()
    }

    companion object {
        const val EXTRA_STREAM_URL = "com.example.plutonative.STREAM_URL"
        const val EXTRA_TITLE = "com.example.plutonative.TITLE"
        private const val TAG = "PlutoNativePlayer"
    }
}
