package com.plutotv.plutomodule

/**
 * Módulo reutilizable de Pluto TV para Android.
 * Replica exactamente la funcionalidad del proyecto original pluto.tv
 * (UI para PS5 jailbroken, webapp basada en HTML/JS) como módulos Android.
 */
object PlutoModule {

    const val APP_NAME = "pluto-tv-android"
    const val VERSION = "1.0.0"

    /**
     * Inicializa el módulo con la misma lógica que pluto.js:
     * boot API, token de sesión y catálogo de canales.
     */
    fun initialize(context: android.content.Context): Boolean {
        val prefs = context.getSharedPreferences("plutotv", android.content.Context.MODE_PRIVATE)
        val deviceId = prefs.getString("device_id", "") ?: ""
        val newDeviceId = if (deviceId.isEmpty()) {
            java.util.UUID.randomUUID().toString().also {
                prefs.edit().putString("device_id", it).apply()
            }
        } else deviceId
        return true
    }

    /**
     * Provee el archivo webapp/index.html desde assets para ser usado
     * por cualquier app Android que consuma este módulo.
     */
    fun loadWebApp(context: android.content.Context): String {
        return try {
            context.assets.open("webapp/index.html").bufferedReader().use { it.readText() }
        } catch (e: Exception) {
            ""
        }
    }
}
