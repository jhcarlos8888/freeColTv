package com.plutotv.app

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.plutotv.plutomodule.PlutoModule
import com.plutotv.plutomodule.PlutoService
import com.plutotv.plutomodule.PlutoWebView

class MainActivity : AppCompatActivity() {

    private lateinit var plutoWebView: PlutoWebView
    private lateinit var plutoService: PlutoService

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        PlutoModule.initialize(this)
        plutoService = PlutoService(this)

        plutoWebView = PlutoWebView(this)
        plutoWebView.loadWebAppAssets(this)

        val container = findViewById<android.widget.FrameLayout>(R.id.web_container)
        container.addView(plutoWebView)

        val bootResponse = plutoService.boot()
        if (bootResponse != null) {
            Toast.makeText(this, "Pluto TV conectado. Región activa.", Toast.LENGTH_LONG).show()
        } else {
            Toast.makeText(this, "No se pudo conectar a Pluto TV.", Toast.LENGTH_LONG).show()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        plutoWebView.destroy()
    }
}
