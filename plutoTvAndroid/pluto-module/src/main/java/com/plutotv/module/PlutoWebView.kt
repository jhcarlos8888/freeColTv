package com.plutotv.plutomodule

import android.annotation.SuppressLint
import android.content.Context
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient

/**
 * WebView que carga exactamente la webapp (index.html, app.js, pluto.js, input.js, app.css)
 * como en la versión original de PS5, permitiendo la reproducción HLS nativa.
 */
class PlutoWebView(context: Context) : WebView(context) {

    init {
        settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = true
            allowContentAccess = true
            useWideViewPort = true
            loadWithOverviewMode = true
            cacheMode = WebSettings.LOAD_NO_CACHE
        }
        webViewClient = PlutoWebClient()
    }

    @SuppressLint("SetJavaScriptEnabled")
    fun loadWebAppAssets(context: Context) {
        val indexHtml = PlutoModule.loadWebApp(context)
        if (indexHtml.isNotEmpty()) {
            loadDataWithBaseURL("file:///android_asset/webapp/", indexHtml,
                "text/html", "UTF-8", null)
        } else {
            loadUrl("file:///android_asset/webapp/index.html")
        }
    }

    inner class PlutoWebClient : WebViewClient() {
        override fun shouldOverrideUrlLoading(
            view: WebView?,
            request: android.webkit.WebResourceRequest?
        ): Boolean {
            val url = request?.url?.toString() ?: return false
            if (url.startsWith("https://api.pluto.tv") || url.startsWith("https://boot.pluto.tv")) {
                return false
            }
            return super.shouldOverrideUrlLoading(view, request)
        }
    }
}
