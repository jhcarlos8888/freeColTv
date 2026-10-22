package com.freecoltv.app.ui.info

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.freecoltv.app.databinding.ActivityPublicDomainBinding

/**
 * Pantalla informativa que referencia contenido gratuito y legal.
 *
 * No transmite películas directamente (requeriría una API VOD diferente);
 * dirige al usuario hacia fuentes de dominio público, principalmente
 * Internet Archive.
 */
class PublicDomainInfoActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPublicDomainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPublicDomainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.info.text = "Fuente: Internet Archive (archive.org)\n" +
                "Contenido: películas de dominio público, CC, o autorizadas."

        binding.buttonArchive.setOnClickListener {
            val url = "https://archive.org/details/feature_films"
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
            } catch (e: Exception) {
                Toast.makeText(this, "No se pudo abrir el navegador", Toast.LENGTH_SHORT).show()
            }
        }
    }
}
